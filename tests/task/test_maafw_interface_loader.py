import json
import tempfile
import unittest
from pathlib import Path

from app.task.MaaFW.tools.core.automas_maafw_interface.loader import (
    MaaFWInterfaceLoadError,
    load_interface_model,
)
from app.task.MaaFW.tools.core.automas_maafw_interface.models import MaaFWInterface

INTERFACE_WITH_IMPORT = {
    "interface_version": 2,
    "name": "Demo",
    "task": [{"name": "Main", "entry": "main"}],
    "option": {
        "OptAlpha": {
            "type": "select",
            "cases": [{"name": "Red"}, {"name": "Blue"}],
        },
    },
    "import": ["fragments/tasks.json"],
}

FRAGMENT = {
    "task": [{"name": "Extra", "entry": "extra"}],
    "option": {
        "OptBeta": {
            "type": "select",
            "cases": [{"name": "On"}, {"name": "Off"}],
        },
    },
}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class MaafwInterfaceLoaderTest(unittest.TestCase):
    def test_loads_interface_and_merges_import_fragments(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_json(root / "interface.json", INTERFACE_WITH_IMPORT)
            write_json(root / "fragments" / "tasks.json", FRAGMENT)

            interface = load_interface_model(root)
            self.assertIsInstance(interface, MaaFWInterface)
            self.assertEqual(interface.name, "Demo")
            task_names = [task.name for task in interface.task]
            self.assertEqual(task_names, ["Main", "Extra"])
            self.assertIn("OptBeta", interface.option)

    def test_reports_missing_interface_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(MaaFWInterfaceLoadError) as ctx:
                load_interface_model(Path(temp_dir))
            self.assertIn("interface.json", str(ctx.exception))

    def test_detects_circular_import(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_json(
                root / "interface.json",
                {**INTERFACE_WITH_IMPORT, "import": ["fragments/self.json"]},
            )
            write_json(root / "fragments" / "self.json", {"import": ["interface.json"]})

            with self.assertRaises(MaaFWInterfaceLoadError) as ctx:
                load_interface_model(root)
            self.assertIn("循环导入", str(ctx.exception))

    def test_rejects_absolute_import_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_json(
                root / "interface.json",
                {**INTERFACE_WITH_IMPORT, "import": ["C:/Windows/evil.json"]},
            )

            with self.assertRaises(MaaFWInterfaceLoadError) as ctx:
                load_interface_model(root)
            self.assertIn("绝对路径", str(ctx.exception))

    def test_rejects_parent_traversal_import_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            outside = Path(temp_dir).parent / "outside.json"
            write_json(outside, FRAGMENT)
            write_json(
                root / "interface.json",
                {**INTERFACE_WITH_IMPORT, "import": ["../outside.json"]},
            )

            with self.assertRaises(MaaFWInterfaceLoadError) as ctx:
                load_interface_model(root)
            self.assertIn("..", str(ctx.exception))

    def test_rejects_missing_import_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_json(
                root / "interface.json",
                {**INTERFACE_WITH_IMPORT, "import": ["fragments/nope.json"]},
            )

            with self.assertRaises(MaaFWInterfaceLoadError) as ctx:
                load_interface_model(root)
            self.assertIn("import 文件不存在", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
