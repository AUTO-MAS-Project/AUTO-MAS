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
    status: str = Field(default="", description="Init/Scanned/Confirmed/Error")
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
    if "error" in result:
        return QrCreateOut(code=500, status="error", message=result["error"])
    return QrCreateOut(ticket=result["ticket"], qr_url=result["qr_url"], device=result["device"])


@router.post("/check", summary="轮询扫码状态", response_model=QrCheckOut)
async def qr_check(body: QrCheckIn = Body(...)) -> QrCheckOut:
    """轮询状态，确认后 cookies 直接从响应头获取"""
    try:
        from app.tools.miyoushe_qr import check_qr_status
        result = await check_qr_status(body.ticket, body.device)
    except Exception as e:
        return QrCheckOut(code=500, status="error", message=str(e))
    if "error" in result:
        return QrCheckOut(code=500, status="error", message=result["error"])
    return QrCheckOut(
        status=result.get("status", ""),
        cookies_str=result.get("cookies_str", ""),
    )


@router.post("/save", summary="保存 cookie 到账号配置", response_model=OutBase)
async def qr_save(body: QrSaveIn = Body(...)) -> OutBase:
    try:
        data = {"GameSignAccount": {"MiyousheToken": body.cookie}}
        await Config.update_game_sign_account(body.account_uid, data)
        result = Config.ToolsConfig._game_sign_result_data
        for platform in list(result.keys()):
            result[platform] = [g for g in result[platform] if g.get("account_uid") != body.account_uid]
            if not result[platform]:
                del result[platform]
    except Exception as e:
        return OutBase(code=500, status="error", message=str(e))
    return OutBase(message="米游社 Token 已保存")
