"""模拟器配置与设备中间上界（相对 Game* 收窄）。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import Field

from app.config import (
    ConfigCollection,
    ConfigGroup,
    ExecutablePath,
    FilePath,
    Trigger,
    UiVisibility,
    trigger_field,
    ui,
    ui_visibility,
)
from app.config.shortcuts import collection
from app.models.config.game import (
    TRIGGER_TICKET,
    DeviceStatus,
    GameDeviceEntry,
    GameEntry,
)

if TYPE_CHECKING:
    from app.plugin.base.emulator import EmulatorControl


# Pydantic 子类重新声明并收窄字段，沿用配置模型的逐字段继承豁免。
class EmulatorDeviceEntry(GameDeviceEntry):
    """模拟器设备：序号、adb 地址；通行触发器含最小化/商店/删实例。"""

    class Info(GameDeviceEntry.Info):
        index: Annotated[str, ui(visibility=UiVisibility.DISABLE)] = Field(
            default="0", description="多开序号"
        )
        adb_address: Annotated[str, ui(visibility=UiVisibility.DISABLE)] = Field(
            default="", description="ADB 连接地址"
        )

    class Action(GameDeviceEntry.Action):
        minimize: Trigger = Field(default=None, description="最小化")
        maximize: Trigger = Field(default=None, description="最大化")
        open_store: Trigger = Field(default=None, description="打开应用商店")
        delete_instance: Trigger = Field(default=None, description="删除多开")
        install_app: Trigger = Field(default=None, description="安装应用")

    class Installation(ConfigGroup):
        path: FilePath = Field(default=None, description="要安装的 APK 文件")

    info: Info = Field(default_factory=Info, description="设备信息")  # pyright: ignore[reportIncompatibleVariableOverride]
    action: Annotated[Action, ui(visibility=lambda entry: entry._vis_actions())] = (  # pyright: ignore[reportIncompatibleVariableOverride]
        Field(default_factory=Action, description="设备操作")
    )
    installation: Installation = Field(
        default_factory=Installation, description="应用安装"
    )

    @property
    def _control(self) -> EmulatorControl:
        """收窄为模拟器管理实例；类型不符则上抛。"""
        from app.plugin.base.emulator import EmulatorControl as EC

        ctrl = super()._control
        if not isinstance(ctrl, EC):
            raise TypeError("非模拟器管理实例")
        return ctrl

    @ui_visibility("action.open_store")
    def _vis_open_store(self) -> UiVisibility:
        """仅为在线设备展示应用商店入口，并按控制器忙闲决定是否可用。"""
        if self.info.status != DeviceStatus.ONLINE:
            return UiVisibility.HIDE
        return UiVisibility.SHOW

    @ui_visibility("action.delete_instance")
    def _vis_delete_instance(self) -> UiVisibility:
        """只允许删除已停止且未被托管占用的设备。"""
        if (
            self.info.status
            in {
                DeviceStatus.ONLINE,
                DeviceStatus.STARTING,
                DeviceStatus.CLOSEING,
                DeviceStatus.CREATING,
            }
            or self._device_in_use()
        ):
            return UiVisibility.DISABLE
        return UiVisibility.SHOW

    @trigger_field("action.minimize", finish_on_cancel=True)
    async def on_minimize(self) -> None:
        """以用户触发器身份请求模拟器控制器最小化当前实例。"""
        await self._control.minimize(self.uid, ticket=TRIGGER_TICKET)

    @trigger_field("action.maximize", finish_on_cancel=True)
    async def on_maximize(self) -> None:
        """以用户触发器身份请求模拟器控制器最大化当前实例。"""
        await self._control.maximize(self.uid, ticket=TRIGGER_TICKET)

    @trigger_field("action.open_store", finish_on_cancel=True)
    async def on_open_store(self) -> None:
        """以用户触发器身份请求模拟器控制器打开当前实例的应用商店。"""
        await self._control.open_store(self.uid, ticket=TRIGGER_TICKET)

    @trigger_field("action.delete_instance", finish_on_cancel=True)
    async def on_delete_instance(self) -> None:
        """以用户触发器身份请求模拟器控制器删除当前实例，成功后移除设备条目。

        适配插件删除后只把条目标成墓碑；条目、指向它的绑定和按设备存的基准由宿主
        统一清掉。删除失败直接上抛，条目保持原样。
        """
        from app.core.game_manager import GameManager

        game = self.parent.parent if self.parent is not None else None
        await self._control.delete_instance(self.uid, ticket=TRIGGER_TICKET)
        if isinstance(game, GameEntry):
            await GameManager.remove_deleted_devices(game, [self.uid])

    @ui_visibility("action.install_app")
    def _vis_install_app(self) -> UiVisibility:
        return (
            UiVisibility.SHOW
            if self.info.status == DeviceStatus.ONLINE and not self._device_in_use()
            else UiVisibility.DISABLE
        )

    def _device_in_use(self) -> bool:
        game = self.parent.parent if self.parent is not None else None
        return (
            isinstance(game, GameEntry)
            and game._game_control is not None
            and game._control.device_usage(self.uid) is not None
        )

    @trigger_field("action.install_app", finish_on_cancel=True)
    async def on_install_app(self) -> None:
        if self.installation.path is None:
            raise ValueError("请先选择 APK 文件")
        await self._control.install_app(
            self.uid, self.installation.path, ticket=TRIGGER_TICKET
        )


class EmulatorEntry(GameEntry):
    """模拟器游戏配置：路径、等待；建多开触发器。"""

    class Info(GameEntry.Info):
        type: Annotated[Literal["emulator"], ui(visibility=UiVisibility.HIDE)] = Field(  # pyright: ignore[reportIncompatibleVariableOverride]
            default="emulator", description="模拟器"
        )
        path: ExecutablePath = Field(default=None, description="管理器或控制台路径")
        max_wait_time: int = Field(
            default=300, ge=1, le=9999, description="操作最大等待时间（秒）"
        )

    class Action(GameEntry.Action):
        create_instance: Trigger = Field(default=None, description="新建多开")

    class Creation(ConfigGroup):
        name: str = Field(default="", description="新实例名称")

    info: Info = Field(default_factory=Info, description="游戏信息")  # pyright: ignore[reportIncompatibleVariableOverride]
    action: Annotated[Action, ui(visibility=lambda entry: entry._vis_actions())] = (  # pyright: ignore[reportIncompatibleVariableOverride]
        Field(default_factory=Action, description="游戏操作")
    )
    creation: Creation = Field(default_factory=Creation, description="新建实例")
    devices: ConfigCollection[EmulatorDeviceEntry] = collection(EmulatorDeviceEntry)  # type: ignore[assignment]  # pyright: ignore[reportIncompatibleVariableOverride]

    @property
    def _control(self) -> EmulatorControl:
        """收窄为模拟器管理实例；类型不符则上抛。"""
        from app.plugin.base.emulator import EmulatorControl as EC

        ctrl = super()._control
        if not isinstance(ctrl, EC):
            raise TypeError("非模拟器管理实例")
        return ctrl

    @trigger_field("action.create_instance", finish_on_cancel=True)
    async def on_create_instance(self) -> None:
        """请求当前模拟器控制器创建新实例，具体创建方式由模拟器适配实现。"""
        await self._control.create_instance(self.creation.name or None)
