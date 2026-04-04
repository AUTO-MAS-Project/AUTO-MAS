from __future__ import annotations

from typing import Any

from pydantic import Field

from .common_contract import ApiModel, OutBase


class WSClientCreateIn(ApiModel):
    """创建 WebSocket 客户端请求"""

    name: str = Field(..., description="客户端名称，用于标识")
    url: str = Field(
        ..., description="WebSocket 服务器地址，如 ws://localhost:5140/path"
    )
    ping_interval: float = Field(default=15.0, description="心跳发送间隔（秒）")
    ping_timeout: float = Field(default=30.0, description="心跳超时时间（秒）")
    reconnect_interval: float = Field(default=5.0, description="重连间隔（秒）")
    max_reconnect_attempts: int = Field(
        default=-1, description="最大重连次数，-1为无限"
    )


class WSClientCreateOut(OutBase):
    """创建客户端响应"""

    data: dict[str, Any] | None = Field(default=None, description="返回数据")


class WSClientConnectIn(ApiModel):
    """连接请求"""

    name: str = Field(..., description="客户端名称")


class WSClientDisconnectIn(ApiModel):
    """断开连接请求"""

    name: str = Field(..., description="客户端名称")


class WSClientRemoveIn(ApiModel):
    """删除客户端请求"""

    name: str = Field(..., description="客户端名称")


class WSClientSendIn(ApiModel):
    """发送消息请求"""

    name: str = Field(..., description="客户端名称")
    message: dict[str, Any] = Field(..., description="要发送的 JSON 消息")


class WSClientSendJsonIn(ApiModel):
    """发送自定义 JSON 消息请求"""

    name: str = Field(..., description="客户端名称")
    msg_id: str = Field(default="Client", description="消息 ID")
    msg_type: str = Field(..., description="消息类型")
    data: dict[str, Any] = Field(default_factory=dict, description="消息数据")


class WSClientAuthIn(ApiModel):
    """发送认证请求"""

    name: str = Field(..., description="客户端名称")
    token: str = Field(..., description="认证 Token")
    auth_type: str = Field(default="auth", description="认证消息类型")
    extra_data: dict[str, Any] | None = Field(
        default=None, description="额外认证数据"
    )


class WSClientStatusIn(ApiModel):
    """获取客户端状态请求"""

    name: str = Field(..., description="客户端名称")


class WSClientStatusOut(OutBase):
    """客户端状态响应"""

    data: dict[str, Any] | None = Field(default=None, description="状态数据")


class WSClientListOut(OutBase):
    """客户端列表响应"""

    data: dict[str, Any] | None = Field(default=None, description="客户端列表")


class WSMessageHistoryOut(OutBase):
    """消息历史响应"""

    data: dict[str, Any] | None = Field(default=None, description="消息历史")


class WSClearHistoryIn(ApiModel):
    """清空消息历史请求"""

    name: str | None = Field(default=None, description="客户端名称，为空则清空所有")


class WSCommandsOut(OutBase):
    """可用命令列表响应"""

    data: dict[str, Any] | None = Field(default=None, description="命令列表")


__all__ = [
    "WSClientCreateIn",
    "WSClientCreateOut",
    "WSClientConnectIn",
    "WSClientDisconnectIn",
    "WSClientRemoveIn",
    "WSClientSendIn",
    "WSClientSendJsonIn",
    "WSClientAuthIn",
    "WSClientStatusIn",
    "WSClientStatusOut",
    "WSClientListOut",
    "WSMessageHistoryOut",
    "WSClearHistoryIn",
    "WSCommandsOut",
]
