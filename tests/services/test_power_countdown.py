import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from app.core.ws import protocol
from app.services.system import System


class PowerCountdownTest(unittest.IsolatedAsyncioTestCase):
    async def test_power_task_publishes_countdown_each_second(self):
        sleeps: list[float] = []

        async def fake_sleep(seconds: float):
            sleeps.append(seconds)

        with (
            patch("app.services.system.Publisher.send", new_callable=AsyncMock) as send,
            patch.object(System, "countdown", 3),
            patch.object(System, "set_power", new_callable=AsyncMock) as set_power,
            patch("app.services.system.asyncio.sleep", side_effect=fake_sleep),
        ):
            await System._power_task("Shutdown")

        self.assertEqual(len(sleeps), 3)
        remaining_values = [
            call.kwargs["data"].remaining for call in send.await_args_list
        ]
        self.assertEqual(remaining_values, [3, 2, 1])
        for call in send.await_args_list:
            self.assertEqual(call.kwargs["id"], protocol.ID_MAIN)
            self.assertEqual(call.kwargs["type"], protocol.POWER_COUNTDOWN_UPDATED)
            self.assertEqual(call.kwargs["data"].operation, "Shutdown")
        set_power.assert_awaited_once_with("Shutdown")

    async def test_cancel_power_task_publishes_cancelled(self):
        with patch(
            "app.services.system.Publisher.send", new_callable=AsyncMock
        ) as send:
            System.power_task = asyncio.create_task(asyncio.sleep(60))
            await asyncio.sleep(0.01)

            await System.cancel_power_task()

        send.assert_awaited_once()
        self.assertEqual(send.await_args.kwargs["id"], protocol.ID_MAIN)
        self.assertEqual(
            send.await_args.kwargs["type"], protocol.POWER_COUNTDOWN_CANCELLED
        )

    async def test_cancel_power_task_raises_when_no_task(self):
        System.power_task = None
        with patch(
            "app.services.system.Publisher.send", new_callable=AsyncMock
        ) as send:
            with self.assertRaises(RuntimeError):
                await System.cancel_power_task()
        send.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
