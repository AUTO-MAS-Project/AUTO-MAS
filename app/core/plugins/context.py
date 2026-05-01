#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

from __future__ import annotations

from pathlib import Path
from copy import deepcopy
from typing import Any, Dict, Callable, Optional, Iterator, Protocol
import asyncio
import inspect
import logging

from .cache_store import PluginCacheManager
from .event_bus import EventBus
from .event_contract import EventErrorPolicy, EventScope
from .runtime_api import RuntimeAPI
from .service_registry import ServiceRegistry
from .server import PluginServerFacade, PluginServerRegistry, plugin_server


class PluginLogger(Protocol):
    """插件上下文使用的最小日志协议。"""

    def debug(self, message: Any, *args: Any, **kwargs: Any) -> Any: ...

    def info(self, message: Any, *args: Any, **kwargs: Any) -> Any: ...

    def warning(self, message: Any, *args: Any, **kwargs: Any) -> Any: ...

    def error(self, message: Any, *args: Any, **kwargs: Any) -> Any: ...

    def exception(self, message: Any, *args: Any, **kwargs: Any) -> Any: ...


class PluginContext:
    """面向插件的上下文对象，公开受控的 MAS 功能。"""

    plugin_name: str
    instance_id: str
    config: PluginConfigProxy
    logger: logging.Logger
    event: PluginEventFacade
    service: ServiceFacade
    server: PluginServerFacade
    runtime_api: RuntimeAPI
    runtime: RuntimeFacade
    cache: PluginCacheManager

    def __init__(
        self,
        *,
        plugin_name: str,
        instance_id: str | None = None,
        config: Dict[str, Any],
        logger: logging.Logger,
        events: EventBus,
        runtime_capabilities: Optional[Dict[str, Callable[..., Any]]] = None,
        service_registry: Optional[ServiceRegistry] = None,
        server_registry: Optional[PluginServerRegistry] = None,
        provides: Optional[set[str]] = None,
        needs: Optional[set[str]] = None,
        wants: Optional[set[str]] = None,
    ) -> None:
        # 基础必要属性
        self.plugin_name = plugin_name
        self.instance_id = instance_id or plugin_name
        self.config = PluginConfigProxy(config)
        self.logger = logger
        self.event = PluginEventFacade(
            plugin_name=self.plugin_name,
            instance_id=self.instance_id,
            events=events,
        )

        # service 门面负责插件服务声明、赋值、依赖注入和未声明访问告警。
        self.service = ServiceFacade(
            ctx=self,
            plugin_name=self.plugin_name,
            instance_id=self.instance_id,
            logger=self.logger,
            registry=service_registry,
            provides=provides,
            needs=needs,
            wants=wants,
        )

        # server 门面负责声明插件对外 HTTP/WS 能力与前端动作。
        self.server = PluginServerFacade(
            registry=server_registry or plugin_server,
            plugin_name=self.plugin_name,
            instance_id=self.instance_id,
        )

        # 解释器能力函数集合
        self.runtime_api = RuntimeAPI(
            plugin_name=self.plugin_name,
            instance_id=self.instance_id,
            config=self.config,
            logger=self.logger,
            runtime_capabilities=runtime_capabilities,
        )
        self.runtime = RuntimeFacade(self.runtime_api)

        # 缓存管理器
        self.cache = PluginCacheManager(
            plugin_name=self.plugin_name,
            instance_id=self.instance_id,
            data_root=Path.cwd() / "data",
            logger=self.logger,
        )

    def provide(self, name: str) -> None:
        """声明服务槽位。"""
        self.service.provide(name)

    def set(self, name: str, value: Any) -> None:
        """设置服务实例值。"""
        self.service.set(name, value)

    def get(self, name: str, default: Any = None) -> Any:
        """读取服务实例值。"""
        return self.service.get(name, default)

    def inject(
        self,
        needs: str | list[str] | set[str] | None = None,
        wants: str | list[str] | set[str] | None = None,
        ready: Optional[Callable[..., Any]] = None,
    ) -> None:
        """注册动态依赖并在满足时触发回调。"""
        self.service.inject(needs=needs, wants=wants, ready=ready)


class PluginConfigProxy(dict[str, Any]):
    """插件配置代理，兼容字典访问并提供 set/update/reset 语义。"""

    def __init__(self, initial: Dict[str, Any] | None = None) -> None:
        data = deepcopy(initial) if isinstance(initial, dict) else {}
        super().__init__(data)
        self._source_config: Dict[str, Any] = deepcopy(data)

    def set(self, key: str, value: Any) -> None:
        """
        设置单个配置项。

        Args:
            key (str): 配置键。
            value (Any): 配置值。

        Returns:
            None: 无返回值。

        Raises:
            TypeError: `key` 不是字符串时抛出。
            ValueError: `key` 为空字符串时抛出。
        """
        if not key.strip():
            raise ValueError("配置键不能为空字符串")
        self[key] = value

    def update(self, values: Dict[str, Any] | None = None, **kwargs: Any) -> None:  # type: ignore[override]
        """
        批量更新配置项。

        Args:
            values (Dict[str, Any] | None): 待合并配置字典，可为 None。
            **kwargs (Any): 额外键值对参数。

        Returns:
            None: 无返回值。

        Raises:
            TypeError: `values` 非字典时抛出。
        """

        payload: Dict[str, Any] = {}
        if isinstance(values, dict):
            payload.update(values)
        if kwargs:
            payload.update(kwargs)

        for key, value in payload.items():
            self.set(key, value)

    def reset(self, values: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """
        删除源配置并以新配置重建当前配置。

        Args:
            values (Dict[str, Any] | None): 新配置对象；为 None 时重置为空字典。

        Returns:
            Dict[str, Any]: 重置后的配置快照。

        Raises:
            TypeError: `values` 非字典且非 None 时抛出。
        """

        next_source = deepcopy(values) if isinstance(values, dict) else {}
        self._source_config = deepcopy(next_source)
        super().clear()
        super().update(deepcopy(next_source))
        return self.to_dict()

    def to_dict(self) -> Dict[str, Any]:
        """返回当前配置的深拷贝字典。"""
        return deepcopy(dict(self))

    def source_dict(self) -> Dict[str, Any]:
        """返回源配置的深拷贝字典。"""
        return deepcopy(self._source_config)

    def __iter__(self) -> Iterator[str]:
        """返回配置键的迭代器。"""
        return super().__iter__()


class ServiceFacade:
    """插件服务门面。"""

    def __init__(
        self,
        *,
        ctx: PluginContext,
        plugin_name: str,
        instance_id: str,
        logger: logging.Logger | Any,
        registry: Optional[ServiceRegistry],
        provides: Optional[set[str]] = None,
        needs: Optional[set[str]] = None,
        wants: Optional[set[str]] = None,
    ) -> None:
        self._ctx: PluginContext = ctx
        self._plugin_name: str = plugin_name
        self._instance_id: str = instance_id
        self._logger: logging.Logger | Any = logger
        self._registry: ServiceRegistry = registry or ServiceRegistry()

        self._provides = set(provides or set())
        self._needs = set(needs or set())
        self._wants = set(wants or set())
        self._declared = set(self._provides | self._needs | self._wants)

        self._registry.bind(self._instance_id, self._needs, self._wants)
        for name in self._provides:
            self._registry.provide(name, self._instance_id)

    @staticmethod
    def _names(raw: str | list[str] | tuple[str, ...] | set[str] | None) -> set[str]:
        if raw is None:
            return set()
        if isinstance(raw, str):
            name = raw.strip()
            return {name} if name else set()
            result: set[str] = set()
            for item in raw:
                text = str(item or "").strip()
                if text:
                    result.add(text)
            return result
        return set()

    def _warn(self, name: str) -> None:
        if name in self._declared:
            return
        # 保持运行时兼容，只做行为引导。
        self._logger.warning(
            f"访问未声明服务: plugin={self._plugin_name}, instance={self._instance_id}, service={name}"
        )

    @staticmethod
    def _call(func: Callable[..., Any], ctx: PluginContext) -> Callable[[], Any]:
        def wrapped() -> Any:
            try:
                signature = inspect.signature(func)
            except (TypeError, ValueError):
                # 对无法反射签名的可调用对象，按无参调用兼容。
                return func()

            if not signature.parameters:
                return func()
            # 有参回调默认注入 PluginContext，降低插件侧样板代码。
            return func(ctx)

        return wrapped

    def provide(self, name: str) -> None:
        service = str(name or "").strip()
        if not service:
            return
        self._declared.add(service)
        self._provides.add(service)
        self._registry.provide(service, self._instance_id)

    def set(self, name: str, value: Any) -> None:
        service = str(name or "").strip()
        if not service:
            return
        self.provide(service)
        self._registry.set(service, value, self._instance_id)

    def get(self, name: str, default: Any = None) -> Any:
        service = str(name or "").strip()
        if not service:
            return default
        self._warn(service)
        return self._registry.take(service, self._instance_id, default)

    def inject(
        self,
        needs: str | list[str] | set[str] | None = None,
        wants: str | list[str] | set[str] | None = None,
        ready: Optional[Callable[..., Any]] = None,
    ) -> None:
        # 动态注入会持续合并依赖声明，确保后续 get() 不被误报未声明。
        needset = self._names(needs)
        wantset = self._names(wants)
        self._needs.update(needset)
        self._wants.update(wantset)
        self._declared.update(needset)
        self._declared.update(wantset)

        callback: Optional[Callable[[], Any]] = None
        if callable(ready):
            callback = self._call(ready, self._ctx)

        self._registry.inject(
            owner=self._instance_id,
            needs=self._needs,
            wants=self._wants,
            ready=callback,
        )

    def miss(self) -> "set[str]":
        return self._registry.miss(self._instance_id)


class RuntimeFacade:
    """RuntimeAPI 语法糖包装层，提供更简洁的调用方式。"""

    def __init__(self, api: RuntimeAPI) -> None:
        self._api = api

    def info(self, force_refresh: bool = False) -> Dict[str, Any]:
        """获取运行时环境信息。"""
        return self._api.get_runtime_info(force_refresh=force_refresh)

    def set(
        self,
        *,
        python_executable: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        options: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """更新 runtime 配置选项。"""
        payload: Dict[str, Any] = {}
        if isinstance(options, dict):
            payload.update(options)
        if python_executable is not None:
            payload["python_executable"] = python_executable
        if timeout_seconds is not None:
            payload["python_timeout_seconds"] = timeout_seconds
        if kwargs:
            payload.update(kwargs)
        return self._api.set_runtime_options(payload)

    async def run(
        self,
        code: str,
        *,
        python_executable: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
    ) -> Dict[str, Any]:
        """执行 Python 代码片段。"""
        return await self._api.run_python_snippet(
            code,
            python_executable=python_executable,
            timeout_seconds=timeout_seconds,
        )

    def __getattr__(self, name: str) -> Any:
        """回退到 RuntimeAPI，保持历史调用方式兼容。"""
        return getattr(self._api, name)


class PluginEventFacade:
    """插件事件门面，统一提供监听、取消监听与事件发射能力。"""

    def __init__(
        self,
        *,
        plugin_name: str,
        instance_id: str,
        events: EventBus,
    ) -> None:
        """
        初始化插件事件门面。

        Args:
            plugin_name (str): 插件名。
            instance_id (str): 插件实例 ID。
            events: 底层事件总线对象。

        Returns:
            None: 无返回值。

        Raises:
            TypeError: `plugin_name` 不是字符串时抛出。
            ValueError: `plugin_name` 为空字符串时抛出。
            TypeError: `instance_id` 不是字符串时抛出。
            ValueError: `instance_id` 为空字符串时抛出。
            AttributeError: `events` 缺少 `on/off/emit` 任意方法时抛出。
        """

        if not plugin_name.strip():
            raise ValueError("plugin_name 不能为空字符串")
        if not instance_id.strip():
            raise ValueError("instance_id 不能为空字符串")

        for method_name in ("on", "off", "emit"):
            if not hasattr(events, method_name):
                raise AttributeError(f"events 缺少必要方法: {method_name}")

        self._plugin_name: str = plugin_name
        self._instance_id: str = instance_id
        self._events: EventBus = events

    def on(
        self,
        event: str,
        handler: Callable[[Any], Any],
        *,
        priority: int = 0,
        scope: EventScope = "global",
        once: bool = False,
        error_policy: EventErrorPolicy | None = None,
    ) -> str:
        """
        注册事件监听器。

        Args:
            event (str): 事件名。
            handler (Callable[[Any], Any]): 事件处理函数。
            priority (int): 监听优先级，数值越大越先执行。
            scope (EventScope): 监听作用域，支持 global 或 instance。
            once (bool): 是否触发一次后自动解绑。
            error_policy (EventErrorPolicy | None): 监听器级错误策略。

        Returns:
            str: 监听器 ID。

        Raises:
            TypeError: `event` 或 `handler` 类型不合法时抛出。
            ValueError: `event` 或策略参数不合法时抛出。
        """
        return self._events.on(
            event,
            handler,
            priority=priority,
            scope=scope,
            once=once,
            error_policy=error_policy,
            owner_plugin_name=self._plugin_name,
            owner_instance_id=self._instance_id,
        )

    def off(
        self,
        event: str,
        handler: Callable[[Any], Any] | None = None,
        *,
        listener_id: str | None = None,
    ) -> None:
        """
        取消事件监听。

        Args:
            event (str): 事件名。
            handler (Callable[[Any], Any] | None): 监听函数对象。
            listener_id (str | None): 监听器 ID。

        Returns:
            None: 无返回值。

        Raises:
            ValueError: `handler` 与 `listener_id` 同时为空时抛出。
        """
        self._events.off(event, handler, listener_id=listener_id)

    async def emit_async(
        self,
        event: str,
        payload: Any = None,
        *,
        scope: EventScope = "instance",
        error_policy: EventErrorPolicy = "continue",
    ) -> None:
        """
        异步发送事件。

        默认使用 instance 作用域，并自动附带当前实例 ID 作为来源。

        Args:
            event (str): 事件名。
            payload (Any): 事件载荷。
            scope (EventScope): 事件作用域。
            error_policy (EventErrorPolicy): 事件错误策略。

        Returns:
            None: 无返回值。

        Raises:
            ValueError: 底层事件总线校验参数失败时抛出。
            Exception: 在 `error_policy="raise"` 且监听器失败时向上抛出。
        """
        kwargs: Dict[str, Any] = {
            "scope": scope,
            "error_policy": error_policy,
        }
        if scope == "instance":
            kwargs["source_instance_id"] = self._instance_id

        await self._events.emit(event, payload, **kwargs)

    def emit(
        self,
        event: str,
        payload: Any = None,
        *,
        scope: EventScope = "instance",
        error_policy: EventErrorPolicy = "continue",
    ) -> None:
        """
        同步桥接发送事件。

        Args:
            event (str): 事件名。
            payload (Any): 事件载荷。
            scope (EventScope): 事件作用域。
            error_policy (EventErrorPolicy): 事件错误策略。

        Returns:
            None: 无返回值。

        Raises:
            ValueError: 底层事件总线校验参数失败时抛出。
            Exception: 在 `error_policy="raise"` 且监听器失败时向上抛出。
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(
                self.emit_async(
                    event,
                    payload,
                    scope=scope,
                    error_policy=error_policy,
                )
            )
            return

        loop.create_task(
            self.emit_async(
                event,
                payload,
                scope=scope,
                error_policy=error_policy,
            )
        )

    def off_all(self) -> None:
        """
        取消当前实例注册的全部监听器。

        Returns:
            None: 无返回值。
        """
        if hasattr(self._events, "off_by_instance"):
            self._events.off_by_instance(self._instance_id)
