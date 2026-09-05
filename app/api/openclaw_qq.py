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

from fastapi import APIRouter, Body

from app.models.schema import (
    OpenClawQQQrCheckIn,
    OpenClawQQQrCheckOut,
    OpenClawQQQrStartOut,
    OpenClawQQStatusOut,
    OutBase,
)
from app.services.openclaw_qq import openclaw_qq_manager

router = APIRouter(prefix="/api/setting/openclaw-qq", tags=["QQ 官方机器人通知"])


@router.post(
    "/status",
    summary="查询 QQ 官方机器人绑定状态",
    response_model=OpenClawQQStatusOut,
)
async def get_status() -> OpenClawQQStatusOut:
    """返回 QQ 绑定状态，不返回协议凭据。"""

    try:
        state = openclaw_qq_manager.status()
    except Exception as exc:
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
        result = await openclaw_qq_manager.start_login()
    except ValueError as exc:
        return OpenClawQQQrStartOut(code=400, status="error", message=str(exc))
    except Exception as exc:
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
async def check_login(
    body: OpenClawQQQrCheckIn = Body(...),
) -> OpenClawQQQrCheckOut:
    """轮询二维码状态；确认后自动保存 QQ 机器人凭据。"""

    try:
        result = await openclaw_qq_manager.check_login(session_id=body.sessionId)
    except Exception as exc:
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
        await openclaw_qq_manager.unbind()
    except Exception as exc:
        return OutBase(
            code=500,
            status="error",
            message=f"解除 QQ 绑定失败: {type(exc).__name__}: {exc}",
        )
    return OutBase(message="QQ 官方机器人已解除绑定")
