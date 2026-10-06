"""通用进程游戏配置与设备配置。"""

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


class WinProcessDevice(GameDeviceEntry):
    """已跟踪的进程。"""

    class Info(GameDeviceEntry.Info):
        index: Annotated[str, ui(visibility=UiVisibility.DISABLE)] = Field(
            default="0", description="进程序号"
        )

    info: Info = Field(default_factory=Info, description="设备信息")


class WinProcessGame(GameEntry):
    """通用进程 / 客户端配置。"""

    class Info(GameEntry.Info):
        type: Annotated[str, ui(visibility=UiVisibility.HIDE)] = Field(
            default="client", description="模拟器或客户端"
        )
        path: str = Field(default="", description="可执行文件路径")
        args: str = Field(default="", description="启动参数")
        wait_time: int = Field(default=300, description="等待时间（秒）")
        force_kill: bool = Field(default=False, description="关闭时强制结束")
        boss_key: str = Field(default="[]", description="老板键")

    info: Info = Field(default_factory=Info, description="游戏信息")
    devices: ConfigCollection[WinProcessDevice] = collection(WinProcessDevice)
