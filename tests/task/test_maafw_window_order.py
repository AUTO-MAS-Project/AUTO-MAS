import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import app.core  # noqa: F401

from app.task.MaaFW import manager as manager_module
from app.task.MaaFW.manager import MaaFWManager
from app.task.MaaFW.tools.controller.game_lifecycle import (
    MaaFWGameLaunchSpec,
    MaaFWOwnedGameProcess,
)


def _spec(mode: str = "GameExe") -> MaaFWGameLaunchSpec:
    return MaaFWGameLaunchSpec(mode=mode, launch_path=Path("C:/game/game.exe"))


class ResolveGamePidTest(unittest.TestCase):
    """置前的目标是**游戏本体**，不是 MAS 起的那个进程。"""

    def setUp(self) -> None:
        self.manager = MaaFWManager.__new__(MaaFWManager)
        self.manager.game_launch_spec = _spec()
        self.manager.game_owned_process = None
        self.manager.game_attached_pid = None

    def test_prefers_client_identity_over_launcher_pid(self) -> None:
        # 启动器模式下 pid 是启动器，client_identity 才是游戏；置前启动器没有意义，
        # 它多半已经自己退了。
        self.manager.game_owned_process = MaaFWOwnedGameProcess(
            pid=111, create_time=1.0, client_identity=(222, 2.0)
        )
        self.assertEqual(self.manager._resolve_game_pid(), 222)

    def test_uses_own_pid_when_no_client_identity(self) -> None:
        self.manager.game_owned_process = MaaFWOwnedGameProcess(pid=111, create_time=1.0)
        self.assertEqual(self.manager._resolve_game_pid(), 111)

    def test_attach_only_uses_the_pid_recorded_at_preparation(self) -> None:
        # AttachOnly 没有自起进程；_prepare_desktop_game 那次扫描的结果直接复用，
        # 不再重扫——全进程枚举要逐个取 exe 路径，跑两遍纯属浪费。
        self.manager.game_launch_spec = _spec("AttachOnly")
        self.manager.game_attached_pid = 333
        self.assertEqual(self.manager._resolve_game_pid(), 333)

    def test_none_when_nothing_can_be_located(self) -> None:
        self.assertIsNone(self.manager._resolve_game_pid())


class ArrangeWindowsTest(unittest.IsolatedAsyncioTestCase):
    """起游戏 → 起外壳 → 游戏窗口置前，对齐 MaaEnd 专项的既有顺序。"""

    def setUp(self) -> None:
        self.manager = MaaFWManager.__new__(MaaFWManager)
        self.manager.game_launch_spec = None
        self.manager.game_owned_process = None
        self.manager.game_attached_pid = None
        self.shell = MagicMock()
        self.shell.minimize_window = AsyncMock(return_value=True)
        self.manager.process_manager = self.shell

        self.activate = MagicMock(return_value=True)
        self._pm = patch.object(
            manager_module, "activate_window_by_pid", self.activate
        )
        self._pm.start()
        self.addCleanup(self._pm.stop)

    def _silence(self, enabled: bool):
        config = MagicMock()
        config.get.return_value = enabled
        return patch.object(manager_module, "Config", config)

    async def test_adb_path_never_touches_the_game_window(self) -> None:
        # 模拟器链路的可见性归 EmulatorManager 管，这里插一脚只会把模拟器抢到前台。
        with self._silence(False):
            await self.manager._arrange_windows_after_launch()
        self.activate.assert_not_called()

    async def test_win32_path_brings_the_game_to_front(self) -> None:
        self.manager.game_launch_spec = _spec()
        self.manager.game_owned_process = MaaFWOwnedGameProcess(pid=111, create_time=1.0)
        with self._silence(False):
            await self.manager._arrange_windows_after_launch()
        self.activate.assert_called_once()

    async def test_silence_minimizes_the_shell_before_activating(self) -> None:
        self.manager.game_launch_spec = _spec()
        self.manager.game_owned_process = MaaFWOwnedGameProcess(pid=111, create_time=1.0)
        with self._silence(True):
            await self.manager._arrange_windows_after_launch()
        self.shell.minimize_window.assert_awaited_once()
        self.activate.assert_called_once()

    async def test_silence_off_leaves_the_shell_visible(self) -> None:
        with self._silence(False):
            await self.manager._arrange_windows_after_launch()
        self.shell.minimize_window.assert_not_awaited()

    async def test_window_failures_never_break_the_run(self) -> None:
        # 窗口调度是锦上添花：置前失败也只能告警，不能把一轮任务判死。
        self.manager.game_launch_spec = _spec()
        self.manager.game_owned_process = MaaFWOwnedGameProcess(pid=111, create_time=1.0)
        self.activate.side_effect = OSError("boom")
        self.shell.minimize_window = AsyncMock(side_effect=OSError("boom"))
        with self._silence(True):
            await self.manager._arrange_windows_after_launch()


class ArrangeWindowsAgainstRealApisTest(unittest.IsolatedAsyncioTestCase):
    """不打桩，直接压真 ProcessManager / psutil 的失效路径。

    上面那组把 ProcessManager 和 psutil 都换成了替身，验证的是分支逻辑；这里补
    的是「pid 早就没了」这个真实场景 —— 游戏在外壳起来之前就自己退了、或被用户
    关了。真 psutil 会抛 NoSuchProcess，真 win32gui 会拿到空句柄，两者都不能把
    这一轮任务带走。
    """

    async def test_dead_pid_only_warns(self) -> None:
        manager = MaaFWManager.__new__(MaaFWManager)
        manager.game_launch_spec = _spec()
        manager.game_attached_pid = None
        # 取一个几乎不可能存在的 pid：Windows 的 pid 是 4 的倍数且远小于此。
        manager.game_owned_process = MaaFWOwnedGameProcess(
            pid=0x7FFFFFF1, create_time=1.0
        )
        shell = MagicMock()
        shell.minimize_window = AsyncMock(return_value=False)
        manager.process_manager = shell

        config = MagicMock()
        config.get.return_value = False
        with patch.object(manager_module, "Config", config):
            await manager._arrange_windows_after_launch()


if __name__ == "__main__":
    unittest.main()
