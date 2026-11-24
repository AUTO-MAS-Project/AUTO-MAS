import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core import Config, Notify
from app.models.config.script import OkNteConfig, OkNteUserConfig
from app.models.task import TaskUserItem
from app.task.OkNte import manager as manager_module
from app.task.OkNte.AutoProxy import AutoProxyTask
from app.task.OkNte.manager import OkNteManager
from app.task.OkNte.ScriptConfig import ScriptConfigTask
from app.task.OkNte.tools.native_config import mark_config_injected
from app.task.OkNte.tools.runtime import OkNteProcessManager
from app.utils import process
from tests.config_support import activate_config
from tests.support.scheduler import create_runtime_tree


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "original_exists", "changed_after_run"),
    [
        ("Folder", True, False),
        ("Folder", False, False),
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
        live_config.parent.mkdir(parents=True, exist_ok=True)
        live_config.write_text(user.name, encoding="utf-8")
        mark_config_injected(
            snapshot, config_path, script_id=script_id, folder_mode=mode == "Folder"
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
        assert (snapshot / "config.json").read_text(encoding="utf-8") == "original"

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
@pytest.mark.parametrize("task_class", [AutoProxyTask, ScriptConfigTask])
async def test_config_entry_points_stop_before_writing_when_body_is_running(
    tmp_path, monkeypatch, task_class
):
    uid = uuid.uuid4()
    _root, script, _user = await create_runtime_tree(user_id=str(uid))
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

    async def is_stopped(path, *, all_sessions=False):
        return not (path == worker and all_sessions)

    monkeypatch.setattr(process, "is_process_stopped", is_stopped)
    monkeypatch.setattr(process, "kill_process", AsyncMock(return_value=True))
    monkeypatch.setattr(OkNteProcessManager, "kill", AsyncMock())
    with pytest.raises(RuntimeError, match="已停止下发配置"):
        await task.set_oknte()
    assert config_file.read_text(encoding="utf-8") == "in use"
