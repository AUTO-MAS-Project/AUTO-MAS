"""游戏与设备配置上界。具体路径、adb 等由适配插件子类添加。"""

from __future__ import annotations

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
    trigger_field,
    ui,
    ui_visibility,
)
from app.config.shortcuts import collection
from app.config.signals import CollectionChangeEvent
from app.models.emulator import DeviceStatus as DeviceStatus

if TYPE_CHECKING:
    from app.plugin.base.game import GameControl


# 统一设备删除信号：任一游戏的 ``devices`` 删掉成员后发出（sender=该 devices
# 集合，kwargs ``uid``=被删设备 uid）。引用设备的配置订这一处即可，不必逐个游戏订。
# 经 ``send_async`` 发送，接收者须为协程函数。
device_removed = Signal("game.device_removed")

# 设备条目被移除后，指向它的托管 / 账号绑定写入的不可用原因。
DEVICE_DELETED_REASON = "所绑定的设备实例已删除"


def is_deleted_device(device: GameDeviceEntry) -> bool:
    """适配插件删除实例后先标记 ``info.tombstone``，宿主随后移除条目。

    标记到移除之间（或旧版遗留、移除被推迟）的设备不再是可用设备：
    不列入下拉、不允许绑定或运行，也不在游戏管理页显示。
    """
    return bool(getattr(device.info, "tombstone", False))


# 触发器专用票。用户操作权限最高：只受控制器忙标记约束，不受实例订阅登记约束。
# 任务票一律由 ``GameManager.subscribe`` 的 ``lock_s`` 签发（token 为 uuid4），
# 故全零 token 不可能与任务票撞上。校验按同一性（``is``）判定，不看字段。
# 定义在此而非 ``plugin.base.game``：那边 import 本模块，反向引用会成环。
TRIGGER_TICKET = LockTicket(
    mode="s", token=UUID(int=0), issuer=UUID(int=0), cascade=False
)


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
        open: Trigger = Field(default=None, description="启动")
        close: Trigger = Field(default=None, description="关闭")
        show: Trigger = Field(default=None, description="显示")
        hide: Trigger = Field(default=None, description="隐藏")
        minimize: Trigger = Field(default=None, description="最小化")
        maximize: Trigger = Field(default=None, description="最大化")

    info: Info = Field(default_factory=Info, description="设备信息")
    action: Annotated[Action, ui(visibility=lambda entry: entry._vis_actions())] = (
        Field(default_factory=Action, description="设备操作")
    )

    @property
    def _control(self) -> GameControl[GameEntry, GameDeviceEntry]:
        """父游戏上的管理实例；配置生命周期内必达，否则上抛。"""
        col = self.parent
        game = col.parent if col is not None else None
        if not isinstance(game, GameEntry):
            raise RuntimeError("设备未挂入游戏配置")
        return game._control

    def _vis_actions(self) -> UiVisibility:
        collection = self.parent
        game = collection.parent if collection is not None else None
        return game._vis_actions() if isinstance(game, GameEntry) else UiVisibility.SHOW

    @ui_visibility("action.open")
    def _vis_open(self) -> UiVisibility:
        """设备已在线或正在启动时隐藏启动操作，其余状态按控制器忙闲决定是否可用。"""
        if self.info.status in {DeviceStatus.ONLINE, DeviceStatus.STARTING}:
            return UiVisibility.HIDE
        return UiVisibility.SHOW

    @ui_visibility("action.close")
    def _vis_close(self) -> UiVisibility:
        """仅为在线、启动中或异常设备展示关闭操作，并遵循控制器忙闲限制。"""
        if self.info.status not in {
            DeviceStatus.ONLINE,
            DeviceStatus.STARTING,
            DeviceStatus.ERROR,
        }:
            return UiVisibility.HIDE
        return UiVisibility.SHOW

    @ui_visibility("action.show")
    def _vis_show(self) -> UiVisibility:
        """仅为在线设备展示显示窗口操作，并遵循控制器忙闲限制。"""
        if self.info.status != DeviceStatus.ONLINE:
            return UiVisibility.HIDE
        return UiVisibility.SHOW

    @ui_visibility("action.hide")
    def _vis_hide(self) -> UiVisibility:
        """仅为在线设备展示隐藏窗口操作，并遵循控制器忙闲限制。"""
        return self._vis_show()

    @ui_visibility("action.minimize")
    def _vis_minimize(self) -> UiVisibility:
        return self._vis_show()

    @ui_visibility("action.maximize")
    def _vis_maximize(self) -> UiVisibility:
        return self._vis_show()

    @trigger_field("action.open", finish_on_cancel=True)
    async def on_open(self) -> None:
        # 触发器带特殊票免订阅校验（用户权限最高）；
        # 手动操作的准入由游戏目标的 action 组统一判断。
        """以用户触发器身份请求控制器启动当前设备，具体执行限制由控制器处理。"""
        await self._control.open(self.uid, ticket=TRIGGER_TICKET)

    @trigger_field("action.close", finish_on_cancel=True)
    async def on_close(self) -> None:
        """以用户触发器身份请求控制器关闭当前设备。"""
        await self._control.close(self.uid, ticket=TRIGGER_TICKET)

    @trigger_field("action.show", finish_on_cancel=True)
    async def on_show(self) -> None:
        """以用户触发器身份请求控制器显示当前设备窗口。"""
        await self._control.show(self.uid, ticket=TRIGGER_TICKET)

    @trigger_field("action.hide", finish_on_cancel=True)
    async def on_hide(self) -> None:
        """以用户触发器身份请求控制器隐藏当前设备窗口。"""
        await self._control.hide(self.uid, ticket=TRIGGER_TICKET)

    @trigger_field("action.minimize", finish_on_cancel=True)
    async def on_minimize(self) -> None:
        await self._control.minimize(self.uid, ticket=TRIGGER_TICKET)

    @trigger_field("action.maximize", finish_on_cancel=True)
    async def on_maximize(self) -> None:
        await self._control.maximize(self.uid, ticket=TRIGGER_TICKET)


class GameEntry(ConfigEntry):
    """游戏主配置上界。插件继承后加自己的字段，并注册进 GameConfig。"""

    class Info(ConfigGroup):
        name: str = Field(default="新游戏", description="实例命名")
        type: Annotated[
            Literal["emulator", "client"], ui(visibility=UiVisibility.HIDE)
        ] = Field(default="emulator", description="模拟器或客户端")
        concurrent_execution: bool = Field(
            default=False, description="是否允许并发运行"
        )

    class Action(ConfigGroup):
        refresh: Trigger = Field(default=None, description="刷新设备列表")

    info: Info = Field(default_factory=Info, description="游戏信息")
    action: Annotated[Action, ui(visibility=lambda entry: entry._vis_actions())] = (
        Field(default_factory=Action, description="游戏操作")
    )
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

    @property
    def actions_busy(self) -> bool:
        """安装配置正被修改、控制器在执行，或本目标有已受理的触发器。"""
        return (
            self._lock_x is not None
            or (self._game_control is not None and self._game_control.busy)
            or bool(self.action._trigger_uids)
            or any(device.action._trigger_uids for device in self.devices.values())
        )

    def _vis_actions(self) -> UiVisibility:
        return UiVisibility.DISABLE if self.actions_busy else UiVisibility.SHOW

    @trigger_field("action.refresh", finish_on_cancel=True)
    async def on_refresh(self) -> None:
        """走配置触发器刷新 devices，受主配置 S 锁约束；随后收走已删除的设备。"""
        from app.core.game_manager import GameManager

        await self._control.refresh()
        await GameManager.remove_deleted_devices(self)

    @staticmethod
    async def on_add_devices(sender: object, event: CollectionChangeEvent) -> None:
        """GameConfig 实例级 add / init_add：把新游戏的 devices 删除接到统一信号。"""
        _ = sender
        if not isinstance(event.entry, GameEntry):
            raise TypeError(f"非 GameEntry: {event.entry}")
        event.entry.bind_runtime_signals()

    def bind_runtime_signals(self) -> None:
        """按设备集合声明订阅，允许新增条目仍处于激活事务时建立关联。"""
        type(self.devices).disconnect(
            GameEntry.on_remove_device, phase="runtime", kind="remove"
        )
        type(self.devices).connect(
            GameEntry.on_remove_device, phase="runtime", kind="remove"
        )

    @staticmethod
    async def on_remove_device(sender: object, event: CollectionChangeEvent) -> None:
        """单个游戏 devices 的 remove → 转发为 ``device_removed``。"""
        if not isinstance(sender, ConfigCollection) or not isinstance(
            sender.parent, GameEntry
        ):
            return
        await device_removed.send_async(sender, uid=event.uid)
