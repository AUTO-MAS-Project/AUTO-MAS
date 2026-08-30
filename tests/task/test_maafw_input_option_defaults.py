"""`input` 型选项的取值来源：用户填了才用，没填当空。

真机（M9A + 雷电）暴露的缺陷：M9A 的 `自定义兑换码` 在 interface 里声明
``"default": "占位"``，而该选项直接挂在「使用兑换码」任务上、**永远生效**。
此前没填就回退到 default，于是把字面量「占位」当真兑换码提交，
游戏兑换不掉，该任务卡死。

对照证据：
- MFAAvalonia 自己的配置里，未填写的输入持久化为 ``""``（不是 default）
- M9A agent 的 `_split_custom_codes` 对空串产出 0 个兑换码，直接跳过
- 需要哨兵默认值的选项，interface 作者写在 switch 的 case override 里
  （`自定义吃糖次数=No -> EatCandyStart.max_hit=114514`），不依赖 input default
"""

import unittest

import app.core  # noqa: F401  # 初始化宿主配置

from app.task.MaaFW.tools.core.automas_maafw_interface.models import MaaFWInterface
from app.task.MaaFW.tools.core.automas_maafw_runner.pipeline_override import (
    MaaFWPipelineOverrideBuilder,
)

INTERFACE = {
    "interface_version": 2,
    "name": "Demo",
    "controller": [{"name": "安卓端", "type": "Adb"}],
    "resource": [{"name": "官服", "path": ["{PROJECT_DIR}/resource/base"]}],
    "task": [
        {"name": "使用兑换码", "entry": "redeem_code", "option": ["自定义兑换码"]},
        {"name": "多字段", "entry": "Multi", "option": ["作战关卡(自定义)"]},
    ],
    "option": {
        "自定义兑换码": {
            "type": "input",
            "inputs": [
                {"name": "兑换码", "default": "占位", "pipeline_type": "string"}
            ],
            "pipeline_override": {
                "redeem_codeStart": {"attach": {"codes": "{兑换码}"}}
            },
        },
        "作战关卡(自定义)": {
            "type": "input",
            "inputs": [
                {"name": "章节号", "default": "2", "pipeline_type": "string"},
                {"name": "关卡号", "default": "6", "pipeline_type": "string"},
            ],
            "pipeline_override": {
                "SelectStage": {"attach": {"stage": "{章节号}-{关卡号}"}}
            },
        },
    },
}


def build(options):
    interface = MaaFWInterface.model_validate(INTERFACE)
    builder = MaaFWPipelineOverrideBuilder(
        interface, controller_names={"安卓端"}, resource_name="官服"
    )
    return builder, interface


class UnsetInputIsEmptyTest(unittest.TestCase):
    def _override(self, task: str, options):
        builder, _ = build(options)
        return builder.build_task_pipeline_override(task, options)

    def test_unset_input_does_not_leak_the_interface_default(self) -> None:
        override = self._override("使用兑换码", {})
        codes = override["redeem_codeStart"]["attach"]["codes"]
        self.assertEqual(codes, "")
        self.assertNotIn("占位", str(override))

    def test_empty_option_mapping_is_also_empty(self) -> None:
        override = self._override("使用兑换码", {"自定义兑换码": {}})
        self.assertEqual(override["redeem_codeStart"]["attach"]["codes"], "")

    def test_user_value_is_used_verbatim(self) -> None:
        override = self._override(
            "使用兑换码", {"自定义兑换码": {"兑换码": "ABC123 DEF456"}}
        )
        self.assertEqual(
            override["redeem_codeStart"]["attach"]["codes"], "ABC123 DEF456"
        )

    def test_user_value_as_plain_string_is_used(self) -> None:
        override = self._override("使用兑换码", {"自定义兑换码": "XYZ"})
        self.assertEqual(override["redeem_codeStart"]["attach"]["codes"], "XYZ")

    def test_multi_field_input_leaves_every_unset_field_empty(self) -> None:
        override = self._override("多字段", {})
        self.assertEqual(override["SelectStage"]["attach"]["stage"], "-")

    def test_partially_filled_multi_field_keeps_the_filled_one(self) -> None:
        override = self._override("多字段", {"作战关卡(自定义)": {"章节号": "5"}})
        self.assertEqual(override["SelectStage"]["attach"]["stage"], "5-")


if __name__ == "__main__":
    unittest.main()
