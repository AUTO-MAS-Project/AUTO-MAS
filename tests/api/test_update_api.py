import unittest
from unittest.mock import AsyncMock, patch

from app.api.update import cancel_update_download, switch_update_download_to_cnb


class UpdateApiTest(unittest.IsolatedAsyncioTestCase):
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
