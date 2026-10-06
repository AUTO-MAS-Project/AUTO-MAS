"""游戏与设备配置上界。具体路径、adb 等由适配插件子类添加。"""

from __future__ import annotations

from enum import IntEnum
from typing import TYPE_CHECKING, Annotated, Literal

from uuid import UUID

from blinker import Signal
from pydantic import Field, PrivateAttr

from app.config import (
    ConfigCollection,
    ConfigEntry,
    ConfigGroup,
    LockTicket,
    Trigger,
    UiVisibility,
    ui,
    ui_visibility,
)
from app.config.shortcuts import collection, trigger_field
from app.config.signals import CollectionChangeEvent

if TYPE_CHECKING:
    from app.plugin.base.game import GameControl


# 统一设备删除信号：任一游戏的 ``devices`` 删掉成员后发出（sender=该 devices
# 集合，kwargs ``uid``=被删设备 uid）。引用设备的配置订这一处即可，不必逐个游戏订。
# 经 ``send_async`` 发送，接收者须为协程函数。
device_removed = Signal("game.device_removed")


# 触发器专用票。用户操作权限最高：只受控制器忙标记约束，不受实例订阅登记约束。
# 任务票一律由 ``GameManager.subscribe`` 的 ``lock_s`` 签发（token 为 uuid4），
# 故全零 token 不可能与任务票撞上。校验按同一性（``is``）判定，不看字段。
# 定义在此而非 ``plugin.base.game``：那边 import 本模块，反向引用会成环。
TRIGGER_TICKET = LockTicket(
    mode="s", token=UUID(int=0), issuer=UUID(int=0), cascade=False
)


class DeviceStatus(IntEnum):
    """设备状态。管理器与设备配置共用。"""

    ONLINE = 0
    OFFLINE = 1
    STARTING = 2
    CLOSEING = 3
    ERROR = 4
    NOT_FOUND = 5
    UNKNOWN = 10


class GameDeviceEntry(ConfigEntry):
    """设备上界。除触发器外前端不可改；操作经父游戏配置上的管理实例。"""

    class Info(ConfigGroup):
        name: Annotated[str, ui(visibility=UiVisibility.DISABLE)] = Field(
            default="设备", description="实例名称"
        )
        status: Annotated[DeviceStatus, ui(visibility=UiVisibility.DISABLE)] = Field(
            default=DeviceStatus.OFFLINE, description="实例状态"
        )

    class Action(ConfigGroup):
        open: Trigger = Field(default=False, description="启动")
        close: Trigger = Field(default=False, description="关闭")
        show: Trigger = Field(default=False, description="显示")
        hide: Trigger = Field(default=False, description="隐藏")

    info: Info = Field(default_factory=Info, description="设备信息")
    action: Action = Field(default_factory=Action, description="设备操作")

    @property
    def _control(self) -> GameControl[GameEntry, GameDeviceEntry]:
        """父游戏上的管理实例；配置生命周期内必达，否则上抛。"""
        col = self.parent
        game = col.parent if col is not None else None
        if not isinstance(game, GameEntry):
            raise RuntimeError("设备未挂入游戏配置")
        return game._control

    @property
    def busy(self) -> bool:
        """是否有操作正在执行（供 UI 查询）。

        单次操作互斥标志只在控制器上：一台设备的操作要经哪个执行器排队由
        控制器决定，配置这边再存一份只会两处不一致。管理实例取不到时按
        「不忙」处理 —— 那是配置还没挂上控制器，不该把按钮一律禁掉。
        """
        try:
            return self._control.busy
        except Exception:
            return False

    def _busy_vis(self) -> UiVisibility:
        """忙时禁用、闲时显示。各 ``_vis_*`` 的公共尾巴。"""
        return UiVisibility.DISABLE if self.busy else UiVisibility.SHOW

    @ui_visibility("action.open")
    def _vis_open(self) -> UiVisibility:
        if self.info.status in {DeviceStatus.ONLINE, DeviceStatus.STARTING}:
            return UiVisibility.HIDE
        return self._busy_vis()

    @ui_visibility("action.close")
    def _vis_close(self) -> UiVisibility:
        if self.info.status not in {
            DeviceStatus.ONLINE,
            DeviceStatus.STARTING,
            DeviceStatus.ERROR,
        }:
            return UiVisibility.HIDE
        return self._busy_vis()

    @ui_visibility("action.show")
    def _vis_show(self) -> UiVisibility:
        if self.info.status != DeviceStatus.ONLINE:
            return UiVisibility.HIDE
        return self._busy_vis()

    @ui_visibility("action.hide")
    def _vis_hide(self) -> UiVisibility:
        if self.info.status != DeviceStatus.ONLINE:
            return UiVisibility.HIDE
        return self._busy_vis()

    @trigger_field("action.open")
    async def on_open(self) -> None:
        # 触发器带特殊票免订阅校验（用户权限最高）；
        # 操作互斥由控制器自己的执行器管（``GameControl.busy``）
        await self._control.open(self.uid, ticket=TRIGGER_TICKET)

    @trigger_field("action.close")
    async def on_close(self) -> None:
        await self._control.close(self.uid, ticket=TRIGGER_TICKET)

    @trigger_field("action.show")
    async def on_show(self) -> None:
        await self._control.show(self.uid, ticket=TRIGGER_TICKET)

    @trigger_field("action.hide")
    async def on_hide(self) -> None:
        await self._control.hide(self.uid, ticket=TRIGGER_TICKET)


class GameEntry(ConfigEntry):
    """游戏主配置上界。插件继承后加自己的字段，并注册进 GameConfig。"""

    class Info(ConfigGroup):
        name: str = Field(default="新游戏", description="实例命名")
        type: Annotated[
            Literal["emulator", "client"], ui(visibility=UiVisibility.HIDE)
        ] = Field(default="emulator", description="模拟器或客户端")
        concurrent_execution: Annotated[bool, ui(visibility=UiVisibility.HIDE)] = Field(
            default=False, description="是否允许并发运行"
        )

    class Action(ConfigGroup):
        refresh: Trigger = Field(default=False, description="刷新设备列表")

    info: Info = Field(default_factory=Info, description="游戏信息")
    action: Action = Field(default_factory=Action, description="游戏操作")
    devices: ConfigCollection[GameDeviceEntry] = collection(GameDeviceEntry)

    # 框架 add 时写入；业务经 ``_control`` / subscribe 取，不要直接读存储
    _game_control: GameControl[GameEntry, GameDeviceEntry] | None = PrivateAttr(
        default=None
    )

    @property
    def _control(self) -> GameControl[GameEntry, GameDeviceEntry]:
        """配置生命周期内必挂管理实例；未挂载则上抛。"""
        ctrl = self._game_control
        if ctrl is None:
            raise RuntimeError("游戏管理实例未挂载")
        return ctrl

    @trigger_field("action.refresh")
    async def on_refresh(self) -> None:
        """走配置触发器刷新 devices，受主配置 S 锁约束。"""
        await self._control.refresh()

    @staticmethod
    async def on_add_devices(sender: object, event: CollectionChangeEvent) -> None:
        """GameConfig 实例级 add / init_add：把新游戏的 devices 删除接到统一信号。"""
        _ = sender
        if not isinstance(event.entry, GameEntry):
            raise TypeError(f"非 GameEntry: {event.entry}")
        event.entry.devices.connect(
            GameEntry.on_remove_device, phase="runtime", kind="remove"
        )

    @staticmethod
    async def on_remove_device(sender: object, event: CollectionChangeEvent) -> None:
        """单个游戏 devices 的 remove → 转发为 ``device_removed``。"""
        await device_removed.send_async(sender, uid=event.uid)
