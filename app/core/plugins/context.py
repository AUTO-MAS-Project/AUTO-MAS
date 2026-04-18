#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

from collections.abc import Iterable, Iterator, Mapping
from copy import deepcopy
import asyncio
from pathlib import Path
from typing import Any, Callable, cast

from .cache_store import PluginCacheManager
from .event_bus import EventBus
from .event_contract import EventErrorPolicy, EventScope
from .runtime_api import RuntimeAPI
from app.utils.logger import LoggerLike



class PluginContext:
    """面向插件的上下文对象，公开受控的 MAS 功能。"""

    def __init__(
        self,
        *,
        plugin_name: str,
        instance_id: str | None = None,
        config: dict[str, Any],
        logger: LoggerLike,
        events: EventBus,
        runtime_capabilities: dict[str, Callable[..., Any]] | None = None,
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

class PluginConfigProxy(dict[str, Any]):
    """插件配置代理，兼容字典访问并提供 set/update/reset 语义。"""

    def __init__(self, initial: Mapping[str, Any] | None = None) -> None:
        data = deepcopy(dict(initial)) if initial is not None else {}
        super().__init__(data)
        self._source_config: dict[str, Any] = deepcopy(data)

    def set(self, key: object, value: Any) -> None:
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
        if not isinstance(key, str):
            raise TypeError("配置键必须是字符串")
        if not key.strip():
            raise ValueError("配置键不能为空字符串")
        self[key] = value

    def update(self, *args: Any, **kwargs: Any) -> None:
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
        if len(args) > 1:
            raise TypeError("update(values) 最多只接受一个位置参数")

        items: list[tuple[object, Any]] = []
        if args:
            values = args[0]
            if values is None:
                items = []
            elif isinstance(values, Mapping):
                mapping = cast(Mapping[object, Any], values)
                items = list(mapping.items())
            else:
                try:
                    items = list(cast(Iterable[tuple[object, Any]], values))
                except Exception as e:
                    raise TypeError(
                        "update(values) 的 values 必须是映射、键值对迭代器或 None"
                    ) from e

        for key, value in items:
            self.set(key, value)
        for key, value in kwargs.items():
            self.set(key, value)

    def reset(self, values: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """
        删除源配置并以新配置重建当前配置。

        Args:
            values (Dict[str, Any] | None): 新配置对象；为 None 时重置为空字典。

        Returns:
            Dict[str, Any]: 重置后的配置快照。

        Raises:
            TypeError: `values` 非字典且非 None 时抛出。
        """
        next_source = deepcopy(dict(values)) if values is not None else {}
        self._source_config = deepcopy(next_source)
        super().clear()
        super().update(deepcopy(next_source))
        return self.to_dict()

    def to_dict(self) -> dict[str, Any]:
        """返回当前配置的深拷贝字典。"""
        return deepcopy(dict(self))

    def source_dict(self) -> dict[str, Any]:
        """返回源配置的深拷贝字典。"""
        return deepcopy(self._source_config)

    def __iter__(self) -> Iterator[str]:
        """返回配置键的迭代器。"""
        return super().__iter__()




class RuntimeFacade:
    """RuntimeAPI 语法糖包装层，提供更简洁的调用方式。"""

    def __init__(self, api: RuntimeAPI) -> None:
        self._api = api

    def info(self, force_refresh: bool = False) -> dict[str, Any]:
        """获取运行时环境信息。"""
        return self._api.get_runtime_info(force_refresh=force_refresh)

    def set(
        self,
        *,
        python_executable: str | None = None,
        timeout_seconds: int | None = None,
        options: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """更新 runtime 配置选项。"""
        payload: dict[str, Any] = {}
        if options is not None:
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
        python_executable: str | None = None,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
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
        plugin_name: object,
        instance_id: object,
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
        if not isinstance(plugin_name, str):
            raise TypeError("plugin_name 必须是字符串")
        if not plugin_name.strip():
            raise ValueError("plugin_name 不能为空字符串")
        if not isinstance(instance_id, str):
            raise TypeError("instance_id 必须是字符串")
        if not instance_id.strip():
            raise ValueError("instance_id 不能为空字符串")

        self._plugin_name = plugin_name
        self._instance_id = instance_id
        self._events = events

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
        kwargs: dict[str, Any] = {
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
        self._events.off_by_instance(self._instance_id)
