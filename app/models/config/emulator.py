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
from app.config.shortcuts import collection, trigger_field
from app.models.config.game import (
    TRIGGER_TICKET,
    DeviceStatus,
    GameDeviceEntry,
    GameEntry,
)

if TYPE_CHECKING:
    from app.plugin.base.emulator import EmulatorControl


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

    info: Info = Field(default_factory=Info, description="设备信息")
    action: Action = Field(default_factory=Action, description="设备操作")

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
        if self.info.status != DeviceStatus.ONLINE:
            return UiVisibility.HIDE
        return self._busy_vis()

    @ui_visibility("action.maximize")
    def _vis_maximize(self) -> UiVisibility:
        if self.info.status != DeviceStatus.ONLINE:
            return UiVisibility.HIDE
        return self._busy_vis()

    @ui_visibility("action.open_store")
    def _vis_open_store(self) -> UiVisibility:
        if self.info.status != DeviceStatus.ONLINE:
            return UiVisibility.HIDE
        return self._busy_vis()

    @ui_visibility("action.delete_instance")
    def _vis_delete_instance(self) -> UiVisibility:
        if self.info.status == DeviceStatus.STARTING:
            return UiVisibility.HIDE
        return self._busy_vis()

    @trigger_field("action.minimize")
    async def on_minimize(self) -> None:
        await self._control.minimize(self.uid, ticket=TRIGGER_TICKET)

    @trigger_field("action.maximize")
    async def on_maximize(self) -> None:
        await self._control.maximize(self.uid, ticket=TRIGGER_TICKET)

    @trigger_field("action.open_store")
    async def on_open_store(self) -> None:
        await self._control.open_store(self.uid, ticket=TRIGGER_TICKET)

    @trigger_field("action.delete_instance")
    async def on_delete_instance(self) -> None:
        await self._control.delete_instance(self.uid, ticket=TRIGGER_TICKET)


class EmulatorEntry(GameEntry):
    """模拟器游戏配置：路径、等待；建多开触发器。"""

    class Info(GameEntry.Info):
        type: Annotated[Literal["emulator"], ui(visibility=UiVisibility.HIDE)] = Field(
            default="emulator", description="模拟器"
        )
        path: ExecutablePath = Field(default=None, description="管理器或控制台路径")
        max_wait_time: int = Field(default=300, description="操作最大等待时间（秒）")

    class Action(GameEntry.Action):
        create_instance: Trigger = Field(default=False, description="新建多开")

    info: Info = Field(default_factory=Info, description="游戏信息")
    action: Action = Field(default_factory=Action, description="游戏操作")
    devices: ConfigCollection[EmulatorDeviceEntry] = collection(EmulatorDeviceEntry)

    @property
    def _control(self) -> EmulatorControl:
        """收窄为模拟器管理实例；类型不符则上抛。"""
        from app.plugin.base.emulator import EmulatorControl as EC

        ctrl = super()._control
        if not isinstance(ctrl, EC):
            raise TypeError("非模拟器管理实例")
        return ctrl

    @trigger_field("action.create_instance")
    async def on_create_instance(self) -> None:
        await self._control.create_instance()
