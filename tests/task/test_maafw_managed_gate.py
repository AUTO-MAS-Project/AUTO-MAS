"""第三层（managed）服务层的导入与 **未接线** 断言。

三层规划 §4：第三层的前置是第二层稳定，而第二层尚未真机验证。
本目录因此处于「落库不接线」状态——本文件的主要价值就是**把这个状态钉死**：
任何人把它接进 `task_manager` 或 Config 模型，这里都会红。
"""

import ast
import unittest
from pathlib import Path

import app.core  # noqa: F401  # 初始化宿主配置

from app.task.MaaFW.tools.embedded.managed import (
    MaaFWManagedEnvironmentService,
    ManagedServiceError,
    ManagedServiceGateway,
    managed_project_identity,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MANAGED_DIR = (
    REPO_ROOT / "app" / "task" / "MaaFW" / "tools" / "embedded" / "managed"
)


def plugin_framework_imports(path: Path) -> list[str]:
    """返回该文件真正 import 的插件宿主层模块名。

    用 AST 而不是原文扫描：docstring 里为了说明"为什么不搬"会提到
    `app.plugins`，原文扫描会把说明本身当成违规。
    """

    found: list[str] = []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(
                alias.name
                for alias in node.names
                if alias.name.split(".")[0] in {"auto_mas_core"}
                or alias.name.startswith("app.plugins")
            )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.startswith("app.plugins") or module.split(".")[0] == "auto_mas_core":
                found.append(module)
        elif isinstance(node, ast.Attribute) and node.attr == "get_service":
            found.append("ctx.get_service")
        elif isinstance(node, ast.Name) and node.id == "PluginHttpRequest":
            found.append("PluginHttpRequest")
    return found


class ManagedPackageImportTest(unittest.TestCase):
    def test_public_surface_is_importable(self) -> None:
        self.assertTrue(issubclass(ManagedServiceError, RuntimeError))
        self.assertTrue(callable(ManagedServiceGateway))
        self.assertTrue(callable(MaaFWManagedEnvironmentService))
        self.assertTrue(callable(managed_project_identity))

    def test_plugin_host_layer_files_are_not_ported(self) -> None:
        """`plugin`/`schema`/`adapter` 依赖 app.plugins，按指南 §4 规则 6 不搬。"""

        for absent in ("plugin.py", "schema.py", "adapter.py"):
            self.assertFalse((MANAGED_DIR / absent).exists(), absent)
        self.assertTrue((MANAGED_DIR / "py.typed").exists())

    def test_no_plugin_framework_coupling_remains(self) -> None:
        for path in sorted(MANAGED_DIR.glob("*.py")):
            with self.subTest(module=path.name):
                self.assertEqual(plugin_framework_imports(path), [])


class ManagedLayerStaysUnwiredTest(unittest.TestCase):
    """第三层没有解 gate —— 改动下面任何一条都要先过三层规划的前置判断。"""

    def test_task_manager_does_not_reference_the_managed_layer(self) -> None:
        source = (REPO_ROOT / "app" / "core" / "task_manager.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("embedded.managed", source)
        self.assertNotIn("ManagedServiceGateway", source)

    def test_no_manager_references_the_managed_layer(self) -> None:
        for name in ("manager.py", "embedded_manager.py"):
            source = (REPO_ROOT / "app" / "task" / "MaaFW" / name).read_text(
                encoding="utf-8"
            )
            with self.subTest(module=name):
                self.assertNotIn("embedded.managed", source)

    def test_project_source_axis_is_not_in_the_config_model(self) -> None:
        """三层规划 §5 的 `Project.Source` 轴尚未引入，第三层因此无从开启。"""

        source = (REPO_ROOT / "app" / "models" / "config.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn('"Project", "Source"', source)
        self.assertNotIn("Project_Source", source)

    def test_managed_enabled_still_defaults_to_false(self) -> None:
        from app.models.config import MaaFWConfig

        self.assertFalse(MaaFWConfig().get("Managed", "Enabled"))


class ManagedProjectIdentityTest(unittest.TestCase):
    def test_manifest_wins_when_complete(self) -> None:
        self.assertEqual(
            managed_project_identity(
                {
                    "ProjectId": "stale",
                    "Version": "v0",
                    "ProjectManifest": {"projectId": "M9A", "version": "v3.14.8"},
                }
            ),
            ("M9A", "v3.14.8"),
        )

    def test_incomplete_manifest_falls_back_to_config_fields(self) -> None:
        self.assertEqual(
            managed_project_identity(
                {
                    "ProjectId": "M9A",
                    "Version": "v3.14.8",
                    "ProjectManifest": {"projectId": "M9A"},
                }
            ),
            ("M9A", "v3.14.8"),
        )

    def test_missing_everything_yields_empty_strings(self) -> None:
        self.assertEqual(managed_project_identity({}), ("", ""))

    def test_non_mapping_manifest_is_ignored(self) -> None:
        self.assertEqual(
            managed_project_identity({"ProjectId": "M9A", "ProjectManifest": "junk"}),
            ("M9A", ""),
        )

    def test_blank_values_are_treated_as_absent(self) -> None:
        self.assertEqual(
            managed_project_identity({"ProjectId": "   ", "Version": ""}),
            ("", ""),
        )


class ManagedModuleShapeTest(unittest.TestCase):
    def test_modules_do_not_import_maa_at_module_level(self) -> None:
        for path in sorted(MANAGED_DIR.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            with self.subTest(module=path.name):
                for node in tree.body:
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            self.assertFalse(alias.name.split(".")[0] == "maa")
                    elif isinstance(node, ast.ImportFrom):
                        self.assertNotEqual((node.module or "").split(".")[0], "maa")


if __name__ == "__main__":
    unittest.main()
