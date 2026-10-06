"""雷电管理实例。"""

from __future__ import annotations

from uuid import UUID

from auto_mas_core import GameControl, LockTicket

from .manager import LDManager
from .schema import LDPlayerDevice, LDPlayerGame
from .search import search_ldplayer


class LDPlayerControl(GameControl[LDPlayerGame, LDPlayerDevice]):
    """把设备 uid 转成多开序号后交给 ``LDManager``。"""

    def __init__(self, config: LDPlayerGame | None = None) -> None:
        super().__init__(config=config)
        self._mgr: LDManager | None = None

    @property
    def config(self) -> LDPlayerGame:
        entry = super().config
        if not isinstance(entry, LDPlayerGame):
            raise TypeError("配置不是 LDPlayerGame")
        return entry

    def _ensure(self) -> LDManager:
        entry = self.config
        if self._mgr is None:
            self._mgr = LDManager(entry)
        return self._mgr

    async def refresh(self) -> None:
        entry = self.config
        infos = await self._ensure().getInfo(None)
        by_index = {str(dev.info.index): dev for dev in entry.devices.values()}
        seen: set[str] = set()
        for idx, info in (infos or {}).items():
            key = str(idx)
            seen.add(key)
            title = getattr(info, "title", key)
            status = getattr(info, "status", 1)
            adb = getattr(info, "adb_address", "") or ""
            current = by_index.get(key)
            if current is None:
                entry.devices.add(
                    LDPlayerDevice,
                    payload={
                        "info": {
                            "name": title,
                            "status": int(status),
                            "index": key,
                            "adb_address": adb,
                        }
                    },
                )
                continue
            current.info.name = title
            current.info.status = status
            current.info.adb_address = adb
            await current.commit()
        for key, dev in by_index.items():
            if key not in seen:
                entry.devices.remove(dev.uid)
        await entry.devices.commit()

    async def _run(self, device_uid: UUID, op: str) -> None:
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
        await self.refresh()

    async def open(self, device_uid: UUID, *, ticket: LockTicket) -> None:
        self.check_subscription(device_uid, ticket)
        await self._run(device_uid, "open")

    async def close(self, device_uid: UUID, *, ticket: LockTicket) -> None:
        self.check_subscription(device_uid, ticket)
        await self._run(device_uid, "close")

    async def show(self, device_uid: UUID, *, ticket: LockTicket) -> None:
        self.check_subscription(device_uid, ticket)
        await self._run(device_uid, "show")

    async def hide(self, device_uid: UUID, *, ticket: LockTicket) -> None:
        self.check_subscription(device_uid, ticket)
        await self._run(device_uid, "hide")

    async def minimize(self, device_uid: UUID, *, ticket: LockTicket) -> None:
        await self.hide(device_uid, ticket=ticket)

    async def maximize(self, device_uid: UUID, *, ticket: LockTicket) -> None:
        await self.show(device_uid, ticket=ticket)


async def search_installed() -> list[LDPlayerGame]:
    """返回未激活的雷电配置实例。"""
    found = await search_ldplayer()
    rows: list[LDPlayerGame] = []
    for item in found:
        rows.append(
            LDPlayerGame(
                info=LDPlayerGame.Info(
                    name=item.get("name") or "雷电",
                    path=item.get("path") or "",
                    type="emulator",
                )
            )
        )
    return rows
