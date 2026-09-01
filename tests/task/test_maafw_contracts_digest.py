import tempfile
import unittest
from pathlib import Path

import app.core

from app.task.MaaFW.tools.core.automas_maafw_project_update.contracts import (
    artifact_id_for,
    canonical_json,
    normalise_sha256,
    project_fingerprint,
    safe_relative_path,
)


class MaafwContractsDigestTest(unittest.TestCase):
    def test_normalise_sha256_accepts_valid_hex_and_prefixed_uppercase(self) -> None:
        value = "a" * 64
        self.assertEqual(normalise_sha256(value), value)
        self.assertEqual(normalise_sha256(f"sha256:{value.upper()}"), value)

    def test_normalise_sha256_rejects_invalid_input(self) -> None:
        self.assertIsNone(normalise_sha256("z" * 64))
        self.assertIsNone(normalise_sha256("a" * 63))
        self.assertIsNone(normalise_sha256("a" * 65))
        self.assertIsNone(normalise_sha256(""))
        self.assertIsNone(normalise_sha256(None))

    def test_artifact_id_is_deterministic_and_ignores_signed_url_query(self) -> None:
        base = artifact_id_for(
            "GitHub", "v1.2.3", "https://example.com/download/pkg.zip?sig=aaa"
        )
        again = artifact_id_for(
            "GitHub", "v1.2.3", "https://example.com/download/pkg.zip?sig=bbb"
        )
        self.assertEqual(base, again)
        self.assertEqual(len(base), 24)
        other_version = artifact_id_for(
            "GitHub", "v1.2.4", "https://example.com/download/pkg.zip?sig=aaa"
        )
        self.assertNotEqual(base, other_version)

    def test_artifact_id_prefers_explicit_24hex_identity(self) -> None:
        explicit = "a1b2c3d4e5f67890fedcba98"
        resolved = artifact_id_for(
            "source", "v9", "https://example.com/whatever.zip", explicit=explicit
        )
        self.assertEqual(resolved, explicit)

    def test_project_fingerprint_is_deterministic_and_content_sensitive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "interface.json").write_text('{"name": "demo"}', encoding="utf-8")
            bin_dir = root / "bin"
            bin_dir.mkdir()
            (bin_dir / "a.txt").write_text("hello", encoding="utf-8")

            baseline = project_fingerprint(root)
            self.assertIsNotNone(baseline)
            self.assertEqual(baseline, project_fingerprint(str(root)))

            (bin_dir / "a.txt").write_text("changed", encoding="utf-8")
            self.assertNotEqual(baseline, project_fingerprint(root))

    def test_project_fingerprint_ignores_reserved_updater_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "f.txt").write_text("payload", encoding="utf-8")
            reserved_dir = root / ".mas-update"
            reserved_dir.mkdir()
            (reserved_dir / "state.json").write_text("{}", encoding="utf-8")

            with tempfile.TemporaryDirectory() as clean_dir:
                clean_root = Path(clean_dir)
                (clean_root / "f.txt").write_text("payload", encoding="utf-8")
                self.assertEqual(
                    project_fingerprint(root),
                    project_fingerprint(clean_root),
                )

    def test_project_fingerprint_requires_existing_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "no-such-dir"
            self.assertIsNone(project_fingerprint(missing))

    def test_canonical_json_sorts_keys_compactly(self) -> None:
        self.assertEqual(canonical_json({"b": 1, "a": 2}), '{"a":2,"b":1}')

    def test_safe_relative_path_normalises_backslash_to_posix(self) -> None:
        self.assertEqual(safe_relative_path("a\\b\\c.txt"), "a/b/c.txt")
        self.assertEqual(safe_relative_path("dir/file.json"), "dir/file.json")

    def test_safe_relative_path_rejects_unsafe_paths(self) -> None:
        for raw_path in (
            "",
            "   ",
            "/etc/passwd",
            "C:/Windows/config",
            "C:\\Windows\\config",
            "../outside.json",
            "a/../b.json",
            ".mas-update/state.json",
        ):
            with self.subTest(raw_path=raw_path):
                with self.assertRaises(ValueError):
                    safe_relative_path(raw_path)


if __name__ == "__main__":
    unittest.main()
