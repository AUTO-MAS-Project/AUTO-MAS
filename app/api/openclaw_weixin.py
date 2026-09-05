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

"""微信 Claw 扫码绑定 API。"""

from fastapi import APIRouter, Body

from app.models.schema import (
    OpenClawWeixinQrCheckIn,
    OpenClawWeixinQrCheckOut,
    OpenClawWeixinQrStartOut,
    OpenClawWeixinStatusOut,
    OutBase,
)
from app.services.openclaw_weixin import openclaw_weixin_manager

router = APIRouter(
    prefix="/api/setting/openclaw-weixin", tags=["微信 Claw 通知"]
)


@router.post(
    "/status",
    summary="查询微信 Claw 绑定状态",
    response_model=OpenClawWeixinStatusOut,
)
async def get_status() -> OpenClawWeixinStatusOut:
    """返回微信绑定状态，不返回协议凭据。"""

    try:
        state = openclaw_weixin_manager.status()
    except Exception as exc:
        return OpenClawWeixinStatusOut(
            code=500,
            status="error",
            message=f"查询微信绑定状态失败: {type(exc).__name__}: {exc}",
        )
    return OpenClawWeixinStatusOut(
        enabled=state.enabled,
        connected=state.connected,
        state=state.state,
        contextReady=state.context_ready,
        message=state.message,
    )


@router.post(
    "/login/start",
    summary="创建微信 Claw 登录二维码",
    response_model=OpenClawWeixinQrStartOut,
)
async def start_login() -> OpenClawWeixinQrStartOut:
    """创建二维码；Bot Token 等凭据只在后台登录确认后保存。"""

    try:
        result = await openclaw_weixin_manager.start_login()
    except ValueError as exc:
        return OpenClawWeixinQrStartOut(code=400, status="error", message=str(exc))
    except Exception as exc:
        return OpenClawWeixinQrStartOut(
            code=500,
            status="error",
            message=f"创建微信二维码失败: {type(exc).__name__}: {exc}",
        )
    return OpenClawWeixinQrStartOut(
        sessionId=result.session_id,
        qrUrl=result.qr_url,
        message="请使用微信扫描二维码",
    )


@router.post(
    "/login/check",
    summary="查询微信 Claw 登录状态",
    response_model=OpenClawWeixinQrCheckOut,
)
async def check_login(
    body: OpenClawWeixinQrCheckIn = Body(...),
) -> OpenClawWeixinQrCheckOut:
    """查询二维码状态；确认后自动保存账号凭据。"""

    try:
        result = await openclaw_weixin_manager.check_login(
            session_id=body.sessionId,
            verify_code=body.verifyCode,
        )
    except Exception as exc:
        return OpenClawWeixinQrCheckOut(
            code=500,
            status="error",
            sessionId=body.sessionId,
            state="error",
            message=f"查询微信登录状态失败: {type(exc).__name__}: {exc}",
        )
    return OpenClawWeixinQrCheckOut(
        sessionId=result.session_id,
        state=result.state,
        connected=result.connected,
        contextReady=result.context_ready,
        message=result.message,
    )


@router.post(
    "/unbind",
    summary="解除微信 Claw 绑定",
    response_model=OutBase,
)
async def unbind() -> OutBase:
    """解除绑定并清理本地保存的微信协议状态。"""

    try:
        await openclaw_weixin_manager.unbind()
    except Exception as exc:
        return OutBase(
            code=500,
            status="error",
            message=f"解除微信绑定失败: {type(exc).__name__}: {exc}",
        )
    return OutBase(message="微信 Claw 已解除绑定")
