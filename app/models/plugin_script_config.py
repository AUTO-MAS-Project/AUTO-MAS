#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

from __future__ import annotations

import json
from typing import Any

from app.models.ConfigBase import ConfigBase, ConfigItem, JSONValidator, MultipleConfig


def _resolve_provider_by_type_key(type_key: str):
    normalized_type_key = str(type_key or "").strip()
    if not normalized_type_key:
        return None

    try:
        from app.core.script_types import script_type_registry

        return script_type_registry.get(normalized_type_key)
    except Exception:
        return None


class PluginUserConfig(ConfigBase):
    """插件脚本用户配置的宿主容器。"""

    related_config: dict[str, MultipleConfig] = {}  # type: ignore[type-arg]

    def __init__(self) -> None:
        self.Meta_PluginTypeKey = ConfigItem("Meta", "PluginTypeKey", "")
        self.Info_Name = ConfigItem("Info", "Name", "新用户")
        self.PluginData_Config = ConfigItem(
            "PluginData", "Config", "{}", JSONValidator()
        )
        super().__init__()


class PluginUserMultipleConfig(MultipleConfig[PluginUserConfig]):
    """在宿主存储和真实脚本配置之间做用户配置转换。"""

    def __init__(self, owner: "PluginScriptConfig") -> None:
        self._owner = owner
        super().__init__([PluginUserConfig])

    def _resolve_provider(self):
        return _resolve_provider_by_type_key(
            str(self._owner.get("Meta", "PluginTypeKey") or "").strip()
        )

    async def toDict(
        self, if_decrypt: bool = True, regenerate_uuids: bool = False
    ) -> dict[str, list | dict]:
        raw = await super().toDict(if_decrypt, regenerate_uuids)
        provider = self._resolve_provider()
        if provider is None:
            return raw

        from app.core import Config as RuntimeConfig
        from app.core.script_types import strip_sub_configs

        data: dict[str, list | dict] = {"instances": []}
        for instance in raw.get("instances", []):
            if not isinstance(instance, dict):
                continue

            uid = instance.get("uid")
            if not isinstance(uid, str):
                continue

            payload = raw.get(uid)
            if not isinstance(payload, dict):
                continue

            plugin_data = payload.get("PluginData")
            raw_config = (
                plugin_data.get("Config")
                if isinstance(plugin_data, dict)
                else None
            )
            parsed = json.loads(raw_config) if raw_config and raw_config != "{}" else {}
            normalized = RuntimeConfig._normalize_configbase_payload_for_form(
                provider.user_config_class,
                parsed,
            )
            if RuntimeConfig._is_configbase_class(provider.user_config_class):
                normalized = strip_sub_configs(normalized)

            info = normalized.setdefault("Info", {})
            if isinstance(info, dict):
                name = payload.get("Info", {}).get("Name") if isinstance(payload.get("Info"), dict) else None
                if isinstance(name, str) and name.strip() and not info.get("Name"):
                    info["Name"] = name.strip()

            data["instances"].append(
                {"uid": uid, "type": provider.user_config_class.__name__}
            )
            data[uid] = normalized

        return data

    async def load(self, data: dict):
        provider = self._resolve_provider()
        if provider is None:
            await super().load(data)
            return

        from app.core import Config as RuntimeConfig

        translated: dict[str, list | dict] = {"instances": []}
        for instance in data.get("instances", []):
            if not isinstance(instance, dict):
                continue

            uid = instance.get("uid")
            if not isinstance(uid, str):
                continue

            payload = data.get(uid)
            if not isinstance(payload, dict):
                continue

            normalized = RuntimeConfig._normalize_configbase_payload_for_storage(
                provider.user_config_class,
                payload,
            )

            user_name = ""
            info = payload.get("Info")
            if isinstance(info, dict) and isinstance(info.get("Name"), str):
                user_name = info["Name"].strip()
            if not user_name and isinstance(payload.get("user_name"), str):
                user_name = str(payload["user_name"]).strip()

            translated["instances"].append({"uid": uid, "type": "PluginUserConfig"})
            translated[uid] = {
                "Meta": {"PluginTypeKey": provider.type_key},
                "Info": {"Name": user_name},
                "PluginData": {
                    "Config": json.dumps(normalized, ensure_ascii=False),
                },
            }

        await super().load(translated)


class PluginScriptConfig(ConfigBase):
    """插件脚本配置的宿主容器。"""

    related_config: dict[str, MultipleConfig] = {}  # type: ignore[type-arg]

    def __init__(self) -> None:
        self.Meta_PluginTypeKey = ConfigItem("Meta", "PluginTypeKey", "")
        self.Info_Name = ConfigItem("Info", "Name", "新插件脚本")
        self.PluginData_Config = ConfigItem(
            "PluginData", "Config", "{}", JSONValidator()
        )
        self.UserData = PluginUserMultipleConfig(self)
        super().__init__()

    def _resolve_provider(self):
        return _resolve_provider_by_type_key(
            str(super().get("Meta", "PluginTypeKey") or "").strip()
        )

    def _read_plugin_config_data(self) -> dict[str, Any]:
        raw = super().get("PluginData", "Config")
        parsed = json.loads(raw) if raw and raw != "{}" else {}
        provider = self._resolve_provider()
        if provider is None:
            return parsed

        from app.core import Config as RuntimeConfig

        return RuntimeConfig._normalize_configbase_payload_for_form(
            provider.script_config_class,
            parsed,
        )

    def get(self, group: str, name: str) -> Any:
        try:
            return super().get(group, name)
        except AttributeError:
            group_data = self._read_plugin_config_data().get(group)
            if isinstance(group_data, dict) and name in group_data:
                return group_data[name]
            raise
