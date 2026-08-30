"""非字符串 input 未填写时的取值来源。

真机（MaaEnd v2.26.0）暴露的回归：把「未填写的 input 一律当空」推广到全部
类型后，`int("")` 直接把运行计划构建打崩，check 阶段报
``invalid literal for int() with base 10: ''``。

两类 input 的语义本就不同：

- 字符串：空串是**合法取值**。M9A 的 `自定义兑换码` 没填就该是空，
  它的 default「占位」是 UI 提示而非该应用的值（见
  test_maafw_input_option_defaults.py）。
- 数值/布尔：没有「空」这个取值。MaaEnd 的 61 个非字符串 input 默认值全是
  真数字（SupplyPlanLimit 260、分辨率 1280x720、T_CREDS 3580000），
  未填写就必须回落到 default。
"""

import unittest
from pathlib import Path

import app.core  # noqa: F401  # 初始化宿主配置

from app.task.MaaFW.tools.core.automas_maafw_interface.models import MaaFWInterface
from app.task.MaaFW.tools.core.automas_maafw_runner.pipeline_override import (
    MaaFWPipelineOverrideBuilder,
)

INTERFACE = {
    "interface_version": 2,
    "name": "Demo",
    "controller": [{"name": "桌面端", "type": "Win32"}],
    "resource": [{"name": "官服", "path": ["{PROJECT_DIR}/resource"]}],
    "task": [
        {"name": "补给", "entry": "Supply", "option": ["补给上限"]},
        {"name": "分辨率", "entry": "Res", "option": ["关闭时分辨率"]},
        {"name": "开关", "entry": "Toggle", "option": ["布尔项"]},
        {"name": "兑换", "entry": "Redeem", "option": ["兑换码"]},
        {"name": "缺省", "entry": "NoDefault", "option": ["无默认值的数值"]},
    ],
    "option": {
        "补给上限": {
            "type": "input",
            "inputs": [
                {"name": "上限", "default": "260", "pipeline_type": "int"}
            ],
            "pipeline_override": {"SupplyStart": {"attach": {"limit": "{上限}"}}},
        },
        "关闭时分辨率": {
            "type": "input",
            "inputs": [
                {"name": "宽", "default": "1280", "pipeline_type": "int"},
                {"name": "高", "default": "720", "pipeline_type": "int"},
            ],
            "pipeline_override": {
                "ResStart": {"attach": {"w": "{宽}", "h": "{高}"}}
            },
        },
        "布尔项": {
            "type": "input",
            "inputs": [
                {"name": "开", "default": "true", "pipeline_type": "bool"}
            ],
            "pipeline_override": {"ToggleStart": {"attach": {"on": "{开}"}}},
        },
        "兑换码": {
            "type": "input",
            "inputs": [
                {"name": "码", "default": "占位", "pipeline_type": "string"}
            ],
            "pipeline_override": {"RedeemStart": {"attach": {"codes": "{码}"}}},
        },
        "无默认值的数值": {
            "type": "input",
            "inputs": [{"name": "数", "pipeline_type": "int"}],
            "pipeline_override": {"NoDefaultStart": {"attach": {"n": "{数}"}}},
        },
    },
}


def override(task: str, options):
    interface = MaaFWInterface.model_validate(INTERFACE)
    builder = MaaFWPipelineOverrideBuilder(
        interface, controller_names={"桌面端"}, resource_name="官服"
    )
    return builder.build_task_pipeline_override(task, options)


class NumericInputFallsBackToDefaultTest(unittest.TestCase):
    def test_unset_int_uses_the_declared_default(self) -> None:
        self.assertEqual(override("补给", {})["SupplyStart"]["attach"]["limit"], 260)

    def test_unset_int_is_typed_not_stringified(self) -> None:
        value = override("补给", {})["SupplyStart"]["attach"]["limit"]
        self.assertIsInstance(value, int)

    def test_every_unset_field_of_a_multi_field_input_falls_back(self) -> None:
        attach = override("分辨率", {})["ResStart"]["attach"]
        self.assertEqual((attach["w"], attach["h"]), (1280, 720))

    def test_partially_filled_keeps_the_user_value_and_defaults_the_rest(self) -> None:
        attach = override("分辨率", {"关闭时分辨率": {"宽": "1920"}})["ResStart"][
            "attach"
        ]
        self.assertEqual((attach["w"], attach["h"]), (1920, 720))

    def test_user_value_still_wins(self) -> None:
        self.assertEqual(
            override("补给", {"补给上限": {"上限": "999"}})["SupplyStart"]["attach"][
                "limit"
            ],
            999,
        )

    def test_unset_bool_uses_the_default_not_a_silent_false(self) -> None:
        """空串喂给 bool 不会崩，但会静默变 False —— 同一类缺陷。"""

        self.assertIs(override("开关", {})["ToggleStart"]["attach"]["on"], True)

    def test_missing_default_reports_which_field_is_at_fault(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            override("缺省", {})
        message = str(ctx.exception)
        self.assertIn("无默认值的数值", message)
        self.assertIn("数", message)
        # 不能再是那句看不出所以然的 int() 报错
        self.assertNotIn("invalid literal", message)


class StringInputStaysEmptyTest(unittest.TestCase):
    """回归护栏：修数值类型不能把兑换码那个坑放回来。"""

    def test_unset_string_does_not_leak_the_interface_default(self) -> None:
        attach = override("兑换", {})["RedeemStart"]["attach"]
        self.assertEqual(attach["codes"], "")
        self.assertNotIn("占位", str(attach))


MAAEND = Path("D:/MAS/tmp/maafw-embedded-target/MaaEnd-win-x86_64-v2.26.0")


@unittest.skipUnless(MAAEND.is_dir(), "MaaEnd 靶子不在本机")
class RealMaaEndProjectTest(unittest.TestCase):
    """真靶子回归：MaaEnd 有 61 个非字符串 input，check 阶段曾直接崩。"""

    def test_run_plan_builds(self) -> None:
        from app.task.MaaFW.tools.core.automas_maafw_interface.service import (
            MaaFWInterfaceService,
        )
        from app.task.MaaFW.tools.core.automas_maafw_runner.service import (
            MaaFWRunnerService,
        )

        interface = MaaFWInterfaceService().load(MAAEND)
        plan = MaaFWRunnerService().build_plan(
            MAAEND,
            interface,
            controller_name=None,
            resource_name=None,
            selected_preset=None,
            task_snapshot=None,
        )
        self.assertTrue(plan.tasks)
        self.assertEqual(plan.controllerType, "Win32")


if __name__ == "__main__":
    unittest.main()
