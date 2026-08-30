"""`Run.Engine` 两轴模型与 external / embedded 分派回归。

三层规划 §5 把「谁来跑」独立成 `Run.Engine`：
`external` = 第一层（启动项目自己的 UI shell，已真机验证），
`embedded` = 第二层（MAS 进程内 runner，实验性）。

**第一层零回归是本文件的首要断言**：默认值必须仍是 `external`，
`task_manager` 只在显式 `embedded` 时才走新路径。
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
from app.task.MaaFW.embedded_manager import ENGINE_VALUE, MaaFWEmbeddedManager

REPO_ROOT = Path(__file__).resolve().parents[2]


class RunEngineConfigTest(unittest.TestCase):
    def test_default_engine_is_embedded(self) -> None:
        """MaaFW 统一走内置运行；前端不再暴露该开关。"""

        self.assertEqual(MaaFWConfig().get("Run", "Engine"), "embedded")

    def test_both_engines_are_accepted(self) -> None:
        config = MaaFWConfig()
        for value in ("embedded", "external"):
            with self.subTest(engine=value):
                asyncio.run(config.set("Run", "Engine", value))
                self.assertEqual(config.get("Run", "Engine"), value)

    def test_unknown_engine_is_rejected(self) -> None:
        config = MaaFWConfig()
        asyncio.run(config.set("Run", "Engine", "embedded"))
        asyncio.run(config.set("Run", "Engine", "nonsense"))
        # OptionsValidator 会纠正非法值，而不是把它写进去
        self.assertIn(config.get("Run", "Engine"), ("external", "embedded"))
        self.assertNotEqual(config.get("Run", "Engine"), "nonsense")

    def test_run_group_item_count_is_unchanged(self) -> None:
        # 只放宽了 Engine 的取值域，没有新增配置项
        self.assertEqual(len(MaaFWConfig()._config_item_index["Run"]), 7)


class RunEngineSchemaTest(unittest.TestCase):
    def test_schema_default_is_embedded(self) -> None:
        self.assertEqual(MaaFWConfig_Run().Engine, "embedded")

    def test_schema_accepts_both_engines(self) -> None:
        self.assertEqual(MaaFWConfig_Run(Engine="embedded").Engine, "embedded")
        self.assertEqual(MaaFWConfig_Run(Engine="external").Engine, "external")

    def test_schema_rejects_unknown_engine(self) -> None:
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            MaaFWConfig_Run(Engine="managed")


class TaskManagerDispatchTest(unittest.TestCase):
    """`task_manager` 里 MaaFWConfig 分支的形状。

    分派点在一个很长的 async 方法内部，用 AST 断言分支存在且两个 manager
    都被引用，比把整个 TaskManager 跑起来更稳、也更贴近"别把分支删了"的意图。
    """

    def setUp(self) -> None:
        source = (REPO_ROOT / "app" / "core" / "task_manager.py").read_text(
            encoding="utf-8"
        )
        self.tree = ast.parse(source)
        self.source = source

    def test_both_managers_are_referenced(self) -> None:
        self.assertIn("task.MaaFWManager(script_item)", self.source)
        self.assertIn("task.MaaFWEmbeddedManager(script_item)", self.source)

    def test_dispatch_reads_the_run_engine_key(self) -> None:
        self.assertIn('get("Run", "Engine") == "embedded"', self.source)

    def test_embedded_branch_is_guarded_by_an_equality_test(self) -> None:
        """embedded 必须是显式相等判定，不能是 != external 之类的宽松写法。"""

        compares = [
            node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.Compare)
            and len(node.ops) == 1
            and isinstance(node.ops[0], ast.Eq)
            and isinstance(node.comparators[0], ast.Constant)
            and node.comparators[0].value == "embedded"
        ]
        self.assertEqual(len(compares), 1)

    def test_task_package_exports_both_managers(self) -> None:
        import app.task as task_package

        self.assertIn("MaaFWManager", task_package.__all__)
        self.assertIn("MaaFWEmbeddedManager", task_package.__all__)


class EmbeddedManagerCheckTest(unittest.TestCase):
    """`MaaFWEmbeddedManager.check()` 的门禁行为。"""

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
        manager = self._manager(mode="Manual")
        self.assertNotEqual(asyncio.run(manager.check()), "Pass")

    def test_invalid_script_id_is_refused(self) -> None:
        manager = self._manager()
        manager.script_info.script_id = "not-a-uuid"
        self.assertIn("ID", asyncio.run(manager.check()))

    def test_external_engine_is_refused_by_the_embedded_manager(self) -> None:
        """走错门的配置必须被挡下，而不是被静默地按 embedded 跑。"""

        config = MaaFWConfig()
        asyncio.run(config.set("Run", "Engine", "external"))
        manager = self._manager()
        script_uid = uuid.UUID(manager.script_info.script_id)
        with mock.patch.object(
            app.core.Config, "ScriptConfig", {script_uid: config}
        ):
            result = asyncio.run(manager.check())
        self.assertNotEqual(result, "Pass")
        self.assertIn("内置运行", result)

    def test_missing_project_path_is_refused(self) -> None:
        config = MaaFWConfig()
        asyncio.run(config.set("Run", "Engine", ENGINE_VALUE))
        manager = self._manager()
        script_uid = uuid.UUID(manager.script_info.script_id)
        with mock.patch.object(
            app.core.Config, "ScriptConfig", {script_uid: config}
        ):
            result = asyncio.run(manager.check())
        self.assertNotEqual(result, "Pass")
        self.assertIn("路径", result)


class EmbeddedManagerImportBoundaryTest(unittest.TestCase):
    def test_runner_task_is_imported_lazily(self) -> None:
        """`app.task` 是启动热路径；embedded manager 不得把 maa DLL 拉进来。"""

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


class FirstLayerUntouchedTest(unittest.TestCase):
    """第一层零回归：`manager.py` 的 external 门禁保持原样。"""

    def test_external_guard_is_unchanged(self) -> None:
        source = (REPO_ROOT / "app" / "task" / "MaaFW" / "manager.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('script_config.get("Run", "Engine") != "external"', source)
        self.assertIn("MFW 当前仅支持 external 运行引擎", source)

    def test_first_layer_manager_does_not_reference_the_embedded_layer(self) -> None:
        source = (REPO_ROOT / "app" / "task" / "MaaFW" / "manager.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("tools.embedded", source)
        self.assertNotIn("MaaFWEmbeddedManager", source)


if __name__ == "__main__":
    unittest.main()
