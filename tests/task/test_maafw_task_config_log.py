"""任务配置日志不该被「框架错误」兜底腰斩。

真机（MaaEnd v2.26.0）日志里的样子：

    MaaFW 任务配置: label=🎁基建任务; ... "KeymapFightSkill2":"2","Keyma
    … MaaFW 框架错误详情已省略 1041 个字符，完整内容请查看本次运行的 .maafw.log

两处不对：

1. 这行是任务配置，不是框架错误诊断，却被 `_framework_ui_message` 这条**给
   错误用的**兜底按每行 240 字符砍掉，JSON 断在半个键名上。
2. 兜底文案把它叫「框架错误详情」，张冠李戴。

根因是限额只管了 options，没管整行：override_nodes 名字一长（MaaEnd 的
_AutoEcoFarmEnterCameraModeFallbackReleaseOnError 之流）整行就顶穿宿主的
_FRAMEWORK_UI_LOG_MAX_CHARS。同一次运行里 5 条配置只有第一条（968 字符）
幸存，其余 4 条全被砍到 240。
"""

import sys
import unittest
from unittest import mock

import app.core  # noqa: F401  # 初始化宿主配置

MAA_MODULES = (
    "maa",
    "maa.agent_client",
    "maa.context",
    "maa.controller",
    "maa.custom_action",
    "maa.custom_recognition",
    "maa.define",
    "maa.event_sink",
    "maa.job",
    "maa.library",
    "maa.notification_handler",
    "maa.resource",
    "maa.tasker",
    "maa.toolkit",
)


def load(name: str):
    patcher = mock.patch.dict(
        sys.modules, {mod: mock.MagicMock() for mod in MAA_MODULES}
    )
    patcher.start()
    import importlib

    return importlib.import_module(name), patcher


def find_formatter(module):
    import inspect

    for attr, value in vars(module).items():
        if inspect.isfunction(value) and "task_config" in attr.lower():
            return value
    raise AssertionError("未找到任务配置日志格式化函数")


class TaskConfigLineIsBoundedAtSourceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module, patcher = load(
            "app.task.MaaFW.tools.core.automas_maafw_runner.runner"
        )
        self.addCleanup(patcher.stop)
        self.format = find_formatter(self.module)

    def _plan(self, options=None, overrides=0):
        from app.task.MaaFW.tools.core.automas_maafw_runner.models import (
            MaaFWTaskRunPlan,
        )

        return MaaFWTaskRunPlan(
            name="DijiangRewards",
            label="🎁基建任务",
            entry="DijiangRewards",
            logOptions=options or {},
            overrideNodes=[
                f"_AutoEcoFarmEnterCameraModeFallbackReleaseOnError{i}"
                for i in range(overrides)
            ],
        )

    def test_long_line_stays_under_the_host_forward_limit(self) -> None:
        line = self.format(
            self._plan({"KeymapFight": {f"K{i}": str(i) for i in range(40)}}, 35)
        )
        self.assertLessEqual(len(line), self.module.TASK_CONFIG_LOG_LINE_LIMIT)

    def test_source_limit_leaves_room_below_the_host_limit(self) -> None:
        """低于宿主上限才不会二次截断 —— 相等也不行，宿主还要加时间戳等前缀。"""

        host = load("app.task.MaaFW.tools.embedded.runner_task")[0]
        self.assertLess(
            self.module.TASK_CONFIG_LOG_LINE_LIMIT,
            host._FRAMEWORK_UI_LOG_MAX_CHARS,
        )

    def test_override_nodes_survive_intact(self) -> None:
        """砍的是 options；override_nodes 与结尾必须完整，否则看不出跑了什么。"""

        line = self.format(
            self._plan({"KeymapFight": {f"K{i}": str(i) for i in range(40)}}, 35)
        )
        self.assertIn("override_nodes=", line)
        self.assertTrue(line.rstrip().endswith("...(+23)"), line[-60:])

    def test_short_line_is_untouched(self) -> None:
        line = self.format(self._plan({"A": "1"}, 2))
        self.assertIn('options={"A":"1"}', line)
        self.assertNotIn("...", line.split("options=")[1].split(";")[0])


class FallbackWordingIsNeutralTest(unittest.TestCase):
    """兜底会套在所有转发的 worker 日志上，不只错误诊断。"""

    def setUp(self) -> None:
        self.module, patcher = load("app.task.MaaFW.tools.embedded.runner_task")
        self.addCleanup(patcher.stop)

    def test_does_not_call_arbitrary_content_a_framework_error(self) -> None:
        summary = self.module._framework_ui_message(
            "MaaFW 任务配置: " + "x" * 4000
        )
        self.assertIn("已省略", summary)
        self.assertNotIn("框架错误详情", summary)
        self.assertIn(".maafw.log", summary)


if __name__ == "__main__":
    unittest.main()
