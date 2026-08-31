"""MaaFW 脚本的分派：内置运行是唯一目标。

第一层（`manager.py` + `tools/external` + `tools/controller`，启动项目自己的
UI shell）已随本次清理删除——它从未随任何 tag 发布过（引入提交 `1259f5fe`
不是 `v5.5.0-beta.1` 的祖先），产品上也早已不在 UI 暴露。

本文件替代原先的 `test_maafw_engine_dispatch.py`：那时要守的是「双引擎分派、
默认 external、第一层零回归」，现在要守的恰好相反——**分派没有分支，
第一层不留残迹，`Run.Engine` 这个键不再存在**。
"""

import ast
import asyncio
import unittest
import uuid
from pathlib import Path
from unittest import mock

import app.core  # noqa: F401  # 初始化宿主配置

from app.models.config import MaaFWConfig
from app.models.schema import MaaFWConfig_Run
from app.task.MaaFW.embedded_manager import MaaFWEmbeddedManager

REPO_ROOT = Path(__file__).resolve().parents[2]
TASK_MANAGER = REPO_ROOT / "app" / "core" / "task_manager.py"


class DispatchHasNoBranchTest(unittest.TestCase):
    """`task_manager` 里 MaaFWConfig 分支的形状。

    分派点在一个很长的 async 方法内部，用源码/AST 断言比把整个 TaskManager
    跑起来更稳，也更贴近「别把分支加回来」的意图。
    """

    def setUp(self) -> None:
        self.source = TASK_MANAGER.read_text(encoding="utf-8")
        self.tree = ast.parse(self.source)

    def test_maafw_dispatches_to_the_embedded_manager(self) -> None:
        self.assertIn("task.MaaFWEmbeddedManager(script_item)", self.source)

    def test_no_first_layer_manager_is_referenced(self) -> None:
        self.assertNotIn("task.MaaFWManager(", self.source)

    def test_dispatch_no_longer_reads_the_engine_key(self) -> None:
        self.assertNotIn('"Run", "Engine"', self.source)

    def test_no_engine_string_comparison_survives(self) -> None:
        """别留下 `== "embedded"` 之类的死判定。"""

        for node in ast.walk(self.tree):
            if isinstance(node, ast.Constant) and node.value in (
                "embedded",
                "external",
            ):
                self.fail(f"task_manager 仍有引擎字面量 {node.value!r}")

    def test_task_package_exports_only_the_embedded_manager(self) -> None:
        import app.task as task_package

        self.assertIn("MaaFWEmbeddedManager", task_package.__all__)
        self.assertNotIn("MaaFWManager", task_package.__all__)
        with self.assertRaises(AttributeError):
            task_package.MaaFWManager  # noqa: B018


class FirstLayerRemovedTest(unittest.TestCase):
    def test_first_layer_modules_are_gone(self) -> None:
        base = REPO_ROOT / "app" / "task" / "MaaFW"
        for relative in ("manager.py", "tools/external", "tools/controller"):
            with self.subTest(path=relative):
                self.assertFalse((base / relative).exists())

    def test_nothing_imports_the_first_layer(self) -> None:
        for path in (REPO_ROOT / "app").rglob("*.py"):
            source = path.read_text(encoding="utf-8", errors="replace")
            with self.subTest(module=str(path.relative_to(REPO_ROOT))):
                self.assertNotIn("MaaFW.manager", source)
                self.assertNotIn("MaaFW.tools.external", source)
                self.assertNotIn("MaaFW.tools.controller", source)

    def test_run_engine_key_is_gone_from_the_config_model(self) -> None:
        self.assertNotIn("Engine", MaaFWConfig()._config_item_index.get("Run", {}))

    def test_run_engine_field_is_gone_from_the_schema(self) -> None:
        self.assertNotIn("Engine", MaaFWConfig_Run.model_fields)


class EmbeddedManagerGateTest(unittest.TestCase):
    """`MaaFWEmbeddedManager.check()` 的早期门禁（不依赖磁盘上的项目）。"""

    def _manager(self, mode: str = "AutoProxy") -> MaaFWEmbeddedManager:
        script_info = mock.Mock()
        script_info.task_info = mock.Mock()
        script_info.task_info.mode = mode
        script_info.script_id = str(uuid.uuid4())
        script_info.user_list = [mock.Mock()]
        return MaaFWEmbeddedManager(script_info)

    def test_requires_a_bound_task_item(self) -> None:
        script_info = mock.Mock()
        script_info.task_info = None
        with self.assertRaises(RuntimeError):
            MaaFWEmbeddedManager(script_info)

    def test_non_autoproxy_mode_is_refused(self) -> None:
        self.assertNotEqual(asyncio.run(self._manager(mode="Manual").check()), "Pass")

    def test_invalid_script_id_is_refused(self) -> None:
        manager = self._manager()
        manager.script_info.script_id = "not-a-uuid"
        self.assertIn("ID", asyncio.run(manager.check()))


class EmbeddedManagerImportBoundaryTest(unittest.TestCase):
    def test_runner_task_is_imported_lazily(self) -> None:
        """`app.task` 是启动热路径；本模块不得把 maa DLL 拉进来。"""

        source = (
            REPO_ROOT / "app" / "task" / "MaaFW" / "embedded_manager.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = (
                    node.module
                    if isinstance(node, ast.ImportFrom)
                    else node.names[0].name
                )
                self.assertNotIn("runner_task", module or "")
        self.assertIn("from app.task.MaaFW.tools.embedded.runner_task import", source)

    def test_importing_app_task_does_not_load_maa(self) -> None:
        source = (
            REPO_ROOT / "app" / "task" / "MaaFW" / "embedded_manager.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("\nimport maa", source)
        self.assertNotIn("\nfrom maa", source)


if __name__ == "__main__":
    unittest.main()
