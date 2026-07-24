from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Literal, Protocol

PageSection = Literal["main", "bottom", "dev"]
PageRenderer = Literal["component", "iframe", "custom-element"]
EventScope = Literal["global", "instance"]
EventErrorPolicy = Literal["continue", "raise"]

BROWSER_RUNTIME_SERVICE = "browser.runtime.v1"


class BrowserRuntimeError(RuntimeError):
    """浏览器运行时跨插件契约的稳定错误。"""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        operation: str,
        retryable: bool = False,
        safe_details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.operation = operation
        self.retryable = retryable
        self.safe_details = dict(safe_details or {})

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "operation": self.operation,
            "retryable": self.retryable,
            "details": self.safe_details,
        }


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

    @property
    def instance_data_dir(self) -> Path: ...

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
    body: bytes
    json: Any
    instance_id: str


class PluginHttpResponse(Protocol):
    body: Any
    status_code: int
    headers: dict[str, str]
    media_type: str | None


class PluginWebSocketSession(Protocol):
    websocket: Any
    path: str
    instance_id: str

    async def send_json(self, data: Any) -> None: ...
    async def send_text(self, data: str) -> None: ...
    async def close(self, code: int = 1000, reason: str = "正常关闭") -> None: ...


class PluginServerFacade(Protocol):
    def http(
        self,
        path: str,
        handler: Any,
        *,
        methods: Iterable[str] | None = None,
        action: str | dict[str, Any] | None = None,
    ) -> Any: ...
    def action(
        self,
        id: str,
        label: str,
        path: str,
        *,
        method: str = "POST",
        payload: Any = None,
        refresh: bool = False,
    ) -> Any: ...
    def websocket(
        self,
        path: str,
        on_message: Any,
        *,
        on_connect: Any | None = None,
        on_disconnect: Any | None = None,
        ping_interval: float = 15.0,
        ping_timeout: float = 30.0,
    ) -> Any: ...
    async def open_ws(
        self,
        name: str,
        url: str,
        *,
        on_message: Any | None = None,
        on_connect: Any | None = None,
        on_disconnect: Any | None = None,
        reconnect: bool = True,
        ping_interval: float = 15.0,
        ping_timeout: float = 30.0,
    ) -> Any: ...


class BrowserRuntimeService(Protocol):
    """跨插件 Chromium 浏览器运行时契约。"""

    def snapshot(self) -> dict[str, Any]: ...
    async def prepare(self, request: dict[str, Any] | None = None) -> dict[str, Any]: ...
    async def open_session(self, request: dict[str, Any]) -> dict[str, Any]: ...
    async def session_status(
        self,
        session_id: str,
        *,
        session_token: str,
    ) -> dict[str, Any]: ...
    async def navigate(
        self,
        session_id: str,
        url: str,
        *,
        session_token: str,
    ) -> dict[str, Any]: ...
    async def activate(self, session_id: str, *, session_token: str) -> bool: ...
    async def capture(
        self,
        session_id: str,
        *,
        session_token: str,
        image_format: Literal["jpeg", "png", "webp"] = "jpeg",
        quality: int = 90,
    ) -> bytes: ...
    async def execute_script(
        self,
        session_id: str,
        script: str,
        *args: Any,
        session_token: str,
    ) -> Any: ...
    async def execute_cdp(
        self,
        session_id: str,
        command: str,
        params: dict[str, Any] | None = None,
        *,
        session_token: str,
    ) -> dict[str, Any]: ...
    async def automation_handoff(
        self,
        session_id: str,
        *,
        session_token: str,
    ) -> dict[str, Any]: ...
    async def release_automation_handoff(
        self,
        session_id: str,
        *,
        session_token: str,
        lease_token: str,
    ) -> dict[str, Any]: ...
    async def close_session(
        self,
        session_id: str,
        *,
        session_token: str,
    ) -> dict[str, Any]: ...


class LogFacade(Protocol):
    def __getattr__(self, name: str) -> Any: ...


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
    data_dir: Path
    log: LogFacade
    page: PageFacade

    def provide(self, name: str) -> None: ...
    def set(self, name: str, value: Any) -> None: ...
    def get(self, name: str, default: Any = None) -> Any: ...
    def inject(self, needs: Any = None, wants: Any = None, ready: Any = None) -> None: ...


__all__ = [
    "BROWSER_RUNTIME_SERVICE",
    "BrowserRuntimeError",
    "BrowserRuntimeService",
    "EventErrorPolicy",
    "EventScope",
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
