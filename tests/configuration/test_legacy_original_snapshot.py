from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.configuration.compat import legacy_original_snapshot as snapshot_module
from app.configuration.compat.legacy_original_snapshot import (
    LEGACY_ROOT_FILE_NAMES,
    LegacyDataUpgradeRequiredError,
    LegacyOriginalSnapshotError,
    LegacyOriginalSnapshotPermissionError,
    ensure_legacy_original_snapshot,
)


class LegacyOriginalSnapshotTest(unittest.TestCase):
    def test_pre_v111_data_fails_before_creating_immutable_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_dir = root / "config"
            config_dir.mkdir()
            (config_dir / "Config.json").write_text("{}", encoding="utf-8")
            data_dir = root / "data"
            data_dir.mkdir()
            with closing(sqlite3.connect(data_dir / "data.db")) as database:
                database.execute("CREATE TABLE version(v text)")
                database.execute("INSERT INTO version VALUES(?)", ("v1.7",))
                database.commit()

            with self.assertRaisesRegex(
                LegacyDataUpgradeRequiredError,
                r"v1\.7.*Config\.check_data",
            ):
                ensure_legacy_original_snapshot(config_dir)

            self.assertFalse((config_dir / ".config-v2-original").exists())

    def test_v111_data_allows_immutable_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_dir = root / "config"
            config_dir.mkdir()
            data_dir = root / "data"
            data_dir.mkdir()
            with closing(sqlite3.connect(data_dir / "data.db")) as database:
                database.execute("CREATE TABLE version(v text)")
                database.execute("INSERT INTO version VALUES(?)", ("v1.11",))
                database.commit()

            snapshot = ensure_legacy_original_snapshot(config_dir)

            self.assertTrue(snapshot.created)

    def test_snapshot_preserves_root_order_and_opaque_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"
            config_dir.mkdir()
            expected: dict[str, bytes] = {}
            for index, name in enumerate(LEGACY_ROOT_FILE_NAMES):
                content = f'{{"root":{index},"secret":"opaque-{index}"}}\r\n'.encode()
                expected[name] = content
                (config_dir / name).write_bytes(content)

            snapshot = ensure_legacy_original_snapshot(config_dir)
            manifest = json.loads(snapshot.manifest_path.read_text(encoding="utf-8"))

            self.assertTrue(snapshot.created)
            self.assertEqual(
                [record["name"] for record in manifest["roots"]],
                list(LEGACY_ROOT_FILE_NAMES),
            )
            for record in manifest["roots"]:
                name = record["name"]
                self.assertEqual(
                    (snapshot.generation_path / "files" / name).read_bytes(),
                    expected[name],
                )
                self.assertEqual(
                    record["sha256"],
                    hashlib.sha256(expected[name]).hexdigest(),
                )
            self.assertNotIn(
                "opaque-",
                snapshot.manifest_path.read_text(encoding="utf-8"),
            )

    def test_second_call_reuses_first_generation_after_legacy_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"
            config_dir.mkdir()
            root_path = config_dir / "Config.json"
            root_path.write_bytes(b'{"value":"original"}')

            first = ensure_legacy_original_snapshot(config_dir)
            root_path.write_bytes(b'{"value":"normalized-later"}')
            second = ensure_legacy_original_snapshot(config_dir)

            self.assertFalse(second.created)
            self.assertEqual(second.generation, first.generation)
            self.assertEqual(
                (second.generation_path / "files" / "Config.json").read_bytes(),
                b'{"value":"original"}',
            )
            generations = [
                path
                for path in (
                    config_dir / ".config-v2-original" / "generations"
                ).iterdir()
                if not path.name.startswith(".")
            ]
            self.assertEqual(generations, [first.generation_path])

    def test_valid_orphan_generation_recovers_missing_current(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"
            first = ensure_legacy_original_snapshot(config_dir)
            current_path = config_dir / ".config-v2-original" / "CURRENT"
            current_path.unlink()

            recovered = ensure_legacy_original_snapshot(config_dir)

            self.assertFalse(recovered.created)
            self.assertEqual(recovered.generation, first.generation)
            self.assertTrue(current_path.is_file())
            self.assertEqual(
                json.loads(current_path.read_text(encoding="utf-8"))["generation"],
                first.generation,
            )

    def test_missing_roots_are_explicit_without_placeholder_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"

            snapshot = ensure_legacy_original_snapshot(config_dir)
            manifest = json.loads(snapshot.manifest_path.read_text(encoding="utf-8"))

            self.assertEqual(
                [record["name"] for record in manifest["roots"]],
                list(LEGACY_ROOT_FILE_NAMES),
            )
            self.assertTrue(
                all(record["exists"] is False for record in manifest["roots"])
            )
            self.assertTrue(
                all(
                    record[field] is None
                    for record in manifest["roots"]
                    for field in ("sha256", "size_bytes", "mtime_ns", "snapshot")
                )
            )
            self.assertEqual(
                list((snapshot.generation_path / "files").iterdir()),
                [],
            )

    def test_capture_does_not_change_original_hash_or_mtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"
            config_dir.mkdir()
            root_path = config_dir / "ScriptConfig.json"
            content = b"\xef\xbb\xbf{\"preserve\":\"bytes\"}\r\n"
            root_path.write_bytes(content)
            os.utime(root_path, ns=(1_700_000_000_000_000_000,) * 2)
            before = root_path.stat()
            before_hash = hashlib.sha256(root_path.read_bytes()).hexdigest()

            snapshot = ensure_legacy_original_snapshot(config_dir)

            after = root_path.stat()
            self.assertEqual(
                hashlib.sha256(root_path.read_bytes()).hexdigest(),
                before_hash,
            )
            self.assertEqual(after.st_mtime_ns, before.st_mtime_ns)
            record = next(
                record
                for record in json.loads(
                    snapshot.manifest_path.read_text(encoding="utf-8")
                )["roots"]
                if record["name"] == root_path.name
            )
            self.assertEqual(record["mtime_ns"], before.st_mtime_ns)
            self.assertEqual(record["size_bytes"], len(content))

    def test_corrupted_current_fails_closed_without_new_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"
            first = ensure_legacy_original_snapshot(config_dir)
            current_path = config_dir / ".config-v2-original" / "CURRENT"
            current_path.write_text("../other-generation", encoding="utf-8")

            with self.assertRaisesRegex(LegacyOriginalSnapshotError, "CURRENT"):
                ensure_legacy_original_snapshot(config_dir)

            self.assertTrue(first.generation_path.is_dir())
            self.assertEqual(
                [
                    path
                    for path in first.generation_path.parent.iterdir()
                    if not path.name.startswith(".")
                ],
                [first.generation_path],
            )

    def test_dangling_current_symlink_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"
            ensure_legacy_original_snapshot(config_dir)
            current_path = config_dir / ".config-v2-original" / "CURRENT"
            current_path.unlink()
            try:
                current_path.symlink_to(config_dir / "does-not-exist")
            except OSError as exc:
                self.skipTest(f"symlink creation unavailable: {exc}")

            with self.assertRaisesRegex(
                LegacyOriginalSnapshotError,
                "CURRENT",
            ):
                ensure_legacy_original_snapshot(config_dir)

    def test_lexical_reparse_current_fails_closed_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"
            ensure_legacy_original_snapshot(config_dir)
            current_path = config_dir / ".config-v2-original" / "CURRENT"
            current_path.unlink()
            real_lexical_stat = snapshot_module._lexical_stat
            reparse_attribute = getattr(
                stat,
                "FILE_ATTRIBUTE_REPARSE_POINT",
                0x400,
            )
            fake_reparse = SimpleNamespace(
                st_mode=stat.S_IFREG,
                st_file_attributes=reparse_attribute,
            )

            def lexical_stat(path: Path):
                if path == current_path:
                    return fake_reparse
                return real_lexical_stat(path)

            with patch.object(
                snapshot_module,
                "_lexical_stat",
                side_effect=lexical_stat,
            ):
                with self.assertRaisesRegex(
                    LegacyOriginalSnapshotError,
                    "CURRENT",
                ):
                    ensure_legacy_original_snapshot(config_dir)

    def test_windows_reparse_directory_is_never_plain(self) -> None:
        reparse_attribute = getattr(
            stat,
            "FILE_ATTRIBUTE_REPARSE_POINT",
            0x400,
        )
        junction_stat = SimpleNamespace(
            st_mode=stat.S_IFDIR,
            st_file_attributes=reparse_attribute,
        )

        self.assertFalse(snapshot_module._is_plain_directory_stat(junction_stat))

    def test_unsafe_lock_directory_fails_before_capture(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"
            generations_dir = (
                config_dir / ".config-v2-original" / "generations"
            )
            generations_dir.mkdir(parents=True)
            (generations_dir.parent / "LOCK").mkdir()
            root_path = config_dir / "Config.json"
            root_path.write_bytes(b'{"value":"untouched"}')
            before = root_path.stat()

            with self.assertRaisesRegex(
                LegacyOriginalSnapshotError,
                "LOCK",
            ):
                ensure_legacy_original_snapshot(config_dir)

            after = root_path.stat()
            self.assertEqual(root_path.read_bytes(), b'{"value":"untouched"}')
            self.assertEqual(after.st_mtime_ns, before.st_mtime_ns)
            self.assertEqual(list(generations_dir.iterdir()), [])

    def test_dangling_file_for_missing_root_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"
            first = ensure_legacy_original_snapshot(config_dir)
            dangling = first.generation_path / "files" / "Config.json"
            try:
                dangling.symlink_to(first.generation_path / "absent")
            except OSError as exc:
                self.skipTest(f"symlink creation unavailable: {exc}")

            with self.assertRaisesRegex(
                LegacyOriginalSnapshotError,
                "unexpectedly has snapshot bytes",
            ):
                ensure_legacy_original_snapshot(config_dir)

    def test_corrupted_manifest_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"
            first = ensure_legacy_original_snapshot(config_dir)
            first.manifest_path.write_text("{broken", encoding="utf-8")

            with self.assertRaisesRegex(
                LegacyOriginalSnapshotError,
                "manifest",
            ):
                ensure_legacy_original_snapshot(config_dir)

    def test_staging_directory_never_uses_mkdtemp_owner_only_acl(self) -> None:
        # Python 3.12 的 mkdtemp 在 Windows 上附加仅限当前令牌的 DACL,
        # 发布后的 generation 会对另一提升级别的进程拒绝访问。
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"
            with patch.object(
                snapshot_module.tempfile,
                "mkdtemp",
                side_effect=AssertionError(
                    "generation staging must not use tempfile.mkdtemp"
                ),
            ):
                snapshot = ensure_legacy_original_snapshot(config_dir)

            self.assertTrue(snapshot.created)
            self.assertTrue(snapshot.generation_path.is_dir())
            self.assertEqual(
                [
                    path.name
                    for path in snapshot.generation_path.parent.iterdir()
                ],
                [snapshot.generation],
            )

    def test_access_denied_generation_recovers_with_acl_reset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"
            first = ensure_legacy_original_snapshot(config_dir)
            manifest_path = first.manifest_path
            state = {"repaired": False}
            real_lstat = Path.lstat

            def fake_lstat(self: Path):
                if self == manifest_path and not state["repaired"]:
                    raise PermissionError(13, "Access is denied", str(self), 5)
                return real_lstat(self)

            def fake_repair(path: Path) -> bool:
                self.assertEqual(path, first.generation_path)
                state["repaired"] = True
                return True

            with (
                patch.object(Path, "lstat", fake_lstat),
                patch.object(
                    snapshot_module,
                    "_try_restore_acl_inheritance",
                    side_effect=fake_repair,
                ),
            ):
                recovered = ensure_legacy_original_snapshot(config_dir)

            self.assertFalse(recovered.created)
            self.assertEqual(recovered.generation, first.generation)
            self.assertTrue(state["repaired"])

    def test_access_denied_generation_fails_closed_without_acl_repair(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"
            first = ensure_legacy_original_snapshot(config_dir)
            manifest_path = first.manifest_path
            real_lstat = Path.lstat

            def fake_lstat(self: Path):
                if self == manifest_path:
                    raise PermissionError(13, "Access is denied", str(self), 5)
                return real_lstat(self)

            with (
                patch.object(Path, "lstat", fake_lstat),
                patch.object(
                    snapshot_module,
                    "_try_restore_acl_inheritance",
                    return_value=False,
                ),
            ):
                with self.assertRaisesRegex(
                    LegacyOriginalSnapshotPermissionError,
                    "not accessible",
                ):
                    ensure_legacy_original_snapshot(config_dir)

    def test_corrupted_snapshot_bytes_fail_hash_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"
            config_dir.mkdir()
            (config_dir / "ToolsConfig.json").write_bytes(b'{"value":"original"}')
            first = ensure_legacy_original_snapshot(config_dir)
            copied_root = first.generation_path / "files" / "ToolsConfig.json"
            copied_root.write_bytes(b'{"value":"tampered"}')

            with self.assertRaisesRegex(
                LegacyOriginalSnapshotError,
                "size mismatch|hash mismatch",
            ):
                ensure_legacy_original_snapshot(config_dir)


if __name__ == "__main__":
    unittest.main()
