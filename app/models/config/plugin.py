#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""插件注册表、插件目录（市场）与插件自有配置基类。"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, ClassVar, Literal

from pydantic import Field, PrivateAttr, field_validator

from app.config import (
    ConfigCollection,
    ConfigEntry,
    ConfigGroup,
    ConfigNode,
    Trigger,
    UiVisibility,
    Virtual,
    ui,
    virtual_field,
)
from app.config.shortcuts import trigger_field, ui_visibility
from app.plugin.base.plugin import BasePlugin
from app.plugin.types import LifecycleContext, PluginCodeDrift, PluginState


class PluginConfig(ConfigEntry):
    """插件自有配置基类。启用后实例挂 PluginRecord._config；uid 复用注册表项。"""


class PluginRecord(ConfigEntry):
    """已安装插件注册表项：元数据 + 状态由 Manager 回写；四 Trigger 仅开闸。

    不用配置信号维护级联/状态。前端 update 须剔除非 Trigger 字段。

    运行时一律挂本 live 条目的 PrivateAttr（不落盘）：
    ``_plugin`` / ``_plugin_cls`` / ``_config`` / ``_degraded_wants`` / ``_project_dir``。
    """

    class Info(ConfigGroup):
        package_name: str = Field(default="", description="发行包名")
        plugin_name: str = Field(default="", description="插件名")
        version: str = Field(default="", description="版本")
        docs_url: str = Field(default="", description="文档 URL")
        import_name: str = Field(
            default="",
            description="可 import 的顶层包名；发现刷新写入；load 读 __init__.PLUGIN",
        )
        requires: list[str] = Field(
            default_factory=list,
            description="硬依赖服务名（load 后由类属性写入；启用级联）",
        )
        wants: list[str] = Field(
            default_factory=list,
            description="弱依赖服务名（load 后由类属性写入；缺失降级）",
        )
        source: Literal["", "installed", "local"] = Field(
            default="", description="发现源：installed | local"
        )
        state: PluginState = Field(
            default=PluginState.UNLOADED,
            description="插件状态（PluginState；Manager 回写）",
        )
        lifecycle_context: LifecycleContext = Field(
            default=LifecycleContext.IDLE,
            description="生命周期语境（LifecycleContext；Manager 写入，非 Trigger）",
        )
        enabled: bool = Field(
            default=False, description="是否启用（意图；Manager 回写）"
        )
        last_error: str = Field(default="", description="最近错误")
        is_core: bool = Field(default=False, description="是否核心插件")
        is_local: bool = Field(default=False, description="是否本地目录插件")
        code_drift: PluginCodeDrift = Field(
            default=PluginCodeDrift.NORMAL,
            description="与最近一次发现/磁盘的差异：normal=一致；needs_reload=需重载；package_removed=包缺失",
        )
        enable: Trigger = Field(default=False, description="启用（写 True 开闸）")
        disable: Trigger = Field(default=False, description="禁用（写 True 开闸）")
        reload: Trigger = Field(default=False, description="重载（写 True 开闸）")
        uninstall: Trigger = Field(default=False, description="卸载（写 True 开闸）")

        @field_validator("code_drift", mode="before")
        @classmethod
        def normalize_code_drift(cls, value: object) -> object:
            return PluginCodeDrift.NORMAL if value == "" else value

    info: Info = Field(default_factory=Info, description="插件注册表项")

    # ── 运行时（只写 live；勿写工作区壳）──
    _plugin: BasePlugin | None = PrivateAttr(default=None)
    _plugin_cls: type[BasePlugin] | None = PrivateAttr(default=None)
    _config: PluginConfig | None = PrivateAttr(default=None)  # 插件自有配置实例
    _degraded_wants: list[str] = PrivateAttr(default_factory=list)
    # 来源搜索根：本地为 src，已安装包为 site-packages；由 discover.refresh 写入。
    _project_dir: Path | None = PrivateAttr(default=None)

    @trigger_field("info.enable")
    async def on_enable(self) -> None:
        from app.core.plugin_manager import Plugin

        await Plugin.enable(self)

    @trigger_field("info.disable")
    async def on_disable(self) -> None:
        from app.core.plugin_manager import Plugin

        await Plugin.disable(self)

    @trigger_field("info.reload")
    async def on_reload(self) -> None:
        from app.core.plugin_manager import Plugin

        await Plugin.reload(self)

    @trigger_field("info.uninstall")
    async def on_uninstall(self) -> None:
        from app.core.plugin_manager import Plugin

        await Plugin.uninstall(self)

    def _lifecycle_busy(self) -> bool:
        """××中不可开闸。"""
        return self.effective.info.state in {
            PluginState.LOADING,
            PluginState.ENABLING,
            PluginState.DISABLING,
            PluginState.RELOADING,
            PluginState.UNLOADING,
        }

    @ui_visibility("info.enable")
    def _vis_enable(self) -> UiVisibility:
        """仅禁用 / runtime 故障可启用。"""
        info = self.effective.info
        if info.is_core or self._lifecycle_busy():
            return UiVisibility.DISABLE
        if info.state in {PluginState.DISABLED, PluginState.FAULT_RUNTIME}:
            return UiVisibility.SHOW
        return UiVisibility.DISABLE

    @ui_visibility("info.disable")
    def _vis_disable(self) -> UiVisibility:
        """仅已启用且非核心可禁用。"""
        info = self.effective.info
        if info.is_core or self._lifecycle_busy():
            return UiVisibility.DISABLE
        if info.state == PluginState.ENABLED:
            return UiVisibility.SHOW
        return UiVisibility.DISABLE

    @ui_visibility("info.reload")
    def _vis_reload(self) -> UiVisibility:
        """已加载稳态（含 runtime 故障）可重载；核心 / load 故障 / ××中不可。"""
        info = self.effective.info
        if info.is_core or self._lifecycle_busy():
            return UiVisibility.DISABLE
        if info.state == PluginState.FAULT_LOAD:
            return UiVisibility.DISABLE
        if info.state in {
            PluginState.ENABLED,
            PluginState.DISABLED,
            PluginState.FAULT_RUNTIME,
        }:
            return UiVisibility.SHOW
        return UiVisibility.DISABLE

    @ui_visibility("info.uninstall")
    def _vis_uninstall(self) -> UiVisibility:
        """已加载项可卸载；核心 / 本地 / ××中不可。"""
        info = self.effective.info
        if info.is_core or info.is_local or self._lifecycle_busy():
            return UiVisibility.DISABLE
        if info.state in {
            PluginState.ENABLED,
            PluginState.DISABLED,
            PluginState.FAULT_LOAD,
            PluginState.FAULT_RUNTIME,
        }:
            return UiVisibility.SHOW
        return UiVisibility.DISABLE


class PluginRegistryCollection(ConfigCollection[PluginRecord]):
    """插件注册表集合，提供按插件名查找的专用接口。"""

    _default_entry_types: ClassVar[tuple[type[ConfigNode], ...]] = (PluginRecord,)

    def by_name(self, name: str) -> PluginRecord | None:
        """按 ``plugin_name`` 查找注册表项；没有匹配项时返回 ``None``。"""
        for record in self.values():
            if record.info.plugin_name == name:
                return record
        return None


class PluginMeta(ConfigEntry):
    """插件目录（市场）条目：刷新写入；install Trigger 开闸安装。

    展示字段：隐藏 ``*_i18n`` 字典 + Virtual 按 ``setting.language.locale`` 暴露。
    """

    class Info(ConfigGroup):
        package_name: str = Field(default="", description="包名")
        plugin_name: str = Field(default="", description="插件名")
        version: str = Field(default="", description="版本")
        docs_url: str = Field(default="", description="文档 URL")
        homepage: str = Field(default="", description="主页 URL")
        requires_dist: list[str] = Field(
            default_factory=list, description="Requires-Dist 列表"
        )
        display_name_i18n: Annotated[
            dict[str, str], ui(visibility=UiVisibility.HIDE)
        ] = Field(default_factory=dict, description="展示名 i18n 字典")
        description_i18n: Annotated[
            dict[str, str], ui(visibility=UiVisibility.HIDE)
        ] = Field(default_factory=dict, description="描述 i18n 字典")
        tags_i18n: Annotated[
            dict[str, list[str]], ui(visibility=UiVisibility.HIDE)
        ] = Field(default_factory=dict, description="标签 i18n 字典")
        display_name: Virtual[str] = None
        description: Virtual[str] = None
        tags: Virtual[list[str]] = None
        install: Trigger = Field(default=False, description="安装（写 True 开闸）")

    info: Info = Field(default_factory=Info, description="目录项")

    @staticmethod
    def _locale() -> str:
        from app.core.config import Config

        return Config.setting.language.locale or "zh_CN"

    @staticmethod
    def _pick_str(mapping: dict[str, str]) -> str:
        locale = PluginMeta._locale()
        for key in (locale, "zh_CN", "en"):
            value = mapping.get(key)
            if isinstance(value, str) and value:
                return value
        for value in mapping.values():
            if isinstance(value, str) and value:
                return value
        return ""

    @staticmethod
    def _pick_tags(mapping: dict[str, list[str]]) -> list[str]:
        locale = PluginMeta._locale()
        for key in (locale, "zh_CN", "en"):
            value = mapping.get(key)
            if isinstance(value, list) and value:
                return list(value)
        for value in mapping.values():
            if isinstance(value, list) and value:
                return list(value)
        return []

    @virtual_field("info.display_name")
    def compute_display_name(self) -> str:
        return self._pick_str(self.info.display_name_i18n)

    @virtual_field("info.description")
    def compute_description(self) -> str:
        return self._pick_str(self.info.description_i18n)

    @virtual_field("info.tags")
    def compute_tags(self) -> list[str]:
        return self._pick_tags(self.info.tags_i18n)

    @ui_visibility("info.install")
    def _vis_install(self) -> UiVisibility:
        """注册表已有同插件名 / 同包名条目时安装按钮不可用。"""
        from app.core.config import Config

        info = self.effective.info
        plugin_id = (info.plugin_name or "").strip()
        if plugin_id and Config.plugin_registry.by_name(plugin_id) is not None:
            return UiVisibility.DISABLE
        package = (info.package_name or "").strip()
        if package:
            pkg_key = package.replace("_", "-").lower()
            for record in Config.plugin_registry.values():
                if (
                    record.info.package_name or ""
                ).replace("_", "-").lower() == pkg_key:
                    return UiVisibility.DISABLE
        return UiVisibility.SHOW

    @trigger_field("info.install")
    async def on_install(self) -> None:
        from app.core.plugin_manager import Plugin

        await Plugin.install(self)
