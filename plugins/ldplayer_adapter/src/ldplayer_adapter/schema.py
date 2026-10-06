"""雷电游戏配置与设备配置。"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from auto_mas_core import (
    ConfigCollection,
    GameDeviceEntry,
    GameEntry,
    UiVisibility,
    collection,
    ui,
)


class LDPlayerDevice(GameDeviceEntry):
    """多开设备。"""

    class Info(GameDeviceEntry.Info):
        index: Annotated[str, ui(visibility=UiVisibility.DISABLE)] = Field(
            default="0", description="多开序号"
        )
        adb_address: Annotated[str, ui(visibility=UiVisibility.DISABLE)] = Field(
            default="", description="ADB 地址"
        )

    info: Info = Field(default_factory=Info, description="设备信息")


class LDPlayerGame(GameEntry):
    """雷电模拟器配置。"""

    class Info(GameEntry.Info):
        type: Annotated[str, ui(visibility=UiVisibility.HIDE)] = Field(
            default="emulator", description="模拟器或客户端"
        )
        path: str = Field(default="", description="dnconsole.exe 路径")
        max_wait_time: int = Field(default=300, description="最大等待时间（秒）")
        boss_key: str = Field(default="[]", description="老板键")
        force_kill: bool = Field(default=False, description="关闭时强制结束")

    info: Info = Field(default_factory=Info, description="游戏信息")
    devices: ConfigCollection[LDPlayerDevice] = collection(LDPlayerDevice)
