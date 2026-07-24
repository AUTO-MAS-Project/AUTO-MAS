from __future__ import annotations

import shutil
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path

from manual_release_safety import ArchiveBudgets, extract_zip_safely


class ManualReleaseArchiveSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.test_root = Path(
            tempfile.mkdtemp(prefix="auto-mas-manual-release-safety-")
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.test_root)

    def write_zip(
        self,
        name: str,
        entries: list[tuple[str | zipfile.ZipInfo, bytes]],
    ) -> Path:
        archive_path = self.test_root / name
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for entry_name, payload in entries:
                archive.writestr(entry_name, payload)
        return archive_path

    def assert_rejected(
        self,
        archive_path: Path,
        *,
        budgets: ArchiveBudgets | None = None,
    ) -> None:
        destination = self.test_root / f"rejected-{archive_path.stem}"
        with self.assertRaises((FileExistsError, ValueError)):
            extract_zip_safely(archive_path, destination, budgets=budgets)
        self.assertFalse(destination.exists())

    def test_extracts_a_benign_archive_atomically(self) -> None:
        archive_path = self.write_zip(
            "good.zip",
            [("bundle/", b""), ("bundle/release.txt", b"release")],
        )
        destination = self.test_root / "good-output"

        extracted = extract_zip_safely(archive_path, destination)

        self.assertEqual(
            extracted,
            [str(destination / "bundle" / "release.txt")],
        )
        self.assertEqual(
            (destination / "bundle" / "release.txt").read_bytes(),
            b"release",
        )

    def test_rejects_traversal_with_either_separator(self) -> None:
        for index, entry_name in enumerate(("../escape.txt", r"..\escape.txt")):
            archive_path = self.write_zip(
                f"traversal-{index}.zip",
                [(entry_name, b"escape")],
            )
            self.assert_rejected(archive_path)
            self.assertFalse((self.test_root / "escape.txt").exists())

    def test_rejects_ads_devices_and_duplicate_canonical_paths(self) -> None:
        for name, entries in (
            ("ads.zip", [("file.txt:stream", b"bad")]),
            ("device.zip", [("NUL.txt", b"bad")]),
            (
                "duplicate.zip",
                [("Folder/File.txt", b"one"), ("folder/file.TXT", b"two")],
            ),
        ):
            self.assert_rejected(self.write_zip(name, entries))

    def test_rejects_symlink_and_special_entries(self) -> None:
        symlink = zipfile.ZipInfo("link")
        symlink.create_system = 3
        symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
        self.assert_rejected(self.write_zip("symlink.zip", [(symlink, b"target")]))

    def test_enforces_entry_file_expanded_and_archive_budgets(self) -> None:
        archive_path = self.write_zip(
            "budgets.zip",
            [("one.txt", b"1234"), ("two.txt", b"5678")],
        )
        for budgets in (
            ArchiveBudgets(max_entries=1),
            ArchiveBudgets(max_file_bytes=3),
            ArchiveBudgets(max_expanded_bytes=7),
            ArchiveBudgets(max_archive_bytes=1),
        ):
            self.assert_rejected(archive_path, budgets=budgets)

    def test_refuses_an_existing_destination(self) -> None:
        archive_path = self.write_zip("existing.zip", [("file.txt", b"data")])
        destination = self.test_root / "existing-output"
        destination.mkdir()
        sentinel = destination / "sentinel.txt"
        sentinel.write_text("keep", encoding="utf-8")

        with self.assertRaises(FileExistsError):
            extract_zip_safely(archive_path, destination)

        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    def test_rejects_invalid_budget_construction(self) -> None:
        for value in (0, -1, True):
            with self.assertRaises(ValueError):
                ArchiveBudgets(max_entries=value)


if __name__ == "__main__":
    unittest.main()
