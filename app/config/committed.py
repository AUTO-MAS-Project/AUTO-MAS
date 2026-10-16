"""配置内存提交后的不可变摘要与受管理观察者；不表示 YAML 已落盘。"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

logger = logging.getLogger("配置提交事件")


@dataclass(frozen=True)
class CommittedConfigChange:
    """只暴露身份与路径，不保留配置对象或字段值。"""

    config_uid: UUID
    root_uid: UUID
    config_type: str
    changed_paths: tuple[str, ...]


@dataclass(frozen=True)
class ConfigCommittedEvent:
    """一次外层事务的摘要；revision 在当前进程的管理器内单调递增。"""

    event_id: UUID
    revision: int
    changes: tuple[CommittedConfigChange, ...]


type CommittedCallback = Callable[[ConfigCommittedEvent], Awaitable[None] | None]


class ConfigEvents(Protocol):
    """插件可消费的提交观察接口。"""

    def connect(self, callback: CommittedCallback) -> CommittedSubscription: ...

    async def close(self) -> None: ...


class CommittedSubscription:
    """同一观察者按提交顺序消费；慢观察者不占配置锁、不阻塞其他观察者。"""

    def __init__(self, callback: CommittedCallback, *, owner: object | None) -> None:
        self.callback = callback
        self.owner = owner
        self._pending: deque[ConfigCommittedEvent] = deque()
        self._task: asyncio.Task[None] | None = None
        self._closed = False

    def enqueue(self, event: ConfigCommittedEvent) -> None:
        if not self._closed:
            self._pending.append(event)
            try:
                asyncio.get_running_loop().call_soon(self._start)
            except RuntimeError:
                pass

    def _start(self) -> None:
        if self._task is not None or not self._pending:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # 同步配置入口的事件在下一次 drain 时交给事件循环。
            return
        self._task = loop.create_task(self._deliver(), name="config-committed")

    async def _deliver(self) -> None:
        try:
            while self._pending and not self._closed:
                event = self._pending.popleft()
                try:
                    result = self.callback(event)
                    if inspect.isawaitable(result):
                        await result
                except Exception:
                    logger.exception("配置提交观察者执行失败: %s", event.event_id)
        finally:
            self._task = None

    async def drain(self) -> None:
        """等待当前队列处理完；供需要外部效果已完成的宿主入口使用。"""
        self._start()
        task = self._task
        if task is not None and task is not asyncio.current_task():
            await asyncio.shield(task)

    async def close(self) -> None:
        """注销时丢弃未消费事件，并等待在途回调取消收尾。"""
        self._closed = True
        self._pending.clear()
        task = self._task
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


class CommittedEventBus:
    """进程内提交观察者；插件重载按 owner 注销，退出后拒绝新订阅。"""

    def __init__(self) -> None:
        self._subscriptions: list[CommittedSubscription] = []
        self._closed = False

    def connect(
        self, callback: CommittedCallback, *, owner: object | None = None
    ) -> CommittedSubscription:
        if self._closed:
            raise RuntimeError("配置提交事件已关闭")
        subscription = CommittedSubscription(callback, owner=owner)
        self._subscriptions.append(subscription)
        return subscription

    def publish(self, event: ConfigCommittedEvent) -> None:
        if not self._closed:
            for subscription in tuple(self._subscriptions):
                subscription.enqueue(event)

    async def disconnect(self, subscription: CommittedSubscription) -> None:
        if subscription in self._subscriptions:
            self._subscriptions.remove(subscription)
        await subscription.close()

    async def disconnect_owner(self, owner: object) -> None:
        for subscription in tuple(self._subscriptions):
            if subscription.owner is owner:
                await self.disconnect(subscription)

    async def drain(self) -> None:
        await asyncio.gather(*(s.drain() for s in tuple(self._subscriptions)))

    async def shutdown(self) -> None:
        self._closed = True
        for subscription in tuple(self._subscriptions):
            await self.disconnect(subscription)


class BoundConfigEvents:
    """宿主按插件实例绑定所有权，注销后禁止旧实例再次订阅。"""

    def __init__(self, bus: CommittedEventBus, *, owner: object) -> None:
        self._bus = bus
        self._owner = owner
        self._closed = False

    def connect(self, callback: CommittedCallback) -> CommittedSubscription:
        if self._closed:
            raise RuntimeError("插件配置观察接口已关闭")
        return self._bus.connect(callback, owner=self._owner)

    async def close(self) -> None:
        self._closed = True
        await self._bus.disconnect_owner(self._owner)
