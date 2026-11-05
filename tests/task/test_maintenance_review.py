"""维护预检的区服声明、跳过状态和执行顺序。"""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.config import (
    MaaUserConfig,
)
from app.models.game_maintenance import MaintenanceWindow
from app.models.task import ScriptItem, UserItem
from app.task import manager_base as base


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
