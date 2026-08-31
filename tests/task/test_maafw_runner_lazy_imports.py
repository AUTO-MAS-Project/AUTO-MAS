"""worker 侧包内的**延迟导入**必须也是树内路径，失败原因必须能到达用户。

两条都是真机跑出来的缺陷：

1. `runner.py` 有两处函数体内的 `from automas_maafw_agent_env...`（插件形态的
   顶层包）。移植时的改写只覆盖了行首导入，这两条缩进在函数里，漏了。
   它们直到运行期真正准备 agent 环境时才求值，因此所有导入测试都测不出来。
2. 那次失败在任务页上只显示「启动游戏：任务执行失败」——runner 用
   `MaaFW 任务执行失败: {exc}` 发的日志正好命中噪声过滤器的标记而被丢弃，
   而失败摘要又没读 `errorMessage`，真正的 `ModuleNotFoundError` 无处可见。
"""

import ast
import unittest
from pathlib import Path

import app.core  # noqa: F401  # 初始化宿主配置

REPO_ROOT = Path(__file__).resolve().parents[2]
PORTED_DIRS = (
    REPO_ROOT / "app/task/MaaFW/tools/core",
    REPO_ROOT / "app/task/MaaFW/tools/embedded",
)
PLUGIN_TOP_LEVEL_PREFIXES = ("automas_maafw", "automas_script_maafw")


def plugin_form_imports(path: Path) -> list[tuple[int, str]]:
    """返回文件里**任意缩进层级**的插件形态跨包导入。

    `ast.walk` 会走进函数体，正是行首正则漏掉的那一类。
    """

    found: list[tuple[int, str]] = []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level == 0 and module.startswith(PLUGIN_TOP_LEVEL_PREFIXES):
                found.append((node.lineno, module))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(PLUGIN_TOP_LEVEL_PREFIXES):
                    found.append((node.lineno, alias.name))
    return found


class NoPluginFormImportsTest(unittest.TestCase):
    def test_no_plugin_top_level_imports_remain(self) -> None:
        offenders: list[str] = []
        for root in PORTED_DIRS:
            for path in sorted(root.rglob("*.py")):
                for lineno, module in plugin_form_imports(path):
                    offenders.append(
                        f"{path.relative_to(REPO_ROOT)}:{lineno} -> {module}"
                    )
        self.assertEqual(
            offenders,
            [],
            "插件形态的顶层包导入在树内不存在，运行期才会炸：\n" + "\n".join(offenders),
        )

    def test_scan_actually_reaches_nested_imports(self) -> None:
        """确认扫描能看到函数体内的导入，否则这个测试是假绿的。"""

        source = "def f():\n    from automas_maafw_agent_env.env import x\n"
        tree = ast.parse(source)
        nested = [
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.level == 0
        ]
        self.assertEqual(nested, ["automas_maafw_agent_env.env"])


class FailureReasonReachesUserTest(unittest.TestCase):
    def setUp(self) -> None:
        import sys
        from unittest import mock

        maa_modules = (
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
        patcher = mock.patch.dict(
            sys.modules, {name: mock.MagicMock() for name in maa_modules}
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        import importlib

        self.module = importlib.import_module(
            "app.task.MaaFW.tools.embedded.runner_task"
        )

    @staticmethod
    def _result(error: str, failed_task: str = "启动游戏"):
        return type("R", (), {"errorMessage": error, "failedTask": failed_task})()

    @staticmethod
    def _plan():
        task = type("T", (), {"name": "启动游戏", "entry": "StartUp", "label": None})()
        return type("P", (), {"tasks": [task]})()

    def test_error_message_is_surfaced(self) -> None:
        summary = self.module._failed_task_user_summary(
            self._result("No module named 'automas_maafw_agent_env'"), self._plan()
        )
        self.assertIn("启动游戏", summary)
        self.assertIn("automas_maafw_agent_env", summary)

    def test_missing_error_message_keeps_the_plain_summary(self) -> None:
        summary = self.module._failed_task_user_summary(self._result(""), self._plan())
        self.assertEqual(summary, "启动游戏：任务执行失败")

    def test_only_the_first_line_is_used(self) -> None:
        summary = self.module._failed_task_user_summary(
            self._result("第一行原因\nTraceback (most recent call last):\n  ..."),
            self._plan(),
        )
        self.assertIn("第一行原因", summary)
        self.assertNotIn("Traceback", summary)

    def test_overlong_reason_is_truncated(self) -> None:
        summary = self.module._failed_task_user_summary(
            self._result("x" * 5000), self._plan()
        )
        self.assertLess(len(summary), 400)
        self.assertIn("…", summary)

    def test_works_without_a_matching_plan(self) -> None:
        summary = self.module._failed_task_user_summary(
            self._result("boom", failed_task="未知任务"), None
        )
        self.assertIn("未知任务", summary)
        self.assertIn("boom", summary)


if __name__ == "__main__":
    unittest.main()
