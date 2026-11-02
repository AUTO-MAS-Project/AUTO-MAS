"""维护预检的区服声明、跳过状态和执行顺序。"""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core import Config
from app.core.task_manager.manager import TaskInfo
from app.models.config import (
    BetterGIConfig,
    GeneralUserConfig,
    MaaConfig,
    MaaEndUserConfig,
    MaaUserConfig,
)
from app.models.game_maintenance import MaintenanceWindow
from app.models.task import ScriptItem, UserItem
from app.task import maintenance
from app.task import manager_base as base
from app.task.general.manager import GeneralManager
from app.task.MAA.manager import MaaManager
from app.task.MaaEnd.manager import MaaEndManager
from app.utils import IS_WINDOWS
from tests.config_support import activate_config


class TestManager(base.ScriptManagerBase):
    __test__ = False

    def maintenance_game(self, user_config):
        return "arknights"

    async def main_task(self):
        pass

    async def final_task(self):
        pass

    async def on_crash(self, error):
        raise error


def manager(mode="AutoProxy"):
    result = TestManager()
    result.task_info = SimpleNamespace(
        mode=mode,
        task_id="test",
        get_active_maintenance=AsyncMock(return_value=None),
        send_notice=AsyncMock(),
    )
    result.script_info = ScriptItem(str(uuid.uuid4()), "test", "等待")
    return result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "adapter,cls,field,value,game",
    [
        (MaaManager, MaaUserConfig, "Server", "Official", "arknights"),
        (MaaManager, MaaUserConfig, "Server", "Bilibili", "arknights"),
        (MaaManager, MaaUserConfig, "Server", "YoStarEN", None),
        (MaaEndManager, MaaEndUserConfig, "Resource", "官服", "endfield"),
        (GeneralManager, GeneralUserConfig, None, None, None),
    ],
)
async def test_server_matching(monkeypatch, adapter, cls, field, value, game):
    user = cls()
    await activate_config(user)
    if field:
        await user.update(
            type(user).model_validate({"Info": {field: value}}), check_visibility=False
        )
    lookup = AsyncMock(return_value=object())
    info = TaskInfo(
        mode="AutoProxy", task_id="test", queue_id=None, script_id=None, user_id=None
    )
    monkeypatch.setattr(info, "schedule_on_change", lambda: None)
    script = ScriptItem(script_id=str(uuid.uuid4()), name="test", status="等待")
    info.script_list = [script]
    instance = adapter(script)
    result = await maintenance.get_user_maintenance(
        instance.maintenance_game(user), lookup=lookup
    )
    if game:
        lookup.assert_awaited_once_with(game)
        assert result is lookup.return_value
    else:
        lookup.assert_not_awaited()
        assert result is None


@pytest.mark.asyncio
@pytest.mark.parametrize("active", [False, True])
async def test_precheck_marks_only_maintenance_users(active):
    window = MaintenanceWindow(
        datetime.now(timezone.utc), datetime.now(timezone.utc) + timedelta(hours=1)
    )
    instance = manager()
    instance.task_info.get_active_maintenance.return_value = window if active else None
    user = UserItem("u", "test", "等待")
    assert await instance.check_user_before_run(user, MaaUserConfig()) is (not active)
    assert user.maintenance_skipped is active
    assert user.status == ("跳过" if active else "等待")
    assert bool(user.log_record) is active
    assert not instance.has_proxy_run
    instance.task_info.get_active_maintenance.assert_awaited_once_with("arknights")
    assert instance.task_info.send_notice.await_count == int(active)
    if active:
        notice = instance.task_info.send_notice.await_args.kwargs
        assert notice["level"] == "info"
        assert window.reason in notice["message"]


@pytest.mark.asyncio
async def test_config_session_does_not_check_maintenance():
    instance = manager("ScriptConfig")
    assert await instance.check_user_before_run(
        UserItem("u", "test", "等待"), MaaUserConfig()
    )
    instance.task_info.get_active_maintenance.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("all_maintenance", [False, True])
async def test_update_runs_before_maintenance_and_all_skip_bypasses_proxy(
    all_maintenance,
):
    instance = manager()
    selected = [(uuid.uuid4(), MaaUserConfig()), (uuid.uuid4(), MaaUserConfig())]
    instance.selected_user_configs = lambda items=None: selected
    instance.update_game_before_run = AsyncMock()
    instance.notify_maintenance = AsyncMock()
    window = MaintenanceWindow(
        datetime.now(timezone.utc), datetime.now(timezone.utc) + timedelta(hours=1)
    )

    windows = iter([window, window if all_maintenance else None])

    async def lookup(game):
        assert game == "arknights"
        instance.update_game_before_run.assert_awaited_once()
        return next(windows)

    instance.task_info.get_active_maintenance = AsyncMock(side_effect=lookup)
    instance.main_task = AsyncMock()
    await instance._run_main_task()
    assert instance.maintenance_only is all_maintenance
    assert instance.main_task.await_count == int(not all_maintenance)
    assert instance.task_info.get_active_maintenance.await_count == len(selected)
    assert instance.notify_maintenance.await_count == int(all_maintenance)
    if all_maintenance:
        assert instance.all_users_maintenance_skipped
        assert instance.script_info.status == "跳过"
        assert not instance.has_proxy_run


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled,cdk", [(False, ""), (True, "review-cdk")])
@pytest.mark.skipif(not IS_WINDOWS, reason="secret storage uses Windows DPAPI")
async def test_maa_resource_update_keeps_takeover_credentials(
    monkeypatch, tmp_path, enabled, cdk
):
    from app.task.MAA import manager as maa

    script_id = uuid.uuid4()
    config = MaaConfig()
    await activate_config(config)
    await config.update(
        type(config).model_validate({"Update": {"TakeoverEnabled": enabled}}),
        check_visibility=False,
    )
    await config.update(
        type(config).model_validate({"Update": {"MirrorChyanCDK": cdk}})
    )
    monkeypatch.setattr(Config, "ScriptConfig", {script_id: config})
    info = TaskInfo("AutoProxy", "test", None, str(script_id), None)
    monkeypatch.setattr(info, "schedule_on_change", lambda: None)
    script = ScriptItem(str(script_id), "test", "等待")
    info.script_list = [script]
    instance = maa.MaaManager(script)
    instance.script_config = config
    instance.maa_set_path = tmp_path / "config"
    instance.temp_path = tmp_path / "Temp"
    monkeypatch.setattr(maa, "use_maa_github_update", lambda *args, **kwargs: False)
    monkeypatch.setattr(maa, "read_pending_update", lambda root: ("", ""))
    monkeypatch.setattr(maa, "read_installed_release", lambda root: ("v6.1.0", "x64"))
    monkeypatch.setattr(maa, "has_delegated_update_failure", lambda root: False)
    monkeypatch.setattr(
        maa, "prepare_maa_software_before_run", AsyncMock(return_value="v6.1.0")
    )
    monkeypatch.setattr(maa, "update_maa", AsyncMock())
    update = AsyncMock()
    monkeypatch.setattr(maa, "prepare_install_resources", update)
    result = await instance._prepare_updates_once(
        SimpleNamespace(update_config_dir=tmp_path / "config")
    )
    assert result is enabled
    if enabled:
        update.assert_awaited_once()
        assert update.await_args.kwargs["cdk"] == cdk
        assert update.await_args.kwargs["github"] is False
    else:
        update.assert_not_awaited()


@pytest.mark.asyncio
async def test_bettergi_report_keeps_nodes_and_summary(monkeypatch):
    from app.task.BetterGI import manager as bgi

    script_id = uuid.uuid4()
    config = BetterGIConfig()
    await activate_config(config)
    monkeypatch.setattr(Config, "ScriptConfig", {script_id: config})
    info = TaskInfo("AutoProxy", "test", None, str(script_id), None)
    monkeypatch.setattr(info, "schedule_on_change", lambda: None)
    script = ScriptItem(str(script_id), "test", "运行")
    info.script_list = [script]
    instance = bgi.BetterGIManager(script)
    instance.check_result = "Pass"
    script.user_list = [UserItem("a", "A", "部分失败"), UserItem("b", "B", "异常")]
    script.user_list[0].push_log = [("info", "node-A", 0.0)]
    script.user_list[1].push_log = [("info", "node-B", 0.0)]
    push = AsyncMock()
    monkeypatch.setattr(bgi.Notify, "push_proxy_result", push)
    await instance.final_task()
    report = push.await_args.kwargs["report"]
    assert report.completed_count == 1
    assert report.uncompleted_count == 1
    assert "node-A" in report.result and "node-B" in report.result
    assert report.result in script.log
