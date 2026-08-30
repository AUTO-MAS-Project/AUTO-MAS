"""MaaFW 第二层集成层（`tools/embedded`）的导入与纯逻辑回归。

`runner_task` 会经 runner 包间接 import maa，本文件在 mock 下验证其可导入，
不实例化 `Tasker`/`Controller`、不起子进程、不做全进程枚举。
"""

import ast
import asyncio
import importlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import app.core  # noqa: F401  # 初始化宿主配置

from app.task.MaaFW.tools.embedded import (
    MaaFWManagedExecutionRoute,
    MaaFWRegistryService,
    MaaFWRuntimePoolRoute,
    MaaFWRuntimeRouteError,
    normalize_project_path,
    release_project_path,
    try_reserve_project_path,
)
from app.task.MaaFW.tools.embedded.configuration_reuse import (
    MaaFWConfigurationReuseError,
    discover_configuration_sources,
    public_configuration_plan,
    stable_json_hash,
    user_records_hash,
)
from app.task.MaaFW.tools.embedded.runtime_route import (
    runtime_pool_route_from_service,
)

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

EMBEDDED_DIR = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "task"
    / "MaaFW"
    / "tools"
    / "embedded"
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


class EmbeddedLayerImportTest(unittest.TestCase):
    def test_pure_modules_import_without_maa(self) -> None:
        base = "app.task.MaaFW.tools.embedded"
        for name in ("project_path", "registry", "runtime_route", "configuration_reuse"):
            with self.subTest(module=name):
                self.assertIsNotNone(importlib.import_module(base + "." + name))

    def test_runner_task_imports_under_a_mocked_maa(self) -> None:
        import sys

        patched = {name: mock.MagicMock() for name in MAA_MODULES}
        with mock.patch.dict(sys.modules, patched):
            module = importlib.import_module(
                "app.task.MaaFW.tools.embedded.runner_task"
            )
            self.assertTrue(hasattr(module, "MaaFWPluginAutoProxyTask"))

    def test_plugin_host_layer_is_not_ported(self) -> None:
        """插件 HTTP 宿主层的文件按移植指南 §4 规则 6 不搬。"""

        for absent in (
            "plugin.py",
            "schema.py",
            "adapter.py",
            "configuration_controller.py",
        ):
            self.assertFalse((EMBEDDED_DIR / absent).exists(), absent)

    def test_no_plugin_framework_coupling_remains(self) -> None:
        for path in sorted(EMBEDDED_DIR.glob("*.py")):
            with self.subTest(module=path.name):
                self.assertEqual(plugin_framework_imports(path), [])

    def test_worker_module_path_points_into_the_tree(self) -> None:
        source = (EMBEDDED_DIR / "runner_task.py").read_text(encoding="utf-8")
        self.assertIn(
            "app.task.MaaFW.tools.core.automas_maafw_runner.worker",
            source,
        )
        self.assertNotIn('"automas_maafw_runner.worker"', source)


class ProjectPathReservationTest(unittest.IsolatedAsyncioTestCase):
    def test_normalization_is_case_and_separator_insensitive(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            project = Path(root) / "Project"
            project.mkdir()
            self.assertEqual(
                normalize_project_path(project),
                normalize_project_path(str(project).upper()),
            )

    async def test_second_reservation_fails_fast(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            project = Path(root) / "Project"
            project.mkdir()
            key = await try_reserve_project_path(project)
            self.assertIsNotNone(key)
            try:
                self.assertIsNone(await try_reserve_project_path(project))
            finally:
                await release_project_path(key)

    async def test_release_frees_the_reservation(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            project = Path(root) / "Project"
            project.mkdir()
            key = await try_reserve_project_path(project)
            await release_project_path(key)
            second = await try_reserve_project_path(project)
            self.assertIsNotNone(second)
            await release_project_path(second)

    async def test_release_is_none_safe_and_idempotent(self) -> None:
        await release_project_path(None)
        await release_project_path("")
        await release_project_path("no-such-key")

    async def test_concurrent_reservations_grant_exactly_one(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            project = Path(root) / "Project"
            project.mkdir()
            results = await asyncio.gather(
                *(try_reserve_project_path(project) for _ in range(8))
            )
            granted = [key for key in results if key is not None]
            try:
                self.assertEqual(len(granted), 1)
            finally:
                for key in granted:
                    await release_project_path(key)


class RegistryServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = MaaFWRegistryService()

    def test_controller_provider_round_trip(self) -> None:
        self.registry.register_controller_provider({"key": "adb", "displayName": "ADB"})
        self.assertEqual(
            self.registry.get_controller_provider("adb"),
            {"key": "adb", "displayName": "ADB"},
        )
        self.assertEqual(len(self.registry.list_controller_providers()), 1)
        self.registry.unregister_controller_provider("adb")
        self.assertIsNone(self.registry.get_controller_provider("adb"))

    def test_re_registering_a_key_replaces_the_definition(self) -> None:
        self.registry.register_controller_provider({"key": "adb", "displayName": "A"})
        self.registry.register_controller_provider({"key": "adb", "displayName": "B"})
        self.assertEqual(len(self.registry.list_controller_providers()), 1)
        self.assertEqual(
            self.registry.get_controller_provider("adb")["displayName"], "B"
        )

    def test_empty_key_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.registry.register_controller_provider({"key": "  "})
        with self.assertRaises(ValueError):
            self.registry.register_project_pack({"key": ""})

    def test_unregistering_an_unknown_key_is_a_noop(self) -> None:
        self.registry.unregister_controller_provider("nope")
        self.registry.unregister_project_pack("nope")
        self.assertEqual(self.registry.list_controller_providers(), [])


class RuntimeRouteTest(unittest.TestCase):
    def test_missing_service_is_reported(self) -> None:
        with self.assertRaises(MaaFWRuntimeRouteError):
            runtime_pool_route_from_service(None)

    def test_service_without_storage_info_is_reported(self) -> None:
        with self.assertRaises(MaaFWRuntimeRouteError):
            runtime_pool_route_from_service(object())

    def test_route_is_built_from_storage_info(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            service = mock.Mock()
            service.storage_info.return_value = {"root": root, "poolId": "pool-1"}
            route = runtime_pool_route_from_service(service)
            self.assertIsInstance(route, MaaFWRuntimePoolRoute)
            self.assertEqual(route.pool_id, "pool-1")
            self.assertEqual(route.root, Path(root).resolve())

    def test_managed_execution_route_is_frozen(self) -> None:
        route = MaaFWManagedExecutionRoute(
            runtime_id="maafw-runtime-abc",
            maafw_requirement="maafw==4.0.0",
            runtime_requirements=("maafw==4.0.0",),
            python_constraint="==3.13.*",
            shared_agent_dependencies_complete=True,
            managed_python_agent_indexes=(0,),
        )
        with self.assertRaises(Exception):
            route.runtime_id = "other"  # type: ignore[misc]


class ConfigurationReuseTest(unittest.TestCase):
    """`configuration_reuse` 取 mfwa 1465 行版（基准对照 §3.2），纯库落地。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_missing_source_is_reported(self) -> None:
        with self.assertRaises(MaaFWConfigurationReuseError):
            discover_configuration_sources(self.root / "nope")

    def test_empty_directory_discovers_nothing(self) -> None:
        empty = self.root / "empty"
        empty.mkdir()
        self.assertEqual(discover_configuration_sources(empty), [])

    def test_stable_hash_is_key_order_independent(self) -> None:
        self.assertEqual(
            stable_json_hash({"a": 1, "b": [2, 3]}),
            stable_json_hash({"b": [2, 3], "a": 1}),
        )
        self.assertNotEqual(stable_json_hash({"a": 1}), stable_json_hash({"a": 2}))

    def test_user_records_hash_ignores_record_order(self) -> None:
        left = [
            {"id": "u2", "type": "maafw", "config": {"x": 1}},
            {"id": "u1", "type": "maafw", "config": {"y": 2}},
        ]
        right = list(reversed(left))
        self.assertEqual(user_records_hash(left), user_records_hash(right))

    def test_user_records_hash_tracks_config_changes(self) -> None:
        base = [{"id": "u1", "type": "maafw", "config": {"x": 1}}]
        changed = [{"id": "u1", "type": "maafw", "config": {"x": 2}}]
        self.assertNotEqual(user_records_hash(base), user_records_hash(changed))

    def test_public_plan_drops_target_payloads(self) -> None:
        plan = {
            "planId": "p1",
            "schemaVersion": 1,
            "kind": "external",
            "target": "new-user",
            "summary": {"count": 2},
            "readyToApply": True,
            "orphans": [],
            # 内部字段不得进预览
            "targetPayloads": {"secret": "value"},
            "userConfigs": [{"password": "hunter2"}],
        }
        public = public_configuration_plan(plan)
        self.assertEqual(public["planId"], "p1")
        self.assertNotIn("targetPayloads", public)
        self.assertNotIn("userConfigs", public)
        self.assertNotIn("hunter2", json.dumps(public, ensure_ascii=False))

    def test_public_plan_is_a_deep_copy(self) -> None:
        plan = {"planId": "p1", "summary": {"tasks": ["a"]}, "orphans": []}
        public = public_configuration_plan(plan)
        public["summary"]["tasks"].append("b")
        self.assertEqual(plan["summary"]["tasks"], ["a"])


if __name__ == "__main__":
    unittest.main()
