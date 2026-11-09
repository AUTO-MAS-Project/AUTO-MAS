"""停止已运行的 MFW 账号后，同一项目仍可再次运行。"""

import asyncio
import uuid

import pytest

from app.models.config import MaaFWConfig, MaaFWUserConfig
from app.task.MaaFW.tools.embedded.project_path import (
    release_project_path,
    try_reserve_project_path,
)
from app.task.MaaFW.tools.embedded.runner_task import MaaFWPluginAutoProxyTask
from app.utils.common.process.scope import current_process_scope
from tests.config_support import activate_config
from tests.task_stop_support import StopTask, add_script


@pytest.mark.asyncio
async def test_stopped_account_releases_project_after_emulator_close_is_cancelled(
    isolated_app_paths,
):
    entered, close_attempted = asyncio.Event(), asyncio.Event()
    account = None
    user_id = uuid.uuid4()
    config = await activate_config(
        MaaFWConfig.build(payload={"Emulator": {"Index": "1"}})
    )
    user = await activate_config(MaaFWUserConfig())

    class Emulator:
        async def close(self, index):
            # 关闭设备仍可能被收尾时限取消，不能因此漏掉项目预约的释放。
            scope = current_process_scope.get()
            assert scope is not None and scope.requested
            close_attempted.set()
            raise asyncio.CancelledError

    class RunningAccount(MaaFWPluginAutoProxyTask):
        async def main_task(self):
            # 隔离游戏执行，只建立真实账号运行时持有的项目预约与设备状态。
            assert await self._try_enter_project_path()
            self.check_result = "Pass"
            self.opened_emulator = True
            entered.set()
            await asyncio.Event().wait()

    class Task(StopTask):
        async def main_task(self):
            nonlocal account
            script = await add_script(
                info=self.task_info, script_id=str(config.uid), user_id=str(user_id)
            )
            account = RunningAccount(
                script_info=script,
                script_config=config,
                user_config={user_id: user},
                emulator_manager=Emulator(),
            )
            await self.spawn(account)

    task = Task()
    task.start()
    try:
        await asyncio.wait_for(entered.wait(), timeout=3)
        await asyncio.wait_for(task.stop(), timeout=3)
        assert close_attempted.is_set()
        assert account is not None
        key = await try_reserve_project_path(account.project_path)
        try:
            assert key is not None, "停止后项目仍被占用，下一次运行将被跳过"
        finally:
            await release_project_path(key)
    finally:
        await task.stop()
        if account is not None:
            await account._release_project_path()
