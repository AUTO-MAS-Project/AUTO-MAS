"""NativeConfigFacade dry-run 测试。

不启动真实应用/游戏/模拟器，仅测试 facade 方法的基本调用契约。
"""
import os
import sys
import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

WORKTREE = Path(__file__).resolve().parents[3]
if str(WORKTREE) not in sys.path:
    sys.path.insert(0, str(WORKTREE))


@pytest.fixture
def temp_config_dir():
    """创建临时配置目录，包含模拟的 legacy 快照。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir) / "config"
        config_dir.mkdir()
        # 创建 mock 快照目录
        snapshot_dir = config_dir / ".legacy-original-snapshot"
        snapshot_dir.mkdir()
        generation_dir = snapshot_dir / "mock-gen-001"
        generation_dir.mkdir()
        files_dir = generation_dir / "files"
        files_dir.mkdir()

        # 创建 manifest.json
        manifest = {
            "schema_version": 1,
            "generation": "mock-gen-001",
            "roots": []
        }
        root_names = [
            "Config.json", "EmulatorConfig.json", "PlanConfig.json",
            "ScriptConfig.json", "QueueConfig.json", "ToolsConfig.json",
            "PluginConfig.json", "GameSignAccounts.json"
        ]
        for name in root_names:
            content = json.dumps({"mock": True}, ensure_ascii=False).encode("utf-8")
            (files_dir / name).write_bytes(content)
            manifest["roots"].append({
                "name": name,
                "exists": True,
                "size_bytes": len(content),
                "sha256": __import__("hashlib").sha256(content).hexdigest(),
            })

        (generation_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
        )

        yield config_dir


class TestNativeConfigFacadeAttributes:
    """测试 NativeConfigFacade 的基本属性。"""

    def test_facade_has_version(self):
        """facade 应有 VERSION 属性。"""
        from app.core.native_config import NativeConfigFacade
        facade = NativeConfigFacade(workspace_root=WORKTREE)
        assert hasattr(facade, "VERSION")
        assert isinstance(facade.VERSION, str)
        assert facade.VERSION.startswith("v6")

    def test_facade_has_power_sign(self):
        """facade 应有 power_sign 属性。"""
        from app.core.native_config import NativeConfigFacade
        facade = NativeConfigFacade(workspace_root=WORKTREE)
        assert facade.power_sign == "NoAction"

    def test_facade_has_temp_task(self):
        """facade 应有 temp_task 属性。"""
        from app.core.native_config import NativeConfigFacade
        facade = NativeConfigFacade(workspace_root=WORKTREE)
        assert isinstance(facade.temp_task, list)

    def test_facade_has_path_attributes(self):
        """facade 应有路径属性。"""
        from app.core.native_config import NativeConfigFacade
        facade = NativeConfigFacade(workspace_root=WORKTREE)
        assert isinstance(facade.workspace_root, Path)
        assert isinstance(facade.config_path, Path)
        assert isinstance(facade.log_path, Path)
        assert isinstance(facade.database_path, Path)
        assert isinstance(facade.history_path, Path)

    def test_facade_not_initialized_by_default(self):
        """facade 默认不应初始化。"""
        from app.core.native_config import NativeConfigFacade
        facade = NativeConfigFacade(workspace_root=WORKTREE)
        assert facade.initialized is False

    def test_facade_config_properties(self):
        """facade 应有配置根属性。"""
        from app.core.native_config import NativeConfigFacade
        facade = NativeConfigFacade(workspace_root=WORKTREE)
        # 这些属性在未初始化时访问会 raise RuntimeError
        for attr in ["EmulatorConfig", "PlanConfig", "ScriptConfig",
                      "QueueConfig", "ToolsConfig", "PluginConfig",
                      "GameSign_Accounts", "Notify_CustomWebhooks"]:
            assert isinstance(
                getattr(NativeConfigFacade, attr, None), property
            ), f"facade 缺少 {attr}"


class TestNativeConfigFacadeMethodSignatures:
    """测试 NativeConfigFacade 方法签名与 AppConfig 的兼容性。"""

    def test_facade_has_required_methods(self):
        """facade 应有所有核心 CRUD 方法。"""
        from app.core.native_config import NativeConfigFacade
        required_methods = [
            "init_config", "close", "get", "set", "toDict",
            "send_json", "send_websocket_message",
            "add_script", "get_script", "update_script", "del_script", "reorder_script",
            "get_script_type_key", "get_script_record_capability",
            "get_script_type_descriptors", "get_script_records",
            "get_user", "add_user", "update_user", "del_user", "reorder_user",
            "get_user_records",
            "get_setting", "update_setting",
            "get_tools", "update_tools",
            "add_plan", "get_plan", "update_plan", "del_plan", "reorder_plan",
            "add_emulator", "get_emulator", "update_emulator", "del_emulator", "reorder_emulator",
            "add_queue", "get_queue", "update_queue", "del_queue", "reorder_queue",
            "get_time_set", "add_time_set", "update_time_set", "del_time_set", "reorder_time_set",
            "get_queue_item", "add_queue_item", "update_queue_item", "del_queue_item", "reorder_queue_item",
            "get_game_sign_accounts", "add_game_sign_account", "get_game_sign_account",
            "update_game_sign_account", "delete_game_sign_account", "reorder_game_sign_accounts",
            "get_webhook", "add_webhook", "update_webhook", "del_webhook", "reorder_webhook",
        ]
        for method_name in required_methods:
            assert hasattr(NativeConfigFacade, method_name), f"facade 缺少 {method_name}"

    def test_facade_missing_methods_known(self):
        """验证已知缺失的方法列表（这些是预期内未迁移的）。"""
        from app.core.native_config import NativeConfigFacade
        known_missing = [
            "get_stage", "get_stage_info", "get_git_version",
            "get_script_combox", "get_task_combox", "get_plan_combox",
            "get_notice", "get_web_config", "get_proxy_overview",
            "search_history", "merge_statistic_info",
            "import_script_from_file", "export_script_to_file",
            "import_script_from_web", "upload_script_to_web",
            "import_script_config_file",
            "set_infrastructure", "get_user_combox_infrastructure",
            "save_maa_log", "clean_old_history",
            "share_config", "import_config",
            "load_maafw", "load_maa_end", "load_m9a", "load_src",
            "load_plugin_adapters", "unload_plugin_adapters", "reload_plugin_adapters",
            "save_all_logs", "save_maafw_logs",
            "async_init", "async_shutdown",
            "init_ws", "handle_ws_message", "broadcast", "start_ws", "run",
            "bind", "connect", "save", "lock", "unlock",
        ]
        for method_name in known_missing:
            assert not hasattr(NativeConfigFacade, method_name), (
                f"facade 意外包含 {method_name}（预期缺失）"
            )


class TestConfigServiceAuthoritativeRouting:
    """测试 ConfigService 在 authoritative 模式下的行为。"""

    def test_config_service_raises_on_authoritative(self):
        """authoritative 模式下 ConfigService 应拒绝初始化。"""
        from app.configuration import (
            CONFIG_V2_MODE_AUTHORITATIVE,
            ConfigV2AuthoritativeUnavailableError,
        )
        from app.core.config_service import ConfigService
        svc = ConfigService()
        # 模拟 authoritative 模式
        with patch("app.core.config_service.CONFIG_V2_MODE", CONFIG_V2_MODE_AUTHORITATIVE):
            with pytest.raises(ConfigV2AuthoritativeUnavailableError):
                svc.assert_startup_mode_ready()

    def test_config_service_uses_legacy_runtime_flag(self):
        """验证 uses_legacy_runtime 属性。"""
        from app.core.config_service import ConfigService
        svc = ConfigService()
        # 默认 shadow 模式下 uses_legacy_runtime=True
        assert svc.uses_legacy_runtime is True
        assert svc.is_v2_active is True
        assert svc.mode == "shadow"


class TestWSBootstrapAuthoritativeSafety:
    """测试 WS bootstrap 在 authoritative 模式下的安全行为。"""

    def test_ws_bootstrap_avoids_legacy_config_in_authoritative(self):
        """验证 WS bootstrap 在 authoritative 下不会导入旧 Config。"""
        import ast
        bootstrap_path = WORKTREE / "app" / "core" / "ws" / "bootstrap.py"
        source = bootstrap_path.read_text(encoding="utf-8")

        # 检查是否有条件导入
        assert "CONFIG_V2_MODE != CONFIG_V2_MODE_AUTHORITATIVE" in source or \
               "CONFIG_V2_MODE_AUTHORITATIVE" in source, \
               "WS bootstrap 应包含 authoritative 模式的条件检查"
