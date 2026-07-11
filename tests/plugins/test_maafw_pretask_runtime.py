import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


REPO_ROOT = Path(__file__).resolve().parents[2]
for plugin_name in (
    "automas_maafw_agent_env",
    "automas_maafw_interface",
    "automas_maafw_runner",
):
    sys.path.insert(0, str(REPO_ROOT / "plugins" / plugin_name / "src"))

from automas_maafw_interface.models import (
    MaaFWInterface,
    build_pretask_task_name,
    iter_pretasks,
)
from automas_maafw_runner.run_plan import build_maafw_run_plan


class MaaFWPretaskRuntimeTest(unittest.TestCase):
    def test_enabled_pretask_runs_with_compact_nested_option_json(self) -> None:
        with TemporaryDirectory() as temporary_dir:
            project_path = Path(temporary_dir)
            executable = project_path / "agent" / "go-service.exe"
            executable.parent.mkdir()
            executable.write_bytes(b"test")
            interface = self._build_interface()
            pretask_name = build_pretask_task_name(iter_pretasks(interface)[0])

            plan = build_maafw_run_plan(
                project_path,
                interface,
                task_snapshot={
                    "taskOrder": ["Daily", pretask_name],
                    "taskChecked": {"Daily": True, pretask_name: True},
                    "taskOptions": {
                        pretask_name: {
                            "Region": "CN",
                            "DisplayType": "Window",
                            "Resolution": "1920x1080",
                        },
                    },
                },
            )

            self.assertEqual(len(plan.pretasks), 1)
            pretask = plan.pretasks[0]
            self.assertEqual(pretask.name, pretask_name)
            self.assertEqual(pretask.executable, str(executable))
            self.assertEqual(pretask.args[:2], ["--pretask", "GameSetting"])
            self.assertEqual(
                json.loads(pretask.args[-1]),
                {
                    "Region": "CN",
                    "DisplayType": "Window",
                    "Resolution": "1920x1080",
                },
            )

    def test_pretask_requires_manual_add(self) -> None:
        with TemporaryDirectory() as temporary_dir:
            project_path = Path(temporary_dir)
            executable = project_path / "agent" / "go-service.exe"
            executable.parent.mkdir()
            executable.write_bytes(b"test")

            plan = build_maafw_run_plan(
                project_path,
                self._build_interface(),
                task_snapshot={
                    "taskOrder": ["Daily"],
                    "taskChecked": {"Daily": True},
                    "taskOptions": {},
                },
            )

            self.assertEqual(plan.pretasks, [])

    def test_hotkey_option_is_ignored_without_blocking_task(self) -> None:
        with TemporaryDirectory() as temporary_dir:
            project_path = Path(temporary_dir)
            plan = build_maafw_run_plan(
                project_path,
                self._build_interface(),
                task_snapshot={
                    "taskOrder": ["Daily"],
                    "taskChecked": {"Daily": True},
                    "taskOptions": {
                        "Daily": {"Keymap": {"Fight": "Ctrl+Z"}},
                    },
                },
            )

            self.assertEqual(plan.tasks[0].pipelineOverride, {})
            self.assertNotIn("Keymap", plan.tasks[0].options)

    @staticmethod
    def _build_interface() -> MaaFWInterface:
        return MaaFWInterface.model_validate(
            {
                "interface_version": 2,
                "name": "PretaskTest",
                "controller": [{"name": "Win32-Front", "type": "Win32"}],
                "resource": [{"name": "base", "path": []}],
                "pretask": {
                    "name": "GameSetting",
                    "exec": "agent/go-service",
                    "args": ["--pretask", "GameSetting"],
                    "controller": ["Win32-Front"],
                    "option": ["Region", "DisplayType"],
                },
                "task": [{"name": "Daily", "entry": "Daily"}],
                "global_option": ["Keymap"],
                "option": {
                    "Region": {
                        "type": "select",
                        "default_case": "CN",
                        "cases": [{"name": "CN"}, {"name": "Global"}],
                    },
                    "DisplayType": {
                        "type": "select",
                        "default_case": "Window",
                        "cases": [
                            {"name": "Window", "option": ["Resolution"]},
                            {"name": "Fullscreen", "option": ["Resolution"]},
                        ],
                    },
                    "Resolution": {
                        "type": "select",
                        "default_case": "1280x720",
                        "cases": [
                            {"name": "1280x720"},
                            {"name": "1920x1080"},
                        ],
                    },
                    "Keymap": {
                        "type": "hotkey",
                        "hotkeys": [{"name": "Fight", "default": "E"}],
                        "pipeline_override": {
                            "Fight": {
                                "key": "{Fight.primary}",
                                "modifier": "{Fight.modifier1}",
                            }
                        },
                    },
                },
            }
        )


if __name__ == "__main__":
    unittest.main()
