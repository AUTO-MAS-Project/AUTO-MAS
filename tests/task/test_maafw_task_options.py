import unittest

import app.core  # noqa: F401

from app.task.MaaFW.tools.core.automas_maafw_interface import MaaFWInterface
from app.task.MaaFW.tools.core.automas_maafw_interface.models import (
    MaaFWOption,
    MaaFWOptionCase,
    MaaFWTask,
)
from app.task.MaaFW.tools.external.mfaavalonia import (
    build_option_entries,
    build_task_items,
)
from app.task.MaaFW.tools.external.models import TaskSelection


def _interface() -> MaaFWInterface:
    """带顶层 option 声明的最小 interface。

    形状对齐真实 M9A：``select`` 型给 cases，checkbox 与自由输入型的值
    由调用方给出，interface 侧只声明选项名。
    """

    return MaaFWInterface(
        interface_version=2,
        name="opt-project",
        controller=[{"name": "安卓端", "type": "Adb"}],
        resource=[{"name": "简中"}],
        task=[
            MaaFWTask(
                name="收取荒原",
                entry="Wilderness",
                option=["好梦井", "低阶柜台", "目标账号(可选)"],
            ),
            MaaFWTask(name="启动游戏", entry="StartUp"),
        ],
        option={
            "好梦井": MaaFWOption(
                type="select",
                cases=[
                    MaaFWOptionCase(name="不使用"),
                    MaaFWOptionCase(name="使用"),
                    MaaFWOptionCase(name="仅周末使用"),
                ],
            ),
            "低阶柜台": MaaFWOption(type="select", cases=[MaaFWOptionCase(name="启用")]),
            "目标账号(可选)": MaaFWOption(type="select"),
        },
    )


def _task(interface: MaaFWInterface, name: str) -> MaaFWTask:
    return next(task for task in interface.task if task.name == name)


class BuildOptionEntriesTest(unittest.TestCase):
    """选项值 → MFAAvalonia option 条目形状。

    形状依据是真实 M9A 实例配置的 51 条 option 实测（2026-08-29）：
    name 与 index 恒存在，checkbox 型追加 selected_cases，自由输入型追加 data。
    """

    def setUp(self) -> None:
        self.interface = _interface()
        self.task = _task(self.interface, "收取荒原")

    def test_no_values_matches_legacy_index_zero_behaviour(self) -> None:
        # 回归守护：无选项值时必须与「每项 index 0」的旧行为逐字节一致，
        # 否则本次修复会让既有运行结果漂移。
        self.assertEqual(
            build_option_entries(self.interface, self.task, None),
            [
                {"name": "好梦井", "index": 0},
                {"name": "低阶柜台", "index": 0},
                {"name": "目标账号(可选)", "index": 0},
            ],
        )
        self.assertEqual(
            build_option_entries(self.interface, self.task, {}),
            build_option_entries(self.interface, self.task, None),
        )

    def test_select_value_resolves_to_case_index(self) -> None:
        entries = build_option_entries(
            self.interface, self.task, {"好梦井": "仅周末使用"}
        )
        self.assertEqual(entries[0], {"name": "好梦井", "index": 2})

    def test_unknown_case_name_falls_back_to_index_zero(self) -> None:
        entries = build_option_entries(self.interface, self.task, {"好梦井": "不存在"})
        self.assertEqual(entries[0], {"name": "好梦井", "index": 0})

    def test_list_value_becomes_selected_cases(self) -> None:
        entries = build_option_entries(
            self.interface, self.task, {"低阶柜台": ["金兔子", "紫地球仪"]}
        )
        self.assertEqual(
            entries[1],
            {"name": "低阶柜台", "index": 0, "selected_cases": ["金兔子", "紫地球仪"]},
        )

    def test_dict_value_becomes_data(self) -> None:
        entries = build_option_entries(
            self.interface, self.task, {"目标账号(可选)": {"账号": "abc"}}
        )
        self.assertEqual(
            entries[2],
            {"name": "目标账号(可选)", "index": 0, "data": {"账号": "abc"}},
        )

    def test_entry_order_and_range_follow_task_option(self) -> None:
        # 顺序与范围由 task.option 决定，不受传入值的键序或多余键影响。
        entries = build_option_entries(
            self.interface,
            self.task,
            {"目标账号(可选)": {"账号": "a"}, "好梦井": "使用", "不相关": "x"},
        )
        self.assertEqual([e["name"] for e in entries], list(self.task.option))

    def test_task_without_options_returns_empty(self) -> None:
        entries = build_option_entries(
            self.interface, _task(self.interface, "启动游戏"), {"好梦井": "使用"}
        )
        self.assertEqual(entries, [])

    def test_values_flow_through_build_task_items(self) -> None:
        # 端到端：选项值经 TaskSelection.options 进入 TaskItems。
        items = build_task_items(
            self.interface,
            [
                TaskSelection(
                    name="收取荒原",
                    options=build_option_entries(
                        self.interface, self.task, {"好梦井": "使用"}
                    ),
                )
            ],
        )
        self.assertEqual(items[0]["option"][0], {"name": "好梦井", "index": 1})


if __name__ == "__main__":
    unittest.main()
