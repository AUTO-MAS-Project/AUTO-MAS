"""游戏适配：上界外的实现由插件声明类型键、配置类、设备类、管理类与搜索方法；系统段管理类型表。"""

from __future__ import annotations

import asyncio
import inspect
import weakref
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, ClassVar, Generic, Protocol, TypeVar
from uuid import UUID

from app.config.core.node import LockTicket
from app.models.config.game import TRIGGER_TICKET, GameDeviceEntry, GameEntry

from .extension import _AdapterPlugin

TGame = TypeVar("TGame", bound=GameEntry, covariant=True)
TDevice = TypeVar("TDevice", bound=GameDeviceEntry, covariant=True)


class GameRuntime(Protocol):
    """控制器使用的实时启动策略，由宿主读取当前设置。"""

    @property
    def silent(self) -> bool: ...

    @property
    def block_ad(self) -> bool: ...


class DeviceSubscribeError(RuntimeError):
    """实例订阅错误：未订阅或被他人占用。``usage`` 为当前占用者的用途说明。"""

    def __init__(self, message: str, *, usage: str | None = None) -> None:
        super().__init__(message)
        self.usage = usage


@dataclass
class DeviceSubscription:
    """实例订阅记录：谁（``ticket``）、为何（``usage``）、要什么（``expect``）、几次。

    ``expect`` 由品牌解释（模拟器传 ``EmulatorExpect``），基类只负责携带与转交。
    同票重复订阅同台只累加 ``count``，不重复走品牌收尾。
    """

    ticket: LockTicket
    usage: str
    expect: object | None = None
    count: int = 1
    releasing: bool = False
    _release_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)


@dataclass
class DeviceHandle:
    """薄封装中间层：持凭证 + 实例 uid，转发时把两者补上。

    **只负责传参，不含任何校验** —— 校验在每个 Control 方法入口，
    故绕过本类直接调 ``ctrl.open(uid, ticket=...)`` 一样被挡。

    只转发通行操作面。品牌专有操作（如模拟器的 ``launch_app``）直接用
    ``ctrl.launch_app(handle.device_uid, pkg, ticket=handle.ticket)`` 调，
    不为此再派生句柄类型。
    """

    control: GameControl[GameEntry, GameDeviceEntry]
    ticket: LockTicket
    device_uid: UUID
    # 同票可对同台重复订阅；计数在 Control 的登记里，handle 只记自己是否已退订
    _released: bool = field(default=False, init=False)

    async def open(self) -> None:
        await self.control.open(self.device_uid, ticket=self.ticket)

    async def close(self) -> None:
        await self.control.close(self.device_uid, ticket=self.ticket)

    async def show(self) -> None:
        await self.control.show(self.device_uid, ticket=self.ticket)

    async def hide(self) -> None:
        await self.control.hide(self.device_uid, ticket=self.ticket)

    async def minimize(self) -> None:
        await self.control.minimize(self.device_uid, ticket=self.ticket)

    async def maximize(self) -> None:
        await self.control.maximize(self.device_uid, ticket=self.ticket)

    async def release(self) -> None:
        """退订本实例。重复调用无副作用。"""
        if self._released:
            return
        await self.control.unsubscribe_device(self)
        self._released = True


class GameControl(ABC, Generic[TGame, TDevice]):
    """挂在游戏配置私有属性上的管理实例。只弱引用配置，删除后随配置一起回收。"""

    runtime: GameRuntime

    def __init__(self, config: GameEntry | None = None) -> None:
        self._config_ref: weakref.ReferenceType[GameEntry] | None = (
            weakref.ref(config) if config is not None else None
        )
        # 实例订阅登记：device uid → 订阅记录。只在内存 —— 描述实时并发，
        # 不是持久状态；崩溃后残留计数会把还原永久卡住。
        self._subs: dict[UUID, DeviceSubscription] = {}

    def bind_runtime(self, runtime: GameRuntime) -> None:
        """宿主创建控制器后、执行任何操作前注入启动策略。"""
        self.runtime = runtime

    @property
    def config(self) -> GameEntry:
        """返回仍存活的配置；弱引用未设或对象已回收则上抛，使管理器进入废弃态。"""
        ref = self._config_ref
        entry = ref() if ref is not None else None
        if entry is None:
            raise RuntimeError("游戏配置已回收")
        return entry

    @property
    def busy(self) -> bool:
        """是否有单次操作在执行。UI 显隐读它决定按钮是否 ``DISABLE``。

        忙标记只在控制器这一处：操作排在哪个执行器上由控制器自己知道，
        配置那边再存一份必然两处不一致。默认 ``False`` —— 不串行化操作的
        品牌无需重写；串行的品牌（如 MuMu 的单任务执行器）重写成读自己的
        执行态。与实例订阅无关：被别的任务订阅不使按钮变灰，用户权限最高。
        """
        return False

    # ── 实例订阅：校验、订阅、退订。基类一手办完，子类不必重写 ──

    def check_subscription(self, device_uid: UUID, ticket: LockTicket) -> None:
        """每个带实例身份的 Control 方法入口都调；子类 ``super()`` 一行带过。

        触发器票直通；任务票须已订阅该实例，否则上抛 ``DeviceSubscribeError``
        并带出当前占用者的用途说明（若有）。
        """
        if ticket is TRIGGER_TICKET:
            return
        sub = self._subs.get(device_uid)
        if sub is None:
            raise DeviceSubscribeError(f"实例 {device_uid} 未订阅")
        if sub.ticket != ticket:
            raise DeviceSubscribeError(
                f"实例 {device_uid} 已被占用: {sub.usage}", usage=sub.usage
            )

    async def subscribe_device(
        self,
        ticket: LockTicket,
        device_uid: UUID,
        usage: str,
        expect: object | None = None,
    ) -> DeviceHandle:
        """订阅实例，返回句柄。同票重复订阅同台只累加计数。

        首个引用时调 ``_on_device_subscribed`` 做品牌准备（备份配置、写入
        ``expect`` 等）；准备失败则尽力收尾，还原未完成时保留登记供重试。
        已被他票占用时上抛 ``DeviceSubscribeError``，带出占用者用途说明。
        """
        if ticket is TRIGGER_TICKET:
            raise DeviceSubscribeError("触发器票不参与实例订阅")

        sub = self._subs.get(device_uid)
        if sub is not None:
            if sub.ticket != ticket:
                raise DeviceSubscribeError(
                    f"实例 {device_uid} 已被占用: {sub.usage}", usage=sub.usage
                )
            if sub.releasing:
                raise DeviceSubscribeError(
                    f"实例 {device_uid} 尚未完成还原: {sub.usage}", usage=sub.usage
                )
            sub.count += 1
            return DeviceHandle(control=self, ticket=ticket, device_uid=device_uid)

        # 登记在前：他票占用时立刻上抛，不白做一轮品牌准备
        sub = DeviceSubscription(ticket=ticket, usage=usage, expect=expect)
        self._subs[device_uid] = sub
        try:
            await self._on_device_subscribed(device_uid, expect)
        except BaseException:
            with suppress(Exception):
                await self._release_subscription(device_uid, sub, all_references=True)
            raise
        return DeviceHandle(control=self, ticket=ticket, device_uid=device_uid)

    async def unsubscribe_device(self, handle: DeviceHandle) -> None:
        """退订一台实例。计数归零才做品牌收尾，且**不**连带退订游戏订阅。"""
        sub = self._subs.get(handle.device_uid)
        if sub is None or sub.ticket != handle.ticket:
            return
        await self._release_subscription(handle.device_uid, sub, all_references=False)

    async def _release_subscription(
        self, device_uid: UUID, sub: DeviceSubscription, *, all_references: bool
    ) -> None:
        """还原成功才摘登记；失败或取消保留原票，供句柄或宿主重试。"""
        async with sub._release_lock:
            if self._subs.get(device_uid) is not sub:
                return
            if not all_references and sub.count > 1:
                sub.count -= 1
                return
            sub.releasing = True
            await self._on_device_unsubscribed(device_uid)
            del self._subs[device_uid]

    async def unsubscribe_all(self, ticket: LockTicket) -> None:
        """退订该票名下**全部**实例。``GameManager.unsubscribe`` 调用。

        逐台独立收尾：某台失败不影响其余台，末尾统一上抛第一个异常。
        """
        first: BaseException | None = None
        for device_uid, sub in [
            (uid, sub) for uid, sub in self._subs.items() if sub.ticket == ticket
        ]:
            try:
                await self._release_subscription(device_uid, sub, all_references=True)
            except Exception as e:
                if first is None:
                    first = e
        if first is not None:
            raise first

    # ── 品牌钩子：默认无动作，只有需要改实例状态的品牌才重写 ──

    async def _on_device_subscribed(
        self, device_uid: UUID, expect: object | None
    ) -> None:
        """首个引用订阅后的品牌准备（备份配置、写入 ``expect``）。默认无动作。"""

    async def _on_device_unsubscribed(self, device_uid: UUID) -> None:
        """计数归零退订时的品牌收尾（还原配置）。默认无动作。"""

    # ── 通行操作面。``ticket`` 必传：触发器给 TRIGGER_TICKET，任务给订阅票 ──
    # 每个实现都在入口调 ``check_subscription``：中间层只传参，绕过它直接调
    # 裸方法一样要被挡住。

    async def set_block_ad(self, enabled: bool) -> None:
        """全局「屏蔽模拟器广告」开关切换时由 ``GameManager`` 统一下发。

        **非抽象**：没有宿主机侧广告处理的品牌不实现，默认什么都不做。
        只做与实例运行状态无关的部分（例如宿主机侧缓存目录占位）——
        必须等实例起来才能做的屏蔽动作留在品牌自己的启动路径里。
        无实例身份、不改游戏配置，故不校验凭据。
        """
        _ = enabled

    @abstractmethod
    async def refresh(self) -> None:
        """刷新设备信息，直接写入配置的 devices，不返回。无实例身份，不校验凭据。"""

    @abstractmethod
    async def open(self, device_uid: UUID, *, ticket: LockTicket) -> None:
        """启动。"""

    @abstractmethod
    async def close(self, device_uid: UUID, *, ticket: LockTicket) -> None:
        """关闭。"""

    @abstractmethod
    async def show(self, device_uid: UUID, *, ticket: LockTicket) -> None:
        """显示。"""

    @abstractmethod
    async def hide(self, device_uid: UUID, *, ticket: LockTicket) -> None:
        """隐藏。"""

    @abstractmethod
    async def minimize(self, device_uid: UUID, *, ticket: LockTicket) -> None:
        """最小化。"""

    @abstractmethod
    async def maximize(self, device_uid: UUID, *, ticket: LockTicket) -> None:
        """最大化。"""


@dataclass(frozen=True)
class GameTypeDecl:
    """游戏适配统一声明：子类以 ClassVar ``decl`` 一次交出。"""

    game_class: type[GameEntry]
    device_class: type[GameDeviceEntry]
    control_class: type[GameControl[GameEntry, GameDeviceEntry]]
    search: Callable[[], Awaitable[Sequence[GameEntry]]]


class GameAdapterPlugin(_AdapterPlugin, ABC):
    """启用时把游戏配置类登记进 GameConfig；reload 时游戏 reload_type，设备删换类。"""

    game_type_key: ClassVar[str] = ""
    # 子类重写 decl；game_class 等是外部读取面。
    decl: ClassVar[GameTypeDecl | None] = None

    def __init__(self, config: Any = None, record: Any = None) -> None:
        super().__init__(config=config, record=record)

        if (
            self.decl is None
            or self.decl.game_class is GameEntry
            or self.decl.device_class is GameDeviceEntry
            or self.decl.control_class is GameControl
            or inspect.isabstract(self.decl.control_class)
            or not callable(self.decl.search)
        ):
            raise ValueError(
                "游戏适配须以 decl 声明收窄的 game_class、device_class、"
                "具体 control_class 与 search"
            )
        self.game_class = self.decl.game_class
        self.device_class = self.decl.device_class
        self.control_class = self.decl.control_class
