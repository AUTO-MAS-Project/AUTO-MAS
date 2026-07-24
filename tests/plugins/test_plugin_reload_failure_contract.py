"""插件热重载失败状态与 API 契约的回归测试。"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import AsyncMock, MagicMock, call, patch


def _build_manager(
    instances: list[SimpleNamespace],
    reload_results: list[SimpleNamespace],
):
    from app.plugins.manager import _PluginManager

    manager = _PluginManager.__new__(_PluginManager)
    manager._operation_lock = asyncio.Lock()
    manager._config_write_lock = asyncio.Lock()
    manager.plugins_dir = Path("plugins")
    manager.loader = MagicMock()
    manager.loader.plugins_dir = manager.plugins_dir
    manager.loader.records = {}
    manager.loader.reload_instance = AsyncMock(side_effect=reload_results)
    manager.loader.unload_instance = AsyncMock()
    manager.discover_plugins = AsyncMock(return_value={"demo": SimpleNamespace()})
    manager.config_store = MagicMock()
    manager.config_store.load_instances = AsyncMock(return_value=instances)
    return manager


class LoaderReloadFailureContractTest(TestCase):
    """验证加载器不会把失败重载伪装成 closed/unloaded。"""

    def test_reload_failure_preserves_error_status_after_cleanup(self) -> None:
        from app.plugins.loader import PluginLoader

        loader = PluginLoader.__new__(PluginLoader)
        loader._busy = False
        loader._pulse = set()
        loader._task = None
        loader._reload_lock = asyncio.Lock()
        loader.records = {}
        loader.unload_instance = AsyncMock()
        loader.load_instance = AsyncMock(
            return_value=SimpleNamespace(
                status="error",
                error="activation failed",
                plugin_instance=None,
            )
        )
        loader._mark_lifecycle_phase = MagicMock()

        def mark_error(record: SimpleNamespace, message: str) -> None:
            record.status = "error"
            record.error = message

        loader._mark_error = mark_error

        record = asyncio.run(
            loader.reload_instance(
                instance_id="demo:one",
                plugin_name="demo",
                instance_name="Demo",
                config={},
                reason="test",
            )
        )

        self.assertEqual(record.status, "error")
        self.assertIn("activation failed", record.error)
        loader.unload_instance.assert_has_awaits(
            [
                call("demo:one", stop_reason="reload:test"),
                call("demo:one"),
            ]
        )
        self.assertIn(call(record, "reload_failed"), loader._mark_lifecycle_phase.call_args_list)


class ManagerReloadFailureContractTest(TestCase):
    """验证管理器恢复失败后仍向 API 暴露失败结果。"""

    @staticmethod
    def _instance(instance_id: str) -> SimpleNamespace:
        return SimpleNamespace(
            id=instance_id,
            plugin="demo",
            name=instance_id,
            config={"value": instance_id},
            enabled=True,
        )

    def test_single_reload_failure_recovers_runtime_but_raises(self) -> None:
        instance = self._instance("demo:one")
        manager = _build_manager(
            [instance],
            [
                SimpleNamespace(status="closed", error=None),
                SimpleNamespace(status="active", error=None),
            ],
        )

        with patch("app.plugins.manager.schedule_plugin_snapshot") as snapshot:
            with self.assertRaisesRegex(RuntimeError, "运行态已尝试恢复"):
                asyncio.run(manager._reload_instance("demo:one"))

        calls = manager.loader.reload_instance.await_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].kwargs["reason"], "manager.reload_instance")
        self.assertEqual(calls[1].kwargs["reason"], "rollback:重载")
        self.assertEqual(calls[1].kwargs["config"], deepcopy(instance.config))
        snapshot.assert_called_once_with(
            reason="manager.reload_instance_failed",
            discovered={"demo": manager.discover_plugins.return_value["demo"]},
        )

    def test_single_reload_reports_incomplete_runtime_recovery(self) -> None:
        manager = _build_manager(
            [self._instance("demo:one")],
            [
                SimpleNamespace(status="error", error="new runtime failed"),
                SimpleNamespace(status="error", error="rollback runtime failed"),
            ],
        )

        with patch("app.plugins.manager.schedule_plugin_snapshot"):
            with self.assertRaisesRegex(RuntimeError, "重载失败且运行态恢复失败"):
                asyncio.run(manager._reload_instance("demo:one"))

        self.assertEqual(manager.loader.reload_instance.await_count, 2)

    def test_plugin_reload_continues_other_instances_then_reports_failure(self) -> None:
        first = self._instance("demo:one")
        second = self._instance("demo:two")
        manager = _build_manager(
            [first, second],
            [
                SimpleNamespace(status="unloaded", error="first reload failed"),
                SimpleNamespace(status="active", error=None),
                SimpleNamespace(status="active", error=None),
            ],
        )

        with patch("app.plugins.manager.schedule_plugin_snapshot") as snapshot:
            with self.assertRaisesRegex(RuntimeError, "插件重载失败: plugin=demo"):
                asyncio.run(manager._reload_plugin("demo"))

        calls = manager.loader.reload_instance.await_args_list
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[1].kwargs["reason"], "rollback:重载")
        self.assertEqual(calls[2].kwargs["instance_id"], "demo:two")
        snapshot.assert_called_once()


class PluginReloadApiFailureContractTest(TestCase):
    """验证 API 不会将管理器的重载失败转换为成功响应。"""

    def test_instance_reload_returns_error_without_success_snapshot(self) -> None:
        from app.api import plugins as plugin_api

        with (
            patch.object(
                plugin_api.PluginManager,
                "reload_instance",
                new=AsyncMock(side_effect=RuntimeError("runtime recovery failed")),
            ),
            patch.object(plugin_api, "publish_plugin_snapshot", new=AsyncMock()) as snapshot,
        ):
            result = asyncio.run(
                plugin_api.reload_plugin_instance(SimpleNamespace(instanceId="demo:one"))
            )

        self.assertEqual(result.status, "error")
        self.assertEqual(result.code, 500)
        self.assertIn("runtime recovery failed", result.message)
        snapshot.assert_not_awaited()
