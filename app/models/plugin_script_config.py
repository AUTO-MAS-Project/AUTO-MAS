#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

from __future__ import annotations

import json

from app.models.ConfigBase import ConfigBase, ConfigItem, JSONValidator, MultipleConfig


class PluginUserConfig(ConfigBase):
    """插件脚本用户配置的宿主存储容器。"""

    related_config: dict[str, MultipleConfig] = {}  # type: ignore[type-arg]

    def __init__(self) -> None:
        self.Meta_PluginTypeKey = ConfigItem("Meta", "PluginTypeKey", "")
        self.Info_Name = ConfigItem("Info", "Name", "新用户")
        self.PluginData_Config = ConfigItem(
            "PluginData", "Config", "{}", JSONValidator()
        )
        super().__init__()


class PluginUserMultipleConfig(MultipleConfig[PluginUserConfig]):
    """插件用户配置列表，保存时只输出宿主容器结构。"""

    def __init__(self, owner: "PluginScriptConfig") -> None:
        self._owner = owner
        super().__init__([PluginUserConfig])

    def _resolve_provider(self):
        type_key = str(self._owner.get("Meta", "PluginTypeKey") or "").strip()
        if not type_key:
            return None

        try:
            from app.core.script_types import script_type_registry

            return script_type_registry.get(type_key)
        except KeyError:
            return None

    async def load(self, data: dict):
        instances = data.get("instances")
        if not isinstance(instances, list) or all(
            isinstance(instance, dict)
            and instance.get("type") == "PluginUserConfig"
            for instance in instances
        ):
            await super().load(data)
            return

        provider = self._resolve_provider()
        if provider is None:
            await super().load(data)
            return

        from app.core.script_config_codec import form_to_storage

        translated: dict[str, list | dict] = {"instances": []}
        for instance in instances:
            if not isinstance(instance, dict):
                continue

            uid = instance.get("uid")
            if not isinstance(uid, str):
                continue

            payload = data.get(uid)
            if not isinstance(payload, dict):
                continue

            storage_payload = await form_to_storage(provider, payload, "user")
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
                    "Config": json.dumps(storage_payload, ensure_ascii=False),
                },
            }

        await super().load(translated)


class PluginScriptConfig(ConfigBase):
    """插件脚本配置的宿主存储容器。"""

    related_config: dict[str, MultipleConfig] = {}  # type: ignore[type-arg]

    def __init__(self) -> None:
        self.Meta_PluginTypeKey = ConfigItem("Meta", "PluginTypeKey", "")
        self.Info_Name = ConfigItem("Info", "Name", "新插件脚本")
        self.PluginData_Config = ConfigItem(
            "PluginData", "Config", "{}", JSONValidator()
        )
        self.UserData = PluginUserMultipleConfig(self)
        super().__init__()
