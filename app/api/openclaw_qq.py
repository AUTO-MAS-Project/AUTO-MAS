#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""QQ 官方机器人扫码绑定 API。"""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Body
from pydantic import BaseModel, Field

from app.core import Notify
from app.core.notify.channels.openclaw_qq.transport import Sender as Sender
from app.models.config.setting import QQGroupCommandWhitelist
from app.models.schema import OutBase
from app.utils import get_logger


class OpenClawQQQrStartOut(OutBase):
    """QQ 官方机器人二维码创建响应。"""

    sessionId: str = Field(default="", description="二维码登录会话 ID")
    qrUrl: str = Field(default="", description="用于生成二维码的登录链接")


class OpenClawQQQrCheckIn(BaseModel):
    """QQ 官方机器人二维码状态查询请求。"""

    sessionId: str = Field(..., min_length=1, description="二维码登录会话 ID")


class OpenClawQQQrCheckOut(OutBase):
    """QQ 官方机器人二维码及消息网关状态查询响应。"""

    sessionId: str = Field(default="", description="二维码登录会话 ID")
    state: str = Field(
        default="",
        description="轮询状态：waiting、scanned、connecting（已绑定，网关连接中）、connected（网关已就绪）、expired 或 error",
    )
    connected: bool = Field(
        default=False, description="消息网关是否已就绪；绑定成功但仍在连接时为 false"
    )


class OpenClawQQStatusOut(OutBase):
    """QQ 官方机器人通知绑定状态，不返回任何凭据。"""

    enabled: bool = Field(default=False, description="是否启用 QQ 官方机器人通知")
    connected: bool = Field(default=False, description="是否已绑定 QQ 官方机器人")
    state: str = Field(
        default="disconnected",
        description="消息网关状态：disconnected、connecting、connected 或 reconnecting",
    )


class OpenClawQQGroup(BaseModel):
    """自动记录的群，不包含聊天内容。"""

    openId: str = Field(description="机器人收到事件的群 OpenID")
    lastSeen: datetime | None = Field(default=None, description="最近发现时间（UTC）")


class OpenClawQQGroupsOut(OutBase):
    """QQ 通知接收位置及自动记录的群。"""

    bindingId: str = Field(default="", description="绑定版本，用于拒绝旧页面保存")
    targetType: Literal["c2c", "group", "all"] = Field(
        default="c2c", description="通知接收位置"
    )
    groups: list[OpenClawQQGroup] = Field(
        default_factory=list, description="自动记录的群"
    )
    groupCommandWhitelist: QQGroupCommandWhitelist = Field(
        default_factory=list, description="群控制成员 OpenID 白名单，空列表允许所有成员"
    )
    errorCode: str = Field(default="", description="可本地化的错误标识")


class OpenClawQQTargetIn(BaseModel):
    """选择通知位置并可选更新群控制成员白名单。"""

    bindingId: str = Field(min_length=1, description="查询群列表时返回的绑定版本")
    targetType: Literal["c2c", "group", "all"] = Field(description="通知接收位置")
    groupCommandWhitelist: QQGroupCommandWhitelist | None = Field(
        default=None,
        description="群控制成员 OpenID 白名单；省略保持现值，空列表允许所有成员",
    )


router = APIRouter(prefix="/api/setting/openclaw-qq", tags=["QQ 官方机器人通知"])
logger = get_logger("QQ 机器人通知 API")


def _groups_out(sender: Sender) -> OpenClawQQGroupsOut:
    snapshot = sender.groups()
    return OpenClawQQGroupsOut(
        bindingId=snapshot.binding_id,
        targetType=snapshot.target_type,
        groupCommandWhitelist=list(snapshot.group_command_whitelist),
        groups=[
            OpenClawQQGroup(openId=group.openid, lastSeen=group.last_seen)
            for group in snapshot.groups
        ],
    )


@router.post(
    "/groups",
    summary="查询 QQ 通知接收位置及自动记录的群",
    response_model=OpenClawQQGroupsOut,
)
async def get_groups() -> OpenClawQQGroupsOut:
    """只返回自动记录的群和已保存的模式，不枚举 QQ 联系人。"""

    try:
        return _groups_out(Notify.channel_sender("openclaw_qq"))
    except Exception:
        logger.opt(exception=True).warning("查询 QQ 群状态失败")
        return OpenClawQQGroupsOut(
            code=500,
            status="error",
            message="查询 QQ 通知接收位置失败",
            errorCode="request_failed",
        )


@router.post(
    "/target", summary="选择 QQ 通知接收位置", response_model=OpenClawQQGroupsOut
)
async def set_target(body: OpenClawQQTargetIn = Body(...)) -> OpenClawQQGroupsOut:
    """验证绑定版本后保存通知模式与可选的群控制白名单。"""

    try:
        sender = Notify.channel_sender("openclaw_qq")
        await sender.set_target(
            binding_id=body.bindingId,
            target_type=body.targetType,
            group_command_whitelist=body.groupCommandWhitelist,
        )
        return _groups_out(sender)
    except ValueError as exc:
        error_code = str(exc)
        messages = {
            "binding_changed": "机器人绑定已变化，请刷新群列表后重新选择",
            "not_bound": "请先扫码绑定 QQ 官方机器人",
        }
        return OpenClawQQGroupsOut(
            code=400,
            status="error",
            message=messages.get(error_code, "保存 QQ 通知接收位置失败"),
            errorCode=error_code,
        )
    except Exception:
        logger.opt(exception=True).warning("保存 QQ 通知接收位置失败")
        return OpenClawQQGroupsOut(
            code=500,
            status="error",
            message="保存 QQ 通知接收位置失败",
            errorCode="request_failed",
        )


@router.post(
    "/status",
    summary="查询 QQ 官方机器人绑定状态",
    response_model=OpenClawQQStatusOut,
)
async def get_status() -> OpenClawQQStatusOut:
    """返回 QQ 绑定及网关状态，不返回协议凭据。

    connected 表示凭据已绑定；state 表示网关是连接中、已连接还是重连中。
    """

    try:
        state = Notify.channel_sender("openclaw_qq").status()
    except Exception as exc:
        logger.opt(exception=True).warning(
            f"get_status失败: {type(exc).__name__}: {exc}"
        )
        return OpenClawQQStatusOut(
            code=500,
            status="error",
            message=f"查询 QQ 登录状态失败: {type(exc).__name__}: {exc}",
        )
    return OpenClawQQStatusOut(
        enabled=state.enabled,
        connected=state.connected,
        state=state.state,
        message=state.message,
    )


@router.post(
    "/login/start",
    summary="创建 QQ 官方机器人登录二维码",
    response_model=OpenClawQQQrStartOut,
)
async def start_login() -> OpenClawQQQrStartOut:
    """创建二维码；App ID 和客户端密钥只在后台登录确认后保存。"""

    try:
        result = await Notify.channel_sender("openclaw_qq").start_login()
    except ValueError as exc:
        return OpenClawQQQrStartOut(code=400, status="error", message=str(exc))
    except Exception as exc:
        logger.opt(exception=True).warning(
            f"start_login失败: {type(exc).__name__}: {exc}"
        )
        return OpenClawQQQrStartOut(
            code=500,
            status="error",
            message=f"创建 QQ 二维码失败: {type(exc).__name__}: {exc}",
        )
    return OpenClawQQQrStartOut(
        sessionId=result.session_id,
        qrUrl=result.qr_url,
        message="请使用 QQ 扫描二维码",
    )


@router.post(
    "/login/check",
    summary="查询 QQ 官方机器人登录状态",
    response_model=OpenClawQQQrCheckOut,
)
async def check_login(body: OpenClawQQQrCheckIn = Body(...)) -> OpenClawQQQrCheckOut:
    """轮询二维码与消息网关状态。

    扫码确认后先保存凭据，此时可能返回 state=connecting、connected=false；
    网关 READY 后返回 state=connected、connected=true。网关等待超时
    返回 state=error，但绑定凭据仍保留，后台继续重连。
    """

    try:
        result = await Notify.channel_sender("openclaw_qq").check_login(
            session_id=body.sessionId
        )
    except Exception as exc:
        logger.opt(exception=True).warning(
            f"check_login失败: {type(exc).__name__}: {exc}"
        )
        return OpenClawQQQrCheckOut(
            code=500,
            status="error",
            sessionId=body.sessionId,
            state="error",
            message=f"查询 QQ 登录状态失败: {type(exc).__name__}: {exc}",
        )
    return OpenClawQQQrCheckOut(
        sessionId=result.session_id,
        state=result.state,
        connected=result.connected,
        message=result.message,
    )


@router.post(
    "/unbind",
    summary="解除 QQ 官方机器人绑定",
    response_model=OutBase,
)
async def unbind() -> OutBase:
    """解除绑定并清理本地保存的 QQ 协议状态。"""

    try:
        await Notify.channel_sender("openclaw_qq").unbind()
    except Exception as exc:
        logger.opt(exception=True).warning(f"unbind失败: {type(exc).__name__}: {exc}")
        return OutBase(
            code=500,
            status="error",
            message=f"解除 QQ 绑定失败: {type(exc).__name__}: {exc}",
        )
    return OutBase(message="QQ 官方机器人已解除绑定")
