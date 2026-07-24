import asyncio
import json
import os
import stat
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.update import (
    EmbeddedUpdaterManualOnlyError,
    EmbeddedUpdaterPolicyError,
    _UpdateHandler,
)
from app.utils.archive import (
    ArchiveSafetyLimits,
    ArchiveValidationError,
    read_archive_safety_limits,
    safe_extract_zip,
)


class ArchiveSafetyLimitsTest(unittest.TestCase):
    def test_reads_release_validator_environment_names(self):
        limits = read_archive_safety_limits(
            {
                "AUTO_MAS_ARCHIVE_MAX_BYTES": "11",
                "AUTO_MAS_ARCHIVE_MAX_ENTRIES": "12",
                "AUTO_MAS_ARCHIVE_MAX_EXPANDED_BYTES": "13",
                "AUTO_MAS_ARCHIVE_MAX_FILE_BYTES": "14",
            }
        )

        self.assertEqual(limits.max_archive_bytes, 11)
        self.assertEqual(limits.max_entries, 12)
        self.assertEqual(limits.max_expanded_bytes, 13)
        self.assertEqual(limits.max_file_bytes, 14)

    def test_rejects_invalid_environment_limit(self):
        with self.assertRaisesRegex(ArchiveValidationError, "MAX_ENTRIES"):
            read_archive_safety_limits({"AUTO_MAS_ARCHIVE_MAX_ENTRIES": "0"})


class SafeExtractZipTest(unittest.TestCase):
    def test_extracts_valid_archive_into_new_destination(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            archive_path = root / "valid.zip"
            destination = root / "output"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("folder/", b"")
                archive.writestr("folder/payload.txt", b"payload")

            extracted = safe_extract_zip(archive_path, destination)

            self.assertEqual(
                extracted,
                [destination / "folder" / "payload.txt"],
            )
            self.assertEqual(
                (destination / "folder" / "payload.txt").read_bytes(),
                b"payload",
            )

    def test_rejects_unsafe_windows_paths_before_writing_destination(self):
        unsafe_names = (
            "../escape.txt",
            "folder\\..\\escape.txt",
            "/absolute.txt",
            "C:\\absolute.txt",
            "\\\\server\\share\\file.txt",
            "payload.txt:stream",
            "CON.txt",
            "folder./payload.txt",
        )

        for index, unsafe_name in enumerate(unsafe_names):
            with self.subTest(unsafe_name=unsafe_name), TemporaryDirectory() as directory:
                root = Path(directory)
                archive_path = root / f"unsafe-{index}.zip"
                destination = root / "output"
                with zipfile.ZipFile(archive_path, "w") as archive:
                    archive.writestr("safe.txt", b"safe")
                    archive.writestr(unsafe_name, b"unsafe")

                with self.assertRaises(ArchiveValidationError):
                    safe_extract_zip(archive_path, destination)

                self.assertFalse(os.path.lexists(destination))
                self.assertFalse((root / "safe.txt").exists())

    def test_rejects_symbolic_link(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            archive_path = root / "link.zip"
            destination = root / "output"
            link = zipfile.ZipInfo("link")
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr(link, "target")

            with self.assertRaisesRegex(ArchiveValidationError, "符号链接"):
                safe_extract_zip(archive_path, destination)

            self.assertFalse(os.path.lexists(destination))

    def test_rejects_case_insensitive_collision(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            archive_path = root / "collision.zip"
            destination = root / "output"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("Folder/Payload.txt", b"first")
                archive.writestr("folder/payload.TXT", b"second")

            with self.assertRaisesRegex(ArchiveValidationError, "大小写冲突"):
                safe_extract_zip(archive_path, destination)

            self.assertFalse(os.path.lexists(destination))

    def test_rejects_file_directory_collision(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            archive_path = root / "collision.zip"
            destination = root / "output"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("folder/payload.txt", b"payload")
                archive.writestr("folder", b"file")

            with self.assertRaisesRegex(ArchiveValidationError, "文件与目录"):
                safe_extract_zip(archive_path, destination)

            self.assertFalse(os.path.lexists(destination))

    def test_enforces_archive_resource_limits(self):
        cases = (
            (
                ArchiveSafetyLimits(
                    max_archive_bytes=1,
                    max_entries=10,
                    max_expanded_bytes=100,
                    max_file_bytes=100,
                ),
                "MAX_BYTES",
            ),
            (
                ArchiveSafetyLimits(
                    max_archive_bytes=10_000,
                    max_entries=1,
                    max_expanded_bytes=100,
                    max_file_bytes=100,
                ),
                "MAX_ENTRIES",
            ),
            (
                ArchiveSafetyLimits(
                    max_archive_bytes=10_000,
                    max_entries=10,
                    max_expanded_bytes=5,
                    max_file_bytes=100,
                ),
                "MAX_EXPANDED_BYTES",
            ),
            (
                ArchiveSafetyLimits(
                    max_archive_bytes=10_000,
                    max_entries=10,
                    max_expanded_bytes=100,
                    max_file_bytes=5,
                ),
                "MAX_FILE_BYTES",
            ),
        )

        for index, (limits, expected_message) in enumerate(cases):
            with self.subTest(
                expected_message=expected_message
            ), TemporaryDirectory() as directory:
                root = Path(directory)
                archive_path = root / f"limits-{index}.zip"
                destination = root / "output"
                with zipfile.ZipFile(archive_path, "w") as archive:
                    archive.writestr("first.txt", b"123456")
                    archive.writestr("second.txt", b"abcdef")

                with self.assertRaisesRegex(
                    ArchiveValidationError,
                    expected_message,
                ):
                    safe_extract_zip(
                        archive_path,
                        destination,
                        limits=limits,
                    )

                self.assertFalse(os.path.lexists(destination))

    def test_failed_extraction_never_publishes_partial_destination(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            archive_path = root / "broken.zip"
            destination = root / "output"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("first.txt", b"first")
                archive.writestr("second.txt", b"second")

            original_open = zipfile.ZipFile.open
            calls = 0

            def fail_second_member(archive, name, *args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("simulated extraction failure")
                return original_open(archive, name, *args, **kwargs)

            with patch.object(zipfile.ZipFile, "open", fail_second_member):
                with self.assertRaisesRegex(OSError, "simulated"):
                    safe_extract_zip(archive_path, destination)

            self.assertFalse(os.path.lexists(destination))
            self.assertEqual(
                list(root.glob(f".{destination.name}.extract-*")),
                [],
            )

    def test_rejects_existing_destination_without_modifying_it(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            archive_path = root / "valid.zip"
            destination = root / "output"
            destination.mkdir()
            marker = destination / "marker.txt"
            marker.write_text("keep", encoding="utf-8")
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("payload.txt", b"payload")

            with self.assertRaises(FileExistsError):
                safe_extract_zip(archive_path, destination)

            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")


class EmbeddedUpdaterPolicyTest(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _write_snapshot(root: Path, release_policy: object) -> None:
        snapshot_path = root / "res" / "integration-snapshot.json"
        snapshot_path.parent.mkdir(parents=True)
        snapshot_path.write_text(
            json.dumps({"release_policy": release_policy}), encoding="utf-8"
        )

    async def _assert_all_update_entrypoints_blocked(
        self, handler: _UpdateHandler, expected_error: type[RuntimeError]
    ) -> None:
        with patch.object(handler, "_start_download_task") as start_task, patch(
            "app.services.update.Config.get"
        ) as get_config, patch("app.services.update.Config.set", new_callable=AsyncMock) as set_config, patch(
            "app.services.update.httpx.AsyncClient"
        ) as http_client, patch(
            "app.services.update.Publisher.send", new_callable=AsyncMock
        ) as publish, patch("app.services.update.subprocess.Popen") as popen, patch(
            "app.services.update.ProcessRunner.run_process", new_callable=AsyncMock
        ) as run_process, patch(
            "app.services.update.System.set_power", new_callable=AsyncMock
        ) as set_power:
            with self.assertRaises(expected_error):
                await handler.check_update("v6.0.0-alpha")
            with self.assertRaises(expected_error):
                await handler.start_download()
            with self.assertRaises(expected_error):
                await handler.switch_to_cnb()
            with self.assertRaises(expected_error):
                await handler.download_update()
            with self.assertRaises(expected_error):
                await handler.install_update()

        get_config.assert_not_called()
        set_config.assert_not_awaited()
        http_client.assert_not_called()
        start_task.assert_not_called()
        publish.assert_not_awaited()
        popen.assert_not_called()
        run_process.assert_not_awaited()
        set_power.assert_not_awaited()

    async def test_alpha_policy_blocks_all_update_entrypoints_before_side_effects(self):
        handler = _UpdateHandler()

        with TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_snapshot(
                root,
                {
                    "channel": "experimental-alpha",
                    "embedded_updater": "manual-only",
                },
            )

            with patch.object(Path, "cwd", return_value=root), patch.dict(
                "app.services.update.os.environ", {}, clear=True
            ):
                await self._assert_all_update_entrypoints_blocked(
                    handler, EmbeddedUpdaterManualOnlyError
                )

    async def test_invalid_snapshot_policy_blocks_all_entrypoints_before_side_effects(self):
        handler = _UpdateHandler()

        with TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot_path = root / "res" / "integration-snapshot.json"
            snapshot_path.parent.mkdir(parents=True)
            snapshot_path.write_text("{invalid", encoding="utf-8")

            with patch.object(Path, "cwd", return_value=root), patch.dict(
                "app.services.update.os.environ", {}, clear=True
            ):
                await self._assert_all_update_entrypoints_blocked(
                    handler, EmbeddedUpdaterPolicyError
                )

    async def test_alpha_environment_without_snapshot_still_blocks_download_start(self):
        handler = _UpdateHandler()

        with TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(Path, "cwd", return_value=root), patch.dict(
                "app.services.update.os.environ",
                {"AUTO_MAS_RELEASE_CHANNEL": "experimental-alpha"},
                clear=True,
            ):
                await self._assert_all_update_entrypoints_blocked(
                    handler, EmbeddedUpdaterManualOnlyError
                )

    async def test_environment_manual_policy_and_alpha_conflict_fail_closed(self):
        handler = _UpdateHandler()

        cases = (
            (
                {"AUTO_MAS_EMBEDDED_UPDATE_POLICY": "manual-only"},
                EmbeddedUpdaterManualOnlyError,
            ),
            (
                {
                    "AUTO_MAS_RELEASE_CHANNEL": "experimental-alpha",
                    "AUTO_MAS_EMBEDDED_UPDATE_POLICY": "enabled",
                },
                EmbeddedUpdaterPolicyError,
            ),
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for environment, expected_error in cases:
                with self.subTest(environment=environment), patch.object(
                    Path, "cwd", return_value=root
                ), patch.dict(
                    "app.services.update.os.environ", environment, clear=True
                ), patch.object(handler, "_start_download_task") as start_task:
                    with self.assertRaises(expected_error):
                        await handler.start_download()
                    start_task.assert_not_called()

    async def test_non_alpha_runtime_keeps_existing_download_start_behavior(self):
        handler = _UpdateHandler()

        with TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(Path, "cwd", return_value=root), patch.dict(
                "app.services.update.os.environ", {}, clear=True
            ), patch.object(
                handler, "_start_download_task", return_value=True
            ) as start_task:
                self.assertTrue(await handler.start_download())

            start_task.assert_called_once_with()


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
        with TemporaryDirectory() as directory:
            with patch.object(Path, "cwd", return_value=Path(directory)), patch(
                "app.services.update.httpx.AsyncClient"
            ) as client:
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

        with TemporaryDirectory() as directory:
            with patch.object(Path, "cwd", return_value=Path(directory)), patch.object(
                type(handler), "_get_download_source", return_value="GitHub"
            ), patch(
                "app.services.update.Config.set", new_callable=AsyncMock
            ) as set_config:
                switched = await handler.switch_to_cnb()

        self.assertTrue(switched)
        handler.cancel_download.assert_awaited_once_with(notify=False)
        set_config.assert_awaited_once_with("Update", "Source", "CNB")
        handler._start_download_task.assert_called_once_with()

    async def test_switch_to_cnb_does_not_restart_when_config_save_fails(self):
        handler = _UpdateHandler()
        handler.download_task = MagicMock()
        handler.download_task.done.return_value = False
        handler.cancel_download = AsyncMock(return_value=True)
        handler._start_download_task = MagicMock()

        with TemporaryDirectory() as directory:
            with patch.object(Path, "cwd", return_value=Path(directory)), patch.object(
                type(handler), "_get_download_source", return_value="GitHub"
            ), patch(
                "app.services.update.Config.set",
                new_callable=AsyncMock,
                side_effect=RuntimeError("save failed"),
            ), patch(
                "app.services.update.Publisher.send",
                new_callable=AsyncMock,
            ) as send:
                with self.assertRaisesRegex(RuntimeError, "save failed"):
                    await handler.switch_to_cnb()

        handler._start_download_task.assert_not_called()
        self.assertEqual(send.await_args.kwargs["type"], "update.failed")
        self.assertIn("save failed", send.await_args.kwargs["data"]["message"])

    async def test_cancel_download_publishes_canonical_cancel_event(self):
        handler = _UpdateHandler()
        started = asyncio.Event()

        async def running_download():
            started.set()
            await asyncio.Event().wait()

        handler.download_task = asyncio.create_task(running_download())
        await started.wait()

        with patch(
            "app.services.update.Publisher.send", new_callable=AsyncMock
        ) as send:
            cancelled = await handler.cancel_download()

        self.assertTrue(cancelled)
        send.assert_awaited_once_with(id="Update", type="update.cancelled")


class UpdateHandlerInstallTest(unittest.IsolatedAsyncioTestCase):
    async def test_install_update_extracts_to_staging_before_launch(self):
        handler = _UpdateHandler()

        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "UpdatePack_v6.0.1.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("AUTO-MAS-Setup.exe", b"installer")
                archive.writestr("changes.json", b"{}")

            with patch.object(Path, "cwd", return_value=root), patch(
                "app.services.update.subprocess.Popen"
            ) as popen, patch(
                "app.services.update.ProcessRunner.run_process",
                new_callable=AsyncMock,
            ), patch(
                "app.services.update.System.set_power",
                new_callable=AsyncMock,
            ) as set_power:
                await handler.install_update()

            installer_path = Path(popen.call_args.args[0][0])
            self.assertEqual(installer_path.name, "AUTO-MAS-Setup.exe")
            self.assertNotEqual(installer_path.parent, root)
            self.assertEqual(popen.call_args.kwargs["cwd"], installer_path.parent)
            self.assertTrue(installer_path.is_file())
            self.assertFalse((root / "AUTO-MAS-Setup.exe").exists())
            self.assertFalse((root / "changes.json").exists())
            self.assertFalse(package.exists())
            self.assertFalse(handler.is_locked)
            set_power.assert_awaited_once_with("KillSelf")

    async def test_install_update_rejects_unsafe_archive_without_partial_write(self):
        handler = _UpdateHandler()

        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "UpdatePack_v6.0.1.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("AUTO-MAS-Setup.exe", b"installer")
                archive.writestr("../escape.txt", b"unsafe")

            with patch.object(Path, "cwd", return_value=root), patch(
                "app.services.update.subprocess.Popen"
            ) as popen, patch(
                "app.services.update.Publisher.send",
                new_callable=AsyncMock,
            ) as send:
                await handler.install_update()

            popen.assert_not_called()
            self.assertTrue(package.exists())
            self.assertFalse((root / "AUTO-MAS-Setup.exe").exists())
            self.assertFalse((root / ".auto-mas-update").exists())
            self.assertFalse(handler.is_locked)
            self.assertEqual(send.await_args.kwargs["type"], "update.failed")
            self.assertIn("不安全路径", send.await_args.kwargs["data"]["message"])

    async def test_install_update_keeps_package_when_installer_launch_fails(self):
        handler = _UpdateHandler()

        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "UpdatePack_v6.0.1.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("AUTO-MAS-Setup.exe", b"installer")

            with patch.object(Path, "cwd", return_value=root), patch(
                "app.services.update.subprocess.Popen",
                side_effect=OSError("launch failed"),
            ), patch(
                "app.services.update.Publisher.send",
                new_callable=AsyncMock,
            ) as send:
                await handler.install_update()

            self.assertTrue(package.exists())
            self.assertEqual(
                list((root / ".auto-mas-update").glob("extract-*")),
                [],
            )
            self.assertFalse(handler.is_locked)
            self.assertEqual(send.await_args.kwargs["type"], "update.failed")
            self.assertIn("launch failed", send.await_args.kwargs["data"]["message"])


if __name__ == "__main__":
    unittest.main()
