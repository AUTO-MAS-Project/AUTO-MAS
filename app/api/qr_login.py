#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""
米游社扫码登录 API 路由（可选补丁）

可安全删除本文件，不会影响任何已有功能。
删除后同时移除 main.py 中的 include_router 调用。

流程（Passport 模式）:
  1. /create  → 生成二维码 (ticket, qr_url, device)
  2. /check   → 轮询状态 (Init/Scanned/Confirmed)，确认后返回 cookies_str
  3. /save    → 将 cookies 保存到账号配置
"""

from fastapi import APIRouter, Body
from pydantic import BaseModel, Field

from app.core import Config
from app.models.schema import OutBase

router = APIRouter(prefix="/api/tools/sign/miyoushe/qr", tags=["扫码登录"])


# ---- 请求/响应模型 ----


class QrCreateOut(OutBase):
    ticket: str = Field(default="", description="二维码 ticket")
    qr_url: str = Field(default="")
    device: str = Field(default="")


class QrCheckIn(BaseModel):
    ticket: str
    device: str


class QrCheckOut(OutBase):
    status: str = Field(
        default="", description="Init/Scanned/Confirmed/Expired/Canceled/Error"
    )
    cookies_str: str = Field(default="", description="确认后返回的完整 cookie 字符串")


class QrSaveIn(BaseModel):
    account_uid: str = Field(..., description="MAS 账号组 UUID")
    cookie: str


# ---- 端点 ----


@router.post("/create", summary="创建二维码", response_model=QrCreateOut)
async def qr_create() -> QrCreateOut:
    try:
        from app.tools.miyoushe_qr import create_qr_login

        result = await create_qr_login()
    except Exception as e:
        return QrCreateOut(code=500, status="error", message=str(e))
    if not isinstance(result, dict):
        return QrCreateOut(code=500, status="error", message="二维码服务返回格式无效")
    error = result.get("error")
    if error:
        return QrCreateOut(
            code=500,
            status="error",
            message=error if isinstance(error, str) else "创建二维码失败",
        )
    if not all(
        isinstance(result.get(key), str) and result[key]
        for key in ("ticket", "qr_url", "device")
    ):
        return QrCreateOut(code=500, status="error", message="二维码服务返回数据不完整")
    return QrCreateOut(
        ticket=result["ticket"], qr_url=result["qr_url"], device=result["device"]
    )


@router.post("/check", summary="轮询扫码状态", response_model=QrCheckOut)
async def qr_check(body: QrCheckIn = Body(...)) -> QrCheckOut:
    """轮询状态，确认后返回从 Passport 响应提取的 cookies。"""
    try:
        from app.tools.miyoushe_qr import check_qr_status

        result = await check_qr_status(body.ticket, body.device)
    except Exception as e:
        return QrCheckOut(code=500, status="error", message=str(e))
    if not isinstance(result, dict):
        return QrCheckOut(code=500, status="error", message="二维码状态响应格式无效")
    error = result.get("error")
    if error:
        error_status = result.get("status")
        if not isinstance(error_status, str) or not error_status:
            error_status = "error"
        return QrCheckOut(
            code=500,
            status=error_status,
            message=error if isinstance(error, str) else "查询二维码状态失败",
        )
    status = result.get("status")
    if not isinstance(status, str):
        status = ""
    cookies_str = result.get("cookies_str")
    if not isinstance(cookies_str, str):
        cookies_str = ""
    message = result.get("message")
    if not isinstance(message, str):
        message = ""
    return QrCheckOut(
        status=status,
        cookies_str=cookies_str,
        message=message,
    )


@router.post("/save", summary="保存 cookie 到账号配置", response_model=OutBase)
async def qr_save(body: QrSaveIn = Body(...)) -> OutBase:
    try:
        from app.tools.miyoushe import validate_miyoushe_cookie

        cookie = body.cookie.strip()
        validate_miyoushe_cookie(cookie)
        data = {"GameSignAccount": {"MiyousheToken": cookie}}
        await Config.update_game_sign_account(body.account_uid, data)
    except ValueError as e:
        return OutBase(code=400, status="error", message=f"米游社 Token 无效：{e}")
    except Exception as e:
        return OutBase(code=500, status="error", message=str(e))
    return OutBase(message="米游社 Token 已保存")
