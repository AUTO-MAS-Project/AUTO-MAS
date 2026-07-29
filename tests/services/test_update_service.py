import asyncio
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.update import _UpdateHandler


class UpdateHandlerTest(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_download_stops_task_and_removes_temp_file(self):
        handler = _UpdateHandler()
        started = asyncio.Event()

        async def running_download():
            started.set()
            await asyncio.Event().wait()

        with TemporaryDirectory() as directory, patch.object(
            Path, "cwd", return_value=Path(directory)
        ):
            temp_file = Path(directory) / "download.temp"
            temp_file.write_bytes(b"partial")
            handler.download_task = asyncio.create_task(running_download())
            handler.is_locked = True
            await started.wait()

            cancelled = await handler.cancel_download(notify=False)

            self.assertTrue(cancelled)
            self.assertTrue(handler.download_task.done())
            self.assertFalse(temp_file.exists())
            self.assertFalse(handler.is_locked)

    async def test_cancel_download_fails_when_temp_file_cleanup_fails(self):
        handler = _UpdateHandler()
        started = asyncio.Event()

        async def running_download():
            started.set()
            await asyncio.Event().wait()

        handler.download_task = asyncio.create_task(running_download())
        handler.is_locked = True
        await started.wait()

        with patch.object(
            handler,
            "_cleanup_download",
            side_effect=RuntimeError("cleanup failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "cleanup failed"):
                await handler.cancel_download(notify=False)

    async def test_cancelled_error_does_not_enter_retry_failure_path(self):
        handler = _UpdateHandler()
        handler.remote_version = "v9.9.9"
        with patch("app.services.update.httpx.AsyncClient") as client:
            client.return_value.__aenter__.side_effect = asyncio.CancelledError
            with self.assertRaises(asyncio.CancelledError):
                await handler.download_update()

    async def test_get_download_source_returns_selected_source(self):
        handler = _UpdateHandler()
        handler.remote_version = "v9.9.9"
        with patch.object(
            type(handler), "_get_download_source", return_value="GitHub"
        ):
            self.assertEqual(handler._get_download_source(), "GitHub")


class UpdateHandlerSwitchTest(unittest.IsolatedAsyncioTestCase):
    async def test_switch_to_cnb_cancels_saves_config_and_restarts(self):
        handler = _UpdateHandler()
        handler.download_task = MagicMock()
        handler.download_task.done.return_value = False
        handler.cancel_download = AsyncMock(return_value=True)
        handler._start_download_task = MagicMock(return_value=True)

        with patch.object(
            type(handler), "_get_download_source", return_value="GitHub"
        ), patch("app.services.update.Config.set", new_callable=AsyncMock) as set_config:
            switched = await handler.switch_to_cnb()

        self.assertTrue(switched)
        handler.cancel_download.assert_awaited_once_with(notify=False)
        set_config.assert_awaited_once_with("Update", "Source", "CNB")
        handler._start_download_task.assert_called_once()
        restart_job = handler._start_download_task.call_args.kwargs["job"]
        self.assertEqual(restart_job.source, "GitHub")
        self.assertIsNone(restart_job.version)

    async def test_switch_to_cnb_does_not_restart_when_config_save_fails(self):
        handler = _UpdateHandler()
        handler.download_task = MagicMock()
        handler.download_task.done.return_value = False
        handler.cancel_download = AsyncMock(return_value=True)
        handler._start_download_task = MagicMock()

        with patch.object(
            type(handler), "_get_download_source", return_value="GitHub"
        ), patch(
            "app.services.update.Config.set",
            new_callable=AsyncMock,
            side_effect=RuntimeError("save failed"),
        ), patch(
            "app.services.update.Publisher.send",
            new_callable=AsyncMock,
        ):
            with self.assertRaisesRegex(RuntimeError, "save failed"):
                await handler.switch_to_cnb()

        handler._start_download_task.assert_not_called()


if __name__ == "__main__":
    unittest.main()
