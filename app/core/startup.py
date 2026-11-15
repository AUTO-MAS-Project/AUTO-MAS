"""桌面监督器确认启动后，才放行自动业务。"""

import asyncio
from typing import Literal


class StartupActivation:
    """拥有一个后端进程内自动业务的放行状态。"""

    def __init__(self, *, deferred: bool) -> None:
        self.status: Literal["pending", "active", "closed"] = "closed"
        self._ready = asyncio.Event()
        self.prepare(deferred=deferred)

    def prepare(self, *, deferred: bool) -> None:
        """准备本次启动，旧生命周期的等待者按取消结束。"""
        self.close()
        self._ready = asyncio.Event()
        self.status = "pending" if deferred else "active"
        if not deferred:
            self._ready.set()

    async def wait(self) -> None:
        ready = self._ready
        await ready.wait()
        if ready is not self._ready or self.status == "closed":
            raise asyncio.CancelledError

    def activate(self) -> None:
        if self.status == "closed":
            raise RuntimeError("后端正在关闭，无法启动自动业务")
        self.status = "active"
        self._ready.set()

    def close(self) -> None:
        self.status = "closed"
        self._ready.set()


Startup = StartupActivation(deferred=False)
