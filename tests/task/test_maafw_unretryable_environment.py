"""环境级失败不该白重试。

真机现场（2026-08-31）：用户的 Python 运行时标准库损坏，worker 每次都在
``import ctypes`` 处炸掉。默认 ``RunTimesLimit=3``，于是同一个必然失败的错误
被重复三遍，每遍还要重启一次模拟器/游戏——白等好几分钟，最后告诉用户的还是
同一件事。

解释器坏了、依赖没装上，这类失败重试不会有别的结果。与「游戏未能启动」那条
同理，只是判据不同：那条看 controller 的 ``start_app``，这条看环境准备与运行池
自检抛出的消息标记。
"""

import unittest

import app.core  # noqa: F401  # 初始化宿主配置

from app.task.MaaFW.tools.embedded import runner_task


class UnretryableEnvironmentMarkerTest(unittest.TestCase):
    def _unretryable(self, message: str) -> bool:
        return any(
            marker in message
            for marker in runner_task._UNRETRYABLE_ENVIRONMENT_MARKERS
        )

    def test_broken_stdlib_is_not_retried(self) -> None:
        """真机那条原文。"""

        message = (
            "MaaFW 运行异常: installed runtime Python identity could not be "
            "verified: E:/AUTO-MAS/config/maafw_runtime_pool/runtimes/"
            "maafw-runtime-8113c6894dc01899b939dfba/environment/Scripts/python.exe: "
            "MaaFW runtime Python 自检失败：标准库 ctypes 不可用。"
        )
        self.assertTrue(self._unretryable(message))

    def test_environment_preparation_failures_are_not_retried(self) -> None:
        for message in (
            "MaaFW 运行异常: MaaFW Runner 环境准备失败 (exit=1): could not resolve",
            "MaaFW 运行异常: MaaFW Runner 环境准备超时: ['uv', 'pip', 'install']",
            "MaaFW 运行异常: MaaFW runtime ABI 探测失败 (exit=9009): ...",
        ):
            with self.subTest(message=message):
                self.assertTrue(self._unretryable(message))

    def test_ordinary_run_failures_are_still_retried(self) -> None:
        """识别不到、超时、连接抖动这些重试确实可能救回来，不能一起拦掉。"""

        for message in (
            "MaaFW 运行异常: MaaFW 任务运行超时",
            "MaaFW 运行异常: 游戏未能启动（start_app 失败），本轮剩余任务已跳过",
            "MaaFW 运行异常: ADB 设备未就绪",
            "MaaFW 运行异常: MaaFW tasker 已释放，无法继续投递任务",
        ):
            with self.subTest(message=message):
                self.assertFalse(self._unretryable(message))

    def test_markers_are_matched_as_substrings_of_the_wrapped_message(self) -> None:
        """宿主会把原文包成「MaaFW 运行异常: {exc}」，标记必须能在包装后仍命中。"""

        raw = "MaaFW runtime Python 自检失败：标准库 ctypes 不可用。"
        self.assertTrue(self._unretryable(f"MaaFW 运行异常: {raw}"))

    def test_the_loop_breaks_instead_of_continuing(self) -> None:
        """源码级守卫：标记命中时必须 break，不能只是记一行日志继续转。"""

        import inspect

        source = inspect.getsource(runner_task.MaaFWPluginAutoProxyTask.main_task)
        self.assertIn("_UNRETRYABLE_ENVIRONMENT_MARKERS", source)
        marker_pos = source.index("_UNRETRYABLE_ENVIRONMENT_MARKERS")
        tail = source[marker_pos:]
        self.assertIn("break", tail)
        self.assertLess(
            tail.index("break"),
            tail.index("continue"),
            "break 必须在 continue 之前生效，否则永远走不到",
        )


if __name__ == "__main__":
    unittest.main()
