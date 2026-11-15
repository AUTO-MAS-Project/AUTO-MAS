#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be
#   useful, but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""OK-WW 日志成功判定回归测试。

守护 `OkwwAutoProxy.check_log` 对任务成功的判定契约：

- 新版 ok-ww（v3.7.12+）任务完成文案走 gettext 翻译，中文环境不再输出
  `Daily Task Completed`；框架 TaskExecutor 的退出语硬编码英文且仅在
  `DailyTask.run()` 正常返回后打印，是语言无关的成功标志。漏认它会把
  已完成任务误判为「未连接游戏客户端」并反复重试（TODO-16 实测）。
- 旧版 ok-ww（v3.7.4 及更早）没有框架退出语，英文完成日志是唯一标志，
  不能因新增退出语判据而被移除。
- 未出现任何成功标志时，正常退出流程中的断连日志仍须报异常，不允许被
  关窗日志或其他退出路径冒充成功。

日志行按 ok-ww 实机日志构造（CRLF 行尾、`TaskName:消息` 前缀），
经 `check_log` 回调边界注入，与 LogMonitor 按行摄入的格式一致。
"""

import asyncio
from datetime import datetime

import pytest

from app.models.config.script import OkwwUserConfig
from app.task.Okww.AutoProxy import AutoProxyTask
from tests.runtime_support import RuntimeStub as SimpleNamespace


def make_proxy() -> AutoProxyTask:
    proxy = AutoProxyTask.__new__(AutoProxyTask)
    proxy.task_name = "DailyTask"
    proxy.cur_user_config = OkwwUserConfig()
    proxy.script_config = SimpleNamespace(Run=SimpleNamespace(RunTimeLimit=30))
    proxy.cur_user_log = SimpleNamespace(content=[], status="")
    proxy.cur_user_item = SimpleNamespace(status="运行")
    proxy.script_info = SimpleNamespace(log="", log_first_line=0)
    proxy.wait_event = asyncio.Event()

    async def running():
        return True

    proxy.okww_process_manager = SimpleNamespace(is_running=running)
    proxy.is_log_stalled = lambda *args, **kwargs: False
    return proxy


async def judge(lines: list[str]) -> AutoProxyTask:
    proxy = make_proxy()
    await proxy.check_log(lines, datetime.now())
    return proxy


@pytest.mark.parametrize(
    "lines,success",
    [
        pytest.param(
            [
                "2026-11-04 14:38:16,060 INFO TaskExecutor DailyTask:每日任务已完成\r\n",
                "2026-11-04 14:38:16,061 INFO TaskExecutor TaskExecutor:Successfully Executed Task, Exiting Game and App!\r\n",
                "2026-11-04 14:38:21,157 INFO update_window_size hwnd_window:hwnd changed,connected:0\r\n",
            ],
            True,
            id="translated-completion",
        ),
        pytest.param(
            [
                "2026-10-29 11:32:40,714 INFO TaskExecutor DailyTask:Daily Task Completed\r\n",
                "2026-10-29 11:32:45,850 INFO update_window_size hwnd_window:hwnd changed,connected:0\r\n",
            ],
            True,
            id="legacy-completion",
        ),
        pytest.param(
            [
                "2026-11-04 14:05:00,000 INFO update_window_size hwnd_window:hwnd changed,connected:0\r\n",
            ],
            False,
            id="disconnected-without-completion",
        ),
        pytest.param(
            [
                "2026-11-04 14:38:16,061 INFO TaskExecutor TaskExecutor:Successfully Executed Task, Exiting Game and App!\r\n",
                "2026-11-04 14:38:21,157 INFO update_window_size hwnd_window:hwnd changed,connected:0\r\n",
            ],
            True,
            id="framework-completion",
        ),
        pytest.param(
            [
                "2026-11-04 14:30:00,000 INFO TaskExecutor DailyTask:每日任务已完成，开始传送并刷取4C声骸\r\n",
                "2026-11-04 14:35:00,000 INFO update_window_size hwnd_window:hwnd changed,connected:0\r\n",
            ],
            False,
            id="translated-intermediate-step",
        ),
    ],
)
def test_success_verdict_distinguishes_upstream_completion_from_disconnect(
    lines, success
):
    """同批次断连不能盖过完成，也不能把中间步骤误当完成。"""
    proxy = asyncio.run(judge(lines))
    assert proxy.cur_user_log.status == (
        "Success!" if success else "OK-WW 未连接游戏客户端"
    )
    assert proxy.cur_user_item.status == ("完成" if success else "异常")
    assert proxy.wait_event.is_set()


@pytest.mark.parametrize(
    "task_name,custom", [("DailyTask", True), ("MultiAccountConfigTask", False)]
)
def test_waiting_modes_require_the_terminal_success_marker(task_name, custom):
    """自定义参数与多账号批次都须等框架终态，日常完成不能提前放行。"""

    async def scenario():
        proxy = make_proxy()
        proxy.task_name = task_name
        proxy.cur_user_config.Task.IfCustomArguments = custom
        await proxy.check_log(["DailyTask:Daily Task Completed\n"], datetime.now())
        assert proxy.cur_user_item.status == "运行"
        assert not proxy.wait_event.is_set()
        await proxy.check_log(
            ["TaskExecutor:Successfully Executed Task, Exiting Game and App!\n"],
            datetime.now(),
        )
        assert proxy.cur_user_log.status == "Success!"
        assert proxy.cur_user_item.status == "完成"
        assert proxy.wait_event.is_set()

    asyncio.run(scenario())
