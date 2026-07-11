import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(
    0,
    str(REPO_ROOT / "plugins" / "automas_maafw_interface" / "src"),
)

from automas_maafw_interface import load_interface_model


class MaaFWInterfaceImportTest(unittest.TestCase):
    @staticmethod
    def _write_json(path: Path, data: dict) -> None:
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def test_imports_all_project_interface_v2_sections_in_protocol_order(self) -> None:
        with TemporaryDirectory() as temporary_dir:
            project_path = Path(temporary_dir)
            self._write_json(
                project_path / "interface.json",
                {
                    "interface_version": 2,
                    "name": "ImportTest",
                    "controller": [{"name": "desktop", "type": "Win32"}],
                    "resource": [{"name": "base", "path": []}],
                    "task": [{"name": "root-task", "entry": "Root"}],
                    "option": {
                        "shared": {
                            "type": "select",
                            "default_case": "root",
                            "cases": [{"name": "root"}],
                        }
                    },
                    "global_option": ["shared"],
                    "group": [{"name": "root-group", "label": "root"}],
                    "pretask": {"name": "root-pretask", "exec": "root.exe"},
                    "import": ["parent.json"],
                },
            )
            self._write_json(
                project_path / "parent.json",
                {
                    "task": [{"name": "parent-task", "entry": "Parent"}],
                    "option": {
                        "shared": {
                            "type": "select",
                            "default_case": "parent",
                            "cases": [{"name": "parent"}],
                        },
                        "parent-only": {
                            "type": "select",
                            "cases": [{"name": "enabled"}],
                        },
                    },
                    "global_option": ["shared", "parent-only"],
                    "setting": [
                        {"name": "parent-setting", "option": ["parent-only"]}
                    ],
                    "preset": [{"name": "parent-preset", "task": []}],
                    "group": [
                        {"name": "root-group", "label": "ignored"},
                        {"name": "parent-group"},
                    ],
                    "pretask": [
                        {
                            "name": "parent-pretask",
                            "exec": "parent.exe",
                            "controller": ["desktop"],
                            "resource": ["base"],
                            "option": ["parent-only"],
                        }
                    ],
                    "import": ["child.json"],
                },
            )
            self._write_json(
                project_path / "child.json",
                {
                    "task": [{"name": "child-task", "entry": "Child"}],
                    "option": {
                        "shared": {
                            "type": "select",
                            "default_case": "child",
                            "cases": [{"name": "child"}],
                        },
                        "child-only": {
                            "type": "select",
                            "cases": [{"name": "enabled"}],
                        },
                    },
                    "global_option": ["parent-only", "child-only"],
                    "setting": [
                        {"name": "child-setting", "option": ["child-only"]}
                    ],
                    "preset": [{"name": "child-preset", "task": []}],
                    "group": [{"name": "child-group"}],
                    "pretask": {"name": "child-pretask", "exec": "child.exe"},
                    "future_section": {"enabled": True},
                },
            )

            with self.assertLogs(
                "automas.maafw.interface.loader",
                level="WARNING",
            ) as captured_logs:
                interface = load_interface_model(project_path)

        self.assertEqual(
            [task.name for task in interface.task],
            ["root-task", "parent-task", "child-task"],
        )
        self.assertEqual(interface.option["shared"].default_case, "child")
        self.assertEqual(
            interface.global_option,
            ["shared", "parent-only", "child-only"],
        )
        self.assertFalse(hasattr(interface, "setting"))
        self.assertTrue(any("setting" in message for message in captured_logs.output))
        self.assertTrue(
            any("future_section" in message for message in captured_logs.output)
        )
        self.assertEqual(
            [preset.name for preset in interface.preset],
            ["parent-preset", "child-preset"],
        )
        self.assertEqual(
            [(group.name, group.label) for group in interface.group or []],
            [
                ("root-group", "root"),
                ("parent-group", None),
                ("child-group", None),
            ],
        )
        pretasks = interface.pretask if isinstance(interface.pretask, list) else []
        self.assertEqual(
            [pretask.name for pretask in pretasks],
            ["root-pretask", "parent-pretask", "child-pretask"],
        )


if __name__ == "__main__":
    unittest.main()
