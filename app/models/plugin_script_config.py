#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

from __future__ import annotations

from app.models.ConfigBase import ConfigBase, ConfigItem, JSONValidator, MultipleConfig


class PluginUserConfig(ConfigBase):
    """插件声明脚本的用户配置 ConfigBase 适配器。

    将插件 Pydantic 用户配置存储为 JSON 字符串,
    通过 Meta.PluginTypeKey 关联到对应的 ScriptTypeProvider。
    """

    related_config: dict[str, MultipleConfig] = {}  # type: ignore[type-arg]

    def __init__(self) -> None:
        self.Meta_PluginTypeKey = ConfigItem("Meta", "PluginTypeKey", "")
        self.Info_Name = ConfigItem("Info", "Name", "新用户")
        self.PluginData_Config = ConfigItem(
            "PluginData", "Config", "{}", JSONValidator()
        )
        super().__init__()


class PluginScriptConfig(ConfigBase):
    """插件声明脚本的脚本配置 ConfigBase 适配器。

    将插件 Pydantic 脚本配置存储为 JSON 字符串,
    通过 Meta.PluginTypeKey 关联到对应的 ScriptTypeProvider。
    UserData 使用 PluginUserConfig 管理用户列表。
    """

    related_config: dict[str, MultipleConfig] = {}  # type: ignore[type-arg]

    def __init__(self) -> None:
        self.Meta_PluginTypeKey = ConfigItem("Meta", "PluginTypeKey", "")
        self.Info_Name = ConfigItem("Info", "Name", "新插件脚本")
        self.PluginData_Config = ConfigItem(
            "PluginData", "Config", "{}", JSONValidator()
        )
        self.UserData = MultipleConfig([PluginUserConfig])
        super().__init__()
