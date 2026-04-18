#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

from __future__ import annotations

import copy
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from app.models.plugin import PluginInstanceConfig

from .schema import PluginSchemaManager


class PluginConfigStore:
    """负责读取插件实例配置，并结合 Schema 生成有效配置。"""

    @dataclass(slots=True)
    class PluginInstance:
        id: str
        plugin: str
        enabled: bool
        name: str
        config: dict[str, Any]

    @dataclass(slots=True)
    class _ResolvedInstance:
        uid: uuid.UUID
        instance: "PluginConfigStore.PluginInstance"

    def __init__(self, schema_manager: PluginSchemaManager | None = None) -> None:
        self.schema_manager = schema_manager or PluginSchemaManager()

    @staticmethod
    def _normalize_plugin_name(plugin_name: str) -> str:
        normalized = str(plugin_name or "").strip()
        if not normalized:
            raise ValueError("插件名不能为空")
        return normalized

    @staticmethod
    def _normalize_suffix(suffix: str) -> str:
        normalized = str(suffix or "").strip()
        if not normalized:
            raise ValueError("插件实例后缀不能为空")
        return normalized

    def _build_instance_id(self, plugin_name: str, suffix: str) -> str:
        """根据插件名和实例号后缀构造完整实例 ID。"""
        return (
            f"{self._normalize_plugin_name(plugin_name)}:"
            f"{self._normalize_suffix(suffix)}"
        )

    def _resolve_plugin_path(self, plugin_name: str) -> Path:
        """根据插件名解析插件目录路径。"""
        plugins_root = Path.cwd() / "plugins"
        raw_name = str(plugin_name or "").strip()
        if not raw_name:
            return plugins_root / "unknown_plugin"

        base_name = raw_name.split("@", 1)[0].strip() or raw_name
        base_path = plugins_root / base_name
        if base_path.exists():
            return base_path
        return plugins_root / raw_name

    def _resolve_plugin_source_path(
        self,
        plugin_name: str,
        discovered_plugins: Mapping[str, Any] | None = None,
    ) -> Path | None:
        if discovered_plugins is not None and plugin_name in discovered_plugins:
            return getattr(discovered_plugins[plugin_name], "path", None)
        return self._resolve_plugin_path(plugin_name)

    @staticmethod
    def _parse_config_value(value: Any, *, instance_id: str) -> dict[str, Any]:
        if isinstance(value, dict):
            return copy.deepcopy(value)

        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"插件实例配置不是合法 JSON 对象: {instance_id}"
                ) from exc
            if isinstance(parsed, dict):
                return copy.deepcopy(parsed)

        raise ValueError(f"插件实例配置必须是对象: {instance_id}")

    def _build_instance(
        self,
        uid: uuid.UUID,
        instance_config: PluginInstanceConfig,
    ) -> PluginInstance:
        plugin_name = self._normalize_plugin_name(instance_config.get("Info", "Plugin"))
        suffix = self._normalize_suffix(instance_config.get("Info", "Id"))
        instance_id = self._build_instance_id(plugin_name, suffix)
        name = str(instance_config.get("Info", "Name") or instance_id)
        enabled = bool(instance_config.get("Info", "Enabled"))
        config = self._parse_config_value(
            instance_config.get("Data", "Config"),
            instance_id=instance_id,
        )

        return self.PluginInstance(
            id=instance_id,
            plugin=plugin_name,
            enabled=enabled,
            name=name,
            config=config,
        )

    def _resolve_instance(self, instance_id: str) -> _ResolvedInstance:
        from app.core import Config

        for uid, instance_config in Config.PluginConfig.items():
            instance = self._build_instance(uid, instance_config)
            if instance.id == instance_id:
                return self._ResolvedInstance(uid=uid, instance=instance)
        raise ValueError(f"未找到插件实例: {instance_id}")

    def _collect_existing_instance_ids(
        self,
        *,
        exclude_uid: uuid.UUID | None = None,
    ) -> set[str]:
        from app.core import Config

        result: set[str] = set()
        for uid, instance_config in Config.PluginConfig.items():
            if exclude_uid is not None and uid == exclude_uid:
                continue
            result.add(self._build_instance(uid, instance_config).id)
        return result

    def _allocate_unique_instance_id(
        self,
        plugin_name: str,
        *,
        exclude_uid: uuid.UUID | None = None,
    ) -> str:
        existing_ids = self._collect_existing_instance_ids(exclude_uid=exclude_uid)

        for suffix_length in (5, 6, 7, 8):
            for _ in range(32):
                suffix = uuid.uuid4().hex[:suffix_length]
                instance_id = self._build_instance_id(plugin_name, suffix)
                if instance_id not in existing_ids:
                    return instance_id

        raise RuntimeError(f"插件实例 ID 生成失败: {plugin_name}")

    def generate_instance_id(self, plugin_name: str) -> str:
        """生成插件实例 ID。"""
        normalized_plugin = self._normalize_plugin_name(plugin_name)
        return self._allocate_unique_instance_id(normalized_plugin)

    async def load_instances(self) -> list[PluginInstance]:
        """读取并校验插件实例列表。"""
        from app.core import Config

        seen_ids: set[str] = set()
        result: list[PluginConfigStore.PluginInstance] = []

        for uid, instance_config in Config.PluginConfig.items():
            instance = self._build_instance(uid, instance_config)
            if instance.id in seen_ids:
                raise ValueError(f"插件实例 id 重复: {instance.id}")
            seen_ids.add(instance.id)
            result.append(instance)

        return result

    async def create_instance(
        self,
        *,
        plugin_name: str,
        name: str | None = None,
        enabled: bool = True,
        raw_config: dict[str, Any] | None = None,
        discovered_plugins: Mapping[str, Any] | None = None,
    ) -> PluginInstance:
        from app.core import Config

        normalized_plugin = self._normalize_plugin_name(plugin_name)
        if discovered_plugins is not None and normalized_plugin not in discovered_plugins:
            raise ValueError(f"未发现插件: {normalized_plugin}")

        effective_config = self.load_effective_config(
            normalized_plugin,
            self._resolve_plugin_source_path(normalized_plugin, discovered_plugins),
            raw_config or {},
        )
        generated_instance_id = self.generate_instance_id(normalized_plugin)
        _, suffix = generated_instance_id.split(":", 1)
        uid, plugin_config = await Config.PluginConfig.add(PluginInstanceConfig)
        await plugin_config.set_many(
            {
                "Info": {
                    "Plugin": normalized_plugin,
                    "Id": suffix,
                    "Enabled": enabled,
                    "Name": name or f"{normalized_plugin} 实例",
                },
                "Data": {
                    "Config": json.dumps(effective_config, ensure_ascii=False),
                },
            }
        )
        return self._build_instance(uid, plugin_config)

    async def update_instance(
        self,
        instance_id: str,
        *,
        plugin_name: str | None = None,
        name: str | None = None,
        enabled: bool | None = None,
        raw_config: dict[str, Any] | None = None,
        discovered_plugins: Mapping[str, Any] | None = None,
    ) -> tuple[PluginInstance, PluginInstance]:
        from app.core import Config

        resolved = self._resolve_instance(instance_id)
        current = resolved.instance
        next_plugin = (
            current.plugin
            if plugin_name is None
            else self._normalize_plugin_name(plugin_name)
        )
        if discovered_plugins is not None and next_plugin not in discovered_plugins:
            raise ValueError(f"未发现插件: {next_plugin}")

        next_name = current.name if name is None else str(name)
        next_enabled = current.enabled if enabled is None else enabled
        next_config_input = current.config if raw_config is None else raw_config
        effective_config = self.load_effective_config(
            next_plugin,
            self._resolve_plugin_source_path(next_plugin, discovered_plugins),
            next_config_input,
        )

        suffix = self._normalize_suffix(
            Config.PluginConfig[resolved.uid].get("Info", "Id")
        )
        next_instance_id = self._build_instance_id(next_plugin, suffix)
        if next_instance_id in self._collect_existing_instance_ids(exclude_uid=resolved.uid):
            _, suffix = self._allocate_unique_instance_id(
                next_plugin,
                exclude_uid=resolved.uid,
            ).split(":", 1)

        await Config.PluginConfig[resolved.uid].set_many(
            {
                "Info": {
                    "Plugin": next_plugin,
                    "Id": suffix,
                    "Enabled": next_enabled,
                    "Name": next_name,
                },
                "Data": {
                    "Config": json.dumps(effective_config, ensure_ascii=False),
                },
            },
        )
        updated = self._build_instance(resolved.uid, Config.PluginConfig[resolved.uid])
        return current, updated

    async def delete_instance(self, instance_id: str) -> PluginInstance:
        from app.core import Config

        resolved = self._resolve_instance(instance_id)
        await Config.PluginConfig.remove(resolved.uid)
        return resolved.instance

    async def repair_invalid_instances(
        self,
        *,
        missing_instance_ids: set[str],
        failed_instance_ids: set[str],
    ) -> tuple[list[str], list[str]]:
        from app.core import Config

        remove_ids = set(missing_instance_ids)
        disable_ids = set(failed_instance_ids) - remove_ids
        if not remove_ids and not disable_ids:
            return [], []

        removed_ids: list[str] = []
        disabled_ids: list[str] = []
        resolved_instances = [
            self._ResolvedInstance(uid=uid, instance=self._build_instance(uid, config))
            for uid, config in Config.PluginConfig.items()
        ]

        async with Config.PluginConfig.transaction():
            for resolved in resolved_instances:
                current_id = resolved.instance.id
                if current_id in remove_ids:
                    await Config.PluginConfig.remove(resolved.uid)
                    removed_ids.append(current_id)
                    continue

                if current_id in disable_ids and resolved.instance.enabled:
                    await Config.PluginConfig[resolved.uid].set_many(
                        {
                            "Info": {
                                "Enabled": False,
                            }
                        }
                    )
                    disabled_ids.append(current_id)

        return removed_ids, disabled_ids

    def normalize_raw_config(
        self, plugin_name: str, raw_config: dict[str, Any]
    ) -> dict[str, Any]:
        """规范化并深拷贝原始配置对象。"""
        return copy.deepcopy(raw_config)

    def load_schema(
        self,
        plugin_name: str,
        plugin_path: Path | None,
    ) -> dict[str, dict[str, Any]]:
        """加载插件 Schema，兼容本地路径与 PyPI 安装模块。"""
        return self.schema_manager.load_schema(plugin_name, plugin_path)

    def load_effective_config(
        self,
        plugin_name: str,
        plugin_path: Path | None,
        raw_config: dict[str, Any],
    ) -> dict[str, Any]:
        """基于 Schema 生成并校验插件有效配置。"""
        schema = self.load_schema(plugin_name, plugin_path)
        normalized_config = self.normalize_raw_config(plugin_name, raw_config)

        if not schema:
            if normalized_config:
                raise ValueError(f"插件 {plugin_name} 使用了配置项但未声明 schema")
            return normalized_config

        return self.schema_manager.apply_defaults_and_validate(
            plugin_name=plugin_name,
            schema=schema,
            config=normalized_config,
        )
