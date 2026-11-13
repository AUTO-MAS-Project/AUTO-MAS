"""AUTO-MAS 插件协议与开发 SDK。

公开能力：
- 顶层：基类、Config、Plugin（Manager 单例）、PLUGIN（核心插件入口类）
- ``auto_mas_core.utils`` / ``auto_mas_core.services``：宿主整包再导出
- ``auto_mas_core.plugin.services`` / ``.http``：插件系统总线与 HTTP（导入路径消歧）
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.config import (
    ConfigCollection,
    ConfigEntry,
    ConfigGroup,
    ConfigTableColumn,
    ExecutablePath,
    FieldChangeEvent,
    FilePath,
    FolderPath,
    JsonDictString,
    JsonListString,
    LockTicket,
    Trigger,
    UiVisibility,
    Virtual,
    collection,
    encrypted,
    select,
    ui,
    ui_visibility,
    virtual_field,
)
from app.core.background_tasks import BackgroundTaskGroup, BackgroundTaskHandle
from app.models.config import (
    EmulatorDeviceEntry,
    EmulatorEntry,
    GameDeviceEntry,
    GameEntry,
    PlanEntry,
    PluginConfig,
    ScriptEntry,
    UserEntry,
)
from app.models.config.tag import TagItem
from app.models.schema import (
    DownloadRequest,
    DownloadSnapshot,
)
from app.models.task import (
    LogRecord,
    TaskMode,
    TaskScriptItem,
    TaskUserItem,
)
from app.plugin.base import (
    TRIGGER_TICKET,
    BasePlugin,
    DeviceHandle,
    DeviceStatus,
    DeviceSubscribeError,
    DeviceSubscription,
    EmulatorControl,
    EmulatorExpect,
    ExtensionPlugin,
    GameAdapterPlugin,
    GameControl,
    GameTypeDecl,
    ScriptAdapterPlugin,
    ScriptTypeDecl,
)
from app.plugin.base.extension import AdapterRuntime
from app.plugin.base.game import GameRuntime
from app.plugin.config import PluginCommandEntry, trigger_field
from app.plugin.errors import PluginError, PluginPrecheckError
from app.plugin.http import plugin_route
from app.plugin.services import ServiceResolver
from app.plugin.types import PLUGIN_API_VERSION, PluginState
from app.task import (
    MODE_WORKERS,
    AutoProxyWorker,
    ModeWorker,
    ScriptConfigWorker,
    ScriptViewWorker,
    UserExpander,
)

from ._version import __version__
from .core_plugin import CorePlugin

if TYPE_CHECKING:
    from app.core.config import Config as Config
    from app.core.history import History as History
    from app.core.plugin import Plugin as Plugin
    from app.core.ws import Publisher as Publisher
    from app.core.ws import protocol as protocol
    from app.models.schema import WSTaskNoticeData as WSTaskNoticeData

# 发现入口：核心插件类（非 Manager）
PLUGIN = CorePlugin

_LAZY = {
    "Config": ("app.core.config", "Config"),
    "Plugin": ("app.core.plugin", "Plugin"),
    "Publisher": ("app.core.ws", "Publisher"),
    "protocol": ("app.core.ws", "protocol"),
    "WSTaskNoticeData": ("app.models.schema", "WSTaskNoticeData"),
    "History": ("app.core.history", "History"),
}


if not TYPE_CHECKING:

    def __getattr__(name: str) -> Any:
        """按 SDK 公开导出表惰性取得宿主能力并缓存，未公开的名称按属性缺失处理。"""
        target = _LAZY.get(name)
        if target is None:
            raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
        module_name, attr = target
        from importlib import import_module

        value = getattr(import_module(module_name), attr)
        globals()[name] = value
        return value


__all__ = [
    "BackgroundTaskGroup",
    "BackgroundTaskHandle",
    "DownloadRequest",
    "DownloadSnapshot",
    "MODE_WORKERS",
    "AutoProxyWorker",
    "ModeWorker",
    "ScriptConfigWorker",
    "ScriptViewWorker",
    "AdapterRuntime",
    "GameRuntime",
    "ServiceResolver",
    "TRIGGER_TICKET",
    "BasePlugin",
    "Config",
    "ConfigCollection",
    "ConfigEntry",
    "ConfigGroup",
    "ConfigTableColumn",
    "CorePlugin",
    "DeviceHandle",
    "DeviceStatus",
    "DeviceSubscribeError",
    "DeviceSubscription",
    "EmulatorControl",
    "EmulatorDeviceEntry",
    "EmulatorEntry",
    "EmulatorExpect",
    "ExecutablePath",
    "FilePath",
    "FolderPath",
    "JsonDictString",
    "JsonListString",
    "ExtensionPlugin",
    "FieldChangeEvent",
    "GameAdapterPlugin",
    "GameControl",
    "GameTypeDecl",
    "GameDeviceEntry",
    "GameEntry",
    "LogRecord",
    "History",
    "__version__",
    "LockTicket",
    "UiVisibility",
    "PLUGIN",
    "PLUGIN_API_VERSION",
    "Plugin",
    "PluginConfig",
    "PluginCommandEntry",
    "PlanEntry",
    "PluginError",
    "Publisher",
    "ScriptEntry",
    "TagItem",
    "TaskMode",
    "TaskScriptItem",
    "TaskUserItem",
    "UserEntry",
    "UserExpander",
    "WSTaskNoticeData",
    "encrypted",
    "protocol",
    "select",
    "virtual_field",
    "PluginPrecheckError",
    "PluginState",
    "ScriptAdapterPlugin",
    "ScriptTypeDecl",
    "Trigger",
    "Virtual",
    "collection",
    "plugin_route",
    "trigger_field",
    "ui",
    "ui_visibility",
]
