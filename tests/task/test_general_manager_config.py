import tempfile
import unittest
from pathlib import Path

from app.task.general.manager import GeneralManager


class _ScriptConfigStub:
    def __init__(self, mode: str) -> None:
        self.mode = mode

    def get(self, section: str, key: str):
        if (section, key) == ("Script", "ConfigPathMode"):
            return self.mode
        raise AssertionError(f"unexpected config lookup: {section}.{key}")


def _build_manager(root: Path, mode: str) -> GeneralManager:
    manager = object.__new__(GeneralManager)
    manager.script_config = _ScriptConfigStub(mode)
    manager.script_config_path = root / "script-config"
    manager.temp_path = root / "temp"
    manager.external_config_exists = False
    manager.external_config_snapshot_ready = False
    return manager


class GeneralManagerConfigTest(unittest.TestCase):
    def test_folder_snapshot_restores_exact_direct_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manager = _build_manager(root, "Folder")
            manager.script_config_path.mkdir()
            (manager.script_config_path / "keep.txt").write_text(
                "direct", encoding="utf-8"
            )

            manager._snapshot_external_config()
            (manager.script_config_path / "keep.txt").unlink()
            (manager.script_config_path / "managed.txt").write_text(
                "managed", encoding="utf-8"
            )

            manager._restore_external_config()

            self.assertEqual(
                (manager.script_config_path / "keep.txt").read_text(encoding="utf-8"),
                "direct",
            )
            self.assertFalse((manager.script_config_path / "managed.txt").exists())

    def test_file_snapshot_restores_direct_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manager = _build_manager(root, "File")
            manager.script_config_path.write_text("direct", encoding="utf-8")

            manager._snapshot_external_config()
            manager.script_config_path.write_text("managed", encoding="utf-8")

            manager._restore_external_config()

            self.assertEqual(
                manager.script_config_path.read_text(encoding="utf-8"), "direct"
            )

    def test_missing_direct_config_stays_missing_after_restore(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manager = _build_manager(root, "Folder")

            manager._snapshot_external_config()
            manager.script_config_path.mkdir()
            (manager.script_config_path / "managed.txt").write_text(
                "managed", encoding="utf-8"
            )

            manager._restore_external_config()

            self.assertFalse(manager.script_config_path.exists())


if __name__ == "__main__":
    unittest.main()
