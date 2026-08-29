import os
import stat
import tempfile
import unittest
from pathlib import Path

from app.utils.io import force_rmtree


class ForceRmtreeTest(unittest.TestCase):
    def _make_tree_with_readonly_file(self) -> tuple[Path, Path]:
        root = Path(tempfile.mkdtemp())
        nested = root / "objects" / "pack"
        nested.mkdir(parents=True)
        readonly = nested / "pack-0001.idx"
        readonly.write_bytes(b"payload")
        os.chmod(readonly, stat.S_IREAD)
        return root, readonly

    def test_removes_tree_containing_readonly_file(self):
        root, readonly = self._make_tree_with_readonly_file()
        self.addCleanup(self._cleanup, root, readonly)

        force_rmtree(root)

        self.assertFalse(root.exists())

    def test_missing_path_is_noop(self):
        root = Path(tempfile.mkdtemp())
        force_rmtree(root)

        force_rmtree(root)

        self.assertFalse(root.exists())

    @staticmethod
    def _cleanup(root: Path, readonly: Path) -> None:
        if readonly.exists():
            os.chmod(readonly, stat.S_IWRITE)
        if root.exists():
            force_rmtree(root)


if __name__ == "__main__":
    unittest.main()
