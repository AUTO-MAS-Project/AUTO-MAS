"""模拟器恢复耗尽后的真实 MAA 入口与调度状态、持锁收尾。"""

import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core import Publisher
from app.models.config import GeneralConfig, GeneralUserConfig, MaaConfig, MaaUserConfig
from app.models.emulator import EmulatorStartupError
from app.models.task import TaskItem, TaskMode, TaskScriptItem, TaskUserItem
from app.task.MAA.AutoProxy import AutoProxyTask
from app.task.mode_worker import AutoProxyWorker
from app.task.user_expander import UserExpander
from tests.config_support import activate_config
from tests.core.test_task_tree_dispatch import scheduler as scheduler


@pytest.mark.asyncio
async def test_real_maa_startup_failure_keeps_reason_and_avoids_outer_retry(
    tmp_path, monkeypatch, isolated_app_paths
):
    config = await activate_config(
        MaaConfig.model_validate(
            {
                "Info": {"Path": tmp_path},
                "Run": {"RunTimesLimit": 10},
                "Emulator": {"Index": "0"},
            }
        )
    )
    user_id = config.UserData.add(
        MaaUserConfig,
        payload={
            "Info": {
                "Base": "shared",
                "IfQuickConfig": False,
                "Name": "测试账号",
            }
        },
    )
    await config.UserData.commit()
    task = await activate_config(TaskItem())
    script_id = task.scripts.add(
        TaskScriptItem, payload={"info": {"script_id": str(uuid4())}}
    )
    await task.scripts.commit()
    script = task.scripts[script_id]
    script.users.add(
        TaskUserItem, payload={"info": {"user_id": str(user_id), "name": "测试账号"}}
    )
    await script.users.commit()
    await script.set_current_index(0)
    emulator = AsyncMock()
    emulator.open.side_effect = EmulatorStartupError(
        "实例 0 errcode=-503 mainnx connect failed"
    )
    send = AsyncMock()
    monkeypatch.setattr(Publisher, "send", send)
    proxy = AutoProxyTask(
        script, config, config.UserData, emulator, capture_adb=AsyncMock()
    )
    # 保留真实 prepare、main_task 和异常记账；外部命令在模拟器边界失败，MAA 尚未运行。
    await proxy._run_main_task()
    emulator.open.assert_awaited_once()
    emulator.close.assert_not_awaited()
    assert proxy.cur_user_item.status == "异常"
    assert "mainnx connect failed" in proxy.cur_user_item.result
    assert "errcode=-503" in script.current.log
    assert "正在启动模拟器" not in script.current.log
    assert any("-503" in call.kwargs["data"].message for call in send.await_args_list)


@pytest.mark.asyncio
async def test_scheduler_releases_locks_reports_error_and_runs_following_script(
    scheduler,
):
    manager, scripts, _, first_id = scheduler
    second_id = scripts.add(GeneralConfig, payload={"Info": {"Name": "正常脚本"}})
    await scripts.commit()
    scripts[second_id].UserData.add(
        GeneralUserConfig, payload={"Info": {"Status": True, "RemainedDay": -1}}
    )
    await scripts[second_id].UserData.commit()
    finalized, following = [], []
    external_open = AsyncMock(
        side_effect=EmulatorStartupError("errcode=-503 mainnx connect failed")
    )

    class Worker(AutoProxyWorker):
        async def main_logic(self):
            if self.script_info.script_id == str(first_id):
                await external_open("0")
            else:
                assert not scripts[first_id].is_locked
                assert not any(u.is_locked for u in scripts[first_id].UserData.values())
                following.append(self.user_info.uid)
                await self.user_info.set_state(status="完成")

        async def finish(self):
            assert self.user_config.is_locked
            finalized.append(self.user_info.uid)

    class Expander(UserExpander):
        def build_worker(self, user, user_config):
            return Worker(self, user, user_config)

    manager.plugin_expander = lambda script, config: Expander(script, config)
    uid = await manager.start(
        TaskMode.AUTO_PROXY,
        {
            0: {
                "uid": "-",
                "children": {
                    0: {"uid": str(first_id)},
                    1: {"uid": str(second_id)},
                },
            }
        },
    )
    run = manager.task_handler[uid]
    await asyncio.wait_for(run.accomplish.wait(), 3)
    assert run.task_info.status == "error"
    assert following and len(finalized) == 3
    assert all(not config.is_locked for config in scripts.values())
    assert all(
        not user.is_locked
        for config in scripts.values()
        for user in config.UserData.values()
    )
    assert not manager.task_handler
