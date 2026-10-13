"""游戏适配：上界外的实现由插件声明类型键、配置类、设备类、管理类与搜索方法；系统段管理类型表。"""

from __future__ import annotations

import inspect
import weakref
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, ClassVar, Generic, TypeVar
from uuid import UUID

from app.config.core.node import LockTicket
from app.models.config.game import TRIGGER_TICKET, GameDeviceEntry, GameEntry
from app.plugin.types import LifecycleContext, PluginState

from .extension import ExtensionPlugin

TGame = TypeVar("TGame", bound=GameEntry, covariant=True)
TDevice = TypeVar("TDevice", bound=GameDeviceEntry, covariant=True)


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
        self._released = True
        await self.control.unsubscribe_device(self)


class GameControl(ABC, Generic[TGame, TDevice]):
    """挂在游戏配置私有属性上的管理实例。只弱引用配置，删除后随配置一起回收。"""

    def __init__(self, config: GameEntry | None = None) -> None:
        self._config_ref: weakref.ReferenceType[GameEntry] | None = (
            weakref.ref(config) if config is not None else None
        )
        # 实例订阅登记：device uid → 订阅记录。只在内存 —— 描述实时并发，
        # 不是持久状态；崩溃后残留计数会把还原永久卡住。
        self._subs: dict[UUID, DeviceSubscription] = {}

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
        ``expect`` 等）；准备失败则撤销登记并尽力收尾，不留半份占用。
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
            sub.count += 1
            return DeviceHandle(control=self, ticket=ticket, device_uid=device_uid)

        # 登记在前：他票占用时立刻上抛，不白做一轮品牌准备
        self._subs[device_uid] = DeviceSubscription(
            ticket=ticket, usage=usage, expect=expect
        )
        try:
            await self._on_device_subscribed(device_uid, expect)
        except Exception:
            del self._subs[device_uid]
            with suppress(Exception):
                await self._on_device_unsubscribed(device_uid)
            raise
        return DeviceHandle(control=self, ticket=ticket, device_uid=device_uid)

    async def unsubscribe_device(self, handle: DeviceHandle) -> None:
        """退订一台实例。计数归零才做品牌收尾，且**不**连带退订游戏订阅。"""
        sub = self._subs.get(handle.device_uid)
        if sub is None or sub.ticket != handle.ticket:
            return
        sub.count -= 1
        if sub.count > 0:
            return
        # 先摘登记再收尾：收尾失败也不留占位，否则实例永久不可订阅
        del self._subs[handle.device_uid]
        await self._on_device_unsubscribed(handle.device_uid)

    async def unsubscribe_all(self, ticket: LockTicket) -> None:
        """退订该票名下**全部**实例。``GameManager.unsubscribe`` 调用。

        逐台独立收尾：某台失败不影响其余台，末尾统一上抛第一个异常。
        """
        first: BaseException | None = None
        for device_uid in [
            uid for uid, sub in self._subs.items() if sub.ticket == ticket
        ]:
            del self._subs[device_uid]
            try:
                await self._on_device_unsubscribed(device_uid)
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


@dataclass
class _SystemRollback:
    """游戏适配 system_rollback 的唯一真相源。标志 did_*，快照 prev_*。"""

    lifecycle: LifecycleContext
    game_type_added: bool = False
    prev_game_class: type[GameEntry] | None = None
    prev_device_class: type[GameDeviceEntry] | None = None


class GameAdapterPlugin(ExtensionPlugin, ABC):
    """启用时把游戏配置类登记进 GameConfig；reload 时游戏 reload_type，设备删换类。"""

    game_type_key: ClassVar[str] = ""
    # 子类重写 decl；game_class 等是外部读取面。
    decl: ClassVar[GameTypeDecl | None] = None

    def __init__(self, config: Any = None, record: Any = None) -> None:
        super().__init__(config=config, record=record)
        self._system_rollback: _SystemRollback | None = None

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

    def precheck_locks(self) -> None:
        """用本类创建的游戏配置若已锁定，则无法 remove_type / reload_type。"""
        from app.core import Config
        from app.plugin.errors import PluginPrecheckError

        game_class = self.game_class
        for entry in Config.GameConfig.values():
            if not isinstance(entry, game_class) or not entry.is_locked:
                continue
            raise PluginPrecheckError(
                f"用 {game_class.__name__} 创建的游戏配置 {entry.uid} 已锁定，"
                f"无法 remove_type",
                payload={
                    "plugin": self.plugin_name,
                    "game_uid": str(entry.uid),
                    "entry_type": game_class.__name__,
                },
            )

    async def _record_system_rollback(self) -> _SystemRollback:
        """类型表写入前统一记录回退信息。"""
        from app.core import Config

        rb = _SystemRollback(lifecycle=self.lifecycle_context)
        if self.lifecycle_context != LifecycleContext.RELOAD:
            self._system_rollback = rb
            return rb

        games = Config.GameConfig
        game_class = self.game_class
        # 重载换皮前表内仍是旧类对象；实例按表内类匹配，不能只用新 ClassVar
        live_cls = games.effective._entry_types.get(game_class.__name__)
        rb.prev_game_class = live_cls if isinstance(live_cls, type) else None
        match_cls = rb.prev_game_class or game_class
        for entry in list(games.values()):
            if not isinstance(entry, match_cls):
                continue
            # 设备类插件侧只有一个；从任一同类实例类型表取非上界项
            for cls in entry.devices.effective._entry_types.values():
                if cls is GameDeviceEntry:
                    continue
                if isinstance(cls, type) and issubclass(cls, GameDeviceEntry):
                    rb.prev_device_class = cls
                    break
            if rb.prev_device_class is not None:
                break
        self._system_rollback = rb
        return rb

    async def system_enable(self) -> None:
        """按语境登记或重载游戏配置类；reload 时设备删旧加新，不备份设备实例。

        顺序：快照 → 类型表 → ``Plugin.game_types``。
        成功后保留 ``_system_rollback``，供同一次 enable 在 system_enable 之后失败时回滚。
        """
        from app.config import NodeState
        from app.core import Config
        from app.core.plugin_manager import Plugin

        if self.lifecycle_context == LifecycleContext.RELOAD_CASCADE:
            return
        game_class = self.game_class
        device_class = self.device_class
        control_class = self.control_class

        # ── 领域集合尚未 activate：只注入类型表，供稍后热化按类名还原 ──
        if Config.GameConfig.activation_state != NodeState.ACTIVE:
            rb = await self._record_system_rollback()
            # 类型表键仍是框架约定的类名
            Config.GameConfig._entry_types[game_class.__name__] = game_class
            rb.game_type_added = True
        elif self.lifecycle_context == LifecycleContext.RELOAD:
            # ── reload：先快照，再 reload 游戏类，设备统一 remove + add ──
            await self._record_system_rollback()
            Config.GameConfig.reload_type(game_class)
            await Config.GameConfig.commit()
            for entry in list(Config.GameConfig.values()):
                if not isinstance(entry, game_class):
                    continue
                # 卸掉除上界外的旧设备类（含同名换皮），再挂新类
                for cls in list(entry.devices.effective._entry_types.values()):
                    if cls is GameDeviceEntry:
                        continue
                    entry.devices.remove_type(cls)
                    await entry.devices.commit()
                entry.devices.add_type(device_class)
                await entry.devices.commit()
                ctrl = entry._game_control
                if ctrl is None:
                    ctrl = control_class(config=entry)
                    entry._game_control = ctrl
                try:
                    await ctrl.refresh()
                except Exception:
                    pass
        else:
            # ── normal / unload：add_type 游戏类，给已有实例补设备类 ──
            rb = await self._record_system_rollback()
            Config.GameConfig.add_type(game_class)
            await Config.GameConfig.commit()
            rb.game_type_added = True
            for entry in list(Config.GameConfig.values()):
                if not isinstance(entry, game_class):
                    continue
                try:
                    entry.devices.add_type(device_class)
                    await entry.devices.commit()
                except Exception:
                    pass
                ctrl = entry._game_control
                if ctrl is None:
                    ctrl = control_class(config=entry)
                    entry._game_control = ctrl

        assert self.decl is not None
        Plugin.game_types[self.record.uid] = self.decl

    async def system_disable(self) -> None:
        """普通禁用：类型表 → 目录 → 清快照。重载语境三步都不做。"""
        from app.config import NodeState
        from app.core import Config
        from app.core.plugin_manager import Plugin

        if self.lifecycle_context in {
            LifecycleContext.RELOAD,
            LifecycleContext.RELOAD_CASCADE,
        }:
            return

        # ── 1. 类型表 ──
        game_class = self.game_class
        if Config.GameConfig.activation_state != NodeState.ACTIVE:
            Config.GameConfig._entry_types.pop(game_class.__name__, None)
        else:
            Config.GameConfig.remove_type(game_class)
            await Config.GameConfig.commit()
        # ── 2. 搜索/展示目录（仅本适配写入，也仅此处与 rollback 摘掉）──
        Plugin.game_types.pop(self.record.uid, None)
        # ── 3. 清快照 ──
        self._system_rollback = None

    async def system_rollback(
        self,
        during: PluginState,
        lifecycle_context: LifecycleContext,
        exc: BaseException,
    ) -> None:
        """按 ``_system_rollback`` 对称回退；终态顺序与 disable 一致：类型表 → 目录 → 清快照。"""
        _ = exc
        from app.config import NodeState
        from app.core import Config
        from app.core.plugin_manager import Plugin

        rb = self._system_rollback
        game_class = self.game_class
        device_class = self.device_class

        if during == PluginState.ENABLING:
            if lifecycle_context == LifecycleContext.RELOAD_CASCADE:
                return
            if lifecycle_context == LifecycleContext.RELOAD:
                # ── reload：reload_type 回旧类（框架内事务）；设备类公开 API 换回 ──
                if (
                    rb is not None
                    and Config.GameConfig.activation_state == NodeState.ACTIVE
                ):
                    prev = rb.prev_game_class
                    try:
                        if prev is not None:
                            Config.GameConfig.reload_type(prev)
                            await Config.GameConfig.commit()
                        match_cls = prev or game_class
                        for entry in list(Config.GameConfig.values()):
                            if not isinstance(entry, match_cls):
                                continue
                            device_types = entry.devices.effective._entry_types
                            if device_class in device_types.values():
                                entry.devices.remove_type(device_class)
                                await entry.devices.commit()
                            if (
                                rb.prev_device_class is not None
                                and rb.prev_device_class
                                not in entry.devices.effective._entry_types.values()
                            ):
                                entry.devices.add_type(rb.prev_device_class)
                                await entry.devices.commit()
                    except Exception:
                        pass
                # 启用失败后插件非 enabled：目录必须摘掉（可能已写成新 decl）
                Plugin.game_types.pop(self.record.uid, None)
                self._system_rollback = None
                return

            # ── normal / unload：若曾加类型则卸类型表，再摘目录、清快照 ──
            if rb is not None and rb.game_type_added:
                try:
                    if Config.GameConfig.activation_state != NodeState.ACTIVE:
                        Config.GameConfig._entry_types.pop(game_class.__name__, None)
                    else:
                        Config.GameConfig.remove_type(game_class)
                        await Config.GameConfig.commit()
                except Exception:
                    pass
            Plugin.game_types.pop(self.record.uid, None)
            self._system_rollback = None
            return

        if during == PluginState.DISABLING:
            if lifecycle_context in {
                LifecycleContext.RELOAD,
                LifecycleContext.RELOAD_CASCADE,
            }:
                return
            # 禁用失败：不补做 remove_type（可能尚未执行）；只确保目录与快照不脏
            Plugin.game_types.pop(self.record.uid, None)
            self._system_rollback = None
