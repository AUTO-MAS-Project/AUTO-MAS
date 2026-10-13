"""游戏管理主入口：订阅取实例；add 时挂管理实例；搜索汇总已启用插件。"""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Any, Literal, overload
from uuid import UUID

from app.config.core.node import LockTicket
from app.config.signals import CollectionChangeEvent, FieldChangeEvent
from app.models.config.emulator import EmulatorEntry
from app.models.config.game import GameDeviceEntry, GameEntry
from app.plugin.base.emulator import EmulatorControl
from app.plugin.base.game import GameControl
from app.utils import get_logger

logger = get_logger("游戏管理")


class _SerialGate:
    """进程内全局 FIFO 闸门：同一时刻至多一个不支持并行的游戏处于订阅中。

    与配置 S/X 锁正交。等待可取消：排队中的等待者被取消则从队列摘掉；
    已放行后取消由调用方 ``release``（``unsubscribe`` 路径）。
    """

    def __init__(self) -> None:
        self._busy = False
        self._waiters: deque[asyncio.Event] = deque()

    async def acquire(self) -> None:
        if not self._busy and not self._waiters:
            self._busy = True
            return
        ev = asyncio.Event()
        self._waiters.append(ev)
        try:
            await ev.wait()
        except asyncio.CancelledError:
            if ev in self._waiters:
                self._waiters.remove(ev)
            elif ev.is_set():
                # 已出队放行后、wait 返回前被取消：视为持有，交还以免堵死
                self.release()
            raise

    def release(self) -> None:
        if self._waiters:
            self._waiters.popleft().set()
        else:
            self._busy = False


class _GameManager:
    """对外提供订阅、搜索；add 挂载由 Config 对 GameConfig 实例级 connect 本类方法。"""

    def __init__(self) -> None:
        self._found: dict[UUID, Any] = {}
        self._subs: dict[LockTicket, GameEntry] = {}
        self._gate = _SerialGate()
        self._gate_tokens: set[UUID] = set()

    @staticmethod
    async def on_add(sender: object, event: CollectionChangeEvent) -> None:
        """GameConfig 实例级 add / init_add：按已启用声明挂管理实例。

        设备类由游戏配置子类在字段上收窄；此处不再 ``add_type``。
        ``entry`` 缺失或无匹配声明视为异常，上抛以使当次事务失败。
        """
        _ = sender
        if not isinstance(event.entry, GameEntry):
            raise TypeError(f"非 GameEntry: {event.entry}")

        from app.core import Plugin

        for decl in Plugin.game_types.values():
            if isinstance(event.entry, decl.game_class):
                event.entry._game_control = decl.control_class(config=event.entry)
                break
        else:
            raise RuntimeError(f"未找到 {type(event.entry)} 对应的 GameTypeDecl")

    @staticmethod
    async def on_block_ad(sender: object, event: FieldChangeEvent) -> None:
        """全局去广告开关变更 → 逐个游戏下发，各品牌自行决定做不做。

        开关是系统级的，作用面却在各品牌的宿主机侧（缓存目录占位等），故由主入口
        统一扇出，而不是等下一次启动实例时顺带处理 —— 用户关掉开关就该立刻生效。
        单个游戏失败不连累其余：这不是事务，只记警告。
        """
        _ = sender
        from app.core import Config

        enabled = bool(event.value)
        for entry in Config.GameConfig.values():
            try:
                await entry._control.set_block_ad(enabled)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"游戏 {entry.info.name} 去广告开关下发失败: {e}")

    @overload
    async def subscribe(
        self, uid: UUID, *, kind: Literal["emulator"]
    ) -> tuple[EmulatorControl, LockTicket]: ...

    @overload
    async def subscribe(
        self, uid: UUID, *, kind: Literal["client"]
    ) -> tuple[GameControl[GameEntry, GameDeviceEntry], LockTicket]: ...

    @overload
    async def subscribe(
        self, uid: UUID, *, kind: None = None
    ) -> tuple[GameControl[GameEntry, GameDeviceEntry], LockTicket]: ...

    async def subscribe(
        self, uid: UUID, *, kind: Literal["emulator", "client"] | None = None
    ) -> tuple[GameControl[GameEntry, GameDeviceEntry] | EmulatorControl, LockTicket]:
        """对主配置加不覆盖子节点的只读锁，返回已挂载管理实例与解锁凭证。

        ``kind`` 为 ``emulator`` / ``client`` 时校验 ``info.type`` 与 Control 类型；
        ``kind="emulator"`` 时静态类型收窄为 ``EmulatorControl``。
        """
        from app.core import Config

        entry = Config.GameConfig.get(uid)
        if entry is None:
            raise KeyError(f"游戏不存在: {uid}")

        if kind is not None and entry.info.type != kind:
            raise TypeError(
                f"游戏 {uid} 类型为 {entry.info.type!r}，期望 {kind!r}"
            )
        if kind == "emulator" and not isinstance(entry, EmulatorEntry):
            raise TypeError(f"游戏 {uid} 不是模拟器配置")

        # ``_control`` 属性：生命周期内必达，未挂载直接上抛
        ctrl = entry._control
        # 不支持并行：先拿全局闸门再订设备（闸门在 subscribe 内、设备在调用方）
        gated = False
        if not entry.info.concurrent_execution:
            await self._gate.acquire()
            gated = True
        try:
            ticket = await entry.lock_s(cascade=False)
        except BaseException:
            if gated:
                self._gate.release()
            raise
        self._subs[ticket] = entry
        if gated:
            self._gate_tokens.add(ticket.token)
        return ctrl, ticket

    async def unsubscribe(self, ticket: LockTicket) -> None:
        """退订该票名下全部实例，再解开订阅时签发的那把主配置锁。"""
        # 先 unlock 再删登记：unlock 失败时仍可经同一票重试
        entry = self._subs[ticket]
        # 实例先退订：任务异常退出时不留占位，否则实例永久不可订阅。
        # 放在 unlock 之前 —— 还原要写设备配置，而设备 Entry 在 S 锁下仍可写，
        # 顺序反了也能写，但此时票已作废，无从核对归属。
        await entry._control.unsubscribe_all(ticket)
        await entry.unlock(ticket)
        del self._subs[ticket]
        if ticket.token in self._gate_tokens:
            self._gate_tokens.discard(ticket.token)
            self._gate.release()

    async def search(self) -> dict[str, dict[str, Any]]:
        """逐一调用已启用插件声明的 search，暂存未激活实例并返回目录。"""
        from app.core.plugin_manager import Plugin

        found: dict[UUID, Any] = {}
        catalog: dict[str, dict[str, Any]] = {}
        for decl in Plugin.game_types.values():
            rows = await decl.search()
            for entry in rows or []:
                found[entry.uid] = entry
                catalog[str(entry.uid)] = {
                    "name": entry.info.name,
                    "type": entry.info.type,
                    "concurrent_execution": entry.info.concurrent_execution,
                }
        self._found = found
        return catalog

    async def add_found(self, uid: UUID) -> GameEntry:
        """把搜索缓存中的未激活实例写入 GameConfig：add 占位再 update 同步字段。"""
        from app.core import Config

        if uid not in self._found:
            raise KeyError(f"搜索结果不存在或已过期: {uid}")
        if uid in Config.GameConfig:
            raise ValueError(f"游戏已存在: {uid}")
        found = self._found.pop(uid)
        if not isinstance(found, GameEntry):
            raise TypeError(f"非 GameEntry: {type(found)}")

        Config.GameConfig.add(type(found), uid=uid)
        await Config.GameConfig.commit()
        entry = Config.GameConfig[uid]
        await entry.update(found)
        return entry


GameManager = _GameManager()
