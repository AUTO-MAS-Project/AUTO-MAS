import unittest

from app.task.MaaFW.tools.core.automas_maafw_interface.models import (
    MaaFWInterface,
    MaaFWOption,
    MaaFWOptionCase,
    MaaFWPreset,
    MaaFWPresetTask,
    MaaFWTask,
)
from app.task.MaaFW.tools.core.automas_maafw_interface.task_config import (
    CUSTOM_PRESET_NAME,
    MaaFWTaskConfig,
    MaaFWTaskPresetSnapshot,
    normalize_snapshot,
    normalize_task_config,
)


def build_interface_model() -> MaaFWInterface:
    return MaaFWInterface(
        interface_version=2,
        name="Demo",
        version="1.0.0",
        task=[
            MaaFWTask(name="TaskB", entry="entry_b", option=["OptAlpha"]),
            MaaFWTask(name="TaskA", entry="entry_a"),
        ],
        option={
            "OptAlpha": MaaFWOption(
                type="select",
                cases=[
                    MaaFWOptionCase(name="Red"),
                    MaaFWOptionCase(name="Blue"),
                ],
            ),
        },
        preset=[
            MaaFWPreset(name="Fast", task=[MaaFWPresetTask(name="TaskB")]),
        ],
    )


class MaafwTaskConfigNormalizeTest(unittest.TestCase):
    def test_empty_config_normalizes_with_default_preset_snapshots(self) -> None:
        interface_model = build_interface_model()
        normalized = normalize_task_config(MaaFWTaskConfig(), interface_model)

        self.assertEqual(normalized.selectedPreset, CUSTOM_PRESET_NAME)
        self.assertEqual(
            set(normalized.presets.keys()),
            {CUSTOM_PRESET_NAME, "Fast"},
        )
        custom = normalized.presets[CUSTOM_PRESET_NAME]
        self.assertIsInstance(custom, MaaFWTaskPresetSnapshot)
        self.assertEqual(custom.taskOrder, ["TaskB", "TaskA"])
        self.assertEqual(custom.taskChecked, {"TaskB": False, "TaskA": False})
        self.assertEqual(custom.taskOptions["TaskB"]["OptAlpha"], "Red")

        fast = normalized.presets["Fast"]
        self.assertEqual(fast.taskOrder[0], "TaskB")
        self.assertTrue(fast.taskChecked["TaskB"])
        self.assertFalse(fast.taskChecked["TaskA"])

    def test_unknown_selected_preset_resets_to_custom_preset(self) -> None:
        interface_model = build_interface_model()
        config = MaaFWTaskConfig(selectedPreset="NoSuchPreset")
        normalized = normalize_task_config(config, interface_model)
        self.assertEqual(normalized.selectedPreset, CUSTOM_PRESET_NAME)

    def test_normalize_snapshot_keeps_given_order_and_appends_missing_tasks(
        self,
    ) -> None:
        interface_model = build_interface_model()
        snapshot = normalize_snapshot(
            {
                "taskOrder": ["TaskZ", "TaskA"],
                "taskChecked": {"TaskB": True},
                "taskOptions": {},
            },
            interface_model,
        )
        self.assertEqual(snapshot.taskOrder, ["TaskA", "TaskB"])
        self.assertTrue(snapshot.taskChecked["TaskB"])
        self.assertFalse(snapshot.taskChecked["TaskA"])

    def test_normalize_snapshot_from_none_yields_defaults(self) -> None:
        interface_model = build_interface_model()
        snapshot = normalize_snapshot(None, interface_model)
        self.assertEqual(snapshot.taskOrder, ["TaskB", "TaskA"])
        self.assertEqual(snapshot.taskChecked, {"TaskB": False, "TaskA": False})
        self.assertEqual(snapshot.taskOptions["TaskB"]["OptAlpha"], "Red")

    def test_normalize_task_options_keeps_string_case_value(self) -> None:
        interface_model = build_interface_model()
        snapshot = normalize_snapshot(
            {
                "taskOrder": [],
                "taskChecked": {},
                "taskOptions": {"TaskB": {"OptAlpha": "Blue"}},
            },
            interface_model,
        )
        self.assertEqual(snapshot.taskOptions["TaskB"]["OptAlpha"], "Blue")


if __name__ == "__main__":
    unittest.main()
