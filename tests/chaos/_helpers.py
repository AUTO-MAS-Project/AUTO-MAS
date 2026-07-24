#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

"""Chaos 测试共享辅助：stub host、fake plugin、fake config store 与受控 failpoint。

设计原则：
- 完全 deterministic：仅使用 Event/Barrier/fake clock/受控 failpoint，禁止 long sleep。
- 不启动真实 Agent/游戏/模拟器/真实插件包。
- fake plugin 实现 REQUIRED_LIFECYCLE_METHODS，可在生命周期任意阶段注入失败。
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
import types
from contextlib import asynccontextmanager, contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable
from unittest.mock import MagicMock

from app.plugins.context import PluginContext
from app.plugins.event_bus import EventBus
from app.plugins.loader import PluginLoader, PluginRecord
from app.plugins.service_registry import ServiceRegistry
from app.plugins.server import plugin_server


@dataclass
class FakePluginLifecycleLog:
    """记录 fake plugin 生命周期方法调用顺序与参数。"""

    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = field(default_factory=list)

    def record(self, method: str, *args: Any, **kwargs: Any) -> None:
        self.calls.append((method, args, kwargs))

    def method_names(self) -> list[str]:
        return [name for name, _, _ in self.calls]

    def reset(self) -> None:
        self.calls.clear()


class FakePlugin:
    """可控的生命周期插件实现。

    通过 failpoints 字典注入受控失败：
        failpoints = {"on_start": RuntimeError("boom")}
    在对应方法被调用时抛出指定异常。
    """

    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        self.failpoints: dict[str, BaseException | Callable[[], BaseException]] = {}
        self.log: FakePluginLifecycleLog = getattr(ctx, "_fake_log", FakePluginLifecycleLog())
        # 便于测试断言：暴露 service 注册情况
        self.service_values: dict[str, Any] = {}

    async def on_load(self, ctx: PluginContext) -> None:
        self.log.record("on_load", ctx)
        await self._maybe_fail("on_load")

    async def on_start(self) -> None:
        self.log.record("on_start")
        await self._maybe_fail("on_start")
        # 声明一个 service 便于断言清理
        if hasattr(self.ctx, "service"):
            self.ctx.service.set("fake_service", {"started_at": time.time()})

    async def on_stop(self, reason: str) -> None:
        self.log.record("on_stop", reason)
        await self._maybe_fail("on_stop")

    async def on_unload(self) -> None:
        self.log.record("on_unload")
        await self._maybe_fail("on_unload")

    async def on_reload_prepare(self) -> None:
        self.log.record("on_reload_prepare")

    async def on_reload_commit(self) -> None:
        self.log.record("on_reload_commit")

    async def _maybe_fail(self, phase: str) -> None:
        fp = self.failpoints.get(phase)
        if fp is None:
            return
        if callable(fp):
            exc = fp()
        else:
            exc = fp
        if isinstance(exc, BaseException):
            raise exc


class FakePluginModule(types.ModuleType):
    """模拟插件模块对象，导出 Plugin 类与可选声明。

    继承 ``types.ModuleType`` 以确保 ``inspect.ismodule()`` 返回 True，
    匹配 ``PluginLoader._load_plugin_class_from_entry_point`` 的模块分支。
    """

    def __init__(
        self,
        plugin_class: type = FakePlugin,
        *,
        pages: list[dict[str, Any]] | None = None,
        default_instance: dict[str, Any] | None = None,
        script_type_bindings: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__("fake_plugin_module")
        self.Plugin = plugin_class
        if pages is not None:
            self.PAGES = pages
        if default_instance is not None:
            self.DEFAULT_INSTANCE = default_instance
        if script_type_bindings is not None:
            self.SCRIPT_TYPE_BINDINGS = script_type_bindings


def make_fake_plugin_source(
    plugin_name: str,
    module: Any,
    *,
    distribution: str = "fake-dist",
    version: str = "0.0.0",
) -> Any:
    """构造一个可被 loader.discover() 直接接受的 PluginSource。"""
    from app.plugins.loader import PluginLoader

    entry_point = MagicMock()
    entry_point.load = MagicMock(return_value=module)
    entry_point.module = f"fake_{plugin_name}"
    entry_point.dist = MagicMock()
    entry_point.dist.name = distribution
    entry_point.dist.version = version

    source = PluginLoader.PluginSource(
        source="pypi",
        path=None,
        entry_point=entry_point,
        module_name=f"fake_{plugin_name}",
        distribution=distribution,
        version=version,
        system=False,
        locked=False,
        visible=True,
    )
    return source


@contextmanager
def patch_loader_with_fake_plugins(
    loader: PluginLoader,
    fake_plugins: dict[str, Any],
):
    """让 loader.discover() 直接返回 fake_plugins 映射，绕过真实 entry point 扫描。

    fake_plugins: {plugin_name: PluginSource | FakePluginModule}
    若值为 FakePluginModule，则自动包装为 PluginSource。
    """
    sources: dict[str, Any] = {}
    for name, value in fake_plugins.items():
        if hasattr(value, "source") and getattr(value, "source") == "pypi":
            sources[name] = value
        else:
            sources[name] = make_fake_plugin_source(name, value)

    original_discover = loader.discover

    def fake_discover():
        loader.discovered_plugins = dict(sources)
        return loader.discovered_plugins

    loader.discover = fake_discover  # type: ignore[method-assign]
    loader.discovered_plugins = dict(sources)
    try:
        yield sources
    finally:
        loader.discover = original_discover  # type: ignore[method-assign]


class FakeServiceRegistry:
    """轻量 service registry，避免依赖真实 importlib 逻辑。"""

    def __init__(self) -> None:
        self._values: dict[str, Any] = {}
        self._owners: dict[str, set[str]] = {}
        self._watchers: list[Callable[[str, set[str]], None]] = []

    def provide(self, name: str, owner: str) -> None:
        self._owners.setdefault(name, set()).add(owner)

    def set(self, name: str, value: Any, owner: str) -> None:
        self._values[name] = value
        self._owners.setdefault(name, set()).add(owner)

    def take(self, name: str, owner: str, default: Any = None) -> Any:
        return self._values.get(name, default)

    def ready(self, name: str) -> bool:
        return name in self._values

    def owners(self, name: str) -> set[str]:
        return set(self._owners.get(name, set()))

    def drop(self, owner: str) -> None:
        for name in list(self._owners.keys()):
            self._owners[name].discard(owner)
            if not self._owners[name] and name in self._values:
                # 仅在没有其他 owner 时移除值
                pass

    def clear(self) -> None:
        self._values.clear()
        self._owners.clear()

    def watch(self, when: str, callback: Callable[[str, set[str]], None]) -> None:
        self._watchers.append(callback)


@asynccontextmanager
async def isolated_plugin_loader(*, plugins_dir: Path | None = None):
    """提供一个干净的 PluginLoader，使用 fake service registry。

    用法::

        async with isolated_plugin_loader() as (loader, service):
            ...
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) if plugins_dir is None else plugins_dir
        events = EventBus()
        service = ServiceRegistry()
        loader = PluginLoader(
            events=events,
            runtime={},
            plugins_dir=base,
            service=service,
        )
        try:
            yield loader, service
        finally:
            # 清理可能的后台 task
            task = loader._task
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass


@dataclass
class FakePluginConfigStore:
    """内存中的插件配置存储，支持受控失败注入。"""

    root: dict[str, Any]
    save_fail_on_calls: set[int] = field(default_factory=set)
    get_fail: bool = False
    io_delay: float = 0.0
    _save_calls: int = 0
    _id_counter: int = 0

    async def get_root(self, *_args, **_kwargs):
        if self.io_delay:
            await asyncio.sleep(self.io_delay)
        if self.get_fail:
            raise OSError("get_root forced failure")
        return deepcopy(self.root)

    async def save_root(self, _plugins_dir, root, **_kwargs):
        self._save_calls += 1
        if self.io_delay:
            await asyncio.sleep(self.io_delay)
        if self._save_calls in self.save_fail_on_calls:
            raise OSError(f"save_root forced failure #{self._save_calls}")
        self.root = deepcopy(root)

    def load_effective_config(self, _plugin_name, config):
        return deepcopy(config)

    def generate_instance_id(self, plugin_name: str) -> str:
        self._id_counter += 1
        return f"{plugin_name}:tx{self._id_counter}"


def find_free_port(host: str = "127.0.0.1") -> int:
    """分配一个当前空闲的本地 TCP 端口。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


@contextmanager
def occupy_port(host: str, port: int, *, kind: str = "tcp"):
    """占用一个端口用于测试。

    kind:
        - "tcp": 纯 TCP 监听，不响应 HTTP
        - "http_auto_mas": 伪装 AUTO-MAS /health 与 /ws_meta
        - "http_dev": 伪装 AUTO-MAS dev 后端
        - "http_other": 其他 HTTP 服务
    """
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(1)
    server.settimeout(0.5)

    stop = threading.Event()

    def serve():
        while not stop.is_set():
            try:
                conn, _ = server.accept()
            except (socket.timeout, OSError):
                continue
            try:
                _handle_conn(conn, kind)
            except Exception:
                pass
            finally:
                conn.close()

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    try:
        yield
    finally:
        stop.set()
        server.close()
        t.join(timeout=1.0)


def _handle_conn(conn: socket.socket, kind: str) -> None:
    """根据 kind 生成不同的 HTTP/非 HTTP 响应。"""
    conn.settimeout(0.5)
    try:
        data = conn.recv(4096)
    except socket.timeout:
        return
    if not data:
        return
    if kind == "tcp":
        # 不返回任何数据，模拟非 HTTP TCP 服务
        return
    # HTTP 类：解析请求行
    request_line = data.split(b"\r\n", 1)[0].decode("latin-1", "replace")
    parts = request_line.split()
    path = parts[1] if len(parts) >= 2 else "/"

    if kind in ("http_auto_mas", "http_dev"):
        if path == "/api/core/ws_meta":
            payload = {
                "devMode": kind == "http_dev",
                "wsPath": "/api/core/ws",
                "wsAuthToken": None,
            }
            body = json.dumps(payload).encode("utf-8")
            header = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Connection: close\r\n\r\n"
            ).encode("latin-1")
            conn.sendall(header + body)
            return
        if path == "/api/core/health":
            payload = {"ready": True, "backgroundStatus": "ready", "backgroundError": None}
            body = json.dumps(payload).encode("utf-8")
            header = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Connection: close\r\n\r\n"
            ).encode("latin-1")
            conn.sendall(header + body)
            return
        # 其它路径返回 404
        header = (
            "HTTP/1.1 404 Not Found\r\n"
            "Content-Length: 0\r\n"
            "Connection: close\r\n\r\n"
        ).encode("latin-1")
        conn.sendall(header)
        return
    if kind == "http_other":
        body = b"other service"
        header = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/plain\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n\r\n"
        ).encode("latin-1")
        conn.sendall(header + body)
        return


@asynccontextmanager
async def fake_clock():
    """提供受控时间推进上下文（当前仅占位，按需扩展）。"""
    yield
