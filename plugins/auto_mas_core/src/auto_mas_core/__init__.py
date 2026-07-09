from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Protocol

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
    def register(
        self,
        *,
        id: str,
        path: str,
        title: str,
        menu_label: str,
        icon: str = "app",
        component: str = "PluginPage",
        renderer: PageRenderer = "component",
        url: str | None = None,
        frontend_plugin: str | None = None,
        element_tag: str | None = None,
        entry_asset_url: str | None = None,
        style_asset_urls: list[str] | None = None,
        manifest_version: int | None = None,
        section: PageSection = "main",
        order: int = 1000,
        visible: bool = True,
        dev_only: bool = False,
    ) -> PageDeclaration: ...

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
    async def run_python_snippet(
        self,
        code: str,
        *,
        python_executable: str | None = None,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]: ...


class RuntimeFacade(Protocol):
    def info(self, force_refresh: bool = False) -> dict[str, Any]: ...
    def set(
        self,
        *,
        python_executable: str | None = None,
        timeout_seconds: int | None = None,
        options: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]: ...
    async def run(
        self,
        code: str,
        *,
        python_executable: str | None = None,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]: ...


class JsonPluginCache(Protocol):
    cache_name: str
    file_path: Path
    limit: int

    def set(self, key: str, value: Any) -> None: ...
    def get(self, key: str, default: Any = None) -> Any: ...
    def delete(self, key: str) -> bool: ...
    def exists(self, key: str) -> bool: ...
    def update(self, mapping: dict[str, Any]) -> None: ...
    def all(self) -> dict[str, Any]: ...
    def clear(self) -> None: ...
    def stats(self) -> dict[str, Any]: ...


class PluginCacheManager(Protocol):
    plugin_name: str
    instance_id: str

    @property
    def instance_cache_dir(self) -> Path: ...

    def register(
        self,
        *,
        cache_name: str = "default",
        backend: Literal["json", "database"] = "json",
        limit: int | float | str = 1000,
        limit_mode: Literal["count", "bytes"] = "count",
        limit_unit: Literal["b", "kb", "mb", "gb"] = "mb",
    ) -> JsonPluginCache: ...
    def get_registered(self, cache_name: str = "default") -> JsonPluginCache | None: ...
    def list_registered(self) -> dict[str, dict[str, Any]]: ...


class PluginEventFacade(Protocol):
    def on(
        self,
        event: str,
        handler: Any,
        *,
        priority: int = 0,
        scope: EventScope = "global",
        once: bool = False,
        error_policy: EventErrorPolicy | None = None,
    ) -> str: ...
    def off(self, event: str, handler: Any | None = None, *, listener_id: str | None = None) -> None: ...
    def emit(
        self,
        event: str,
        payload: Any = None,
        *,
        scope: EventScope = "global",
        error_policy: EventErrorPolicy = "continue",
    ) -> None: ...
    async def emit_async(
        self,
        event: str,
        payload: Any = None,
        *,
        scope: EventScope = "global",
        error_policy: EventErrorPolicy = "continue",
    ) -> None: ...
    def off_all(self) -> None: ...


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

    async def send_json(self, payload: Any) -> None: ...
    async def receive_json(self) -> Any: ...
    async def close(self) -> None: ...


class PluginServerFacade(Protocol):
    def http(
        self,
        path: str,
        handler: Any,
        *,
        methods: list[str] | tuple[str, ...] | None = None,
    ) -> Any: ...
    def action(
        self,
        id: str,
        handler: Any,
        *,
        label: str | None = None,
        method: str = "POST",
        payload: Any = None,
    ) -> Any: ...
    def websocket(self, path: str, handler: Any) -> Any: ...


class LogFacade(Protocol):
    def __getattr__(self, name: str) -> Any: ...


class GameCenterServiceProtocol(Protocol):
    """游戏中心服务契约 (由 game_center 系统插件提供)

    其他插件通过 ctx.service.get("game_center") 获取实例;
    当 game_center 插件未加载时返回 None, 消费方应自行跳过。
    """

    async def get_config(self, game_id: str | None) -> tuple[list, dict]: ...
    async def add(self, preset_key: str | None = None) -> tuple[Any, Any]: ...
    async def update(self, game_id: str, data: dict) -> None: ...
    async def delete(self, game_id: str) -> None: ...
    async def reorder(self, index_list: list[str]) -> None: ...
    def presets(self) -> list[dict]: ...
    async def check(self, game_id: str) -> dict[str, Any]: ...
    async def install(self, game_id: str) -> dict[str, Any]: ...
    async def cancel(self, game_id: str) -> dict[str, Any]: ...
    async def launch(self, game_id: str) -> dict[str, Any]: ...
    async def close(self, game_id: str) -> dict[str, Any]: ...
    async def open_official_launcher(self, game_id: str) -> dict[str, Any]: ...
    async def install_local_apk(self, game_id: str, apk_path: str) -> dict[str, Any]: ...
    def task_status(self, game_id: str) -> dict[str, Any]: ...
    def register_provider(self, name: str, provider_cls: Any) -> None: ...


class PluginContext(Protocol):
    plugin_name: str
    instance_id: str
    config: PluginConfigProxy
    logger: PluginLogger
    event: PluginEventFacade
    service: ServiceFacade
    server: PluginServerFacade
    runtime_api: RuntimeAPI
    runtime: RuntimeFacade
    cache: PluginCacheManager
    log: LogFacade
    page: PageFacade

    def provide(self, name: str) -> None: ...
    def set(self, name: str, value: Any) -> None: ...
    def get(self, name: str, default: Any = None) -> Any: ...
    def inject(self, needs: Any = None, wants: Any = None, ready: Any = None) -> None: ...


__all__ = [
    "EventErrorPolicy",
    "EventScope",
    "GameCenterServiceProtocol",
    "JsonPluginCache",
    "LogFacade",
    "PageDeclaration",
    "PageFacade",
    "PageRenderer",
    "PageSection",
    "PluginCacheManager",
    "PluginConfigProxy",
    "PluginContext",
    "PluginEventFacade",
    "PluginHttpRequest",
    "PluginHttpResponse",
    "PluginLogger",
    "PluginServerFacade",
    "PluginWebSocketSession",
    "RuntimeAPI",
    "RuntimeFacade",
    "ServiceFacade",
]
