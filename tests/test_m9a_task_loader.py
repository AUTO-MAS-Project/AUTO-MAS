import json
import tempfile
import unittest
from pathlib import Path

from app.task.M9A.task_loader import M9ATaskLoader


class M9ATaskLoaderPathTest(unittest.TestCase):
    @staticmethod
    def _write_task(tasks_dir: Path, name: str) -> None:
        tasks_dir.mkdir(parents=True, exist_ok=True)
        (tasks_dir / "task.json").write_text(
            json.dumps({"task": [{"name": name, "entry": name}]}),
            encoding="utf-8",
        )

    def test_loads_new_tasks_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_task(root / "tasks", "new-task")

            loader = M9ATaskLoader(root)

            self.assertEqual(loader.tasks_dir, root / "tasks")
            self.assertEqual(loader.get_all_task_names(), ["new-task"])

    def test_loads_legacy_resource_tasks_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_task(root / "resource/tasks", "legacy-task")

            loader = M9ATaskLoader(root)

            self.assertEqual(loader.tasks_dir, root / "resource/tasks")
            self.assertEqual(loader.get_all_task_names(), ["legacy-task"])

    def test_prefers_new_tasks_directory_when_both_exist(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_task(root / "tasks", "new-task")
            self._write_task(root / "resource/tasks", "legacy-task")

            loader = M9ATaskLoader(root)

            self.assertEqual(loader.tasks_dir, root / "tasks")
            self.assertEqual(loader.get_all_task_names(), ["new-task"])

    def test_reload_detects_directory_moved_by_hot_update(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            legacy_task = root / "resource/tasks/task.json"
            self._write_task(legacy_task.parent, "legacy-task")
            loader = M9ATaskLoader(root)

            legacy_task.unlink()
            self._write_task(root / "tasks", "new-task")
            loader.reload()

            self.assertEqual(loader.tasks_dir, root / "tasks")
            self.assertEqual(loader.get_all_task_names(), ["new-task"])


if __name__ == "__main__":
    unittest.main()
