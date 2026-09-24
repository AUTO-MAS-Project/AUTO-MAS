#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


"""
森空岛扫码登录 API 路由（可选补丁）

可安全删除本文件，不会影响任何已有功能。
删除后同时移除 main.py 和 app/api/__init__.py 中的 include 调用。

流程:
  1. /create  -> 生成鹰角通行证扫码链接 (ticket, qr_url, device)
  2. /check   -> 轮询状态 (Init/Scanned/Confirmed/Expired/Canceled)
  3. /save    -> 用 scanCode 换取完整森空岛凭据并保存到账号组 SklandToken
"""

from fastapi import APIRouter, Body
from pydantic import BaseModel, Field

from app.core import Config
from app.models.schema import OutBase
from app.utils.logger import get_logger
from app.utils.security import format_exception_reason

router = APIRouter(prefix="/api/tools/sign/skland/qr", tags=["扫码登录"])
logger = get_logger("森空岛扫码登录 API")


def _log_qr_error(stage: str, error: Exception) -> None:
    """记录脱敏诊断，扫码接口不向前端透传异常细节。"""

    logger.warning(format_exception_reason(error, stage=stage, include_message=False))


class SklandQrCreateOut(OutBase):
    ticket: str = Field(default="", description="森空岛扫码 ticket/scanId")
    qr_url: str = Field(default="", description="用于生成二维码的跳转链接")
    device: str = Field(default="", description="本地设备 ID")


class SklandQrCheckIn(BaseModel):
    ticket: str
    device: str = Field(default="")


class SklandQrCheckOut(OutBase):
    status: str = Field(
        default="",
        description="Init/Scanned/Confirmed/Expired/Canceled/Error",
    )
    scan_code: str = Field(default="", description="确认后返回的短时 scanCode")


class SklandQrSaveIn(BaseModel):
    account_uid: str = Field(..., description="MAS 账号组 UUID")
    scan_code: str


@router.post("/create", summary="创建二维码", response_model=SklandQrCreateOut)
async def qr_create() -> SklandQrCreateOut:
    try:
        from app.tools.skland import create_skland_qr_login

        result = await create_skland_qr_login(proxy=Config.proxy)
    except Exception as e:
        _log_qr_error("创建森空岛二维码失败", e)
        return SklandQrCreateOut(
            code=500,
            status="error",
            message="二维码创建失败，请稍后重试",
        )
    if not isinstance(result, dict):
        return SklandQrCreateOut(
            code=500, status="error", message="二维码服务返回格式无效"
        )
    if not all(
        isinstance(result.get(key), str) and result[key]
        for key in ("ticket", "qr_url", "device")
    ):
        return SklandQrCreateOut(
            code=500, status="error", message="二维码服务返回数据不完整"
        )
    return SklandQrCreateOut(
        ticket=result["ticket"],
        qr_url=result["qr_url"],
        device=result["device"],
    )


@router.post("/check", summary="轮询扫码状态", response_model=SklandQrCheckOut)
async def qr_check(body: SklandQrCheckIn = Body(...)) -> SklandQrCheckOut:
    """确认后返回短时 scanCode，由前端随后提交保存。"""
    try:
        from app.tools.skland import check_skland_qr_status

        result = await check_skland_qr_status(
            body.ticket,
            body.device,
            proxy=Config.proxy,
        )
    except Exception as e:
        _log_qr_error("查询森空岛二维码状态失败", e)
        return SklandQrCheckOut(
            code=500,
            status="error",
            message="二维码状态查询失败，请稍后重试",
        )
    if not isinstance(result, dict):
        return SklandQrCheckOut(
            code=500, status="error", message="二维码状态响应格式无效"
        )
    status = result.get("status")
    if not isinstance(status, str) or not status:
        status = "error"
    scan_code = result.get("scan_code")
    if not isinstance(scan_code, str):
        scan_code = ""
    return SklandQrCheckOut(
        status=status,
        scan_code=scan_code,
        message=str(result.get("message") or ""),
    )


@router.post("/save", summary="保存森空岛 Token", response_model=OutBase)
async def qr_save(body: SklandQrSaveIn = Body(...)) -> OutBase:
    try:
        from app.tools.skland import (
            finalize_skland_qr_login,
            validate_skland_credential,
        )

        serialized = await finalize_skland_qr_login(
            body.scan_code,
            proxy=Config.proxy,
        )
        parsed = validate_skland_credential(serialized)
        if any(
            not str(parsed.get(field) or "").strip()
            for field in ("oauthToken", "token", "cred")
        ):
            raise ValueError("森空岛扫码登录未返回完整凭据")
        await Config.update_game_sign_account(
            body.account_uid,
            {"GameSignAccount": {"SklandToken": serialized}},
        )
    except ValueError as e:
        _log_qr_error("保存森空岛 Token 校验失败", e)
        return OutBase(
            code=400,
            status="error",
            message="森空岛扫码登录失败，请重新获取二维码",
        )
    except Exception as e:
        _log_qr_error("保存森空岛 Token 失败", e)
        return OutBase(
            code=500,
            status="error",
            message="森空岛 Token 保存失败，请稍后重试",
        )
    return OutBase(message="森空岛 Token 已保存")
