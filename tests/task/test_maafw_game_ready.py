import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import app.core  # noqa: F401

from app.task.MaaFW import manager as manager_module
from app.task.MaaFW.manager import MaaFWManager
from app.task.MaaFW.tools.controller.game_lifecycle import (
    MaaFWGameLaunchSpec,
    MaaFWOwnedGameProcess,
)


def _spec(mode: str = "DirectExe", wait_time: int = 60) -> MaaFWGameLaunchSpec:
    return MaaFWGameLaunchSpec(
        mode=mode,
        launch_path=Path("C:/game/launcher.exe"),
        process_name="game.exe",
        wait_time=wait_time,
    )


class GameReadyWaitTest(unittest.IsolatedAsyncioTestCase):
    """「等待时间」的语义是 UI 写死的：等**实际游戏进程/窗口**出现。

    此前 wait_time 只被解析进 spec，没有任何调用点 —— 起完 exe 立刻起外壳。
    进程创建远早于窗口出现，外壳先到就拿不到游戏窗口。
    """

    def setUp(self) -> None:
        self.manager = MaaFWManager.__new__(MaaFWManager)
        self.manager.game_owned_process = MaaFWOwnedGameProcess(
            pid=111, create_time=1.0
        )
        self.visible = MagicMock(return_value=True)
        self._v = patch.object(manager_module, "has_visible_window", self.visible)
        self._v.start()
        self.addCleanup(self._v.stop)
        self._sleep = patch.object(manager_module.asyncio, "sleep", AsyncMock())
        self.sleep = self._sleep.start()
        self.addCleanup(self._sleep.stop)

    async def test_waits_for_the_window_not_just_the_process(self) -> None:
        # 前两轮没窗口，第三轮才有：必须一直等到窗口出现。
        self.visible.side_effect = [False, False, True]
        await self.manager._await_game_ready(_spec())
        self.assertEqual(self.visible.call_count, 3)
        self.assertEqual(self.sleep.await_count, 2)

    async def test_gives_up_after_wait_time_without_failing_the_run(self) -> None:
        # 等不到不判死：外壳自己也有重试，用户也可能就是想把等待交给外壳。
        self.visible.return_value = False
        self.visible.side_effect = None
        await self.manager._await_game_ready(_spec(wait_time=5))
        self.assertEqual(self.visible.call_count, 5)

    async def test_zero_wait_time_skips_the_wait_entirely(self) -> None:
        await self.manager._await_game_ready(_spec(wait_time=0))
        self.visible.assert_not_called()

    async def test_attach_only_and_url_never_wait(self) -> None:
        # AttachOnly 的客户端已在跑（_prepare_desktop_game 拦过）；URL 交给协议
        # 处理程序，MAS 既不持有也猜不出它会拉起什么。
        for mode in ("AttachOnly", "URL"):
            with self.subTest(mode=mode):
                self.visible.reset_mock()
                await self.manager._await_game_ready(_spec(mode))
                self.visible.assert_not_called()

    async def test_launcher_mode_waits_for_the_client_and_records_it(self) -> None:
        """启动器模式下 MAS 起的是启动器，要等的是它拉起来的游戏本体。

        身份记进 client_identity —— 窗口置前和结束收尾都按它来。此前这个字段
        从没被赋过值，启动器模式下游戏本体既不会被置前也不会被关闭。
        """

        client = SimpleNamespace(pid=222, create_time=lambda: 2.0)
        with patch.object(manager_module, "wait_for_client", return_value=client):
            await self.manager._await_game_ready(_spec("LauncherExe"))
        self.assertEqual(self.manager.game_owned_process.client_identity, (222, 2.0))
        # 等的是游戏本体的窗口，不是启动器的。
        self.assertEqual(self.visible.call_args.args[0], 222)

    async def test_launcher_mode_tolerates_a_missing_client(self) -> None:
        with patch.object(manager_module, "wait_for_client", return_value=None):
            await self.manager._await_game_ready(_spec("LauncherExe"))
        self.assertIsNone(self.manager.game_owned_process.client_identity)
        self.visible.assert_not_called()


if __name__ == "__main__":
    unittest.main()
