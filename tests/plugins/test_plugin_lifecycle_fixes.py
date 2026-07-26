#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

"""插件生命周期收口修复的回归测试。

覆盖：
- realtime 敏感字段脱敏
- manager install_plugin_package 幽灵 distribution 回滚
- manager uninstall_plugin_package orphan 实例清理
- manager stop() 取消 _pending_local_install
- loader reload_instance 与 _sync 竞态保护
- _set_instance_enabled 配置写锁
"""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.plugins.realtime import (
    SENSITIVE_VALUE_REDACTED,
    _redact_instances_sensitive,
    _redact_sensitive_config,
    _redact_sensitive_schema,
)


# ---------------------------------------------------------------------------
# 1. realtime 敏感字段脱敏
# ---------------------------------------------------------------------------


class RealtimeSensitiveRedactionTest(unittest.TestCase):
    """验证 build_plugin_snapshot 推送前对 instances config 的敏感字段脱敏。"""

    def test_redact_sensitive_config_replaces_marked_fields(self) -> None:
        schema = {
            "password": {"type": "string", "sensitive": True},
            "username": {"type": "string", "sensitive": False},
        }
        config = {"password": "secret123", "username": "admin"}
        redacted = _redact_sensitive_config(config, schema)
        self.assertEqual(redacted["password"], SENSITIVE_VALUE_REDACTED)
        self.assertEqual(redacted["username"], "admin")

    def test_redact_sensitive_config_preserves_original(self) -> None:
        schema = {"token": {"type": "string", "sensitive": True}}
        config = {"token": "abc", "data": "keep"}
        original = deepcopy(config)
        _redact_sensitive_config(config, schema)
        # 原始 dict 不应被修改（返回的是副本）
        self.assertEqual(config, original)

    def test_redact_sensitive_config_no_schema_fails_closed(self) -> None:
        config = {"password": "secret"}
        result = _redact_sensitive_config(config, None)
        self.assertEqual(result, {})
        result = _redact_sensitive_config(config, {})
        self.assertEqual(result, {})

    def test_redact_sensitive_config_non_dict_returns_original(self) -> None:
        result = _redact_sensitive_config("not_a_dict", {"x": {}})
        self.assertEqual(result, "not_a_dict")

    def test_redact_sensitive_config_scrubs_nested_and_unknown_fields(self) -> None:
        schema = {
            "account": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "token": {"type": "string", "sensitive": True},
                },
            }
        }
        config = {
            "account": {"name": "alice", "token": "nested-secret"},
            "undeclared": "must-not-leak",
        }

        redacted = _redact_sensitive_config(config, schema)
        self.assertEqual(redacted["account"]["name"], "alice")
        self.assertEqual(redacted["account"]["token"], SENSITIVE_VALUE_REDACTED)
        self.assertEqual(redacted["undeclared"], SENSITIVE_VALUE_REDACTED)

    def test_redact_sensitive_schema_removes_secret_defaults_recursively(self) -> None:
        schema = {
            "account": {
                "properties": {
                    "token": {
                        "sensitive": True,
                        "default": "secret-default",
                        "examples": ["secret-example"],
                    }
                }
            }
        }

        redacted = _redact_sensitive_schema(schema)
        token = redacted["account"]["properties"]["token"]
        self.assertNotIn("default", token)
        self.assertNotIn("examples", token)
        self.assertIn("default", schema["account"]["properties"]["token"])

    def test_schema_builder_exposes_nested_sensitive_properties(self) -> None:
        from pydantic import BaseModel

        from app.plugins.fields import PluginField
        from app.plugins.schema import PluginSchemaManager

        class Account(BaseModel):
            name: str = PluginField(default="alice")
            token: str = PluginField(default="secret-default", sensitive=True)

        class Config(BaseModel):
            account: Account = PluginField(default_factory=Account)

        schema = PluginSchemaManager().build_schema_from_model("nested", Config)
        properties = schema["account"]["properties"]
        self.assertTrue(properties["token"]["sensitive"])

    def test_redact_instances_sensitive_scrubs_by_plugin(self) -> None:
        instances = [
            {
                "id": "inst-1",
                "plugin": "plugin_a",
                "config": {"password": "secret", "name": "test"},
            },
            {
                "id": "inst-2",
                "plugin": "plugin_b",
                "config": {"api_key": "key123"},
            },
        ]
        schemas = {
            "plugin_a": {
                "password": {"sensitive": True},
                "name": {"sensitive": False},
            },
            "plugin_b": {"api_key": {"sensitive": True}},
        }
        redacted = _redact_instances_sensitive(instances, schemas)
        self.assertEqual(redacted[0]["config"]["password"], SENSITIVE_VALUE_REDACTED)
        self.assertEqual(redacted[0]["config"]["name"], "test")
        self.assertEqual(redacted[1]["config"]["api_key"], SENSITIVE_VALUE_REDACTED)

    def test_redact_instances_sensitive_no_schema_hides_config(self) -> None:
        instances = [
            {"id": "inst-1", "plugin": "unknown", "config": {"secret": "val"}},
        ]
        redacted = _redact_instances_sensitive(instances, {})
        self.assertEqual(redacted[0]["config"], {})

    def test_redact_instances_sensitive_preserves_original(self) -> None:
        instances = [
            {"id": "inst-1", "plugin": "p", "config": {"password": "secret"}},
        ]
        schemas = {"p": {"password": {"sensitive": True}}}
        original = deepcopy(instances)
        _redact_instances_sensitive(instances, schemas)
        self.assertEqual(instances, original)


# ---------------------------------------------------------------------------
# 2. manager stop() 取消 _pending_local_install
# ---------------------------------------------------------------------------


class ManagerStopCancelsPendingInstallTest(unittest.TestCase):
    """验证 stop() 取消 _pending_local_install 后台任务。"""

    def test_stop_cancels_pending_install_task(self) -> None:
        from app.plugins.manager import _PluginManager

        manager = _PluginManager.__new__(_PluginManager)
        manager.started = True
        manager.events = MagicMock()
        manager.events.clear = MagicMock()
        manager.loader = MagicMock()
        manager.loader.unload_all = AsyncMock()

        cancelled = asyncio.Event()

        async def long_running():
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                cancelled.set()
                raise

        loop = asyncio.new_event_loop()
        try:
            manager._pending_local_install = loop.create_task(long_running())
            loop.run_until_complete(manager.stop())
            self.assertTrue(cancelled.is_set())
            self.assertIsNone(manager._pending_local_install)
        finally:
            loop.close()

    def test_stop_without_pending_install(self) -> None:
        from app.plugins.manager import _PluginManager

        manager = _PluginManager.__new__(_PluginManager)
        manager.started = True
        manager.events = MagicMock()
        manager.events.clear = MagicMock()
        manager.loader = MagicMock()
        manager.loader.unload_all = AsyncMock()
        manager._pending_local_install = None

        asyncio.run(manager.stop())
        self.assertIsNone(manager._pending_local_install)

    def test_stop_when_not_started_is_noop(self) -> None:
        from app.plugins.manager import _PluginManager

        manager = _PluginManager.__new__(_PluginManager)
        manager.started = False
        # 不应访问任何其他属性
        asyncio.run(manager.stop())


# ---------------------------------------------------------------------------
# 3. loader reload_instance 与 _sync 竞态保护
# ---------------------------------------------------------------------------


class LoaderReloadRaceProtectionTest(unittest.TestCase):
    """验证 reload_instance 等待 _sync 完成并设置 _busy。"""

    def test_reload_waits_for_in_flight_sync(self) -> None:
        from app.plugins.loader import PluginLoader

        loader = PluginLoader.__new__(PluginLoader)
        loader._busy = False
        loader._pulse = set()
        loader._task = None
        loader._reload_lock = asyncio.Lock()
        loader.records = {}

        sync_completed = asyncio.Event()

        async def in_flight_sync():
            sync_completed.set()
            await asyncio.sleep(0.05)

        async def scenario():
            loader._task = asyncio.get_running_loop().create_task(in_flight_sync())
            # reload_instance 会先 await _task
            # 由于 records 为空，old_record 为 None，load_instance 会被调用
            # 我们 mock load_instance 和 unload_instance 来避免实际加载
            loader.unload_instance = AsyncMock()
            loader.load_instance = AsyncMock(
                return_value=SimpleNamespace(
                    status="active",
                    plugin_instance=None,
                    generation=0,
                    reload_count=0,
                )
            )
            loader._mark_lifecycle_phase = MagicMock()
            loader._call_optional_lifecycle_method = AsyncMock()

            await loader.reload_instance(
                instance_id="test",
                plugin_name="test_plugin",
                instance_name="Test",
                config={},
            )

        asyncio.run(scenario())
        self.assertTrue(sync_completed.is_set())
        self.assertFalse(loader._busy)

    def test_reload_sets_busy_during_execution(self) -> None:
        from app.plugins.loader import PluginLoader

        loader = PluginLoader.__new__(PluginLoader)
        loader._busy = False
        loader._pulse = set()
        loader._task = None
        loader._reload_lock = asyncio.Lock()
        loader.records = {}

        busy_observed = asyncio.Event()

        async def mock_load(**kwargs):
            # 在 load_instance 执行期间，_busy 应为 True
            if loader._busy:
                busy_observed.set()
            return SimpleNamespace(
                status="active",
                plugin_instance=None,
                generation=0,
                reload_count=0,
            )

        async def scenario():
            loader.unload_instance = AsyncMock()
            loader.load_instance = mock_load
            loader._mark_lifecycle_phase = MagicMock()
            loader._call_optional_lifecycle_method = AsyncMock()

            await loader.reload_instance(
                instance_id="test",
                plugin_name="test_plugin",
                instance_name="Test",
                config={},
            )

        asyncio.run(scenario())
        self.assertTrue(busy_observed.is_set())
        self.assertFalse(loader._busy)

    def test_concurrent_reloads_are_serialized(self) -> None:
        from app.plugins.loader import PluginLoader

        loader = PluginLoader.__new__(PluginLoader)
        loader._reload_lock = asyncio.Lock()
        active = 0
        max_active = 0

        async def fake_reload(**_kwargs):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.02)
            active -= 1
            return SimpleNamespace(status="active")

        loader._reload_instance = fake_reload

        async def scenario():
            await asyncio.gather(
                loader.reload_instance(
                    instance_id="one",
                    plugin_name="plugin",
                    instance_name="One",
                    config={},
                ),
                loader.reload_instance(
                    instance_id="two",
                    plugin_name="plugin",
                    instance_name="Two",
                    config={},
                ),
            )

        asyncio.run(scenario())
        self.assertEqual(max_active, 1)


# ---------------------------------------------------------------------------
# 4. _set_instance_enabled 配置写锁
# ---------------------------------------------------------------------------


class ConfigWriteLockTest(unittest.TestCase):
    """验证 _set_instance_enabled 使用配置写锁。"""

    def test_set_instance_enabled_acquires_lock(self) -> None:
        from app.plugins.manager import _PluginManager

        manager = _PluginManager.__new__(_PluginManager)
        manager._config_write_lock = asyncio.Lock()
        manager.plugins_dir = MagicMock()
        manager.config_store = MagicMock()
        manager.config_store.get_root = AsyncMock(
            return_value={
                "instances": [
                    {"id": "inst-1", "plugin": "test", "enabled": False}
                ]
            }
        )
        manager.config_store.save_root = AsyncMock()
        manager.is_system_plugin = MagicMock(return_value=False)

        async def scenario():
            snapshot = {"test": SimpleNamespace()}
            result = await manager._set_instance_enabled(
                "inst-1", True, discovered=snapshot
            )
            return result

        result = asyncio.run(scenario())
        self.assertTrue(result)
        manager.config_store.save_root.assert_called_once()


# ---------------------------------------------------------------------------
# 5. install_plugin_package 幽灵 distribution 回滚
# ---------------------------------------------------------------------------


class InstallPackageRollbackTest(unittest.TestCase):
    """验证 install_plugin_package 在未发现 entry point 时回滚。"""

    def test_install_rolls_back_when_no_entry_point(self) -> None:
        from app.plugins.manager import _PluginManager

        manager = _PluginManager.__new__(_PluginManager)
        manager._operation_lock = asyncio.Lock()
        manager._pending_local_install = None
        manager.plugins_dir = MagicMock()
        manager._normalize_distribution_name = lambda name: _PluginManager._normalize_distribution_name(name)
        manager._validate_package_name = _PluginManager._validate_package_name.__get__(manager, _PluginManager)
        manager.is_system_plugin_package = MagicMock(return_value=False)
        manager._cleanup_package_from_target = MagicMock(return_value=True)
        manager.invalidate_discover_cache = MagicMock()

        # 模拟安装后未发现任何插件
        async def mock_discover(force=False, **kwargs):
            return {}

        manager.discover_plugins = mock_discover
        manager._ensure_local_projects_installed = AsyncMock()
        manager._discover_plugins = MagicMock(return_value={})
        manager._ensure_default_instances = AsyncMock()
        manager._get_valid_discover_cache = MagicMock(return_value=None)
        manager._discover_cache = None
        manager._discover_cache_time = 0.0
        manager._discover_cache_plugins_dir = None
        manager._discover_cache_ttl = 30.0
        manager._discover_lock = asyncio.Lock()

        with (
            patch(
                "app.plugins.manager.uv_pip_install_with_mirror_fallback",
                new_callable=AsyncMock,
            ),
            patch("app.plugins.manager.uv_pip_uninstall", new_callable=AsyncMock) as mock_uninstall,
            patch("app.plugins.manager.get_pypi_site_packages_dir") as mock_target,
        ):
            mock_target.return_value = MagicMock()
            mock_uninstall.return_value = SimpleNamespace(returncode=0)

            with self.assertRaises(RuntimeError) as ctx:
                asyncio.run(manager.install_plugin_package("test-plugin"))

            self.assertIn("未发现该 distribution 的插件入口点", str(ctx.exception))
            self.assertIn("回滚完成", str(ctx.exception))
            # 验证回滚调用了 _cleanup_package_from_target
            manager._cleanup_package_from_target.assert_called_once()
            # 验证回滚调用了 uv_pip_uninstall
            mock_uninstall.assert_called_once()

    def test_install_rejects_system_package(self) -> None:
        from app.plugins.manager import _PluginManager

        manager = _PluginManager.__new__(_PluginManager)
        manager._operation_lock = asyncio.Lock()
        manager._pending_local_install = None
        manager._validate_package_name = _PluginManager._validate_package_name.__get__(manager, _PluginManager)
        manager.is_system_plugin_package = MagicMock(return_value=True)

        with self.assertRaises(ValueError) as ctx:
            asyncio.run(manager.install_plugin_package("auto-mas-core"))

        self.assertIn("不可安装", str(ctx.exception))

    def test_install_discovery_failure_is_rolled_back(self) -> None:
        from app.plugins.manager import _PluginManager

        manager = _PluginManager.__new__(_PluginManager)
        manager._operation_lock = asyncio.Lock()
        manager._pending_local_install = None
        manager.plugins_dir = MagicMock()
        manager._validate_package_name = _PluginManager._validate_package_name.__get__(manager, _PluginManager)
        manager._normalize_distribution_name = _PluginManager._normalize_distribution_name
        manager.is_system_plugin_package = MagicMock(return_value=False)
        manager._cleanup_package_from_target = MagicMock(return_value=True)
        manager.invalidate_discover_cache = MagicMock()
        manager.discover_plugins = AsyncMock(side_effect=RuntimeError("broken metadata"))

        with (
            patch(
                "app.plugins.manager.uv_pip_install_with_mirror_fallback",
                new_callable=AsyncMock,
            ),
            patch(
                "app.plugins.manager.uv_pip_uninstall",
                new_callable=AsyncMock,
                return_value=SimpleNamespace(returncode=0, stderr="", stdout=""),
            ) as mock_uninstall,
            patch("app.plugins.manager.get_pypi_site_packages_dir") as mock_target,
        ):
            mock_target.return_value = MagicMock()
            with self.assertRaisesRegex(RuntimeError, "broken metadata.*回滚完成"):
                asyncio.run(manager.install_plugin_package("test-plugin"))

        manager._cleanup_package_from_target.assert_called_once()
        mock_uninstall.assert_awaited_once()

    def test_package_and_enabled_operations_are_serialized(self) -> None:
        from app.plugins.manager import _PluginManager

        manager = _PluginManager.__new__(_PluginManager)
        manager._operation_lock = asyncio.Lock()
        manager._pending_local_install = None
        active = 0
        max_active = 0

        async def enter_operation(*_args, **_kwargs):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.02)
            active -= 1

        manager._install_plugin_package = enter_operation
        manager._apply_instance_enabled = enter_operation

        async def scenario():
            await asyncio.gather(
                manager.install_plugin_package("plugin-one"),
                manager.apply_instance_enabled("instance-one", True),
            )

        asyncio.run(scenario())
        self.assertEqual(max_active, 1)


class PackageCleanupSafetyTest(unittest.TestCase):
    """验证卸载只清理目标 distribution 自己的文件。"""

    def test_uninstall_rejects_system_package(self) -> None:
        from app.plugins.manager import _PluginManager

        manager = _PluginManager.__new__(_PluginManager)
        manager._operation_lock = asyncio.Lock()
        manager._pending_local_install = None
        manager._validate_package_name = _PluginManager._validate_package_name.__get__(
            manager,
            _PluginManager,
        )
        manager.is_system_plugin_package = MagicMock(return_value=True)

        with self.assertRaisesRegex(ValueError, "系统插件包不可卸载"):
            asyncio.run(manager.uninstall_plugin_package("auto-mas-core"))

    def test_cleanup_preserves_shared_namespace_files(self) -> None:
        from app.plugins.manager import _PluginManager

        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "site-packages"
            owned = target / "shared_namespace" / "owned.py"
            shared = target / "shared_namespace" / "other_distribution.py"
            metadata = target / "shared_plugin-1.0.0.dist-info" / "METADATA"
            for path in (owned, shared, metadata):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(path.name, encoding="utf-8")

            distribution = SimpleNamespace(
                name="shared-plugin",
                version="1.0.0",
                files=[
                    Path("shared_namespace/owned.py"),
                    Path("shared_plugin-1.0.0.dist-info/METADATA"),
                ],
                locate_file=lambda item: target / item,
            )
            manager = _PluginManager.__new__(_PluginManager)
            manager._iter_target_distributions = MagicMock(
                return_value=[distribution]
            )

            removed = manager._cleanup_package_from_target("shared-plugin", target)

            self.assertTrue(removed)
            self.assertFalse(owned.exists())
            self.assertTrue(shared.exists())

    def test_cleanup_rejects_record_path_outside_target(self) -> None:
        from app.plugins.manager import _PluginManager

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "site-packages"
            target.mkdir()
            outside = root / "outside.txt"
            outside.write_text("preserve", encoding="utf-8")
            distribution = SimpleNamespace(
                name="unsafe-plugin",
                version="1.0.0",
                files=[Path("../outside.txt")],
                locate_file=lambda item: target / item,
            )
            manager = _PluginManager.__new__(_PluginManager)
            manager._iter_target_distributions = MagicMock(
                return_value=[distribution]
            )

            with self.assertRaisesRegex(RuntimeError, "site-packages 之外"):
                manager._cleanup_package_from_target("unsafe-plugin", target)
            self.assertEqual(outside.read_text(encoding="utf-8"), "preserve")


# ---------------------------------------------------------------------------
# 6. uninstall_plugin_package orphan 实例清理
# ---------------------------------------------------------------------------


class UninstallOrphanCleanupTest(unittest.TestCase):
    """验证 uninstall_plugin_package 清理 orphan 实例配置。"""

    def test_cleanup_orphan_instances_removes_config(self) -> None:
        from app.plugins.manager import _PluginManager

        manager = _PluginManager.__new__(_PluginManager)
        manager.plugins_dir = MagicMock()
        manager._config_write_lock = asyncio.Lock()
        manager.config_store = MagicMock()
        manager.config_store.get_root = AsyncMock(
            return_value={
                "instances": [
                    {"id": "inst-1", "plugin": "removed_plugin", "config": {}},
                    {"id": "inst-2", "plugin": "kept_plugin", "config": {}},
                ]
            }
        )
        manager.config_store.save_root = AsyncMock()
        manager.loader = MagicMock()
        manager.loader.records = {}

        with patch("app.plugins.manager.schedule_plugin_snapshot"):
            asyncio.run(
                manager._cleanup_orphan_instances(
                    {"removed_plugin"}, {"kept_plugin": SimpleNamespace()}
                )
            )

        # 验证 save_root 被调用，且 instances 只保留了 kept_plugin
        manager.config_store.save_root.assert_called_once()
        saved_root = manager.config_store.save_root.call_args[0][1]
        remaining_plugins = [i["plugin"] for i in saved_root["instances"]]
        self.assertIn("kept_plugin", remaining_plugins)
        self.assertNotIn("removed_plugin", remaining_plugins)

    def test_cleanup_orphan_instances_noop_when_empty(self) -> None:
        from app.plugins.manager import _PluginManager

        manager = _PluginManager.__new__(_PluginManager)
        manager._config_write_lock = asyncio.Lock()
        manager.config_store = MagicMock()

        asyncio.run(manager._cleanup_orphan_instances(set(), {}))
        manager.config_store.get_root.assert_not_called()

    def test_cleanup_orphan_instances_unloads_runtime(self) -> None:
        from app.plugins.manager import _PluginManager

        manager = _PluginManager.__new__(_PluginManager)
        manager.plugins_dir = MagicMock()
        manager._config_write_lock = asyncio.Lock()
        manager.config_store = MagicMock()
        manager.config_store.get_root = AsyncMock(
            return_value={"instances": []}
        )
        manager.config_store.save_root = AsyncMock()
        manager.loader = MagicMock()
        manager.loader.records = {
            "inst-1": SimpleNamespace(plugin_name="removed_plugin"),
        }
        manager.loader.unload_instance = AsyncMock()

        with patch("app.plugins.manager.schedule_plugin_snapshot"):
            asyncio.run(
                manager._cleanup_orphan_instances(
                    {"removed_plugin"}, {}
                )
            )

        manager.loader.unload_instance.assert_called_once_with(
            "inst-1", stop_reason="uninstall_orphan"
        )
        self.assertNotIn("inst-1", manager.loader.records)

    def test_cleanup_orphan_instances_reports_save_failure(self) -> None:
        from app.plugins.manager import _PluginManager

        manager = _PluginManager.__new__(_PluginManager)
        manager.plugins_dir = MagicMock()
        manager._config_write_lock = asyncio.Lock()
        manager.config_store = MagicMock()
        manager.config_store.get_root = AsyncMock(
            return_value={
                "instances": [
                    {"id": "inst-1", "plugin": "removed_plugin", "config": {}},
                ]
            }
        )
        manager.config_store.save_root = AsyncMock(side_effect=OSError("disk full"))
        manager.loader = MagicMock()
        manager.loader.records = {}

        with self.assertRaisesRegex(RuntimeError, "orphan 清理未落盘"):
            asyncio.run(
                manager._cleanup_orphan_instances(
                    {"removed_plugin"},
                    {},
                )
            )


# ---------------------------------------------------------------------------
# 7. API 实例配置与运行态事务
# ---------------------------------------------------------------------------


class _MemoryPluginConfigStore:
    """为 manager 事务测试提供可控的深拷贝持久层。"""

    def __init__(
        self,
        root: dict,
        *,
        fail_save_calls: set[int] | None = None,
        io_delay: float = 0.0,
    ) -> None:
        self.root = deepcopy(root)
        self.fail_save_calls = set(fail_save_calls or set())
        self.io_delay = io_delay
        self.save_calls = 0
        self._id_counter = 0

    async def get_root(self, *_args, **_kwargs):
        if self.io_delay:
            await asyncio.sleep(self.io_delay)
        return deepcopy(self.root)

    async def save_root(self, _plugins_dir, root, **_kwargs):
        self.save_calls += 1
        if self.io_delay:
            await asyncio.sleep(self.io_delay)
        if self.save_calls in self.fail_save_calls:
            raise OSError(f"save failure #{self.save_calls}")
        self.root = deepcopy(root)

    def load_effective_config(self, _plugin_name, config):
        return deepcopy(config)

    def generate_instance_id(self, plugin_name: str) -> str:
        self._id_counter += 1
        return f"{plugin_name}:tx{self._id_counter}"


def _build_transaction_manager(
    root: dict,
    *,
    started: bool,
    store: _MemoryPluginConfigStore | None = None,
):
    from app.plugins.manager import _PluginManager

    manager = _PluginManager.__new__(_PluginManager)
    manager._operation_lock = asyncio.Lock()
    manager._config_write_lock = asyncio.Lock()
    manager.plugins_dir = Path("plugins")
    manager.started = started
    manager.config_store = store or _MemoryPluginConfigStore(root)
    manager.loader = MagicMock()
    manager.loader.plugins_dir = manager.plugins_dir
    manager.loader.records = {}
    manager.loader.load_instance = AsyncMock(
        return_value=SimpleNamespace(status="active", error=None)
    )
    manager.loader.reload_instance = AsyncMock(
        return_value=SimpleNamespace(status="active", error=None)
    )
    manager.loader.unload_instance = AsyncMock()
    manager.discover_plugins = AsyncMock(
        return_value={
            "demo": SimpleNamespace(),
            "other": SimpleNamespace(),
        }
    )
    manager.is_system_plugin = MagicMock(return_value=False)
    manager.ensure_instance_can_delete = AsyncMock()
    return manager


class PluginInstanceTransactionTest(unittest.TestCase):
    """验证 add/update/delete 配置与运行态具有一致的事务边界。"""

    def test_partial_config_update_preserves_omitted_nested_secrets(self) -> None:
        root = {
            "version": 1,
            "instances": [
                {
                    "id": "demo:one",
                    "plugin": "demo",
                    "enabled": False,
                    "name": "One",
                    "config": {
                        "account": {
                            "name": "before",
                            "token": "keep-this-secret",
                        },
                        "retry": 2,
                    },
                }
            ],
        }
        manager = _build_transaction_manager(root, started=False)

        asyncio.run(
            manager.update_instance_transaction(
                instance_id="demo:one",
                config={"account": {"name": "after"}},
            )
        )

        self.assertEqual(
            manager.config_store.root["instances"][0]["config"],
            {
                "account": {
                    "name": "after",
                    "token": "keep-this-secret",
                },
                "retry": 2,
            },
        )

    def test_partial_config_update_allows_explicit_secret_clear(self) -> None:
        root = {
            "version": 1,
            "instances": [
                {
                    "id": "demo:one",
                    "plugin": "demo",
                    "enabled": False,
                    "name": "One",
                    "config": {"account": {"token": "old-secret"}},
                }
            ],
        }
        manager = _build_transaction_manager(root, started=False)

        asyncio.run(
            manager.update_instance_transaction(
                instance_id="demo:one",
                config={"account": {"token": ""}},
            )
        )

        self.assertEqual(
            manager.config_store.root["instances"][0]["config"],
            {"account": {"token": ""}},
        )

    def test_concurrent_updates_do_not_lose_each_others_writes(self) -> None:
        root = {
            "version": 1,
            "instances": [
                {
                    "id": "demo:one",
                    "plugin": "demo",
                    "enabled": False,
                    "name": "One",
                    "config": {},
                },
                {
                    "id": "demo:two",
                    "plugin": "demo",
                    "enabled": False,
                    "name": "Two",
                    "config": {},
                },
            ],
        }
        store = _MemoryPluginConfigStore(root, io_delay=0.01)
        manager = _build_transaction_manager(root, started=False, store=store)

        async def scenario() -> None:
            await asyncio.gather(
                manager.update_instance_transaction(
                    instance_id="demo:one",
                    name="One updated",
                ),
                manager.update_instance_transaction(
                    instance_id="demo:two",
                    name="Two updated",
                ),
            )

        asyncio.run(scenario())
        names = {item["id"]: item["name"] for item in store.root["instances"]}
        self.assertEqual(names["demo:one"], "One updated")
        self.assertEqual(names["demo:two"], "Two updated")

    def test_create_runtime_failure_removes_persisted_instance(self) -> None:
        root = {"version": 1, "instances": []}
        manager = _build_transaction_manager(root, started=True)
        manager.loader.reload_instance = AsyncMock(
            return_value=SimpleNamespace(
                status="unloaded",
                error="activation failed",
            )
        )

        with self.assertRaisesRegex(RuntimeError, "配置与运行态已回滚"):
            asyncio.run(
                manager.create_instance_transaction(
                    plugin_name="demo",
                    name="Broken",
                    enabled=True,
                    config={"token": "value"},
                )
            )

        self.assertEqual(manager.config_store.root["instances"], [])
        manager.loader.unload_instance.assert_awaited_once_with(
            "demo:tx1",
            stop_reason="rollback:新增",
        )

    def test_update_runtime_failure_restores_old_config_and_runtime(self) -> None:
        root = {
            "version": 1,
            "instances": [
                {
                    "id": "demo:one",
                    "plugin": "demo",
                    "enabled": True,
                    "name": "One",
                    "config": {"value": "old"},
                }
            ],
        }
        manager = _build_transaction_manager(root, started=True)
        manager.loader.reload_instance = AsyncMock(
            side_effect=[
                SimpleNamespace(status="unloaded", error="new config rejected"),
                SimpleNamespace(status="active", error=None),
            ]
        )

        with self.assertRaisesRegex(RuntimeError, "配置与运行态已回滚"):
            asyncio.run(
                manager.update_instance_transaction(
                    instance_id="demo:one",
                    config={"value": "new"},
                )
            )

        saved = manager.config_store.root["instances"][0]
        self.assertEqual(saved["config"], {"value": "old"})
        calls = manager.loader.reload_instance.await_args_list
        self.assertEqual(calls[0].kwargs["config"], {"value": "new"})
        self.assertEqual(calls[1].kwargs["config"], {"value": "old"})
        self.assertEqual(calls[1].kwargs["reason"], "rollback:更新")

    def test_update_reports_incomplete_rollback(self) -> None:
        root = {
            "version": 1,
            "instances": [
                {
                    "id": "demo:one",
                    "plugin": "demo",
                    "enabled": True,
                    "name": "One",
                    "config": {"value": "old"},
                }
            ],
        }
        store = _MemoryPluginConfigStore(root, fail_save_calls={2})
        manager = _build_transaction_manager(root, started=True, store=store)
        manager.loader.reload_instance = AsyncMock(
            side_effect=[
                SimpleNamespace(status="unloaded", error="new config rejected"),
                SimpleNamespace(status="active", error=None),
            ]
        )

        with self.assertRaisesRegex(RuntimeError, "回滚不完整.*配置回滚失败"):
            asyncio.run(
                manager.update_instance_transaction(
                    instance_id="demo:one",
                    config={"value": "new"},
                )
            )
        self.assertEqual(store.root["instances"][0]["config"], {"value": "new"})

    def test_delete_unload_failure_restores_instance_and_runtime(self) -> None:
        root = {
            "version": 1,
            "instances": [
                {
                    "id": "demo:one",
                    "plugin": "demo",
                    "enabled": True,
                    "name": "One",
                    "config": {"value": "old"},
                }
            ],
        }
        manager = _build_transaction_manager(root, started=True)
        failed_record = SimpleNamespace(status="active", error=None)
        manager.loader.records["demo:one"] = failed_record

        async def fail_unload(*_args, **_kwargs):
            # PluginLoader 会吞掉 on_stop 异常并把失败写回 record。
            failed_record.status = "error"
            failed_record.error = "RuntimeError: stop failed"

        manager.loader.unload_instance = AsyncMock(side_effect=fail_unload)

        with self.assertRaisesRegex(RuntimeError, "配置与运行态已回滚"):
            asyncio.run(manager.delete_instance_transaction("demo:one"))

        self.assertEqual(len(manager.config_store.root["instances"]), 1)
        manager.loader.reload_instance.assert_awaited_once()
        rollback_call = manager.loader.reload_instance.await_args
        self.assertEqual(rollback_call.kwargs["reason"], "rollback:删除")

    def test_delete_success_unloads_inside_manager_transaction(self) -> None:
        root = {
            "version": 1,
            "instances": [
                {
                    "id": "demo:one",
                    "plugin": "demo",
                    "enabled": True,
                    "name": "One",
                    "config": {},
                }
            ],
        }
        manager = _build_transaction_manager(root, started=True)

        asyncio.run(manager.delete_instance_transaction("demo:one"))

        self.assertEqual(manager.config_store.root["instances"], [])
        manager.ensure_instance_can_delete.assert_awaited_once()
        manager.loader.unload_instance.assert_awaited_once_with(
            "demo:one",
            stop_reason="manager.delete_instance",
        )


class PluginInstanceApiDelegationTest(unittest.TestCase):
    """验证 HTTP/WS 共用的端点只调用 manager 事务入口。"""

    def test_api_endpoints_delegate_mutations_to_manager(self) -> None:
        from app.api import plugins as plugins_api

        instance = {
            "id": "demo:one",
            "plugin": "demo",
            "enabled": True,
            "name": "One",
            "config": {},
        }

        async def scenario():
            with (
                patch.object(
                    plugins_api.PluginManager,
                    "create_instance_transaction",
                    new_callable=AsyncMock,
                    return_value=instance,
                ) as create,
                patch.object(
                    plugins_api.PluginManager,
                    "update_instance_transaction",
                    new_callable=AsyncMock,
                    return_value={"snapshot_reason": "api.plugins.update"},
                ) as update,
                patch.object(
                    plugins_api.PluginManager,
                    "delete_instance_transaction",
                    new_callable=AsyncMock,
                ) as delete,
                patch.object(
                    plugins_api.PluginManager.loader,
                    "unload_instance",
                    new_callable=AsyncMock,
                ) as direct_unload,
                patch.object(
                    plugins_api.config_store,
                    "get_root",
                    new_callable=AsyncMock,
                ) as direct_get,
                patch.object(
                    plugins_api.config_store,
                    "save_root",
                    new_callable=AsyncMock,
                ) as direct_save,
                patch.object(
                    plugins_api,
                    "publish_plugin_snapshot",
                    new_callable=AsyncMock,
                ),
                patch.object(plugins_api, "_schedule_update_snapshot") as schedule,
            ):
                add_out = await plugins_api.add_plugin_instance(
                    plugins_api.PluginAddIn(plugin="demo", name="One")
                )
                update_out = await plugins_api.update_plugin_instance(
                    plugins_api.PluginUpdateIn(
                        instanceId="demo:one",
                        enabled=False,
                    )
                )
                delete_out = await plugins_api.delete_plugin_instance(
                    plugins_api.PluginDeleteIn(instanceId="demo:one")
                )

                self.assertEqual(add_out.code, 200)
                self.assertEqual(update_out.code, 200)
                self.assertEqual(delete_out.code, 200)
                create.assert_awaited_once()
                update.assert_awaited_once()
                delete.assert_awaited_once()
                schedule.assert_called_once_with(
                    "demo:one",
                    reason="api.plugins.update",
                )
                direct_get.assert_not_awaited()
                direct_save.assert_not_awaited()
                direct_unload.assert_not_awaited()

        asyncio.run(scenario())

    def test_api_preserves_error_body_contract(self) -> None:
        from app.api import plugins as plugins_api

        async def scenario():
            with patch.object(
                plugins_api.PluginManager,
                "update_instance_transaction",
                new_callable=AsyncMock,
                side_effect=RuntimeError("回滚不完整: runtime restore failed"),
            ):
                return await plugins_api.update_plugin_instance(
                    plugins_api.PluginUpdateIn(
                        instanceId="demo:one",
                        config={"value": "new"},
                    )
                )

        result = asyncio.run(scenario())
        self.assertEqual(result.code, 500)
        self.assertEqual(result.status, "error")
        self.assertIn("回滚不完整", result.message)




class ServiceFacadeDependencyTest(unittest.TestCase):
    """验证插件门面与注册中心使用一致的依赖名归一化语义。"""

    def test_names_supports_all_public_input_shapes(self) -> None:
        from app.plugins.context import ServiceFacade

        cases = (
            (None, set()),
            ("  alpha  ", {"alpha"}),
            ([" alpha ", "beta", ""], {"alpha", "beta"}),
            ((" alpha ", "beta", None), {"alpha", "beta"}),
            ({" alpha ", "beta", ""}, {"alpha", "beta"}),
        )
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(ServiceFacade._names(raw), expected)

    def test_list_dependencies_wait_until_services_exist(self) -> None:
        from app.plugins.context import ServiceFacade
        from app.plugins.service_registry import ServiceRegistry

        registry = ServiceRegistry()
        ready = MagicMock()
        facade = ServiceFacade(
            ctx=object(),
            plugin_name="consumer",
            instance_id="consumer:one",
            logger=MagicMock(),
            registry=registry,
        )

        facade.inject(needs=["emulator", "foo"], ready=ready)

        self.assertEqual(facade.miss(), {"emulator", "foo"})
        ready.assert_not_called()
        registry.set("emulator", object(), "emulator:provider")
        self.assertEqual(facade.miss(), {"foo"})
        ready.assert_not_called()
        registry.set("foo", object(), "foo:provider")
        self.assertEqual(facade.miss(), set())
        ready.assert_called_once()


class _CoordinatedPluginConfigStore:
    """暴露首个读快照暂停点，稳定复现无锁读改写覆盖竞态。"""

    def __init__(self, root: dict) -> None:
        self.root = deepcopy(root)
        self.first_read_started = asyncio.Event()
        self.allow_first_read = asyncio.Event()
        self.read_count = 0

    async def get_root(self, *_args, **_kwargs) -> dict:
        self.read_count += 1
        snapshot = deepcopy(self.root)
        if self.read_count == 1:
            self.first_read_started.set()
            await self.allow_first_read.wait()
        return snapshot

    async def save_root(self, _plugins_dir, root, **_kwargs) -> None:
        await asyncio.sleep(0)
        self.root = deepcopy(root)


class PluginRepairResilienceTest(unittest.TestCase):
    """验证失效实例修复与用户写入共享事务锁，并在关闭时被回收。"""

    def test_repair_serializes_with_concurrent_config_write(self) -> None:
        from app.plugins.manager import _PluginManager

        async def scenario() -> None:
            store = _CoordinatedPluginConfigStore(
                {
                    "version": 1,
                    "instances": [
                        {
                            "id": "demo:broken",
                            "plugin": "demo",
                            "enabled": True,
                            "name": "Old name",
                            "config": {},
                        }
                    ],
                }
            )
            manager = _PluginManager.__new__(_PluginManager)
            manager.loader = SimpleNamespace(
                startup_failed_instances={"demo:broken": "activation failed"},
                startup_missing_instances=set(),
            )
            manager.config_store = store
            manager.plugins_dir = Path("plugins")
            manager._config_write_lock = asyncio.Lock()
            writer_entered = asyncio.Event()

            async def concurrent_write() -> None:
                async with manager._config_write_lock:
                    writer_entered.set()
                    root = await store.get_root(manager.plugins_dir, {})
                    root["instances"][0]["name"] = "New name"
                    await store.save_root(manager.plugins_dir, root)

            with patch("app.plugins.manager.schedule_plugin_snapshot"):
                repair = asyncio.create_task(
                    manager._repair_invalid_instances_after_start({})
                )
                await asyncio.wait_for(store.first_read_started.wait(), timeout=1)
                writer = asyncio.create_task(concurrent_write())
                await asyncio.sleep(0)
                self.assertFalse(writer_entered.is_set())
                store.allow_first_read.set()
                await asyncio.gather(repair, writer)

            instance = store.root["instances"][0]
            self.assertFalse(instance["enabled"])
            self.assertEqual(instance["name"], "New name")

        asyncio.run(scenario())

    def test_stop_cancels_pending_repair_task(self) -> None:
        from app.plugins.manager import _PluginManager

        async def scenario() -> None:
            manager = _PluginManager.__new__(_PluginManager)
            manager.started = True
            manager.events = MagicMock()
            manager.loader = SimpleNamespace(unload_all=AsyncMock())
            manager._pending_local_install = None
            cancelled = asyncio.Event()

            async def long_running_repair() -> None:
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    cancelled.set()
                    raise

            manager._pending_repair = asyncio.create_task(long_running_repair())
            await asyncio.sleep(0)
            await manager.stop()

            self.assertTrue(cancelled.is_set())
            self.assertIsNone(manager._pending_repair)
            manager.loader.unload_all.assert_awaited_once()

        asyncio.run(scenario())

if __name__ == "__main__":
    unittest.main()
