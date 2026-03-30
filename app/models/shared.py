from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class TagItem(BaseModel):
    text: str = Field(..., description="标签文本")
    color: Literal[
        "red",
        "blue",
        "green",
        "yellow",
        "orange",
        "purple",
        "pink",
        "brown",
        "black",
        "white",
        "gray",
        "silver",
        "gold",
    ] = Field(..., description="标签颜色")


class WebSocketMessage(BaseModel):
    id: str = Field(..., description="消息ID, 为Main时表示消息来自主进程")
    type: Literal["Update", "Message", "Info", "Signal"] = Field(
        ...,
        description="消息类型 Update: 更新数据, Message: 请求弹出对话框, Info: 需要在UI显示的消息, Signal: 程序信号",
    )
    data: dict[str, Any] = Field(..., description="消息数据, 具体内容根据type类型而定")


class DeviceInfo(BaseModel):
    """API 层使用的设备信息模型。"""

    title: str = Field(..., description="设备标题/名称")
    status: int = Field(..., description="设备状态, 参考 DeviceStatus 枚举值")
    adb_address: str = Field(..., description="ADB连接地址")


__all__ = ["TagItem", "WebSocketMessage", "DeviceInfo"]
