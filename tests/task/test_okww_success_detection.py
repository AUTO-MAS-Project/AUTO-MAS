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


def test_custom_task_waits_for_framework_completion():
    async def scenario():
        proxy = make_proxy()
        proxy.cur_user_config.Task.IfCustomArguments = True
        await proxy.check_log(["DailyTask:Daily Task Completed\n"], datetime.now())
        assert not proxy.wait_event.is_set()
        await proxy.check_log(
            ["TaskExecutor:Successfully Executed Task, Exiting Game and App!\n"],
            datetime.now(),
        )
        assert proxy.cur_user_log.status == "Success!"
        assert proxy.wait_event.is_set()

    asyncio.run(scenario())


def test_chinese_completion_with_exit_line_marks_success():
    """新版 ok-ww 中文环境成功：完成文案已翻译，仅退出语可判成功。

    完成日志（中文翻译）、框架退出语与 5 秒后的断连日志可能落入同一
    监控批次；成功判据必须在断连日志之前命中，否则任务被误判重试。
    """

    async def scenario():
        proxy = await judge(
            [
                "2026-11-04 14:38:16,060 INFO TaskExecutor DailyTask:每日任务已完成\r\n",
                "2026-11-04 14:38:16,061 INFO TaskExecutor TaskExecutor:Successfully Executed Task, Exiting Game and App!\r\n",
                "2026-11-04 14:38:21,157 INFO update_window_size hwnd_window:hwnd changed,connected:0\r\n",
            ]
        )
        assert proxy.cur_user_log.status == "Success!"
        assert proxy.cur_user_item.status == "完成"
        assert proxy.wait_event.is_set()

    asyncio.run(scenario())


def test_legacy_english_completion_without_exit_line_marks_success():
    """旧版 ok-ww 成功：无框架退出语，英文完成日志兜底判定。"""

    async def scenario():
        proxy = await judge(
            [
                "2026-10-29 11:32:40,714 INFO TaskExecutor DailyTask:Daily Task Completed\r\n",
                "2026-10-29 11:32:45,850 INFO update_window_size hwnd_window:hwnd changed,connected:0\r\n",
            ]
        )
        assert proxy.cur_user_log.status == "Success!"
        assert proxy.cur_user_item.status == "完成"
        assert proxy.wait_event.is_set()

    asyncio.run(scenario())


def test_disconnect_without_completion_still_fails():
    """未出现成功标志时断连：仍报未连接异常，不得冒充成功。"""

    async def scenario():
        proxy = await judge(
            [
                "2026-11-04 14:05:00,000 INFO update_window_size hwnd_window:hwnd changed,connected:0\r\n",
            ]
        )
        assert proxy.cur_user_log.status == "OK-WW 未连接游戏客户端"
        assert proxy.cur_user_item.status == "异常"
        assert proxy.wait_event.is_set()

    asyncio.run(scenario())


def test_exit_line_alone_without_completion_text_marks_success():
    """仅框架退出语、无任何完成文案也判成功：退出语是独立判据。"""

    async def scenario():
        proxy = await judge(
            [
                "2026-11-04 14:38:16,061 INFO TaskExecutor TaskExecutor:Successfully Executed Task, Exiting Game and App!\r\n",
                "2026-11-04 14:38:21,157 INFO update_window_size hwnd_window:hwnd changed,connected:0\r\n",
            ]
        )
        assert proxy.cur_user_log.status == "Success!"
        assert proxy.cur_user_item.status == "完成"
        assert proxy.wait_event.is_set()

    asyncio.run(scenario())


def test_localized_completion_text_without_exit_line_is_not_success():
    """仅翻译完成文案（含 farm 4C 追加预告）、无退出语：不得判成功。

    翻译文案是 farm 4C 追加阶段在完成日志之前打印的预告，若被误加为
    成功判据，任务会在刷声骸中途被判完成并杀进程；无退出语时它只应
    落回断连异常路径。
    """

    async def scenario():
        proxy = await judge(
            [
                "2026-11-04 14:30:00,000 INFO TaskExecutor DailyTask:每日任务已完成，开始传送并刷取4C声骸\r\n",
                "2026-11-04 14:35:00,000 INFO update_window_size hwnd_window:hwnd changed,connected:0\r\n",
            ]
        )
        assert proxy.cur_user_log.status == "OK-WW 未连接游戏客户端"
        assert proxy.cur_user_item.status == "异常"
        assert proxy.wait_event.is_set()

    asyncio.run(scenario())


def test_native_multi_account_waits_for_whole_batch():
    """单账号日常完成后仍运行，直到上游整批任务正常返回。"""

    async def scenario():
        proxy = make_proxy()
        proxy.task_name = "MultiAccountConfigTask"
        await proxy.check_log(["DailyTask:Daily Task Completed\n"], datetime.now())
        assert proxy.cur_user_item.status == "运行"
        assert not proxy.wait_event.is_set()
        await proxy.check_log(
            ["TaskExecutor:Successfully Executed Task, Exiting Game and App!\n"],
            datetime.now(),
        )
        assert proxy.cur_user_item.status == "完成"
        assert proxy.wait_event.is_set()

    asyncio.run(scenario())
