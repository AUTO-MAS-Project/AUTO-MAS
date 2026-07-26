import asyncio
import io
import subprocess
import sys
import types
import xml.etree.ElementTree as ET
from datetime import datetime
import hashlib
import json
import os
import stat
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock, patch

from PIL import Image

from app.models.emulator import DeviceStatus
from app.plugins import uv_backend
from app.services.system import _SystemHandler
from app.utils.LogMonitor import LogMonitor

# OCR 的推理引擎是运行期可选依赖；本测试只覆盖 ADB/PNG 适配层。
if "rapidocr_onnxruntime" not in sys.modules:
    rapidocr_module = types.ModuleType("rapidocr_onnxruntime")
    rapidocr_module.RapidOCR = MagicMock
    sys.modules["rapidocr_onnxruntime"] = rapidocr_module

from app.utils.OCR.OCRtool import OCRTool, _CREATE_NO_WINDOW
from app.utils.emulator.general import GeneralDeviceManager
from scripts.plugin_tool import run_command

from app.services.update import (
    EmbeddedUpdaterManualOnlyError,
    EmbeddedUpdaterPolicyError,
    UpdateDigestUnavailableError,
    UpdateIntegrityError,
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
            with patch.object(Path, "cwd", return_value=Path(directory)), patch.object(
                handler,
                "_get_download_source",
                return_value="GitHub",
            ), patch(
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
    @staticmethod
    def _bind_job(handler: _UpdateHandler, root: Path, version: str) -> None:
        """模拟下载完成后绑定 job。"""
        handler._download_job_id = "test-job-id"
        handler._download_job_version = version
        handler._download_job_path = root / f"UpdatePack_{version}.zip"
        handler._download_job_expected_size = (
            handler._download_job_path.stat().st_size
        )

    async def test_install_update_extracts_to_staging_before_launch(self):
        handler = _UpdateHandler()

        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "UpdatePack_v6.0.1.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("AUTO-MAS-Setup.exe", b"installer")
                archive.writestr("changes.json", b"{}")

            self._bind_job(handler, root, "v6.0.1")

            with patch.object(Path, "cwd", return_value=root), patch.object(
                handler,
                "_get_download_source",
                return_value="GitHub",
            ), patch(
                "app.services.update.subprocess.Popen"
            ) as popen, patch(
                "app.services.update.ProcessRunner.run_process",
                new_callable=AsyncMock,
            ), patch(
                "app.services.update.System.set_power",
                new_callable=AsyncMock,
            ) as set_power, patch.object(
                handler, "_verify_package_integrity", new_callable=AsyncMock
            ) as verify:
                await handler.install_update()

            verify.assert_awaited_once()
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

            self._bind_job(handler, root, "v6.0.1")

            with patch.object(Path, "cwd", return_value=root), patch.object(
                handler,
                "_get_download_source",
                return_value="GitHub",
            ), patch(
                "app.services.update.subprocess.Popen"
            ) as popen, patch(
                "app.services.update.Publisher.send",
                new_callable=AsyncMock,
            ) as send, patch.object(
                handler, "_verify_package_integrity", new_callable=AsyncMock
            ) as verify:
                await handler.install_update()

            verify.assert_awaited_once()
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

            self._bind_job(handler, root, "v6.0.1")

            with patch.object(Path, "cwd", return_value=root), patch(
                "app.services.update.subprocess.Popen",
                side_effect=OSError("launch failed"),
            ), patch(
                "app.services.update.Publisher.send",
                new_callable=AsyncMock,
            ) as send, patch.object(
                handler, "_verify_package_integrity", new_callable=AsyncMock
            ) as verify:
                await handler.install_update()

            verify.assert_awaited_once()
            self.assertTrue(package.exists())
            self.assertEqual(
                list((root / ".auto-mas-update").glob("extract-*")),
                [],
            )
            self.assertFalse(handler.is_locked)
            self.assertEqual(send.await_args.kwargs["type"], "update.failed")
            self.assertIn("launch failed", send.await_args.kwargs["data"]["message"])

    async def test_install_without_job_binding_fails_before_any_io(self):
        """Lane 01：未绑定 job 时拒绝安装，不扫描目录。"""
        handler = _UpdateHandler()

        with TemporaryDirectory() as directory:
            root = Path(directory)
            # 放一个旧版本更新包，验证不会被扫描到
            old_package = root / "UpdatePack_v5.0.0.zip"
            with zipfile.ZipFile(old_package, "w") as archive:
                archive.writestr("AUTO-MAS-Setup.exe", b"old")

            with patch.object(Path, "cwd", return_value=root), patch.object(
                handler,
                "_get_download_source",
                return_value="GitHub",
            ), patch(
                "app.services.update.subprocess.Popen"
            ) as popen, patch(
                "app.services.update.Publisher.send",
                new_callable=AsyncMock,
            ) as send:
                await handler.install_update()

            popen.assert_not_called()
            self.assertTrue(old_package.exists())
            self.assertFalse(handler.is_locked)
            self.assertEqual(send.await_args.kwargs["type"], "update.failed")
            self.assertIn("未检测到绑定的下载任务", send.await_args.kwargs["data"]["message"])

    async def test_install_fails_closed_when_digest_unavailable(self):
        """Lane 01：无可用摘要时 fail closed，不安装。"""
        handler = _UpdateHandler()
        handler.remote_version = "v6.0.1"

        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "UpdatePack_v6.0.1.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("AUTO-MAS-Setup.exe", b"installer")

            self._bind_job(handler, root, "v6.0.1")

            with patch.object(Path, "cwd", return_value=root), patch.object(
                handler,
                "_get_download_source",
                return_value="GitHub",
            ), patch(
                "app.services.update.subprocess.Popen"
            ) as popen, patch(
                "app.services.update.Publisher.send",
                new_callable=AsyncMock,
            ) as send, patch.object(
                handler,
                "_fetch_trusted_digest",
                new_callable=AsyncMock,
                return_value=None,
            ):
                await handler.install_update()

            popen.assert_not_called()
            self.assertTrue(package.exists())
            self.assertFalse(handler.is_locked)
            # 验证发出了两次事件: verifying 和 failed
            self.assertGreaterEqual(send.await_count, 2)
            type_calls = [call.kwargs["type"] for call in send.call_args_list]
            self.assertIn("update.verifying", type_calls)
            self.assertIn("update.failed", type_calls)

    async def test_install_fails_on_digest_mismatch(self):
        """Lane 01：摘要不匹配时拒绝安装。"""
        handler = _UpdateHandler()
        handler.remote_version = "v6.0.1"

        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "UpdatePack_v6.0.1.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("AUTO-MAS-Setup.exe", b"installer")

            self._bind_job(handler, root, "v6.0.1")

            with patch.object(Path, "cwd", return_value=root), patch.object(
                handler,
                "_get_download_source",
                return_value="GitHub",
            ), patch(
                "app.services.update.subprocess.Popen"
            ) as popen, patch(
                "app.services.update.Publisher.send",
                new_callable=AsyncMock,
            ) as send, patch.object(
                handler,
                "_fetch_trusted_digest",
                new_callable=AsyncMock,
                return_value=("a" * 64, "sha256"),
            ):
                await handler.install_update()

            popen.assert_not_called()
            self.assertTrue(package.exists())
            self.assertFalse(handler.is_locked)
            type_calls = [call.kwargs["type"] for call in send.call_args_list]
            self.assertIn("update.verifying", type_calls)
            self.assertIn("update.failed", type_calls)

    async def test_install_emits_verifying_and_installing_events(self):
        """Lane 01：验证安装事件流：verifying → installing。"""
        handler = _UpdateHandler()
        handler.remote_version = "v6.0.1"

        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "UpdatePack_v6.0.1.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("AUTO-MAS-Setup.exe", b"installer")

            self._bind_job(handler, root, "v6.0.1")

            # 计算真实 SHA256 作为可信摘要
            actual_digest = hashlib.sha256(package.read_bytes()).hexdigest()

            with patch.object(Path, "cwd", return_value=root), patch.object(
                handler,
                "_get_download_source",
                return_value="GitHub",
            ), patch(
                "app.services.update.subprocess.Popen"
            ) as popen, patch(
                "app.services.update.ProcessRunner.run_process",
                new_callable=AsyncMock,
            ), patch(
                "app.services.update.System.set_power",
                new_callable=AsyncMock,
            ), patch(
                "app.services.update.Publisher.send",
                new_callable=AsyncMock,
            ) as send, patch.object(
                handler,
                "_fetch_trusted_digest",
                new_callable=AsyncMock,
                return_value=(actual_digest, "sha256"),
            ):
                await handler.install_update()

            type_calls = [call.kwargs["type"] for call in send.call_args_list]
            self.assertIn("update.verifying", type_calls)
            self.assertIn("update.installing", type_calls)
            self.assertNotIn("update.failed", type_calls)

    async def test_install_rejects_missing_installer(self):
        """Lane 01：更新包根目录缺少 AUTO-MAS-Setup.exe 时失败。"""
        handler = _UpdateHandler()

        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "UpdatePack_v6.0.1.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("some_other_file.txt", b"not an installer")

            self._bind_job(handler, root, "v6.0.1")

            with patch.object(Path, "cwd", return_value=root), patch(
                "app.services.update.subprocess.Popen"
            ) as popen, patch(
                "app.services.update.Publisher.send",
                new_callable=AsyncMock,
            ) as send, patch.object(
                handler, "_verify_package_integrity", new_callable=AsyncMock
            ) as verify:
                await handler.install_update()

            verify.assert_awaited_once()
            popen.assert_not_called()
            self.assertFalse(handler.is_locked)
            self.assertEqual(send.await_args.kwargs["type"], "update.failed")
            self.assertIn("缺少 AUTO-MAS-Setup.exe", send.await_args.kwargs["data"]["message"])

    async def test_concurrent_install_rejected(self):
        """Lane 01：并发安装请求被拒绝。"""
        handler = _UpdateHandler()
        handler.is_locked = True

        with patch(
            "app.services.update.Publisher.send",
            new_callable=AsyncMock,
        ) as send, patch.object(
            handler, "ensure_embedded_updater_available"
        ):
            await handler.install_update()

        self.assertEqual(send.await_args.kwargs["type"], "update.failed")
        self.assertIn("已有更新任务", send.await_args.kwargs["data"]["message"])


class UpdateHandlerDownloadJobTest(unittest.IsolatedAsyncioTestCase):
    """Lane 01：下载 job 绑定与完整性校验测试。"""

    async def test_download_sets_job_binding_on_success(self):
        """下载成功后绑定 job_id、version、path。"""
        handler = _UpdateHandler()
        handler.remote_version = "v6.0.1"

        with TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(Path, "cwd", return_value=root), patch.object(
                handler,
                "_get_download_source",
                return_value="GitHub",
            ), patch(
                "app.services.update.httpx.AsyncClient"
            ) as client:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.headers = {"content-length": "0"}

                aiter_bytes_mock = MagicMock()
                aiter_bytes_mock.__aiter__ = MagicMock(return_value=iter([]))
                mock_response.aiter_bytes = aiter_bytes_mock

                stream_ctx = AsyncMock()
                stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
                stream_ctx.__aexit__ = AsyncMock(return_value=None)

                client_ctx = AsyncMock()
                client_ctx.stream = MagicMock(return_value=stream_ctx)
                client_ctx.__aenter__ = AsyncMock(return_value=client_ctx)
                client_ctx.__aexit__ = AsyncMock(return_value=None)
                client.return_value = client_ctx

                with patch(
                    "app.services.update.Publisher.send",
                    new_callable=AsyncMock,
                ):
                    await handler._download_update_locked()

            self.assertIsNotNone(handler._download_job_id)
            self.assertEqual(handler._download_job_version, "v6.0.1")
            self.assertIsNotNone(handler._download_job_path)
            self.assertTrue(handler._download_job_path.is_file())

    async def test_download_validates_size_before_atomic_promotion(self):
        """Lane 01：下载大小与 Content-Length 不一致时抛异常。"""
        handler = _UpdateHandler()
        handler.remote_version = "v6.0.1"

        with TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(Path, "cwd", return_value=root), patch.object(
                handler,
                "_get_download_source",
                return_value="GitHub",
            ), patch(
                "app.services.update.httpx.AsyncClient"
            ) as client:
                mock_response = MagicMock()
                mock_response.status_code = 200
                # Content-Length 声明 100 字节，实际写入 0
                mock_response.headers = {"content-length": "100"}

                aiter_bytes_mock = MagicMock()
                aiter_bytes_mock.__aiter__ = MagicMock(return_value=iter([]))
                mock_response.aiter_bytes = aiter_bytes_mock

                stream_ctx = AsyncMock()
                stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
                stream_ctx.__aexit__ = AsyncMock(return_value=None)

                client_ctx = AsyncMock()
                client_ctx.stream = MagicMock(return_value=stream_ctx)
                client_ctx.__aenter__ = AsyncMock(return_value=client_ctx)
                client_ctx.__aexit__ = AsyncMock(return_value=None)
                client.return_value = client_ctx

                with patch(
                    "app.services.update.Publisher.send",
                    new_callable=AsyncMock,
                ) as send:
                    await handler._download_update_locked()

            self.assertIsNone(handler._download_job_id)
            self.assertEqual(send.await_args.kwargs["type"], "update.failed")
            self.assertIn("下载失败", send.await_args.kwargs["data"]["message"])

    async def test_compute_sha256_matches_known_value(self):
        """SHA256 计算与已知值一致。"""
        with TemporaryDirectory() as directory:
            test_file = Path(directory) / "test.bin"
            test_file.write_bytes(b"hello world")
            expected = hashlib.sha256(b"hello world").hexdigest()

            actual = _UpdateHandler._compute_sha256(test_file)
            self.assertEqual(actual, expected)

    async def test_cancel_download_clears_job_binding(self):
        """Lane 01：取消下载清除 job 绑定。"""
        handler = _UpdateHandler()
        handler._download_job_id = "stale-job"
        handler._download_job_version = "v9.9.9"
        handler._download_job_path = Path("/fake/path.zip")
        started = asyncio.Event()

        async def running_download():
            started.set()
            await asyncio.Event().wait()

        handler.download_task = asyncio.create_task(running_download())
        handler.is_locked = True
        await started.wait()

        cancelled = await handler.cancel_download(notify=False)

        self.assertTrue(cancelled)
        self.assertIsNone(handler._download_job_id)
        self.assertIsNone(handler._download_job_version)
        self.assertIsNone(handler._download_job_path)


class UpdateHandlerAuthenticityTest(unittest.IsolatedAsyncioTestCase):
    """Lane 01：真实性校验层测试。"""

    async def test_fetch_trusted_digest_returns_none_when_unavailable(self):
        """无法获取摘要时返回 None。"""
        handler = _UpdateHandler()

        with patch(
            "app.services.update.httpx.AsyncClient"
        ) as client:
            mock_response = MagicMock()
            mock_response.status_code = 404
            client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await handler._fetch_trusted_digest(
                "https://example.com/update.zip"
            )
            self.assertIsNone(result)

    async def test_fetch_trusted_digest_parses_sha256_format(self):
        """解析标准 sha256sum 格式。"""
        handler = _UpdateHandler()

        with patch(
            "app.services.update.httpx.AsyncClient"
        ) as client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = (
                "a" * 64 + "  AUTO-MAS-Lite-Setup-v6.0.1-x64.zip\n"
            )
            client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await handler._fetch_trusted_digest(
                "https://example.com/update.zip"
            )
            self.assertIsNotNone(result)
            self.assertEqual(result[0], "a" * 64)

    async def test_fetch_trusted_digest_parses_pure_hex(self):
        """解析纯十六进制摘要格式。"""
        handler = _UpdateHandler()

        with patch(
            "app.services.update.httpx.AsyncClient"
        ) as client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "f" * 64
            client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await handler._fetch_trusted_digest(
                "https://example.com/update.zip"
            )
            self.assertIsNotNone(result)
            self.assertEqual(result[0], "f" * 64)

    async def test_verify_package_integrity_raises_on_mismatch(self):
        """摘要不匹配时抛出 UpdateIntegrityError。"""
        handler = _UpdateHandler()

        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "test.zip"
            package.write_bytes(b"real content")

            handler._download_job_path = package
            handler._download_job_id = "test"
            handler._download_job_version = "v1.0"

            with patch.object(
                handler,
                "_get_download_source",
                return_value="GitHub",
            ), patch.object(
                handler,
                "_get_download_url",
                return_value="https://example.com/pkg.zip",
            ), patch.object(
                handler,
                "_fetch_trusted_digest",
                new_callable=AsyncMock,
                return_value=("0" * 64, "sha256"),
            ):
                with self.assertRaises(UpdateIntegrityError):
                    await handler._verify_package_integrity()

    async def test_verify_package_integrity_raises_when_no_digest(self):
        """无可用摘要时抛出 UpdateDigestUnavailableError。"""
        handler = _UpdateHandler()

        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "test.zip"
            package.write_bytes(b"content")

            handler._download_job_path = package
            handler._download_job_id = "test"
            handler._download_job_version = "v1.0"

            with patch.object(
                handler,
                "_get_download_source",
                return_value="GitHub",
            ), patch.object(
                handler,
                "_get_download_url",
                return_value="https://example.com/pkg.zip",
            ), patch.object(
                handler,
                "_fetch_trusted_digest",
                new_callable=AsyncMock,
                return_value=None,
            ):
                with self.assertRaises(UpdateDigestUnavailableError):
                    await handler._verify_package_integrity()

    async def test_verify_package_integrity_succeeds_on_match(self):
        """摘要匹配时通过校验。"""
        handler = _UpdateHandler()

        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "test.zip"
            content = b"test content for verification"
            package.write_bytes(content)
            expected_digest = hashlib.sha256(content).hexdigest()

            handler._download_job_path = package
            handler._download_job_id = "test"
            handler._download_job_version = "v1.0"

            with patch.object(
                handler,
                "_get_download_source",
                return_value="GitHub",
            ), patch.object(
                handler,
                "_get_download_url",
                return_value="https://example.com/pkg.zip",
            ), patch.object(
                handler,
                "_fetch_trusted_digest",
                new_callable=AsyncMock,
                return_value=(expected_digest, "sha256"),
            ):
                # 不应抛出异常
                await handler._verify_package_integrity()

    def test_validate_download_size_passes_on_match(self):
        """大小匹配时不抛异常。"""
        handler = _UpdateHandler()
        handler._validate_download_size(100, 100)

    def test_validate_download_size_raises_on_mismatch(self):
        """大小不匹配时抛异常。"""
        handler = _UpdateHandler()
        with self.assertRaises(UpdateIntegrityError):
            handler._validate_download_size(100, 200)

    def test_validate_download_size_ignores_zero_expected(self):
        """Content-Length 为 0 时跳过校验。"""
        handler = _UpdateHandler()
        handler._validate_download_size(100, 0)


class GeneralDeviceVisibilityTest(IsolatedAsyncioTestCase):
    async def test_set_visible_checks_main_hwnd_instead_of_pid(self) -> None:
        manager = GeneralDeviceManager.__new__(GeneralDeviceManager)
        manager.config = MagicMock()
        manager.config.get.return_value = 1
        manager.process_managers = {
            "0": SimpleNamespace(main_pid=1234, main_hwnd=5678),
        }
        manager.getStatus = AsyncMock(return_value=DeviceStatus.ONLINE)

        with patch(
            "app.utils.emulator.general.win32gui.IsWindowVisible",
            return_value=True,
        ) as is_window_visible, patch(
            "app.utils.emulator.general.keyboard.press_and_release"
        ) as press_and_release:
            status = await manager.setVisible("0", True)

        self.assertEqual(status, DeviceStatus.ONLINE)
        is_window_visible.assert_called_once_with(5678)
        press_and_release.assert_not_called()


class UpdateAtomicPromotionTest(IsolatedAsyncioTestCase):
    async def test_download_atomically_replaces_existing_target(self) -> None:
        payload = b"new update payload"

        class FakeResponse:
            status_code = 200
            headers = {"content-length": str(len(payload))}

            async def aiter_bytes(self, *, chunk_size: int):
                self.chunk_size = chunk_size
                yield payload

        class FakeStreamContext:
            async def __aenter__(self):
                return FakeResponse()

            async def __aexit__(self, exc_type, exc, traceback):
                return False

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return False

            def stream(self, method: str, url: str, *, timeout: float):
                self.request = (method, url, timeout)
                return FakeStreamContext()

        handler = _UpdateHandler()
        handler.remote_version = "v6.0.1"

        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            root = Path(directory)
            final_path = root / "UpdatePack_v6.0.1.zip"
            final_path.write_bytes(b"stale package")

            with patch.object(Path, "cwd", return_value=root), patch.object(
                handler,
                "ensure_embedded_updater_available",
            ), patch.object(
                handler,
                "_get_download_source",
                return_value="GitHub",
            ), patch.object(
                handler,
                "_get_download_url",
                return_value="https://example.com/update.zip",
            ), patch(
                "app.services.update.httpx.AsyncClient",
                return_value=FakeClient(),
            ), patch(
                "app.services.update.Publisher.send",
                new_callable=AsyncMock,
            ):
                await handler._download_update_locked()

            self.assertEqual(final_path.read_bytes(), payload)
            self.assertEqual(handler._download_job_path, final_path)
            self.assertFalse((root / "download.temp").exists())


class UvBackendWindowsTest(TestCase):
    def tearDown(self) -> None:
        uv_backend._uv_path = None

    def test_explicit_uv_environment_path_has_highest_priority(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            uv_path = Path(directory) / "custom uv.exe"
            uv_path.write_bytes(b"")
            with patch.dict(
                os.environ,
                {"AUTO_MAS_UV_EXE": f'  "{uv_path}"  '},
                clear=False,
            ), patch(
                "app.plugins.uv_backend.os.access",
                return_value=True,
            ), patch(
                "app.plugins.uv_backend.shutil.which",
                return_value="path-uv.exe",
            ):
                self.assertEqual(uv_backend._find_uv(), str(uv_path))

    def test_invalid_explicit_uv_path_falls_back_to_path(self) -> None:
        missing = Path("Z:/missing/uv.exe")
        with patch.dict(
            os.environ,
            {"AUTO_MAS_UV_EXE": str(missing)},
            clear=False,
        ), patch.object(
            Path,
            "cwd",
            return_value=Path("Z:/missing/app"),
        ), patch(
            "app.plugins.uv_backend.shutil.which",
            return_value="fallback-uv.exe",
        ):
            self.assertEqual(uv_backend._find_uv(), "fallback-uv.exe")

    def test_install_uv_decodes_output_as_utf8_with_replacement(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["powershell"],
            returncode=1,
            stdout="",
            stderr="安装失败",
        )
        with patch(
            "app.plugins.uv_backend._find_powershell",
            return_value="powershell.exe",
        ), patch(
            "app.plugins.uv_backend.subprocess.run",
            return_value=completed,
        ) as run:
            self.assertFalse(uv_backend.install_uv(Path("D:/uv-test")))

        self.assertEqual(run.call_args.kwargs["encoding"], "utf-8")
        self.assertEqual(run.call_args.kwargs["errors"], "replace")


class SystemSelfStartXmlTest(IsolatedAsyncioTestCase):
    async def test_self_start_xml_escapes_user_and_executable_path(self) -> None:
        captured: dict[str, str] = {}
        app_root = Path("D:/AUTO&MAS<test>\"quoted\"")
        current_user = "A&B<User>\"name\""

        async def capture_xml(*args: str):
            xml_path = Path(args[args.index("/xml") + 1])
            captured["xml"] = xml_path.read_text(encoding="utf-16")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with patch(
            "app.services.system.getpass.getuser",
            return_value=current_user,
        ), patch.object(
            Path,
            "cwd",
            return_value=app_root,
        ), patch(
            "app.services.system.ProcessRunner.run_process",
            new=AsyncMock(side_effect=capture_xml),
        ):
            await _SystemHandler().set_SelfStart(True)

        root = ET.fromstring(captured["xml"].encode("utf-16"))
        namespace = {"task": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
        author = root.find("task:RegistrationInfo/task:Author", namespace)
        command = root.find("task:Actions/task:Exec/task:Command", namespace)
        self.assertIsNotNone(author)
        self.assertIsNotNone(command)
        self.assertEqual(author.text, current_user)
        self.assertEqual(command.text, str(app_root / "AUTO-MAS.exe"))


class PluginToolEncodingTest(TestCase):
    def test_run_command_uses_utf8_replacement_decoding(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["uv"],
            returncode=0,
            stdout="完成",
            stderr="",
        )
        with patch(
            "scripts.plugin_tool.subprocess.run",
            return_value=completed,
        ) as run:
            result = run_command(["uv", "--version"], cwd=Path("D:/workspace"))

        self.assertTrue(result.ok)
        self.assertEqual(run.call_args.kwargs["encoding"], "utf-8")
        self.assertEqual(run.call_args.kwargs["errors"], "replace")


class OcrAdbWindowsTest(TestCase):
    def test_all_adb_subprocesses_hide_console_windows(self) -> None:
        connected = subprocess.CompletedProcess(
            args=["adb", "devices"],
            returncode=0,
            stdout=b"serial-1\tdevice\n",
            stderr=b"",
        )
        with patch(
            "app.utils.OCR.OCRtool.subprocess.run",
            return_value=connected,
        ) as run:
            OCRTool._ensure_adb_device_connected("adb.exe", "serial-1")
        self.assertEqual(run.call_args.kwargs["creationflags"], _CREATE_NO_WINDOW)

        disconnected = subprocess.CompletedProcess(
            args=["adb", "devices"],
            returncode=0,
            stdout=b"List of devices attached\n",
            stderr=b"",
        )
        connect_ok = subprocess.CompletedProcess(
            args=["adb", "connect"],
            returncode=0,
            stdout=b"connected to 127.0.0.1:5555",
            stderr=b"",
        )
        with patch(
            "app.utils.OCR.OCRtool.subprocess.run",
            side_effect=[disconnected, connect_ok],
        ) as run:
            OCRTool._ensure_adb_device_connected("adb.exe", "127.0.0.1:5555")
        self.assertTrue(
            all(call.kwargs["creationflags"] == _CREATE_NO_WINDOW for call in run.call_args_list)
        )

        raw_data = (
            (1).to_bytes(4, "little")
            + (1).to_bytes(4, "little")
            + (1).to_bytes(4, "little")
            + bytes((255, 0, 0, 255))
        )
        raw_result = subprocess.CompletedProcess(
            args=["adb", "screencap"],
            returncode=0,
            stdout=raw_data,
            stderr=b"",
        )
        with patch(
            "app.utils.OCR.OCRtool.subprocess.run",
            return_value=raw_result,
        ) as run:
            image = OCRTool._adb_screencap_raw("adb.exe", "serial-1")
        self.assertEqual(run.call_args.kwargs["creationflags"], _CREATE_NO_WINDOW)
        self.assertEqual(image.size, (1, 1))
        image.close()

    def test_png_decode_tries_original_bytes_before_crlf_compatibility(self) -> None:
        buffer = io.BytesIO()
        source = Image.new("RGB", (2, 1), (255, 0, 0))
        source.save(buffer, format="PNG")
        source.close()
        png_bytes = buffer.getvalue()
        self.assertIn(b"\r\n", png_bytes)

        result = subprocess.CompletedProcess(
            args=["adb", "screencap", "-p"],
            returncode=0,
            stdout=png_bytes,
            stderr=b"",
        )
        with patch(
            "app.utils.OCR.OCRtool.subprocess.run",
            return_value=result,
        ) as run, patch.object(
            OCRTool,
            "_adb_screencap_raw",
        ) as raw_fallback:
            image = OCRTool._adb_screencap_png("adb.exe", "serial-1")

        self.assertEqual(run.call_args.kwargs["creationflags"], _CREATE_NO_WINDOW)
        self.assertEqual(image.size, (2, 1))
        raw_fallback.assert_not_called()
        image.close()


class LogMonitorRotationTest(IsolatedAsyncioTestCase):
    async def test_stat_race_is_retried_instead_of_terminating_monitor(self) -> None:
        callback = AsyncMock()
        monitor = LogMonitor((0, 19), "%Y-%m-%d %H:%M:%S", callback)
        log_path = MagicMock(spec=Path)
        log_path.exists.return_value = True
        log_path.stat.side_effect = FileNotFoundError("rotated")

        with patch(
            "app.utils.LogMonitor.asyncio.sleep",
            new=AsyncMock(side_effect=asyncio.CancelledError),
        ) as sleep:
            with self.assertRaises(asyncio.CancelledError):
                await monitor.monitor_file(
                    log_path,
                    datetime.now(),
                )

        sleep.assert_awaited_once_with(1)
        callback.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
