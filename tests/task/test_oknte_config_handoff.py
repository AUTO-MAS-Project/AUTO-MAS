import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core import Notify
from app.models.config.script import OkNteConfig, OkNteUserConfig
from app.models.task import TaskUserItem
from app.task.OkNte import manager as manager_module
from app.task.OkNte.manager import OkNteManager
from app.utils import io, process
from tests.config_support import activate_config
from tests.support.scheduler import create_runtime_tree


@pytest.mark.asyncio
async def test_residual_script_blocks_account_handoff_and_config_restore(
    tmp_path, monkeypatch
):
    script_id = str(uuid.uuid4())
    first_id, second_id = uuid.uuid4(), uuid.uuid4()
    _root, script, _user = await create_runtime_tree(
        script_id=script_id, user_id=str(first_id)
    )
    await script.set_users(
        [
            TaskUserItem(user_id=str(first_id), name="first"),
            TaskUserItem(user_id=str(second_id), name="second"),
        ]
    )
    launcher = tmp_path / "ok-nte.exe"
    launcher.touch()
    config_dir = tmp_path / "working-config"
    config_dir.mkdir()
    live_config = config_dir / "config.json"
    live_config.write_text("original", encoding="utf-8")
    config = await activate_config(
        OkNteConfig(
            Info={"RootPath": tmp_path},
            Script={"ScriptPath": launcher, "ConfigPath": config_dir},
        )
    )
    account = await activate_config(OkNteUserConfig())
    snapshot = tmp_path / "Temp"
    manager = OkNteManager(script)
    manager.script_config = config
    manager.user_config = {first_id: account, second_id: account}
    manager.script_config_path = config_dir
    manager.temp_path = snapshot

    async def prepare():
        manager.had_original_script_config = io.commit_native_config_snapshot(
            snapshot, config_dir, script_id=script_id
        )
        manager._snapshot_prepared = True

    async def dispatch(user, _task):
        live_config.write_text(user.name, encoding="utf-8")
        io.mark_native_config_injected(snapshot, config_dir, script_id=script_id)
        await user.set_state(status="异常")

    worker = tmp_path / "data/apps/ok-nte/working/ok-nte.exe"
    worker_running = True

    async def is_stopped(path, *, all_sessions=False):
        return not (worker_running and path == worker and all_sessions)

    monkeypatch.setattr(process, "is_process_stopped", is_stopped)
    monkeypatch.setattr(manager, "check", AsyncMock(return_value="Pass"))
    monkeypatch.setattr(manager, "prepare", prepare)
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
    assert (snapshot / "config.json").read_text(encoding="utf-8") == "original"

    with pytest.raises(RuntimeError, match="无法确认旧 OK-NTE 进程已退出"):
        await manager._recover_previous_run()
    assert live_config.read_text(encoding="utf-8") == "first"
    assert snapshot.exists()

    worker_running = False
    await manager._recover_previous_run()
    assert live_config.read_text(encoding="utf-8") == "original"
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
