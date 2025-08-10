#   AUTO_MAA:A MAA Multi Account Management and Automation Tool
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox

#   This file is part of AUTO_MAA.

#   AUTO_MAA is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO_MAA is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO_MAA. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


from fastapi import APIRouter, Body

from app.core import Config
from app.models.schema import *

router = APIRouter(prefix="/api/info", tags=["信息获取"])


@router.post(
    "/stage", summary="获取关卡号信息", response_model=InfoOut, status_code=200
)
async def get_stage_info() -> InfoOut:

    try:
        if_get_maa_stage, data = await Config.get_stage()
    except Exception as e:
        return InfoOut(code=500, status="error", message=str(e), data={})
    return InfoOut(
        status="success" if if_get_maa_stage else "warning",
        message="获取关卡号信息成功" if if_get_maa_stage else "未能获取活动关卡号信息",
        data=data,
    )


@router.post("/notice", summary="获取通知信息", response_model=InfoOut, status_code=200)
async def get_notice_info() -> InfoOut:

    try:
        data = await Config.get_server_info("notice")
    except Exception as e:
        return InfoOut(code=500, status="error", message=str(e), data={})
    return InfoOut(data=data)


@router.post(
    "/apps_info", summary="获取可下载应用信息", response_model=InfoOut, status_code=200
)
async def get_apps_info() -> InfoOut:

    try:
        data = await Config.get_server_info("apps_info")
    except Exception as e:
        return InfoOut(code=500, status="error", message=str(e), data={})
    return InfoOut(data=data)


@router.post(
    "/get/overview", summary="信息总览", response_model=InfoOut, status_code=200
)
async def add_overview() -> InfoOut:
    try:
        if_get_maa_stage, data = await Config.get_official_activity_stages()

        return InfoOut(
            status="success" if if_get_maa_stage else "warning",
            message="获取活动关卡信息成功" if if_get_maa_stage else "未能获取活动关卡信息",
            data=data,
        )

    except Exception as e:
        return InfoOut(code=500, status="error", message=str(e), data={})

