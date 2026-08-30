"""worker 输出转发不得独占事件循环。

真机（MaaYYs）症状：界面日志停更 67 秒、点停止没反应、期间后端 HTTP 也不响应，
之后所有内容在同一毫秒段一起涌出。

根因是 asyncio 的一个陷阱：`StreamReader` 缓冲里有数据时 `async for` **不会
挂起**，会一路取到缓冲耗尽。MaaFramework 的原生诊断洪峰很大——那次运行里
框架日志在一分钟内产生了 2,416 行——转发循环于是连续几千次不交还控制权，
事件循环被独占，API 处理器和 WS 推送全部饿死。

排除过的：ADB 等待（重试每 15 次记一条，67 秒该有 5 条，实际只有 1 条，
说明设备很快就绪）；worker 卡死（框架日志证明它全程在正常产出）；
停止逻辑本身（一旦送达只用 0.3 秒）。
"""

import ast
import asyncio
import unittest
from pathlib import Path

import app.core  # noqa: F401  # 初始化宿主配置

SOURCE_PATH = (
    Path(__file__).resolve().parents[2]
    / "app/task/MaaFW/tools/embedded/runner_task.py"
)
SOURCE = SOURCE_PATH.read_text(encoding="utf-8")


def relay_functions() -> dict[str, ast.AsyncFunctionDef]:
    tree = ast.parse(SOURCE)
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name in (
            "read_stdout",
            "read_stderr",
        ):
            found[node.name] = node
    return found


class RelayYieldsTest(unittest.TestCase):
    def test_both_relays_exist(self) -> None:
        self.assertEqual(set(relay_functions()), {"read_stdout", "read_stderr"})

    def test_each_relay_yields_periodically(self) -> None:
        """两条转发都要让出——stderr 同样可能被原生输出灌满。"""

        for name, fn in relay_functions().items():
            with self.subTest(relay=name):
                sleeps = [
                    node
                    for node in ast.walk(fn)
                    if isinstance(node, ast.Await)
                    and isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Attribute)
                    and node.value.func.attr == "sleep"
                ]
                self.assertTrue(sleeps, f"{name} 没有让出点")

    def test_the_yield_interval_is_bounded(self) -> None:
        """让出间隔太大等于没让；太小则频繁切换。"""

        from app.task.MaaFW.tools.embedded import runner_task

        interval = runner_task._RELAY_YIELD_EVERY_LINES
        self.assertIsInstance(interval, int)
        self.assertGreaterEqual(interval, 1)
        self.assertLessEqual(interval, 200)


class BufferedStreamStarvesTheLoopTest(unittest.IsolatedAsyncioTestCase):
    """钉住这个 asyncio 行为本身，免得日后有人把让出点删掉。"""

    async def _drain(self, line_count: int, *, yield_every: int | None) -> int:
        reader = asyncio.StreamReader()
        for i in range(line_count):
            reader.feed_data(b"line %d\n" % i)
        reader.feed_eof()

        other_ran = 0

        async def competitor() -> None:
            nonlocal other_ran
            for _ in range(line_count):
                other_ran += 1
                await asyncio.sleep(0)

        task = asyncio.create_task(competitor())
        await asyncio.sleep(0)  # 让竞争者先起跑
        baseline = other_ran

        processed = 0
        async for _ in reader:
            processed += 1
            if yield_every and processed % yield_every == 0:
                await asyncio.sleep(0)
        progressed = other_ran - baseline
        task.cancel()
        return progressed

    async def test_without_yield_the_competitor_never_runs(self) -> None:
        """缓冲已满时不让出，其它协程一步都跑不了 —— 这就是真机上的现象。"""

        self.assertEqual(await self._drain(500, yield_every=None), 0)

    async def test_with_yield_the_competitor_makes_progress(self) -> None:
        progressed = await self._drain(500, yield_every=50)
        self.assertGreater(progressed, 0)


if __name__ == "__main__":
    unittest.main()
