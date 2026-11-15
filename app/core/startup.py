"""桌面监督器确认启动后，才放行自动业务。"""

import asyncio
from typing import Literal


class StartupActivation:
    """拥有一个后端进程内自动业务的放行状态。"""

    def __init__(self, *, deferred: bool) -> None:
        self.status: Literal["pending", "active", "closed"] = (
            "pending" if deferred else "active"
        )
        self._ready = asyncio.Event()
        if not deferred:
            self._ready.set()

    async def wait(self) -> None:
        await self._ready.wait()
        if self.status == "closed":
            raise asyncio.CancelledError

    def activate(self) -> None:
        if self.status == "closed":
            raise RuntimeError("后端正在关闭，无法启动自动业务")
        self.status = "active"
        self._ready.set()

    def close(self) -> None:
        self.status = "closed"
        self._ready.set()
