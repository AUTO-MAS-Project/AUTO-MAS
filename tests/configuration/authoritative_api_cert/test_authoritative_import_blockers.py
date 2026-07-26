"""Config v2 authoritative 模式 import 阻断测试。

这些测试不启动真实应用，仅验证 import 行为和 lazy-loading 机制。
"""
import os
import sys
from pathlib import Path

import pytest

# 确保工作树在 sys.path 中
WORKTREE = Path(__file__).resolve().parents[3]
if str(WORKTREE) not in sys.path:
    sys.path.insert(0, str(WORKTREE))


class TestAuthoritativeStartupMode:
    """验证原生 authoritative 模式已通过启动门禁。"""

    def test_assert_config_v2_startup_mode_ready_accepts_authoritative(self):
        from app.configuration import (
            CONFIG_V2_MODE_AUTHORITATIVE,
            assert_config_v2_startup_mode_ready,
        )

        assert_config_v2_startup_mode_ready(CONFIG_V2_MODE_AUTHORITATIVE)

    def test_shadow_mode_passes(self):
        """shadow 模式下 assert 不应 raise。"""
        from app.configuration import (
            CONFIG_V2_MODE_SHADOW,
            assert_config_v2_startup_mode_ready,
        )
        # 不应该 raise
        assert_config_v2_startup_mode_ready(CONFIG_V2_MODE_SHADOW)


class TestCoreGetattrRouting:
    """验证 app.core.__getattr__ 在 authoritative 下的路由行为。"""

    def test_config_is_native_facade_in_authoritative(self, monkeypatch):
        """authoritative 模式下 Config 应为 NativeConfigFacade 实例。"""
        import app.configuration as configuration
        import app.core

        # The configuration mode is selected when ``app.configuration`` is
        # imported, not on every environment lookup.  Patch the selected
        # runtime value directly and remove only a potential test cache.
        monkeypatch.setattr(
            configuration,
            "CONFIG_V2_MODE",
            configuration.CONFIG_V2_MODE_AUTHORITATIVE,
        )
        app.core.__dict__.pop("Config", None)
        Config = getattr(app.core, "Config")
        from app.core.native_config import NativeConfigFacade
        assert isinstance(Config, NativeConfigFacade)

    def test_config_is_app_config_in_shadow(self, monkeypatch):
        """shadow 模式下 Config 应为旧 AppConfig 实例。"""
        import app.configuration as configuration
        import app.core

        monkeypatch.setattr(
            configuration,
            "CONFIG_V2_MODE",
            configuration.CONFIG_V2_MODE_SHADOW,
        )
        app.core.__dict__.pop("Config", None)
        Config = getattr(app.core, "Config")
        from app.core.config import AppConfig
        assert isinstance(Config, AppConfig)


class TestApiRouterLazyLoading:
    """验证 app.api 路由器延迟加载机制。"""

    def test_router_lazy_import_works(self):
        """app.api 的 __getattr__ 应能延迟加载所有路由器。"""
        from fastapi import APIRouter

        from app.api import (
            core_router,
            emulator_router,
            info_router,
            plan_router,
            plugin_gateway_router,
            plugins_router,
            queue_router,
            setting_router,
            tools_router,
            ws_router,
        )
        for router, name in [
            (core_router, "core"),
            (info_router, "info"),
            (plan_router, "plan"),
            (emulator_router, "emulator"),
            (queue_router, "queue"),
            (tools_router, "tools"),
            (setting_router, "setting"),
            (ws_router, "websocket"),
            (plugins_router, "plugins"),
            (plugin_gateway_router, "plugin_gateway"),
        ]:
            assert isinstance(router, APIRouter), f"{name}_router 应该是 APIRouter 实例"


class TestTopLevelImportBlockers:
    """验证 authoritative 导入闭包不会在模块顶层加载旧 ConfigBase。"""

    MODULES_WITHOUT_TOP_LEVEL_CONFIGBASE = [
        "app.core.script_config_codec",
        "app.core.script_types",
        "app.plugins.script_adapter",
        "app.plugins.script_adapter_schema",
        "app.plugins.script_config_store",
    ]

    @pytest.mark.parametrize("module_name", MODULES_WITHOUT_TOP_LEVEL_CONFIGBASE)
    def test_migrated_module_does_not_import_configbase_at_top_level(
        self,
        module_name,
    ):
        """已迁移模块只能在明确的 legacy 兼容函数中延迟导入旧基类。"""
        import ast
        import importlib.util

        spec = importlib.util.find_spec(module_name)
        assert spec is not None and spec.origin is not None
        tree = ast.parse(Path(spec.origin).read_text(encoding="utf-8"))

        top_level_imports = [
            node
            for node in tree.body
            if isinstance(node, (ast.Import, ast.ImportFrom))
        ]
        assert not any(
            isinstance(node, ast.ImportFrom)
            and node.module
            and "ConfigBase" in node.module
            for node in top_level_imports
        )


@pytest.mark.asyncio
async def test_authoritative_plugin_sync_never_enters_legacy_collection_migration(
    monkeypatch,
):
    """Config v2 roots must not be treated as legacy MultipleConfig objects."""
    import app.configuration as configuration
    from app.plugins.manager import _PluginManager

    monkeypatch.setattr(
        configuration,
        "CONFIG_V2_MODE",
        configuration.CONFIG_V2_MODE_AUTHORITATIVE,
    )

    # A bare manager has none of the loader/registry state required by the
    # legacy migration.  Returning cleanly proves authoritative mode exits
    # before touching that old runtime chain.
    manager = _PluginManager.__new__(_PluginManager)
    await manager._sync_script_types_and_migrate_legacy_configs(discovered={})
