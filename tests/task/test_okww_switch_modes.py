"""原生逐账号运行与批量运行的调度边界。"""

import uuid
from unittest.mock import AsyncMock, Mock

import pytest

from app.models.config.script import OkwwConfig, OkwwUserConfig
from app.models.task import UserItem
from app.task.Okww.AutoProxy import AutoProxyTask
from app.task.Okww.BatchProxy import BatchProxyTask
from app.task.Okww.manager import OkwwManager
from tests.runtime_support import RuntimeStub as SimpleNamespace


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,expected", [("OKWW_SINGLE", [1, 1]), ("OKWW", [2])])
async def test_native_modes_dispatch_selected_accounts(monkeypatch, mode, expected):
    ids = [uuid.uuid4(), uuid.uuid4()]
    users = [
        UserItem(user_id=str(uid), name=f"user {i}", status="等待")
        for i, uid in enumerate(ids)
    ]
    task_info = SimpleNamespace(
        mode="AutoProxy", execution_mode="AutoProxy", user_id=None
    )
    info = SimpleNamespace(
        task_info=task_info,
        script_id=str(uuid.uuid4()),
        user_list=users,
        current_index=0,
    )
    manager = OkwwManager(info)
    manager.task_info = task_info
    manager.script_info = info
    manager.script_config = OkwwConfig.model_validate(
        {"Game": {"AccountSwitchMethod": mode}}
    )
    manager.user_config = {
        uid: OkwwUserConfig.model_validate({"Info": {"Id": value}})
        for uid, value in zip(ids, ["13012346220", "13912347052"])
    }
    manager.game_manager = None
    manager.check = AsyncMock(return_value="Pass")
    manager.prepare = AsyncMock()
    manager.check_user_before_run = AsyncMock(return_value=True)
    manager.notify_user_check_failure = AsyncMock()
    manager.record_user_run_start = Mock()
    manager._restore_script_config_from_temp = AsyncMock()
    monkeypatch.setattr(AutoProxyTask, "check", AsyncMock(return_value="Pass"))
    dispatched = []

    async def run(task):
        assert isinstance(task, BatchProxyTask)
        dispatched.append([user.user_id for user in task.participants])
        # 首个账号耗尽重试后失败，manager 仍须派发下一个账号。
        for user in task.participants:
            await user.set_state(status="异常")

    manager.spawn = AsyncMock(side_effect=run)
    await manager.main_task()
    assert [len(batch) for batch in dispatched] == expected
    assert [uid for batch in dispatched for uid in batch] == [str(uid) for uid in ids]
    assert manager._restore_script_config_from_temp.await_count == len(expected)


def test_existing_batch_value_and_legacy_switch_values_remain_compatible():
    assert (
        OkwwConfig.model_validate(
            {"Game": {"AccountSwitchMethod": "OKWW"}}
        ).Game.AccountSwitchMethod
        == "OKWW"
    )
    assert (
        OkwwConfig.model_validate(
            {"Game": {"AccountSwitch": True}}
        ).Game.AccountSwitchMethod
        == "MAS"
    )
    assert (
        OkwwConfig.model_validate(
            {"Game": {"AccountSwitch": False}}
        ).Game.AccountSwitchMethod
        == "NONE"
    )
    assert OkwwConfig().Game.AccountSwitchMethod == "MAS"
