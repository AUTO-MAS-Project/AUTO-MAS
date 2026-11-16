"""通过真实调度守护 MAA 保存结果与每日代理额度，只隔离外部进程和日志。"""

import asyncio
from datetime import datetime, timedelta

import pytest
from maa_adapter.tasks import auto_proxy, manager, session

from app.models.config import QueueConfig, QueueItem
from app.models.task import TaskMode
from app.utils import constants, io
from plugins.maa_adapter.tests.test_runtime import dispatch
from plugins.maa_adapter.tests.test_runtime import runtime as runtime


@pytest.mark.asyncio
@pytest.mark.parametrize("confirmed", [True, False])
async def test_native_config_save_survives_task_stop(runtime, monkeypatch, confirmed):
    """保存走停止入口时保留 GUI 已确认写盘的修改；未确认保存仍恢复任务前原件。"""
    config_file = runtime.install / "config/gui.new.json"

    class Process(runtime.process):
        opened = False

        async def open_process(self, *args, **kwargs):
            """记录启动并让 GUI 保持运行，直到测试通过真实停止入口请求保存。"""
            await super().open_process(*args, **kwargs)
            self.opened = True
            runtime.started.set()

        async def is_running(self):
            """向配置会话报告受控 GUI 的运行状态。"""
            return self.opened

        async def close(self):
            """模拟 GUI 关闭时写盘；另一场景保持未退出，验证超时不能被误认为保存成功。"""
            if self.opened:
                if not confirmed:
                    await asyncio.Event().wait()
                document = io.read_file(config_file)
                document["Gui"]["MinimizeOnStartup"] = True
                io.write_file(config_file, document)
                self.opened = False

    monkeypatch.setattr(session, "ProcessManager", Process)
    monkeypatch.setattr(session.MaaGuiSession, "GUI_CLOSE_TIMEOUT", 0.05)
    execution = await dispatch(runtime, TaskMode.SCRIPT_CONFIG)
    await asyncio.wait_for(runtime.started.wait(), 5)
    await asyncio.wait_for(execution.stop(), 5)
    assert execution.task_info.info.status == "cancelled"
    assert io.read_file(config_file)["Gui"]["MinimizeOnStartup"] is confirmed
    assert not runtime.script.is_locked and not runtime.user.is_locked


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["limited", "new_day", "manual", "unlimited"])
async def test_daily_quota_is_checked_under_user_lock(runtime, monkeypatch, case):
    """队列遵守当日上限，跨游戏日重置并正常扣天；手动运行和无限次数配置允许继续代理。"""
    current = datetime.now(tz=constants.UTC4)
    runtime.script.Run.ProxyTimesLimit = 0 if case == "unlimited" else 1
    runtime.script.Run.RunTimesLimit = 1
    await runtime.script.commit()
    runtime.user.Data.LastProxyDate = (
        current - timedelta(days=1) if case == "new_day" else current
    )
    runtime.user.Data.ProxyTimes = 1
    runtime.user.Info.RemainedDay = 10
    await runtime.user.commit()

    def game_now(server):
        """在读取游戏日期时确认真实调度已经持有账号锁，并提供确定的本轮日期。"""
        assert runtime.user.is_locked
        return current

    monkeypatch.setattr(manager, "game_now", game_now, raising=False)

    class Process(runtime.process):
        async def is_running(self):
            """让实际代理流程等待受控日志给出任务结果。"""
            return True

    class Monitor:
        def __init__(self, interval, fmt, callback, **kwargs):
            """保存真实 MAA 日志处理入口，稍后从日志边界交付成功结果。"""
            self.callback = callback

        async def start_monitor_file(self, *args, **kwargs):
            """提供与现有专项测试一致的 MAA 成功日志，保留真正的次数和剩余天数结算。"""
            await self.callback(["任务已全部完成！"], datetime.now().astimezone())

        async def stop(self):
            """完成受控日志源的关闭，保持代理收尾协议。"""
            pass

    monkeypatch.setattr(auto_proxy, "ProcessManager", Process)
    monkeypatch.setattr(auto_proxy, "LogMonitor", Monitor)
    if case == "manual":
        execution = await dispatch(runtime, TaskMode.AUTO_PROXY)
    else:
        queues = manager.Config.QueueConfig
        uid = queues.add(QueueConfig)
        await queues.commit()
        queues[uid].QueueItem.add(
            QueueItem, payload={"Info": {"ScriptId": str(runtime.sid)}}
        )
        await queues[uid].QueueItem.commit()
        task_id = await runtime.manager.start(
            TaskMode.AUTO_PROXY, {0: {"uid": str(uid)}}
        )
        execution = runtime.manager.task_handler[task_id]
    await asyncio.wait_for(execution.accomplish.wait(), 10)
    user = execution.task_info.script_list[0].user_list[0]
    assert execution.task_info.info.status == "success", user.result
    assert user.status == ("跳过" if case == "limited" else "完成")
    assert bool(runtime.opened) is (case != "limited")
    assert runtime.user.Data.LastProxyDate.date() == current.date()
    assert runtime.user.Data.ProxyTimes == (2 if case in {"manual", "unlimited"} else 1)
    assert runtime.user.Info.RemainedDay == (9 if case == "new_day" else 10)
    assert not runtime.script.is_locked and not runtime.user.is_locked


@pytest.mark.asyncio
@pytest.mark.parametrize("inactive", ["disabled", "expired"])
async def test_inactive_shared_account_does_not_require_default_configuration(
    runtime, inactive
):
    """原生账号仍可运行时，运行树里保留的禁用或到期共享账号不应触发全局配置拦截。"""
    from maa_adapter.config.user import MaaUserConfig

    uid = runtime.script.users.add(
        MaaUserConfig,
        payload={
            "Info": {
                "Name": "inactive shared",
                "Base": "shared",
                "Status": inactive != "disabled",
                "RemainedDay": 0 if inactive == "expired" else -1,
            }
        },
    )
    await runtime.script.users.commit()
    runtime.script.Run.RunTimesLimit = 1
    await runtime.script.commit()
    task_id = await runtime.manager.start(
        TaskMode.AUTO_PROXY,
        {
            0: {
                "uid": "-",
                "children": {
                    0: {
                        "uid": str(runtime.sid),
                        "children": {
                            0: {"uid": str(runtime.user_id)},
                            1: {"uid": str(uid)},
                        },
                    }
                },
            }
        },
    )
    execution = runtime.manager.task_handler[task_id]
    await asyncio.wait_for(execution.accomplish.wait(), 10)
    script = execution.task_info.script_list[0]
    assert any(user.info.user_id == str(uid) for user in script.users.values())
    assert runtime.opened, script.info.result
