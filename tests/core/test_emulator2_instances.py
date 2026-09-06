import unittest
from pathlib import Path
from unittest.mock import patch

from app.models.emulator import DeviceStatus
from app.utils.emulator2.ldplayer14 import LDPlayer14Manager


class FakeResult:
    """ProcessRunner 的返回值替身。

    ``returncode`` 故意给非 0：实测 ``ldconsole add`` 成功时返回 4，
    实现不能拿它当成功判据。
    """

    def __init__(self, returncode: int = 4) -> None:
        self.returncode = returncode
        self.stdout = ""
        self.stderr = ""


class FakeLDManager(LDPlayer14Manager):
    """绕开父类构造函数（它要求路径真实存在），只保留要测的两个方法。"""

    def __init__(self, listings: list[list[str]]) -> None:
        self._listings = listings
        self._calls: list[tuple] = []
        self._status = DeviceStatus.OFFLINE
        self.emulator_path = Path(r"D:/leidian/LDPlayer14/ldconsole.exe")

        class _Config:
            @staticmethod
            def get(group, name):
                return 300

        self.config = _Config()

    async def get_device_info(self, idx=None):
        current = (
            self._listings[0] if len(self._listings) == 1 else self._listings.pop(0)
        )
        return {native: object() for native in current}

    async def getStatus(self, idx, data=None):
        return self._status


async def _noop_sleep(_seconds):
    return None


class CreateInstanceTest(unittest.IsolatedAsyncioTestCase):
    async def test_success_is_judged_by_the_listing_not_the_return_code(self) -> None:
        """ldconsole add 成功时返回码是 4，所以只能看列表里多没多出实例。"""
        manager = FakeLDManager([["0", "1"], ["0", "1", "2"]])

        with (
            patch(
                "app.utils.emulator2.ldplayer14.ProcessRunner.run_process",
                return_value=FakeResult(4),
            ),
            patch("app.utils.emulator2.ldplayer14.asyncio.sleep", _noop_sleep),
        ):
            native_index = await manager.create_instance("测试机")

        self.assertEqual(native_index, "2")

    async def test_listing_unchanged_is_reported_as_failure(self) -> None:
        manager = FakeLDManager([["0", "1"], ["0", "1"], ["0", "1"], ["0", "1"]])

        with (
            patch(
                "app.utils.emulator2.ldplayer14.ProcessRunner.run_process",
                return_value=FakeResult(0),
            ),
            patch("app.utils.emulator2.ldplayer14.asyncio.sleep", _noop_sleep),
        ):
            with self.assertRaises(RuntimeError):
                await manager.create_instance(None)


class DeleteInstanceTest(unittest.IsolatedAsyncioTestCase):
    async def test_retries_when_ldplayer_recreates_an_empty_instance(self) -> None:
        """实测坑：remove 之后雷电会自动重建一个空实例，必须复核并再删一次。"""
        manager = FakeLDManager(
            [
                ["0", "1", "2"],  # 第一次 remove 后：2 号又回来了
                ["0", "1"],  # 第二次 remove 后：真的没了
            ]
        )

        with (
            patch(
                "app.utils.emulator2.ldplayer14.ProcessRunner.run_process",
                return_value=FakeResult(0),
            ) as runner,
            patch("app.utils.emulator2.ldplayer14.asyncio.sleep", _noop_sleep),
        ):
            await manager.delete_instance("2")

        self.assertEqual(runner.call_count, 2)

    async def test_gives_up_after_the_retry_budget(self) -> None:
        manager = FakeLDManager([["0", "1", "2"]])

        with (
            patch(
                "app.utils.emulator2.ldplayer14.ProcessRunner.run_process",
                return_value=FakeResult(0),
            ),
            patch("app.utils.emulator2.ldplayer14.asyncio.sleep", _noop_sleep),
        ):
            with self.assertRaises(RuntimeError):
                await manager.delete_instance("2")

    async def test_refuses_to_delete_a_running_instance(self) -> None:
        """删一台正在跑任务的设备是不可接受的，先要求关闭。"""
        manager = FakeLDManager([["0", "1", "2"]])
        manager._status = DeviceStatus.ONLINE

        with patch(
            "app.utils.emulator2.ldplayer14.ProcessRunner.run_process",
            return_value=FakeResult(0),
        ) as runner:
            with self.assertRaises(RuntimeError):
                await manager.delete_instance("2")

        runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
