import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import app.api.core as core_api
from app.core.ws import protocol


class CoreCloseTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        core_api._shutdown_task = None

    async def test_close_runs_full_teardown_then_notifies_frontend(self):
        server = MagicMock()
        server.should_exit = False

        with patch.object(
            core_api.ShutdownCoordinator, "run_teardown", new_callable=AsyncMock
        ) as teardown, patch(
            "app.api.core.Publisher.send", new_callable=AsyncMock
        ) as send, patch.object(
            core_api.Config, "server", server
        ), patch.object(core_api, "is_backend_dev_mode", return_value=False):
            result = await core_api.close()
            assert core_api._shutdown_task is not None
            await asyncio.wait_for(core_api._shutdown_task, timeout=1)

        self.assertEqual(result.code, 200)
        # 完整清理先于 ready 通知
        teardown.assert_awaited_once()
        send.assert_awaited_once()
        self.assertEqual(send.await_args.kwargs["id"], protocol.ID_MAIN)
        self.assertEqual(send.await_args.kwargs["type"], protocol.BACKEND_SHUTDOWN_READY)
        self.assertTrue(server.should_exit)

    async def test_teardown_failure_skips_ready_and_exit(self):
        server = MagicMock()
        server.should_exit = False

        with patch.object(
            core_api.ShutdownCoordinator,
            "run_teardown",
            new_callable=AsyncMock,
            side_effect=RuntimeError("teardown failed"),
        ), patch(
            "app.api.core.Publisher.send", new_callable=AsyncMock
        ) as send, patch.object(
            core_api.Config, "server", server
        ), patch.object(core_api, "is_backend_dev_mode", return_value=False):
            await core_api.close()
            assert core_api._shutdown_task is not None
            await asyncio.wait_for(core_api._shutdown_task, timeout=1)

        # 清理失败：不发送 ready、不置退出标志，避免前端在清理未完成时强制关闭
        send.assert_not_awaited()
        self.assertFalse(server.should_exit)

    async def test_close_is_idempotent_while_running(self):
        started = asyncio.Event()
        release = asyncio.Event()

        async def slow_shutdown():
            started.set()
            await release.wait()

        with patch.object(core_api, "_shutdown_backend", side_effect=slow_shutdown):
            first = await core_api.close()
            await started.wait()
            second = await core_api.close()
            release.set()
            assert core_api._shutdown_task is not None
            await asyncio.wait_for(core_api._shutdown_task, timeout=1)

        self.assertEqual(first.code, 200)
        self.assertEqual(second.message, "关闭流程已在进行中")

    async def test_dev_mode_sends_ready_but_keeps_running(self):
        server = MagicMock()
        server.should_exit = False

        with patch.object(
            core_api.ShutdownCoordinator, "run_teardown", new_callable=AsyncMock
        ), patch(
            "app.api.core.Publisher.send", new_callable=AsyncMock
        ) as send, patch.object(
            core_api.Config, "server", server
        ), patch.object(core_api, "is_backend_dev_mode", return_value=True):
            await core_api.close()
            assert core_api._shutdown_task is not None
            await asyncio.wait_for(core_api._shutdown_task, timeout=1)

        send.assert_awaited_once()
        self.assertFalse(server.should_exit)


if __name__ == "__main__":
    unittest.main()
