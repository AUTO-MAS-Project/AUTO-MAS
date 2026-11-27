"""插件实例公开调用的准入与在途执行；不接管返回资源或私建工作。"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from threading import Lock, Thread, current_thread
from typing import Any

from .errors import PluginBusyError


@dataclass(frozen=True)
class _CallContext:
    owner: object
    actor: asyncio.Task | Thread


_current_call: ContextVar[_CallContext | None] = ContextVar("plugin_call", default=None)


@contextmanager
def call_context(*, owner: object | None = None) -> Iterator[object]:
    """绑定调用归属；线程往返沿用发起者，独立 asyncio 子任务使用自己的身份。"""
    try:
        actor = asyncio.current_task() or current_thread()
    except RuntimeError:
        actor = current_thread()
    previous = _current_call.get()
    if owner is None:
        owner = (
            previous.owner
            if previous is not None
            and (
                previous.actor is actor
                or isinstance(previous.actor, Thread) != isinstance(actor, Thread)
            )
            else actor
        )
    token = _current_call.set(_CallContext(owner=owner, actor=actor))
    try:
        yield owner
    finally:
        _current_call.reset(token)


class CallGate:
    def __init__(self) -> None:
        """初始化线程安全的准入和调用计数；排空事件只由所属事件循环操作。"""
        self._accepting = True
        self._lock = Lock()
        self._active: dict[object, int] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._changed = asyncio.Event()

    @property
    def accepting(self) -> bool:
        """读取准入状态，与线程中的登记共用同一把短时锁。"""
        with self._lock:
            return self._accepting

    @accepting.setter
    def accepting(self, value: bool) -> None:
        """原子切换准入状态，关闭后不再允许新的调用登记。"""
        with self._lock:
            self._accepting = value

    def _enter(self, owner: object) -> None:
        """在同一临界区检查准入并登记调用，业务本身不持锁。"""
        with self._lock:
            if not self._accepting:
                raise PluginBusyError("插件正在释放，不再受理调用")
            self._active[owner] = self._active.get(owner, 0) + 1

    def _leave(self, owner: object) -> None:
        """解除一次调用登记，通过所属事件循环唤醒生命周期等待者。"""
        with self._lock:
            self._active[owner] -= 1
            if not self._active[owner]:
                del self._active[owner]
            loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(self._changed.set)

    @contextmanager
    def active_call(self) -> Iterator[None]:
        """持有准入直至整个业务操作退出，停用时等待在途调用。"""
        with call_context() as owner:
            self._enter(owner)
            try:
                yield
            finally:
                self._leave(owner)

    def wrap(self, method: Callable[..., Any]) -> Callable[..., Any]:
        """为同步、异步或返回可等待对象的方法添加准入和在途计数，使卸载能等待真实调用结束。"""
        if inspect.iscoroutinefunction(method):

            @wraps(method)
            async def asynchronous(*args, **kwargs):
                """在异步方法执行前登记调用，无论成功、异常或取消都在结束后释放登记。"""
                with self.active_call():
                    return await method(*args, **kwargs)

            return asynchronous

        @wraps(method)
        def synchronous(*args, **kwargs):
            """登记同步调用并执行原方法；返回可等待对象时将登记保留到异步结果收尾。"""
            with call_context() as owner:
                self._enter(owner)
                try:
                    result = method(*args, **kwargs)
                except BaseException:
                    self._leave(owner)
                    raise
            if inspect.isawaitable(result):

                async def await_result():
                    """等待同步入口返回的异步结果，并在结果结束后释放在途调用登记。"""
                    with call_context(owner=owner):
                        try:
                            return await result
                        finally:
                            self._leave(owner)

                return await_result()
            self._leave(owner)
            return result

        return synchronous

    async def drain(self) -> None:
        """调用者本身可发起生命周期操作；等待其他在途调用退出。"""
        with call_context() as current:
            while True:
                with self._lock:
                    self._loop = asyncio.get_running_loop()
                    self._changed.clear()
                    if not any(owner is not current for owner in self._active):
                        return
                await self._changed.wait()
