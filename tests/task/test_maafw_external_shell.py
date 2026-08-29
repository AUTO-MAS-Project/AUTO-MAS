import tempfile
import unittest
from pathlib import Path

import app.core

from app.task.MaaFW.tools.external.shell import ShellFamily, detect_shell_family


def _touch(root: Path, *names: str) -> None:
    for name in names:
        (root / name).write_text("", encoding="utf-8")


class MaafwExternalShellTest(unittest.TestCase):
    def test_mfaavalonia_detected_by_marker_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _touch(root, "MFAAvalonia.dll", "appsettings.json", "interface.json")

            self.assertEqual(detect_shell_family(root), ShellFamily.MFAAVALONIA)

    def test_detection_ignores_exe_name(self) -> None:
        # M9A 的外壳 exe 是 m9a.exe，MaaKes 的是 MFAAvalonia.exe，两者同为 MFAAvalonia。
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _touch(root, "MFAAvalonia.dll", "appsettings.json", "m9a.exe")
            self.assertEqual(detect_shell_family(root), ShellFamily.MFAAVALONIA)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            # 只有一个 exe 像 MFAAvalonia，但没有特征文件，不算命中。
            _touch(root, "MFAAvalonia.exe")
            self.assertEqual(detect_shell_family(root), ShellFamily.UNKNOWN)

    def test_partial_markers_do_not_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _touch(root, "MFAAvalonia.dll")
            self.assertEqual(detect_shell_family(root), ShellFamily.UNKNOWN)

    def test_unrelated_project_is_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _touch(root, "interface.json", "main.exe")
            self.assertEqual(detect_shell_family(root), ShellFamily.UNKNOWN)

    def test_missing_directory_is_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "nope"
            self.assertEqual(detect_shell_family(missing), ShellFamily.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
