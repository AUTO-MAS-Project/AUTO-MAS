"""AUTO-MAS 插件协议与开发 SDK。

公开能力：
- 顶层：基类、Config、Plugin（Manager 单例）、PLUGIN（核心插件入口类）
- ``auto_mas_core.utils`` / ``auto_mas_core.services``：宿主整包再导出
- ``auto_mas_core.plugin.services`` / ``.http``：插件系统总线与 HTTP（导入路径消歧）
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol

from app.config import (
    ConfigCollection,
    ConfigEntry,
    ConfigGroup,
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
    trigger_field,
    ui,
    ui_visibility,
    virtual_field,
)
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
from app.models.task import (
    HistoryRecordData,
    LogRecordEntry,
    TaskMode,
    TaskScriptItem,
    TaskUserItem,
)
from app.task import (
    MODE_WORKERS,
    AutoProxyWorker,
    ManualReviewWorker,
    ModeWorker,
    ScriptConfigWorker,
    UserExpander,
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
from app.plugin.errors import PluginError, PluginPrecheckError
from app.plugin.http import plugin_route
from app.plugin.types import PLUGIN_API_VERSION, PluginState

from .core_plugin import CorePlugin

if TYPE_CHECKING:
    from app.core.config import Config as Config
    from app.core.plugin_manager import Plugin as Plugin

PageSection = Literal["main", "bottom", "dev"]
PageRenderer = Literal["component", "iframe", "custom-element"]
EventScope = Literal["global", "instance"]
EventErrorPolicy = Literal["continue", "raise"]


class PluginConfigProxy(Protocol):
    def get(self, key: str, default: Any = None) -> Any: ...
    def set(self, key: str, value: Any) -> None: ...
    def update(self, values: dict[str, Any] | None = None, **kwargs: Any) -> None: ...
    def reset(self, values: dict[str, Any] | None = None) -> dict[str, Any]: ...
    def to_dict(self) -> dict[str, Any]: ...
    def source_dict(self) -> dict[str, Any]: ...


class PluginLogger(Protocol):
    def debug(self, message: Any, *args: Any, **kwargs: Any) -> Any: ...
    def info(self, message: Any, *args: Any, **kwargs: Any) -> Any: ...
    def warning(self, message: Any, *args: Any, **kwargs: Any) -> Any: ...
    def error(self, message: Any, *args: Any, **kwargs: Any) -> Any: ...
    def exception(self, message: Any, *args: Any, **kwargs: Any) -> Any: ...


class PageDeclaration(Protocol):
    id: str
    path: str
    title: str
    menu_label: str
    icon: str
    component: str
    renderer: PageRenderer
    url: str | None
    section: PageSection
    order: int
    visible: bool


class PageFacade(Protocol):
    def register(self, *, id: str, path: str, title: str, menu_label: str, icon: str = "app", component: str = "PluginPage", renderer: PageRenderer = "component", url: str | None = None, frontend_plugin: str | None = None, element_tag: str | None = None, entry_asset_url: str | None = None, style_asset_urls: list[str] | None = None, manifest_version: int | None = None, section: PageSection = "main", order: int = 1000, visible: bool = True, dev_only: bool = False) -> PageDeclaration: ...
    def register_many(self, pages: list[Any] | tuple[Any, ...]) -> None: ...
    def unregister_all(self) -> None: ...


class ServiceFacade(Protocol):
    def provide(self, name: str) -> None: ...
    def set(self, name: str, value: Any) -> None: ...
    def get(self, name: str, default: Any = None) -> Any: ...
    def inject(self, needs: Any = None, wants: Any = None, ready: Any = None) -> None: ...
    def miss(self) -> set[str]: ...


class RuntimeAPI(Protocol):
    def set_runtime_options(self, options: dict[str, Any]) -> dict[str, Any]: ...
    def get_runtime_info(self, force_refresh: bool = False) -> dict[str, Any]: ...
    def check_interpreter(self, python_executable: str | None = None) -> dict[str, Any]: ...
    def list_scripts(self) -> Any: ...
    def get_script_log(self, script_id: str, limit: int = 2000) -> Any: ...


class RuntimeFacade(Protocol):
    def info(self, force_refresh: bool = False) -> dict[str, Any]: ...


class JsonPluginCache(Protocol):
    cache_name: str
    file_path: Path
    limit: int


class PluginCacheManager(Protocol):
    plugin_name: str
    instance_id: str


class PluginEventFacade(Protocol):
    def on(self, event: str, handler: Any, *, priority: int = 0, scope: EventScope = "global", once: bool = False, error_policy: EventErrorPolicy | None = None) -> str: ...


class PluginHttpRequest(Protocol):
    method: str
    path: str
    query: dict[str, Any]
    headers: dict[str, str]
    body: Any


class PluginHttpResponse(Protocol):
    status: int
    body: Any
    headers: dict[str, str]


class PluginWebSocketSession(Protocol):
    path: str
    query: dict[str, Any]


class PluginServerFacade(Protocol):
    def http(self, path: str, handler: Any, *, methods: list[str] | tuple[str, ...] | None = None) -> Any: ...


class LogFacade(Protocol):
    def __getattr__(self, name: str) -> Any: ...


# 发现入口：核心插件类（非 Manager）
PLUGIN = CorePlugin

_LAZY = {
    "Config": ("app.core.config", "Config"),
    "Plugin": ("app.core.plugin_manager", "Plugin"),
    "Publisher": ("app.core.ws", "Publisher"),
    "protocol": ("app.core.ws", "protocol"),
    "WSTaskNoticeData": ("app.core.ws.protocol", "WSTaskNoticeData"),
    "history_store": ("app.core.history", "history_store"),
}


def __getattr__(name: str) -> Any:
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr = target
    from importlib import import_module

    value = getattr(import_module(module_name), attr)
    globals()[name] = value
    return value


__all__ = [
    "TRIGGER_TICKET",
    "BasePlugin",
    "Config",
    "ConfigCollection",
    "ConfigEntry",
    "ConfigGroup",
    "CorePlugin",
    "DeviceHandle",
    "DeviceStatus",
    "DeviceSubscribeError",
    "DeviceSubscription",
    "EmulatorControl",
    "EmulatorDeviceEntry",
    "EmulatorEntry",
    "EmulatorExpect",
    "EventErrorPolicy",
    "EventScope",
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
    "HistoryRecordData",
    "LogRecordEntry",
    "history_store",
    "LockTicket",
    "UiVisibility",
    "PLUGIN",
    "PLUGIN_API_VERSION",
    "Plugin",
    "PluginConfig",
    "PluginConfigProxy",
    "PluginLogger",
    "PageDeclaration",
    "PageFacade",
    "PageRenderer",
    "PageSection",
    "ServiceFacade",
    "RuntimeAPI",
    "RuntimeFacade",
    "JsonPluginCache",
    "PluginCacheManager",
    "PluginEventFacade",
    "PluginHttpRequest",
    "PluginHttpResponse",
    "PluginWebSocketSession",
    "PluginServerFacade",
    "LogFacade",
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
