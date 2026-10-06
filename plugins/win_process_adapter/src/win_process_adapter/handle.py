"""通用进程管理实例。"""

from __future__ import annotations

from uuid import UUID

from auto_mas_core import GameControl, LockTicket

from .manager import GeneralDeviceManager
from .schema import WinProcessDevice, WinProcessGame


class WinProcessControl(GameControl[WinProcessGame, WinProcessDevice]):
    """按设备 uid 操作已跟踪进程。"""

    def __init__(self, config: WinProcessGame | None = None) -> None:
        super().__init__(config=config)
        self._mgr: GeneralDeviceManager | None = None

    @property
    def config(self) -> WinProcessGame:
        entry = super().config
        if not isinstance(entry, WinProcessGame):
            raise TypeError("配置不是 WinProcessGame")
        return entry

    def _ensure(self) -> GeneralDeviceManager:
        entry = self.config
        if self._mgr is None:
            self._mgr = GeneralDeviceManager(entry)
        return self._mgr

    async def refresh(self) -> None:
        entry = self.config
        mgr = self._ensure()
        infos = await mgr.getInfo(None)
        by_index = {str(dev.info.index): dev for dev in entry.devices.values()}
        seen: set[str] = set()
        for idx, info in (infos or {}).items():
            key = str(idx)
            seen.add(key)
            current = by_index.get(key)
            title = getattr(info, "title", key)
            status = getattr(info, "status", 1)
            if current is None:
                entry.devices.add(
                    WinProcessDevice,
                    payload={"info": {"name": title, "status": int(status), "index": key}},
                )
                continue
            current.info.name = title
            current.info.status = status
            await current.commit()
        for key, dev in by_index.items():
            if key not in seen:
                entry.devices.remove(dev.uid)
        await entry.devices.commit()

    async def _call(self, device_uid: UUID, op: str) -> None:
        dev = self.config.devices.get(device_uid)
        if dev is None:
            return
        mgr = self._ensure()
        idx = str(dev.info.index)
        if op == "open":
            await mgr.open(idx)
        elif op == "close":
            await mgr.close(idx)
        elif op == "show":
            await mgr.setVisible(idx, True)
        elif op == "hide":
            await mgr.setVisible(idx, False)
        elif op == "minimize":
            pm = mgr.process_managers.get(idx)
            if pm is not None:
                await pm.minimize_window()
        elif op == "maximize":
            pm = mgr.process_managers.get(idx)
            if pm is not None:
                await pm.maximize_window()
        await self.refresh()

    async def open(self, device_uid: UUID, *, ticket: LockTicket) -> None:
        self.check_subscription(device_uid, ticket)
        await self._call(device_uid, "open")

    async def close(self, device_uid: UUID, *, ticket: LockTicket) -> None:
        self.check_subscription(device_uid, ticket)
        await self._call(device_uid, "close")

    async def show(self, device_uid: UUID, *, ticket: LockTicket) -> None:
        self.check_subscription(device_uid, ticket)
        await self._call(device_uid, "show")

    async def hide(self, device_uid: UUID, *, ticket: LockTicket) -> None:
        self.check_subscription(device_uid, ticket)
        await self._call(device_uid, "hide")

    async def minimize(self, device_uid: UUID, *, ticket: LockTicket) -> None:
        self.check_subscription(device_uid, ticket)
        await self._call(device_uid, "minimize")

    async def maximize(self, device_uid: UUID, *, ticket: LockTicket) -> None:
        self.check_subscription(device_uid, ticket)
        await self._call(device_uid, "maximize")


async def search_installed() -> list[WinProcessGame]:
    """通用进程需手动指定路径，不自动搜索。"""
    return []
