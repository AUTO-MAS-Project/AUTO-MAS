#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

from pathlib import Path
from typing import Any, Dict
import uuid

from app.utils import get_logger

from .event_bus import EventBus
from .config_store import PluginConfigStore
from .loader import PluginLoader


logger = get_logger("插件管理器")


class _PluginManager:
    """Coordinates plugin lifecycle and exposes event APIs for MAS core."""

    def __init__(self) -> None:
        self.started = False
        self.events = EventBus()
        self.config_store = PluginConfigStore()
        self.plugins_dir = Path.cwd() / "plugins"
        self.runtime: Dict[str, Any] = {
            "list_scripts": self._list_scripts,
            "get_script_log": self._get_script_log,
        }
        self.loader = PluginLoader(
            events=self.events,
            runtime=self.runtime,
            plugins_dir=self.plugins_dir,
        )

    def _discover_plugins(self) -> Dict[str, Any]:
        """发现插件（兼容本地目录与 PyPI Entry Point）。"""
        return self.loader.discover()

    def _list_scripts(self) -> list[Dict[str, Any]]:
        try:
            from app.core import Config
            scripts = []
            for script_id, script in Config.ScriptConfig.items():
                scripts.append(
                    {
                        "id": str(script_id),
                        "name": script.get("Info", "Name"),
                        "type": type(script).__name__,
                    }
                )
            return scripts
        except Exception as e:
            logger.warning(f"获取脚本列表失败: {e}")
            return []

    def _get_script_log(self, script_id: str, limit: int = 200) -> str:
        try:
            from app.core import Config

            uid = uuid.UUID(script_id)
            script = Config.ScriptConfig.get(uid)
            if script is None:
                return ""

            log_value = getattr(script, "log", None)
            if isinstance(log_value, str):
                if limit <= 0:
                    return log_value
                lines = log_value.splitlines()
                return "\n".join(lines[-limit:])
            return ""
        except Exception as e:
            logger.warning(f"获取脚本日志失败: script_id={script_id}, error={e}")
            return ""

    async def start(self) -> None:
        if self.started:
            logger.warning("插件系统已启动，忽略重复启动")
            return

        discovered = self._discover_plugins()
        self.loader.discovered_plugins = discovered
        instances = await self.config_store.load_instances(
            self.plugins_dir,
            discovered,
            auto_create_missing=False,
        )
        await self.loader.load_instances(instances)
        await self._repair_invalid_instances_after_start(discovered)
        self.started = True
        logger.info("插件系统启动完成")

    async def _repair_invalid_instances_after_start(self, discovered: Dict[str, Any]) -> None:
        """启动后修复失效插件实例配置。"""
        failed = dict(getattr(self.loader, "startup_failed_instances", {}) or {})
        if not failed:
            return

        missing_ids = set(getattr(self.loader, "startup_missing_instances", set()) or set())

        try:
            root = await self.config_store.get_root(
                self.plugins_dir,
                discovered,
                auto_create_missing=False,
            )
        except Exception as e:
            logger.error(f"读取插件配置失败，跳过失效实例修复: {type(e).__name__}: {e}")
            return

        instances = root.get("instances", [])
        if not isinstance(instances, list):
            return

        changed = False
        removed_ids: list[str] = []
        disabled_ids: list[str] = []
        new_instances = []

        for item in instances:
            if not isinstance(item, dict):
                new_instances.append(item)
                continue

            instance_id = str(item.get("id") or "")
            if not instance_id:
                new_instances.append(item)
                continue

            if instance_id in missing_ids:
                removed_ids.append(instance_id)
                changed = True
                continue

            if instance_id in failed and bool(item.get("enabled", False)):
                item["enabled"] = False
                disabled_ids.append(instance_id)
                changed = True

            new_instances.append(item)

        if not changed:
            return

        root["instances"] = new_instances
        try:
            await self.config_store.save_root(self.plugins_dir, root)
        except Exception as e:
            logger.error(f"保存插件配置失败，失效实例修复未落盘: {type(e).__name__}: {e}")
            return

        if removed_ids:
            logger.warning(f"已删除未发现插件的实例配置: {', '.join(removed_ids)}")
        if disabled_ids:
            logger.warning(f"已自动禁用启动失败的插件实例: {', '.join(disabled_ids)}")

    async def stop(self) -> None:
        if not self.started:
            return

        await self.loader.unload_all()
        self.events.clear()
        self.started = False
        logger.info("插件系统已关闭")

    def on(self, event: str, handler) -> None:
        self.events.on(event, handler)

    def off(self, event: str, handler) -> None:
        self.events.off(event, handler)

    def emit(self, event: str, payload: Any = None) -> None:
        self.events.emit(event, payload)

    def list_plugins(self) -> Dict[str, str]:
        return {
            instance_id: record.status
            for instance_id, record in self.loader.records.items()
        }

    async def reload(self) -> None:
        if self.started:
            await self.stop()
        await self.start()

    async def reload_instance(self, instance_id: str) -> None:
        discovered = self._discover_plugins()
        self.loader.discovered_plugins = discovered
        instances = await self.config_store.load_instances(
            self.plugins_dir,
            discovered,
            auto_create_missing=False,
        )
        target = next((item for item in instances if item.id == instance_id), None)
        if target is None:
            raise ValueError(f"未找到插件实例: {instance_id}")

        await self.loader.unload_instance(instance_id)
        if target.enabled:
            await self.loader.load_instance(
                instance_id=target.id,
                plugin_name=target.plugin,
                instance_name=target.name,
                config=target.config,
            )

    async def reload_plugin(self, plugin_name: str) -> None:
        discovered = self._discover_plugins()
        self.loader.discovered_plugins = discovered
        instances = await self.config_store.load_instances(
            self.plugins_dir,
            discovered,
            auto_create_missing=False,
        )
        matched = [item for item in instances if item.plugin == plugin_name]
        if not matched:
            raise ValueError(f"未找到插件实例: {plugin_name}")

        for item in matched:
            await self.loader.unload_instance(item.id)

        for item in matched:
            if not item.enabled:
                continue
            await self.loader.load_instance(
                instance_id=item.id,
                plugin_name=item.plugin,
                instance_name=item.name,
                config=item.config,
            )


PluginManager = _PluginManager()
