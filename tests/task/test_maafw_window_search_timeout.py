"""定位游戏窗口时传给 ProcessManager 的是秒数，不是截止时刻。

真机（MaaEnd）暴露：

    游戏进程已启动，但定位窗口失败: unsupported operand type(s) for +:
    'float' and 'datetime.datetime'

`ProcessManager.search_process` 的第二个参数原本是截止 datetime，dev 的
#473「计时改用单调时钟」把它改成了 `timeout_seconds: float`，内部变成
`time.monotonic() + timeout_seconds`。把 dev 合并进移植分支时文本无冲突、
**语义却变了**，于是这处调用静默失效：窗口没被前置，随后第一个任务识别
不到目标而失败，用户只看到一条与真因无关的任务失败。

因此本文件不做「源码里有没有写对」的字符串断言——那种断言挡不住签名语义
漂移。改为**真的调用一次** `search_process`，让它在找不到进程时按超时抛
RuntimeError；一旦参数类型再次对不上，就会是 TypeError 而不是 RuntimeError。
"""

import asyncio
import unittest

import app.core  # noqa: F401  # 初始化宿主配置

from app.utils.platform.common.process import ProcessInfo, ProcessManager


class SearchProcessTakesSecondsTest(unittest.TestCase):
    def test_a_float_timeout_times_out_instead_of_raising_typeerror(self) -> None:
        manager = ProcessManager()

        async def go():
            await manager.search_process(
                ProcessInfo(exe=r"Z:\definitely\not\a\real\process.exe"),
                0.2,
            )

        with self.assertRaises(RuntimeError) as ctx:
            asyncio.run(go())
        self.assertNotIsInstance(ctx.exception, TypeError)

    def test_a_datetime_deadline_would_be_a_type_error(self) -> None:
        """钉住「传 datetime 是错的」这一事实，免得有人又改回去。"""

        from datetime import datetime, timedelta

        manager = ProcessManager()

        async def go():
            await manager.search_process(
                ProcessInfo(exe=r"Z:\definitely\not\a\real\process.exe"),
                datetime.now() + timedelta(seconds=1),
            )

        with self.assertRaises(TypeError):
            asyncio.run(go())


class RunnerPassesSecondsTest(unittest.TestCase):
    def test_the_constant_is_a_number(self) -> None:
        import sys
        from unittest import mock

        maa_modules = {
            name: mock.MagicMock()
            for name in (
                "maa",
                "maa.agent_client",
                "maa.context",
                "maa.controller",
                "maa.custom_action",
                "maa.custom_recognition",
                "maa.define",
                "maa.event_sink",
                "maa.job",
                "maa.library",
                "maa.notification_handler",
                "maa.resource",
                "maa.tasker",
                "maa.toolkit",
            )
        }
        with mock.patch.dict(sys.modules, maa_modules):
            import importlib

            module = importlib.import_module(
                "app.task.MaaFW.tools.embedded.runner_task"
            )
        self.assertIsInstance(module.WINDOW_SEARCH_TIMEOUT_SECONDS, (int, float))
        self.assertGreater(module.WINDOW_SEARCH_TIMEOUT_SECONDS, 0)


if __name__ == "__main__":
    unittest.main()
