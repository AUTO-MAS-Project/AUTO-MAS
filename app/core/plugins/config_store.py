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

    CONFIG_FILE_NAME = "AUTO_MAS.json"

    @dataclass
    class PluginInstance:
        id: str
        plugin: str
        enabled: bool
        name: str
        config: Dict[str, Any]

    def __init__(self, schema_manager: PluginSchemaManager | None = None) -> None:
        self.schema_manager = schema_manager or PluginSchemaManager()

    def _config_path(self, plugins_dir: Path) -> Path:
        return plugins_dir / self.CONFIG_FILE_NAME

    def _read_root(self, plugins_dir: Path) -> Dict[str, Any]:
        config_path = self._config_path(plugins_dir)
        if not config_path.exists():
            return {"version": 1, "instances": []}

        with config_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            raise ValueError("插件统一配置文件必须是对象")
        if "instances" not in data or not isinstance(data["instances"], list):
            raise ValueError("插件统一配置文件缺少 instances 列表")

        data.setdefault("version", 1)
        return data

    def _write_root(self, plugins_dir: Path, root: Dict[str, Any]) -> None:
        plugins_dir.mkdir(parents=True, exist_ok=True)
        config_path = self._config_path(plugins_dir)
        temp_path = plugins_dir / f"{self.CONFIG_FILE_NAME}.tmp"
        with temp_path.open("w", encoding="utf-8") as f:
            json.dump(root, f, ensure_ascii=False, indent=4)
        temp_path.replace(config_path)

    def _generate_instance_id(self, plugin_name: str) -> str:
        return f"{plugin_name}:{uuid.uuid4().hex[:5]}"

    def generate_instance_id(self, plugin_name: str) -> str:
        """生成插件实例 ID。"""
        return self._generate_instance_id(plugin_name)

    def get_root(
        self,
        plugins_dir: Path,
        discovered_plugins: Dict[str, Path],
        auto_create_missing: bool = True,
    ) -> Dict[str, Any]:
        """读取并补全统一插件配置根对象。"""
        return self.ensure_instances(
            plugins_dir,
            discovered_plugins,
            auto_create_missing=auto_create_missing,
        )

    def save_root(self, plugins_dir: Path, root: Dict[str, Any]) -> None:
        """保存统一插件配置根对象。"""
        if not isinstance(root, dict):
            raise ValueError("插件统一配置根对象必须是字典")
        instances = root.get("instances")
        if not isinstance(instances, list):
            raise ValueError("插件统一配置缺少 instances 列表")
        root.setdefault("version", 1)
        self._write_root(plugins_dir, root)

    def ensure_instances(
        self,
        plugins_dir: Path,
        discovered_plugins: Dict[str, Path],
        auto_create_missing: bool = True,
    ) -> Dict[str, Any]:
        config_exists = self._config_path(plugins_dir).exists()
        root = self._read_root(plugins_dir)
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
        if changed or not config_exists:
            self._write_root(plugins_dir, root)

        return root

    def load_instances(
        self,
        plugins_dir: Path,
        discovered_plugins: Dict[str, Path],
    ) -> List[PluginInstance]:
        root = self.ensure_instances(
            plugins_dir,
            discovered_plugins,
            auto_create_missing=True,
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

    def load_schema(self, plugin_name: str, plugin_path: Path) -> Dict[str, Dict[str, Any]]:
        return self.schema_manager.load_schema(plugin_name, plugin_path)

    def load_effective_config(
        self,
        plugin_name: str,
        plugin_path: Path,
        raw_config: Dict[str, Any],
    ) -> Dict[str, Any]:
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
