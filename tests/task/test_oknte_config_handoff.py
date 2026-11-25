import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core import Config, Notify
from app.models.config.plan import OkNtePlanConfig
from app.models.config.script import OkNteConfig, OkNteUserConfig
from app.models.task import TaskUserItem
from app.task.OkNte import manager as manager_module
from app.task.OkNte.AutoProxy import AutoProxyTask
from app.task.OkNte.config_schema import DAILY_ROUTINE_TASK_FILE
from app.task.OkNte.manager import OkNteManager
from app.task.OkNte.ScriptConfig import ScriptConfigTask
from app.task.OkNte.tools.native_config import (
    config_file_fingerprint,
    publish_staged_config,
)
from app.task.OkNte.tools.runtime import OkNteProcessManager
from app.utils import io, process
from tests.config_support import activate_config
from tests.support.scheduler import create_runtime_tree


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "original_exists", "changed_after_run"),
    [
        ("Folder", True, False),
        ("Folder", False, False),
        ("File", True, False),
        ("File", False, False),
        ("File", False, True),
    ],
)
async def test_residual_script_blocks_account_handoff_and_config_restore(
    tmp_path, monkeypatch, mode, original_exists, changed_after_run
):
    mas_root = tmp_path / "mas"
    mas_root.mkdir()
    monkeypatch.chdir(mas_root)
    script_id = str(uuid.uuid4())
    script_root = tmp_path / "oknte"
    script_root.mkdir()
    launcher = script_root / "ok-nte.exe"
    launcher.touch()
    config_dir = script_root / "working-config"
    live_config = config_dir / "config.json"
    if original_exists:
        config_dir.mkdir()
        live_config.write_text("original", encoding="utf-8")
    config_path = config_dir if mode == "Folder" else live_config
    config = await activate_config(
        OkNteConfig(
            Info={"RootPath": script_root},
            Script={
                "ScriptPath": launcher,
                "ConfigPath": config_path,
                "ConfigPathMode": mode,
            },
        )
    )
    first_id = config.UserData.add(OkNteUserConfig, payload={"Info": {"Name": "first"}})
    second_id = config.UserData.add(
        OkNteUserConfig, payload={"Info": {"Name": "second"}}
    )
    await config.UserData.commit()
    monkeypatch.setattr(Config, "ScriptConfig", {uuid.UUID(script_id): config})
    _root, script, _user = await create_runtime_tree(
        script_id=script_id, user_id=str(first_id)
    )
    await script.set_users(
        [
            TaskUserItem(user_id=str(first_id), name="first"),
            TaskUserItem(user_id=str(second_id), name="second"),
        ]
    )
    snapshot = mas_root / "data" / script_id / "Temp"
    manager = OkNteManager(script)

    async def dispatch(user, _task):
        staged_dir = tmp_path / user.name
        staged_dir.mkdir()
        staged_file = staged_dir / live_config.name
        staged_file.write_text(user.name, encoding="utf-8")
        config_path.parent.mkdir(parents=True, exist_ok=True)
        publish_staged_config(
            staged_dir if mode == "Folder" else staged_file,
            config_path,
            snapshot,
            script_id=script_id,
            folder_mode=mode == "Folder",
        )
        await user.set_state(status="异常")

    worker = script_root / "data/apps/ok-nte/working/ok-nte.exe"
    worker_running = True

    async def is_stopped(path, *, all_sessions=False):
        return not (worker_running and path == worker and all_sessions)

    monkeypatch.setattr(process, "is_process_stopped", is_stopped)
    monkeypatch.setattr(manager, "check", AsyncMock(return_value="Pass"))
    monkeypatch.setattr(manager, "lock_script_config", AsyncMock(return_value=None))
    monkeypatch.setattr(manager, "check_user_before_run", AsyncMock(return_value=True))
    monkeypatch.setattr(manager, "run_user_task", dispatch)
    monkeypatch.setitem(
        manager_module.METHOD_BOOK,
        "AutoProxy",
        lambda **_kwargs: SimpleNamespace(check=AsyncMock(return_value="Pass")),
    )
    monkeypatch.setattr(Notify, "push_proxy_result", AsyncMock())

    await manager.main_task()
    await manager.final_task()

    assert [user.status for user in script.user_list] == ["异常", "等待"]
    assert script.status == "异常"
    assert live_config.read_text(encoding="utf-8") == "first"
    assert snapshot.is_dir()
    if original_exists:
        backup = snapshot / ("config.json" if mode == "Folder" else "config.temp")
        assert backup.read_text(encoding="utf-8") == "original"

    next_manager = OkNteManager(script)
    monkeypatch.setattr(
        next_manager, "lock_script_config", AsyncMock(return_value=None)
    )
    with pytest.raises(RuntimeError, match="无法确认旧 OK-NTE 进程已退出"):
        await next_manager.prepare()
    await next_manager.final_task()
    assert live_config.read_text(encoding="utf-8") == "first"
    assert snapshot.exists()

    worker_running = False
    if changed_after_run:
        live_config.write_text("external edit", encoding="utf-8")
    await next_manager._recover_previous_run()
    if original_exists:
        assert live_config.read_text(encoding="utf-8") == "original"
    elif changed_after_run:
        assert live_config.read_text(encoding="utf-8") == "external edit"
    else:
        assert not config_path.exists()
    assert not snapshot.exists()


@pytest.mark.asyncio
async def test_deferred_file_snapshot_is_kept_when_live_file_has_changed(
    tmp_path, monkeypatch
):
    script_id = str(uuid.uuid4())
    _root, script, _user = await create_runtime_tree(script_id=script_id)
    launcher = tmp_path / "ok-nte.exe"
    launcher.touch()
    live_config = tmp_path / "config.json"
    live_config.write_text("external edit", encoding="utf-8")
    config = await activate_config(
        OkNteConfig(
            Info={"RootPath": tmp_path},
            Script={
                "ScriptPath": launcher,
                "ConfigPath": live_config,
                "ConfigPathMode": "File",
            },
        )
    )
    manager = OkNteManager(script)
    manager.script_config = config
    manager.script_config_path = live_config
    manager.temp_path = tmp_path / "Temp"
    manager.temp_path.mkdir()
    (manager.temp_path / "config.temp").write_text("original", encoding="utf-8")
    monkeypatch.setattr(process, "is_process_stopped", AsyncMock(return_value=True))

    await manager._recover_previous_run()

    assert live_config.read_text(encoding="utf-8") == "external edit"
    preserved = list(tmp_path.glob("Temp.unresolved.*/config.temp"))
    assert len(preserved) == 1
    assert preserved[0].read_text(encoding="utf-8") == "original"
    assert not manager.temp_path.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("task_class", "gui_exit"),
    [
        pytest.param(AutoProxyTask, None, id="autoproxy-blocked"),
        pytest.param(ScriptConfigTask, None, id="gui-launch-blocked"),
        pytest.param(ScriptConfigTask, False, id="gui-exit-unconfirmed"),
        pytest.param(ScriptConfigTask, True, id="gui-exit-confirmed"),
    ],
)
async def test_config_entry_points_require_process_exit(
    tmp_path, monkeypatch, task_class, gui_exit
):
    uid = uuid.uuid4()
    _root, script, user = await create_runtime_tree(user_id=str(uid))
    launcher = tmp_path / "ok-nte.exe"
    launcher.touch()
    live = tmp_path / "runtime-config"
    live.mkdir()
    config_file = live / "tasks.json"
    config_file.write_text("in use", encoding="utf-8")
    log = tmp_path / "runtime.log"
    log.touch()
    config = await activate_config(
        OkNteConfig(
            Info={"RootPath": tmp_path},
            Script={"ScriptPath": launcher, "ConfigPath": live, "LogPath": log},
        )
    )
    account = await activate_config(OkNteUserConfig(Task={"TaskIndex": "2"}))
    task = task_class(script, config, {uid: account}, None)
    assert await task.check() == "Pass"
    await task.prepare()

    worker = tmp_path / "data/apps/ok-nte/working/ok-nte.exe"

    worker_running = gui_exit is None

    async def is_stopped(path, *, all_sessions=False):
        return not (worker_running and path == worker and all_sessions)

    monkeypatch.setattr(process, "is_process_stopped", is_stopped)
    monkeypatch.setattr(process, "kill_process", AsyncMock(return_value=True))
    monkeypatch.setattr(OkNteProcessManager, "kill", AsyncMock())
    if isinstance(task, ScriptConfigTask):
        task.mas_config_dir = tmp_path / "selected-account"
        task.mas_config_dir.mkdir()
        account_file = task.mas_config_dir / "tasks.json"
        account_file.write_text("selected account", encoding="utf-8")
        if gui_exit is not None:

            async def open_gui(*_args, **_kwargs):
                nonlocal worker_running
                worker_running = not gui_exit
                config_file.write_text("gui change", encoding="utf-8")
                task.wait_event.set()

            monkeypatch.setattr(OkNteProcessManager, "open_oknte", open_gui)
            monkeypatch.setattr(
                "app.task.OkNte.ScriptConfig.archive_mas_runtime_backup",
                lambda *_: None,
            )
        await task.execution.run()
        assert user.status == ("完成" if gui_exit else "异常")
        assert account_file.read_text(encoding="utf-8") == (
            "gui change" if gui_exit else "selected account"
        )
    else:
        with pytest.raises(RuntimeError, match="已停止下发配置"):
            await task.set_oknte()
    assert config_file.read_text(encoding="utf-8") == (
        "in use" if gui_exit is None else "gui change"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "malformed", [True, False], ids=["invalid-plan-input", "valid"]
)
async def test_first_config_publish_waits_for_plan_composition(
    tmp_path, monkeypatch, malformed
):
    mas_root = tmp_path / "mas"
    mas_root.mkdir()
    monkeypatch.chdir(mas_root)
    script_root = tmp_path / "oknte"
    script_root.mkdir()
    launcher = script_root / "ok-nte.exe"
    launcher.touch()
    log = script_root / "runtime.log"
    log.touch()
    live = script_root / "runtime-config"
    source = tmp_path / "account-config"
    source.mkdir()
    routine = source / DAILY_ROUTINE_TASK_FILE
    routine.write_text(
        "broken" if malformed else '{"Routine Items":[]}', encoding="utf-8"
    )
    uid = uuid.uuid4()
    script_id = str(uuid.uuid4())
    _root, script, _user = await create_runtime_tree(
        script_id=script_id, user_id=str(uid)
    )
    config = await activate_config(
        OkNteConfig(
            Info={"RootPath": script_root},
            Script={"ScriptPath": launcher, "ConfigPath": live, "LogPath": log},
        )
    )
    account = await activate_config(
        OkNteUserConfig(Info={"IfQuickConfig": False}, Task={"TaskIndex": "2"})
    )
    task = AutoProxyTask(script, config, {uid: account}, None)
    assert await task.check() == "Pass"
    await task.prepare()
    task.plan_active = True

    plan = OkNtePlanConfig()
    monkeypatch.setattr(Config, "PlanConfig", {account.Info.PlanMode: plan})
    monkeypatch.setattr(
        OkNtePlanConfig,
        "get_current_key",
        lambda _: {"Configs": {DAILY_ROUTINE_TASK_FILE: {"Routine Items": []}}},
    )
    monkeypatch.setattr(task, "_ensure_oknte_mas_config_dir", lambda: source)
    monkeypatch.setattr(process, "kill_process", AsyncMock(return_value=True))
    monkeypatch.setattr(process, "is_process_stopped", AsyncMock(return_value=True))
    monkeypatch.setattr(
        "app.task.OkNte.AutoProxy.archive_mas_runtime_backup", lambda *_: None
    )

    if malformed:
        with pytest.raises(json.JSONDecodeError):
            await task.set_oknte()
        assert not live.exists()
    else:
        await task.set_oknte()
        assert (
            json.loads((live / DAILY_ROUTINE_TASK_FILE).read_text(encoding="utf-8"))[
                "Routine Items"
            ]
            == []
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "original_exists", "phase", "external_edit"),
    [
        ("Folder", True, "before", False),
        ("Folder", False, "before", False),
        ("Folder", True, "between-renames", True),
        ("Folder", False, "after", False),
        ("File", True, "before", False),
        ("File", False, "before", False),
        ("File", True, "after", False),
        ("File", False, "after", True),
    ],
)
async def test_next_account_config_can_be_recovered_after_interrupted_publish(
    tmp_path, monkeypatch, mode, original_exists, phase, external_edit
):
    folder_mode = mode == "Folder"
    launcher = tmp_path / "ok-nte.exe"
    launcher.touch()
    live = tmp_path / ("config" if folder_mode else "config.json")
    live_file = live / "config.json" if folder_mode else live
    script_id = str(uuid.uuid4())
    _root, script, _user = await create_runtime_tree(script_id=script_id)
    config = await activate_config(
        OkNteConfig(
            Info={"RootPath": tmp_path},
            Script={"ScriptPath": launcher, "ConfigPath": live, "ConfigPathMode": mode},
        )
    )
    snapshot = tmp_path / "Temp"
    snapshot.mkdir()
    backup = snapshot / ("config.json" if folder_mode else "config.temp")
    if original_exists:
        backup.write_text("native", encoding="utf-8")
    baseline = (
        (
            io.dir_fingerprint(snapshot)
            if folder_mode
            else config_file_fingerprint(backup)
        )
        if original_exists
        else ""
    )
    io.write_native_config_snapshot(
        snapshot,
        script_id=script_id,
        original_exists=original_exists,
        baseline=baseline,
    )
    first, second = tmp_path / "first", tmp_path / "second"
    for staged in (first, second):
        if folder_mode:
            staged.mkdir()
        (staged / "config.json" if folder_mode else staged).write_text(
            staged.name, encoding="utf-8"
        )
    publish_staged_config(
        first, live, snapshot, script_id=script_id, folder_mode=folder_mode
    )

    def replace_dir(staged, destination):
        if phase == "between-renames":
            destination.rename(destination.with_name(destination.name + ".automas-old"))
        raise SystemExit("interrupted during directory publish")

    real_replace = type(second).replace

    def replace_file(path, destination):
        if path == second and destination == live:
            raise SystemExit("interrupted before file publish")
        return real_replace(path, destination)

    write_marker = io.write_native_config_snapshot

    def interrupt_after_swap(*args, **kwargs):
        if (
            kwargs.get("pending_injected") is None
            and live_file.read_text(encoding="utf-8") == "second"
        ):
            raise SystemExit("interrupted after publish")
        return write_marker(*args, **kwargs)

    if external_edit and phase == "between-renames":
        live_file.write_text("external edit", encoding="utf-8")

    with monkeypatch.context() as publishing:
        if phase == "after":
            publishing.setattr(io, "write_native_config_snapshot", interrupt_after_swap)
        elif folder_mode:
            publishing.setattr(io, "swap_in_dir", replace_dir)
        else:
            publishing.setattr(type(second), "replace", replace_file)
        with pytest.raises(SystemExit, match="interrupted"):
            publish_staged_config(
                second, live, snapshot, script_id=script_id, folder_mode=folder_mode
            )
    if external_edit and phase == "after":
        live_file.write_text("external edit", encoding="utf-8")

    manager = OkNteManager(script)
    manager.script_config = config
    manager.script_config_path = live
    manager.temp_path = snapshot
    monkeypatch.setattr(process, "is_process_stopped", AsyncMock(return_value=True))
    await manager._recover_previous_run()

    if external_edit:
        assert live_file.read_text(encoding="utf-8") == "external edit"
    elif original_exists:
        assert live_file.read_text(encoding="utf-8") == "native"
    else:
        assert not live.exists()
    assert not snapshot.exists()
