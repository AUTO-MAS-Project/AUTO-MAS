#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

import copy
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from .schema import PluginSchemaManager


class PluginConfigStore:
    """负责读取插件配置，并结合 Schema 生成有效配置。"""

    @dataclass
    class PluginInstance:
        id: str
        plugin: str
        enabled: bool
        name: str
        config: Dict[str, Any]

    def __init__(self, schema_manager: PluginSchemaManager | None = None) -> None:
        self.schema_manager = schema_manager or PluginSchemaManager()

    def _extract_instance_suffix(self, plugin_name: str, instance_id: str) -> str:
        """从实例 ID 中提取实例号后缀。"""
        if isinstance(instance_id, str) and instance_id.startswith(f"{plugin_name}:"):
            suffix = instance_id.split(":", 1)[1].strip()
            if suffix:
                return suffix
        if isinstance(instance_id, str) and instance_id.strip():
            return instance_id.strip()
        return uuid.uuid4().hex[:5]

    def _build_instance_id(self, plugin_name: str, suffix: str) -> str:
        """根据插件名和实例号后缀构造完整实例 ID。"""
        safe_plugin = str(plugin_name or "unknown_plugin").strip() or "unknown_plugin"
        safe_suffix = str(suffix or "").strip() or uuid.uuid4().hex[:5]
        return f"{safe_plugin}:{safe_suffix}"

    async def _read_root(self) -> Dict[str, Any]:
        """从插件独立配置读取统一配置根对象。"""
        from app.core import Config

        instances: List[Dict[str, Any]] = []
        for instance_config in Config.PluginConfig.PluginInstances.values():
            plugin_name = str(instance_config.get("Info", "Plugin") or "").strip()
            suffix = str(instance_config.get("Info", "Id") or "").strip()
            enabled = bool(instance_config.get("Info", "Enabled"))
            name = str(instance_config.get("Info", "Name") or "未命名实例")

            config_text = instance_config.get("Data", "Config")
            try:
                config = json.loads(config_text) if isinstance(config_text, str) else {}
            except Exception:
                raw_config_text = instance_config.get("Data", "ConfigRaw")
                config = (
                    json.loads(raw_config_text)
                    if isinstance(raw_config_text, str)
                    else {}
                )
            if not isinstance(config, dict):
                config = {}

            if not plugin_name:
                continue

            instances.append(
                {
                    "id": self._build_instance_id(plugin_name, suffix),
                    "plugin": plugin_name,
                    "enabled": enabled,
                    "name": name,
                    "config": config,
                }
            )

        raw_version = Config.PluginConfig.get("Data", "Version")

        try:
            version = int(raw_version)
        except Exception:
            version = 1

        return {
            "version": max(1, version),
            "instances": instances,
        }

    async def _write_root(self, root: Dict[str, Any]) -> None:
        """写入插件独立配置中的统一配置根对象。"""
        from app.core import Config

        version = int(root.get("version", 1))
        raw_instances = root.get("instances", [])
        if not isinstance(raw_instances, list):
            raise ValueError("插件统一配置中的 instances 必须是数组")

        instance_index: Dict[str, Dict[str, Any]] = {}
        instance_list: List[Dict[str, str]] = []

        for item in raw_instances:
            if not isinstance(item, dict):
                raise ValueError("instances 中存在非对象项")

            plugin_name = item.get("plugin")
            if not isinstance(plugin_name, str) or not plugin_name:
                raise ValueError("插件实例缺少有效的 plugin 字段")

            instance_id = item.get("id")
            if not isinstance(instance_id, str) or not instance_id:
                raise ValueError("插件实例缺少有效的 id 字段")

            enabled = item.get("enabled", True)
            if not isinstance(enabled, bool):
                raise ValueError(f"插件实例 {instance_id} 的 enabled 字段必须为布尔值")

            config = item.get("config", {})
            if not isinstance(config, dict):
                raise ValueError(f"插件实例 {instance_id} 的 config 必须是对象")

            name = str(item.get("name") or instance_id)
            suffix = self._extract_instance_suffix(plugin_name, instance_id)

            effective_config = self.load_effective_config(
                plugin_name,
                Path.cwd() / "plugins" / plugin_name,
                config,
            )

            uid = str(uuid.uuid4())
            instance_list.append(
                {
                    "uid": uid,
                    "type": "PluginInstanceConfig",
                }
            )
            instance_index[uid] = {
                "Info": {
                    "Plugin": plugin_name,
                    "Id": suffix,
                    "Enabled": enabled,
                    "Name": name,
                },
                "Data": {
                    "ConfigRaw": json.dumps(effective_config, ensure_ascii=False),
                },
            }

        payload: Dict[str, Any] = {
            "Data": {
                "Version": max(1, version),
            },
            "SubConfigsInfo": {
                "PluginInstances": {
                    "instances": instance_list,
                    **instance_index,
                }
            },
        }

        await Config.PluginConfig.load(payload)

    def _generate_instance_id(self, plugin_name: str) -> str:
        return f"{plugin_name}:{uuid.uuid4().hex[:5]}"

    def generate_instance_id(self, plugin_name: str) -> str:
        """生成插件实例 ID。"""
        return self._generate_instance_id(plugin_name)

    async def get_root(
        self,
        plugins_dir,
        discovered_plugins,
        auto_create_missing: bool = False,
    ) -> Dict[str, Any]:
        """读取并补全统一插件配置根对象。"""
        return await self.ensure_instances(
            plugins_dir,
            discovered_plugins,
            auto_create_missing=auto_create_missing,
        )

    async def save_root(self, plugins_dir, root: Dict[str, Any]) -> None:
        """保存统一插件配置根对象。"""
        if not isinstance(root, dict):
            raise ValueError("插件统一配置根对象必须是字典")
        instances = root.get("instances")
        if not isinstance(instances, list):
            raise ValueError("插件统一配置缺少 instances 列表")
        root.setdefault("version", 1)
        await self._write_root(root)

    async def ensure_instances(
        self,
        plugins_dir,
        discovered_plugins,
        auto_create_missing: bool = False,
    ) -> Dict[str, Any]:
        root = await self._read_root()
        instances: List[Dict[str, Any]] = root.get("instances", [])

        existing_plugins = {
            item.get("plugin")
            for item in instances
            if isinstance(item, dict) and isinstance(item.get("plugin"), str)
        }

        changed = False
        if auto_create_missing:
            for plugin_name in discovered_plugins.keys():
                if plugin_name in existing_plugins:
                    continue
                instances.append(
                    {
                        "id": self._generate_instance_id(plugin_name),
                        "plugin": plugin_name,
                        "enabled": True,
                        "name": f"{plugin_name} 默认实例",
                        "config": {},
                    }
                )
                changed = True

        root["instances"] = instances
        if changed:
            await self._write_root(root)

        return root

    async def load_instances(
        self,
        plugins_dir,
        discovered_plugins,
        auto_create_missing: bool = False,
    ) -> List[PluginInstance]:
        """读取插件实例列表。

        默认不自动创建实例，确保插件实例仅由用户手动创建。
        """
        root = await self.ensure_instances(
            plugins_dir,
            discovered_plugins,
            auto_create_missing=auto_create_missing,
        )
        result: List[PluginConfigStore.PluginInstance] = []
        seen_ids: set[str] = set()

        for item in root.get("instances", []):
            if not isinstance(item, dict):
                raise ValueError("instances 中存在非对象项")

            instance_id = item.get("id")
            plugin_name = item.get("plugin")
            enabled = item.get("enabled", True)
            name = item.get("name") or str(instance_id or "未命名实例")
            config = item.get("config", {})

            if not isinstance(instance_id, str) or not instance_id:
                raise ValueError("插件实例 id 必须是非空字符串")
            if instance_id in seen_ids:
                raise ValueError(f"插件实例 id 重复: {instance_id}")
            seen_ids.add(instance_id)
            if not isinstance(plugin_name, str) or not plugin_name:
                raise ValueError(f"插件实例 {instance_id} 的 plugin 字段无效")
            if not isinstance(enabled, bool):
                raise ValueError(f"插件实例 {instance_id} 的 enabled 字段必须为布尔值")
            if not isinstance(config, dict):
                raise ValueError(f"插件实例 {instance_id} 的 config 必须是对象")

            result.append(
                self.PluginInstance(
                    id=instance_id,
                    plugin=plugin_name,
                    enabled=enabled,
                    name=str(name),
                    config=copy.deepcopy(config),
                )
            )

        return result

    def normalize_raw_config(self, plugin_name: str, raw_config: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(raw_config, dict):
            raise ValueError(f"插件配置必须是对象: {plugin_name}")
        return copy.deepcopy(raw_config)

    def load_schema(self, plugin_name: str, plugin_path: Path | None) -> Dict[str, Dict[str, Any]]:
        """加载插件 Schema，兼容本地路径与 PyPI 安装模块。"""
        return self.schema_manager.load_schema(plugin_name, plugin_path)

    def load_effective_config(
        self,
        plugin_name: str,
        plugin_path: Path | None,
        raw_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """基于 Schema 生成并校验插件有效配置。"""
        schema = self.load_schema(plugin_name, plugin_path)
        normalized_config = self.normalize_raw_config(plugin_name, raw_config)

        if not schema:
            if normalized_config:
                raise ValueError(
                    f"插件 {plugin_name} 使用了配置项但未声明 schema"
                )
            return normalized_config

        return self.schema_manager.apply_defaults_and_validate(
            plugin_name=plugin_name,
            schema=schema,
            config=normalized_config,
        )
