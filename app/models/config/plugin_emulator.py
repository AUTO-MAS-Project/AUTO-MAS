"""模拟器配置与设备中间上界（相对 Game* 收窄）。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import Field

from app.config import (
    ConfigCollection,
    ExecutablePath,
    Trigger,
    UiVisibility,
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
from app.plugin.config import trigger_field

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
        minimize: Trigger = Field(default=False, description="最小化")
        maximize: Trigger = Field(default=False, description="最大化")
        open_store: Trigger = Field(default=False, description="打开应用商店")
        delete_instance: Trigger = Field(default=False, description="删除多开")

    info: Info = Field(default_factory=Info, description="设备信息")  # pyright: ignore[reportIncompatibleVariableOverride]
    action: Action = Field(default_factory=Action, description="设备操作")  # pyright: ignore[reportIncompatibleVariableOverride]

    @property
    def _control(self) -> EmulatorControl:
        """收窄为模拟器管理实例；类型不符则上抛。"""
        from app.plugin.base.emulator import EmulatorControl as EC

        ctrl = super()._control
        if not isinstance(ctrl, EC):
            raise TypeError("非模拟器管理实例")
        return ctrl

    @ui_visibility("action.minimize")
    def _vis_minimize(self) -> UiVisibility:
        """仅为在线设备展示最小化操作，并按控制器忙闲决定是否可用。"""
        if self.info.status != DeviceStatus.ONLINE:
            return UiVisibility.HIDE
        return self._busy_vis()

    @ui_visibility("action.maximize")
    def _vis_maximize(self) -> UiVisibility:
        """仅为在线设备展示最大化操作，并按控制器忙闲决定是否可用。"""
        if self.info.status != DeviceStatus.ONLINE:
            return UiVisibility.HIDE
        return self._busy_vis()

    @ui_visibility("action.open_store")
    def _vis_open_store(self) -> UiVisibility:
        """仅为在线设备展示应用商店入口，并按控制器忙闲决定是否可用。"""
        if self.info.status != DeviceStatus.ONLINE:
            return UiVisibility.HIDE
        return self._busy_vis()

    @ui_visibility("action.delete_instance")
    def _vis_delete_instance(self) -> UiVisibility:
        """启动期间隐藏删除实例操作，其余状态按控制器忙闲决定是否可用。"""
        if self.info.status == DeviceStatus.STARTING:
            return UiVisibility.HIDE
        return self._busy_vis()

    @trigger_field("action.minimize", cancellable=False)
    async def on_minimize(self) -> None:
        """以用户触发器身份请求模拟器控制器最小化当前实例。"""
        await self._control.minimize(self.uid, ticket=TRIGGER_TICKET)

    @trigger_field("action.maximize", cancellable=False)
    async def on_maximize(self) -> None:
        """以用户触发器身份请求模拟器控制器最大化当前实例。"""
        await self._control.maximize(self.uid, ticket=TRIGGER_TICKET)

    @trigger_field("action.open_store", cancellable=False)
    async def on_open_store(self) -> None:
        """以用户触发器身份请求模拟器控制器打开当前实例的应用商店。"""
        await self._control.open_store(self.uid, ticket=TRIGGER_TICKET)

    @trigger_field("action.delete_instance", cancellable=False)
    async def on_delete_instance(self) -> None:
        """以用户触发器身份请求模拟器控制器删除当前实例。"""
        await self._control.delete_instance(self.uid, ticket=TRIGGER_TICKET)


class EmulatorEntry(GameEntry):
    """模拟器游戏配置：路径、等待；建多开触发器。"""

    class Info(GameEntry.Info):
        type: Annotated[Literal["emulator"], ui(visibility=UiVisibility.HIDE)] = Field(  # pyright: ignore[reportIncompatibleVariableOverride]
            default="emulator", description="模拟器"
        )
        path: ExecutablePath = Field(default=None, description="管理器或控制台路径")
        max_wait_time: int = Field(default=300, description="操作最大等待时间（秒）")

    class Action(GameEntry.Action):
        create_instance: Trigger = Field(default=False, description="新建多开")

    info: Info = Field(default_factory=Info, description="游戏信息")  # pyright: ignore[reportIncompatibleVariableOverride]
    action: Action = Field(default_factory=Action, description="游戏操作")  # pyright: ignore[reportIncompatibleVariableOverride]
    devices: ConfigCollection[EmulatorDeviceEntry] = collection(EmulatorDeviceEntry)  # pyright: ignore[reportIncompatibleVariableOverride]

    @property
    def _control(self) -> EmulatorControl:
        """收窄为模拟器管理实例；类型不符则上抛。"""
        from app.plugin.base.emulator import EmulatorControl as EC

        ctrl = super()._control
        if not isinstance(ctrl, EC):
            raise TypeError("非模拟器管理实例")
        return ctrl

    @trigger_field("action.create_instance", cancellable=False)
    async def on_create_instance(self) -> None:
        """请求当前模拟器控制器创建新实例，具体创建方式由模拟器适配实现。"""
        await self._control.create_instance()
