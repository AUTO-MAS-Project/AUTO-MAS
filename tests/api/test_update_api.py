import unittest
from unittest.mock import AsyncMock, patch

from app.api.update import (
    Updater,
    cancel_update_download,
    download_update,
    switch_update_download_to_cnb,
)


class UpdateApiTest(unittest.IsolatedAsyncioTestCase):
    async def test_download_with_target_version_sets_remote_version_before_starting(self):
        original_version = Updater.remote_version
        try:
            with patch(
                "app.api.update.Updater.start_download", AsyncMock(return_value=True)
            ):
                result = await download_update(target_version="v9.9.9")

            self.assertEqual(result.code, 200)
            self.assertEqual(Updater.remote_version, "v9.9.9")
        finally:
            Updater.remote_version = original_version

    async def test_download_returns_conflict_when_download_already_running(self):
        original_version = Updater.remote_version
        try:
            with patch(
                "app.api.update.Updater.start_download", AsyncMock(return_value=False)
            ):
                result = await download_update(target_version="v9.9.9")

            self.assertEqual(result.code, 409)
            self.assertEqual(result.message, "已有更新任务在进行中, 请勿重复操作")
            self.assertEqual(Updater.remote_version, "v9.9.9")
        finally:
            Updater.remote_version = original_version

    async def test_cancel_returns_conflict_when_no_download_is_running(self):
        with patch(
            "app.api.update.Updater.cancel_download", AsyncMock(return_value=False)
        ):
            result = await cancel_update_download()
        self.assertEqual(result.code, 409)

    async def test_cancel_returns_success_when_download_cancelled(self):
        with patch(
            "app.api.update.Updater.cancel_download", AsyncMock(return_value=True)
        ):
            result = await cancel_update_download()
        self.assertEqual(result.code, 200)

    async def test_switch_to_cnb_returns_success_when_started(self):
        with patch(
            "app.api.update.Updater.switch_to_cnb", AsyncMock(return_value=True)
        ):
            result = await switch_update_download_to_cnb()
        self.assertEqual(result.code, 200)

    async def test_switch_to_cnb_returns_conflict_when_not_from_github(self):
        with patch(
            "app.api.update.Updater.switch_to_cnb", AsyncMock(return_value=False)
        ):
            result = await switch_update_download_to_cnb()
        self.assertEqual(result.code, 409)


if __name__ == "__main__":
    unittest.main()
