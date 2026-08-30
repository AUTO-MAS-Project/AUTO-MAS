"""Win32 controller 下 MAS 是否该索要游戏 exe。

真机（Maa_bbb / 识宝）暴露的缺陷：用户在脚本管理页选好了 exe，check 仍报
「当前 MaaFW controller 需要由 MAS 启动游戏，请在脚本管理页选择实际游戏 exe」。

两个独立原因：

1. 读错 key。前端写 ``Game.LaunchPath``（ControlConfigSection.vue），而检查读
   ``Game.Path`` —— 后者按 config.py 的注释是「旧版桌面控制器路径，仅用于
   读取兼容」。
2. 没读 LaunchMode。产品上只保留 AttachOnly（脚本/用户自己启动）与 DirectExe
   （MAS 启动并按 CloseOnFinish 关闭）两种模式，但 runner_task 里从未读过
   LaunchMode，于是 Win32 无论哪种模式都强制要 exe。AttachOnly 下这个路径
   根本用不上，找不到窗口时应由 _resolve_window_handle 报「未找到匹配 MaaFW
   Win32 controller 的窗口」。
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

import app.core  # noqa: F401  # 初始化宿主配置

MAA_MODULES = (
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


def load():
    patcher = mock.patch.dict(
        sys.modules, {name: mock.MagicMock() for name in MAA_MODULES}
    )
    patcher.start()
    import importlib

    return importlib.import_module("app.task.MaaFW.tools.embedded.runner_task"), patcher


class GameLaunchResolutionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module, patcher = load()
        self.addCleanup(patcher.stop)

    def _task(self, values: dict[tuple[str, str], object]):
        task = object.__new__(self.module.MaaFWPluginAutoProxyTask)
        config = mock.Mock()
        config.get.side_effect = lambda section, key: values.get((section, key), "")
        task.script_config = config
        return task

    def test_direct_exe_reads_the_key_the_frontend_writes(self) -> None:
        task = self._task(
            {
                ("Game", "LaunchMode"): "DirectExe",
                ("Game", "LaunchPath"): r"D:\game\game.exe",
            }
        )
        self.assertTrue(task._mas_manages_game_launch())
        self.assertEqual(task._resolve_game_launch_path(), Path(r"D:\game\game.exe"))

    def test_legacy_path_is_still_honoured_as_a_fallback(self) -> None:
        task = self._task(
            {
                ("Game", "LaunchMode"): "DirectExe",
                ("Game", "Path"): r"D:\old\game.exe",
            }
        )
        self.assertEqual(task._resolve_game_launch_path(), Path(r"D:\old\game.exe"))

    def test_launch_path_wins_over_the_legacy_key(self) -> None:
        task = self._task(
            {
                ("Game", "LaunchPath"): r"D:\new\game.exe",
                ("Game", "Path"): r"D:\old\game.exe",
            }
        )
        self.assertEqual(task._resolve_game_launch_path(), Path(r"D:\new\game.exe"))

    def test_no_path_configured_returns_none_not_a_bogus_path(self) -> None:
        self.assertIsNone(self._task({})._resolve_game_launch_path())

    def test_attach_only_is_the_default_and_does_not_manage_launch(self) -> None:
        self.assertFalse(self._task({})._mas_manages_game_launch())
        self.assertFalse(
            self._task({("Game", "LaunchMode"): "AttachOnly"})._mas_manages_game_launch()
        )

    def test_retired_modes_do_not_count_as_mas_managed(self) -> None:
        """LauncherExe / URL 已下线，旧配置不该被当成 MAS 托管启动。"""

        for retired in ("LauncherExe", "URL", ""):
            self.assertFalse(
                self._task(
                    {("Game", "LaunchMode"): retired}
                )._mas_manages_game_launch(),
                retired,
            )


class CheckOnlyDemandsExeWhenMasLaunchesTest(unittest.TestCase):
    """check 阶段的守卫必须同时受 LaunchMode 与 LaunchPath 约束。"""

    def test_guard_is_conditioned_on_launch_mode(self) -> None:
        source = (
            Path(__file__).resolve().parents[2]
            / "app/task/MaaFW/tools/embedded/runner_task.py"
        ).read_text(encoding="utf-8")
        flat = " ".join(source.split())
        self.assertIn(
            'run_plan.tasks and run_plan.controllerType == "Win32" '
            "and self._mas_manages_game_launch()",
            flat,
        )
        # 旧的直读 Game.Path 不该再有
        self.assertNotIn('self.script_config.get("Game", "Path") or ""', flat)

    def test_runtime_launch_returns_early_in_attach_only(self) -> None:
        source = (
            Path(__file__).resolve().parents[2]
            / "app/task/MaaFW/tools/embedded/runner_task.py"
        ).read_text(encoding="utf-8")
        flat = " ".join(source.split())
        self.assertIn("if not self._mas_manages_game_launch(): # AttachOnly", flat)


if __name__ == "__main__":
    unittest.main()
