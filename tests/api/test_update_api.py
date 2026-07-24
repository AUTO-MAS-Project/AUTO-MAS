import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

from app.api.update import (
    Updater,
    cancel_update_download,
    check_update,
    download_update,
    install_update,
    switch_update_download_to_cnb,
)
from app.models.schema import UpdateCheckIn


class UpdateApiTest(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _write_alpha_snapshot(root: Path) -> None:
        snapshot_path = root / "res" / "integration-snapshot.json"
        snapshot_path.parent.mkdir(parents=True)
        snapshot_path.write_text(
            json.dumps(
                {
                    "release_policy": {
                        "channel": "experimental-alpha",
                        "embedded_updater": "manual-only",
                    }
                }
            ),
            encoding="utf-8",
        )

    async def test_download_with_target_version_sets_remote_version_before_starting(self):
        original_version = Updater.remote_version
        try:
            with patch(
                "app.api.update.Updater.start_download", AsyncMock(return_value=True)
            ), patch(
                "app.api.update.Updater.ensure_embedded_updater_available"
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
            ), patch(
                "app.api.update.Updater.ensure_embedded_updater_available"
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

    async def test_alpha_check_returns_manual_conflict_with_complete_payload(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_alpha_snapshot(root)
            with patch("app.services.update.Path.cwd", return_value=root), patch(
                "app.services.update.Config.get"
            ) as get_config, patch("app.services.update.httpx.AsyncClient") as http_client:
                result = await check_update(
                    UpdateCheckIn(current_version="v6.0.0-alpha", if_force=True)
                )

        self.assertEqual(result.code, 409)
        self.assertEqual(result.status, "manual")
        self.assertFalse(result.if_need_update)
        self.assertEqual(result.latest_version, "v6.0.0-alpha")
        self.assertEqual(result.update_info, {})
        self.assertIn("手动下载", result.message)
        get_config.assert_not_called()
        http_client.assert_not_called()

    async def test_alpha_action_endpoints_return_manual_without_starting_work(self):
        original_version = Updater.remote_version
        try:
            Updater.remote_version = "unchanged"
            with TemporaryDirectory() as directory:
                root = Path(directory)
                self._write_alpha_snapshot(root)
                with patch("app.services.update.Path.cwd", return_value=root), patch(
                    "app.services.update.Config.get"
                ) as get_config, patch(
                    "app.api.update.asyncio.create_task"
                ) as create_task:
                    download_result = await download_update(target_version="v9.9.9")
                    switch_result = await switch_update_download_to_cnb()
                    install_result = await install_update()

            for result in (download_result, switch_result, install_result):
                self.assertEqual(result.code, 409)
                self.assertEqual(result.status, "manual")
                self.assertIn("手动下载", result.message)
            self.assertEqual(Updater.remote_version, "unchanged")
            get_config.assert_not_called()
            create_task.assert_not_called()
        finally:
            Updater.remote_version = original_version


if __name__ == "__main__":
    unittest.main()
