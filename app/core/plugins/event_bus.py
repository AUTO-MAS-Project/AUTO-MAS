#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

import asyncio
import inspect
import uuid
from dataclasses import dataclass
from collections import defaultdict
from typing import Any, Callable, DefaultDict, Dict, List, Optional

from app.utils import get_logger

from .event_contract import EventErrorPolicy, EventScope


logger = get_logger("插件事件总线")


class EventDispatchError(Exception):
    """事件分发过程中的聚合异常。"""


@dataclass
class RegisteredHandler:
    """事件总线中的监听器注册记录。"""

    listener_id: str
    event: str
    handler: Callable[[Any], Any]
    priority: int
    scope: EventScope
    once: bool
    error_policy: EventErrorPolicy | None
    owner_plugin_name: Optional[str]
    owner_instance_id: Optional[str]


class EventBus:
    """插件系统进程内事件总线（纯异步并发分发）。"""

    def __init__(self) -> None:
        self._handlers: DefaultDict[str, List[RegisteredHandler]] = defaultdict(list)
        self._lock = asyncio.Lock()

    def on(
        self,
        event: object,
        handler: Callable[[Any], Any],
        *,
        priority: int = 0,
        scope: EventScope = "global",
        once: bool = False,
        error_policy: EventErrorPolicy | None = None,
        owner_plugin_name: Optional[str] = None,
        owner_instance_id: Optional[str] = None,
    ) -> str:
        """
        注册事件监听器并返回监听器 ID。

        Args:
            event (str): 事件名。
            handler (Callable[[Any], Any]): 监听函数或方法。
            priority (int): 监听优先级，数值越大越先执行。
            scope (EventScope): 监听作用域。
            once (bool): 是否触发一次后自动解绑。
            error_policy (EventErrorPolicy | None): 监听器级错误策略，None 表示继承事件级策略。
            owner_plugin_name (Optional[str]): 监听器所属插件名，用于批量解绑。
            owner_instance_id (Optional[str]): 监听器所属实例 ID，用于实例卸载自动解绑。

        Returns:
            str: 注册成功后的监听器 ID。

        Raises:
            TypeError: `event` 不是字符串时抛出。
            ValueError: `event` 为空字符串时抛出。
            TypeError: `handler` 不可调用时抛出。
            ValueError: `scope` 不在允许值集合时抛出。
            ValueError: `error_policy` 不在允许值集合且不为 None 时抛出。
        """
        if not isinstance(event, str):
            raise TypeError("event 必须是字符串")

        normalized_event = event.strip()
        if not normalized_event:
            raise ValueError("event 不能为空字符串")

        if not callable(handler):
            raise TypeError("handler 必须可调用")

        if scope not in {"global", "instance"}:
            raise ValueError("scope 仅支持 global 或 instance")

        if error_policy not in {None, "continue", "raise"}:
            raise ValueError("error_policy 仅支持 None、continue 或 raise")

        listener_id = str(uuid.uuid4())
        record = RegisteredHandler(
            listener_id=listener_id,
            event=normalized_event,
            handler=handler,
            priority=int(priority),
            scope=scope,
            once=bool(once),
            error_policy=error_policy,
            owner_plugin_name=owner_plugin_name,
            owner_instance_id=owner_instance_id,
        )
        handlers = self._handlers[normalized_event]

        for existing in handlers:
            if existing.handler is handler:
                return existing.listener_id

        handlers.append(record)
        handlers.sort(key=lambda item: item.priority, reverse=True)
        return listener_id

    def off(
        self,
        event: str,
        handler: Optional[Callable[[Any], Any]] = None,
        *,
        listener_id: Optional[str] = None,
    ) -> None:
        """
        按事件名移除监听器，支持通过 handler 或 listener_id 精确解绑。

        Args:
            event (str): 事件名。
            handler (Optional[Callable[[Any], Any]]): 目标监听函数。
            listener_id (Optional[str]): 监听器 ID。

        Returns:
            None: 无返回值。

        Raises:
            ValueError: `handler` 与 `listener_id` 同时为空时抛出。
        """
        if handler is None and listener_id is None:
            raise ValueError("off 需要提供 handler 或 listener_id")

        handlers = self._handlers.get(event)
        if not handlers:
            return

        filtered: List[RegisteredHandler] = []
        for item in handlers:
            matched = False
            if handler is not None and item.handler is handler:
                matched = True
            if listener_id is not None and item.listener_id == listener_id:
                matched = True
            if not matched:
                filtered.append(item)

        if filtered:
            self._handlers[event] = filtered
        else:
            self._handlers.pop(event, None)

    def off_by_instance(self, instance_id: str) -> None:
        """
        移除指定插件实例注册的全部监听器。

        Args:
            instance_id (str): 插件实例 ID。

        Returns:
            None: 无返回值。
        """
        for event in list(self._handlers.keys()):
            handlers = self._handlers.get(event, [])
            remained = [
                item for item in handlers if item.owner_instance_id != instance_id
            ]
            if remained:
                self._handlers[event] = remained
            else:
                self._handlers.pop(event, None)

    async def emit(
        self,
        event: str,
        payload: Any = None,
        *,
        scope: EventScope = "global",
        source_instance_id: Optional[str] = None,
        error_policy: EventErrorPolicy = "continue",
    ) -> None:
        """
        异步广播事件。

        该方法固定使用异步并发分发模型：
        - 先按优先级降序分组。
        - 同一优先级内并发执行监听器。
        - 每个优先级组执行完后再进入下一组。

        Args:
            event (str): 事件名。
            payload (Any): 事件载荷。
            scope (EventScope): 事件作用域。
            source_instance_id (Optional[str]): 事件来源实例 ID，instance 作用域下用于路由。
            error_policy (EventErrorPolicy): 事件级错误策略。

        Returns:
            None: 无返回值。

        Raises:
            ValueError: `scope` 为 instance 且 `source_instance_id` 为空时抛出。
            EventDispatchError: 在 raise 策略下监听器执行失败时抛出聚合异常。
        """
        if scope == "instance" and not source_instance_id:
            raise ValueError("instance 作用域事件必须提供 source_instance_id")

        async with self._lock:
            snapshot = list(self._handlers.get(event, []))

        selected = [
            item
            for item in snapshot
            if self._should_dispatch(
                listener=item,
                scope=scope,
                source_instance_id=source_instance_id,
            )
        ]
        if not selected:
            return

        priority_groups: Dict[int, List[RegisteredHandler]] = defaultdict(list)
        for item in selected:
            priority_groups[item.priority].append(item)

        ordered_priorities = sorted(priority_groups.keys(), reverse=True)
        errors: List[BaseException] = []
        once_listener_ids: List[str] = []

        for priority in ordered_priorities:
            current_group = priority_groups[priority]
            tasks = [
                self._invoke_handler(item, payload, event_error_policy=error_policy)
                for item in current_group
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for item, result in zip(current_group, results):
                if item.once:
                    once_listener_ids.append(item.listener_id)
                if isinstance(result, BaseException):
                    errors.append(result)

        if once_listener_ids:
            async with self._lock:
                for listener_id in once_listener_ids:
                    self._off_by_listener_id(listener_id)

        if errors:
            raise EventDispatchError(
                f"事件分发失败: event={event}, count={len(errors)}"
            )

    async def _invoke_handler(
        self,
        listener: RegisteredHandler,
        payload: Any,
        *,
        event_error_policy: EventErrorPolicy,
    ) -> None:
        """执行单个监听器并按策略处理异常。"""
        try:
            if inspect.iscoroutinefunction(listener.handler):
                await listener.handler(payload)
                return

            result = await asyncio.to_thread(listener.handler, payload)
            if inspect.isawaitable(result):
                await result
        except Exception as e:
            current_policy = listener.error_policy or event_error_policy
            logger.exception(
                f"事件处理失败: event={listener.event}, handler={listener.handler}, error={e}"
            )
            if current_policy == "raise":
                raise

    @staticmethod
    def _should_dispatch(
        *,
        listener: RegisteredHandler,
        scope: EventScope,
        source_instance_id: Optional[str],
    ) -> bool:
        """判断监听器是否命中当前事件路由规则。"""
        if scope == "global":
            return listener.scope == "global"

        if listener.scope != "instance":
            return False

        return listener.owner_instance_id == source_instance_id

    def _off_by_listener_id(self, listener_id: str) -> None:
        """按监听器 ID 删除注册记录。"""
        for event in list(self._handlers.keys()):
            handlers = self._handlers.get(event, [])
            remained = [item for item in handlers if item.listener_id != listener_id]
            if remained:
                self._handlers[event] = remained
            else:
                self._handlers.pop(event, None)

    def clear(self) -> None:
        """清空全部监听器。"""
        self._handlers.clear()

    @property
    def handler_count(self) -> Dict[str, int]:
        """返回每个事件下的监听器数量。"""
        return {event: len(handlers) for event, handlers in self._handlers.items()}
