from tests.config_support import activate_config, group_view

"""#1297 本地验证：区服、跳过状态和冲突整合。"""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from app.core import Config
from app.core.task_manager import TaskInfo
from app.models.config import (
    BetterGIConfig,
    GeneralUserConfig,
    MaaConfig,
    MaaEndUserConfig,
    MaaUserConfig,
)
from app.models.task import ScriptItem, TaskExecuteBase, UserItem
from app.services.game_maintenance import MaintenanceWindow
from app.task import maintenance
from app.task import manager_base as base


class TestManager(base.ScriptManagerBase):
    __test__ = False

    async def main_task(self):
        pass

    async def final_task(self):
        pass

    async def on_crash(self, error):
        raise error


def manager(mode="AutoProxy"):
    result = TestManager()
    result.task_info = SimpleNamespace(mode=mode, task_id="test")
    result.script_info = ScriptItem(str(uuid.uuid4()), "test", "等待")
    return result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cls,field,value,game",
    [
        (MaaUserConfig, "Server", "Official", "arknights"),
        (MaaUserConfig, "Server", "Bilibili", "arknights"),
        (MaaUserConfig, "Server", "YoStarEN", None),
        (MaaEndUserConfig, "Resource", "官服", "endfield"),
        (GeneralUserConfig, None, None, None),
    ],
)
async def test_server_matching(monkeypatch, cls, field, value, game):
    user = cls()
    await activate_config(user)
    if field:
        await user.update(
            type(user).model_validate({"Info": {field: value}}), check_visibility=False
        )
    lookup = AsyncMock(return_value=object())
    monkeypatch.setattr(maintenance.GameMaintenance, "get_active", lookup)
    result = await maintenance.get_user_maintenance(user, proxy=None)
    if game:
        lookup.assert_awaited_once_with(game, proxy=None)
        assert result is lookup.return_value
    else:
        lookup.assert_not_awaited()
        assert result is None


@pytest.mark.asyncio
@pytest.mark.parametrize("active", [False, True])
async def test_precheck_marks_only_maintenance_users(monkeypatch, active):
    window = MaintenanceWindow(
        datetime.now(timezone.utc), datetime.now(timezone.utc) + timedelta(hours=1)
    )
    monkeypatch.setattr(
        base, "get_user_maintenance", AsyncMock(return_value=window if active else None)
    )
    send = AsyncMock()
    monkeypatch.setattr(base.Publisher, "send", send)
    instance = manager()
    user = UserItem("u", "test", "等待")
    assert await instance.check_user_before_run(user, MaaUserConfig()) is (not active)
    assert user.maintenance_skipped is active
    assert user.status == ("跳过" if active else "等待")
    assert bool(user.log_record) is active
    assert not instance.has_proxy_run
    assert send.await_count == int(active)


@pytest.mark.asyncio
async def test_config_session_does_not_check_maintenance(monkeypatch):
    lookup = AsyncMock()
    monkeypatch.setattr(base, "get_user_maintenance", lookup)
    instance = manager("ScriptConfig")
    assert await instance.check_user_before_run(
        UserItem("u", "test", "等待"), MaaUserConfig()
    )
    lookup.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("all_maintenance", [False, True])
async def test_update_runs_before_maintenance_and_all_skip_bypasses_proxy(
    monkeypatch, all_maintenance
):
    instance = manager()
    selected = [(uuid.uuid4(), MaaUserConfig()), (uuid.uuid4(), MaaUserConfig())]
    instance.selected_user_configs = lambda items=None: selected
    instance.update_game_before_run = AsyncMock()
    instance.notify_maintenance = AsyncMock()
    window = MaintenanceWindow(
        datetime.now(timezone.utc), datetime.now(timezone.utc) + timedelta(hours=1)
    )

    async def lookup(*args, **kwargs):
        instance.update_game_before_run.assert_awaited_once()
        return window

    lookup_mock = AsyncMock(side_effect=lookup)
    if not all_maintenance:
        lookup_mock.side_effect = [window, None]
    monkeypatch.setattr(base, "get_user_maintenance", lookup_mock)
    monkeypatch.setattr(base.Publisher, "send", AsyncMock())
    normal = AsyncMock()
    monkeypatch.setattr(TaskExecuteBase, "_run_main_task", normal)
    await instance._run_main_task()
    assert instance.maintenance_only is all_maintenance
    assert normal.await_count == int(not all_maintenance)
    assert instance.notify_maintenance.await_count == int(all_maintenance)
    if all_maintenance:
        assert instance.all_users_maintenance_skipped
        assert instance.script_info.status == "跳过"
        assert not instance.has_proxy_run


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled,cdk", [(False, ""), (True, "review-cdk")])
async def test_maa_resource_update_keeps_takeover_credentials(
    monkeypatch, enabled, cdk
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
    instance.selected_user_configs = lambda: [(uuid.uuid4(), MaaUserConfig())]
    update = AsyncMock()
    monkeypatch.setattr(maa, "prepare_queue_resources", update)
    monkeypatch.setattr(base.ScriptManagerBase, "_run_main_task", AsyncMock())
    await instance._run_main_task()
    assert update.await_args.kwargs["cdk"] == (cdk if enabled else None)


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
    info.bind_notifications(SimpleNamespace(push_proxy_result=push))
    await instance.final_task()
    report = push.await_args.kwargs["report"]
    assert report.completed_count == 1
    assert report.uncompleted_count == 1
    assert "node-A" in report.result and "node-B" in report.result
    assert report.result in script.log
