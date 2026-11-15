"""插件实例公开调用的准入与在途执行；不接管返回资源或私建工作。"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from functools import wraps
from typing import Any

from .errors import PluginBusyError


class CallGate:
    def __init__(self) -> None:
        """初始化插件调用准入标记、按任务计数的在途调用表和状态变更事件。"""
        self.accepting = True
        self._active: dict[asyncio.Task | None, int] = {}
        self._changed = asyncio.Event()

    def _enter(self) -> asyncio.Task | None:
        """检查插件是否仍接收调用，登记当前异步任务的调用层数并返回归属任务。"""
        if not self.accepting:
            raise PluginBusyError("插件正在释放，不再受理调用")
        task = asyncio.current_task()
        self._active[task] = self._active.get(task, 0) + 1
        return task

    def _leave(self, task: asyncio.Task | None) -> None:
        """释放一次在途调用计数，并唤醒等待调用清空的生命周期流程。"""
        self._active[task] -= 1
        if not self._active[task]:
            del self._active[task]
        self._changed.set()

    def wrap(self, method: Callable[..., Any]) -> Callable[..., Any]:
        """为同步、异步或返回可等待对象的方法添加准入和在途计数，使卸载能等待真实调用结束。"""
        if inspect.iscoroutinefunction(method):

            @wraps(method)
            async def asynchronous(*args, **kwargs):
                """在异步方法执行前登记调用，无论成功、异常或取消都在结束后释放登记。"""
                task = self._enter()
                try:
                    return await method(*args, **kwargs)
                finally:
                    self._leave(task)

            return asynchronous

        @wraps(method)
        def synchronous(*args, **kwargs):
            """登记同步调用并执行原方法；返回可等待对象时将登记保留到异步结果收尾。"""
            task = self._enter()
            try:
                result = method(*args, **kwargs)
            except BaseException:
                self._leave(task)
                raise
            if inspect.isawaitable(result):

                async def await_result():
                    """等待同步入口返回的异步结果，并在结果结束后释放在途调用登记。"""
                    try:
                        return await result
                    finally:
                        self._leave(task)

                return await_result()
            self._leave(task)
            return result

        return synchronous

    async def drain(self) -> None:
        """调用者本身可发起生命周期操作；等待其他在途调用退出。"""
        current = asyncio.current_task()
        while any(task is not current for task in self._active):
            self._changed.clear()
            await self._changed.wait()
