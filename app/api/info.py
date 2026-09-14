#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import time

import httpx
from fastapi import APIRouter, Body

from app.core import Config
from app.models.schema import *
from app.utils import get_logger

router = APIRouter(prefix="/api/info", tags=["信息获取"])
logger = get_logger("信息获取 API")

## 碧蓝档案活动数据取自 Kivo 古书馆时间轴。该接口对 Origin 做了白名单校验，
## 只有 kivo.wiki 自己的来源能拿到数据，浏览器直连必定 403，所以由后端中转
## ——后端请求不带 Origin，可以正常取回。
## 地址末尾的斜杠不能省：少写会被 301 重定向到带斜杠的版本，而 httpx 默认不跟随。
KIVO_TIMELINE_URL = "https://api.kivo.wiki/api/v1/timeline/"

## 活动排期变化很慢，缓存十分钟，避免每个前端反复打这个第三方接口
BLUEARCHIVE_CACHE_TTL = 600

## 缓存条数上限：参数组合本来就有限（3 个服 × 页数 × 每页条数），
## 但接口对调用方是开放的，给个上限免得异常调用把进程内存撑大
BLUEARCHIVE_CACHE_MAX_ENTRIES = 32
_bluearchive_cache: dict[str, tuple[float, dict]] = {}


def _prune_bluearchive_cache(now: float) -> None:
    """先清掉过期项，仍超出上限时按写入时间淘汰最旧的。"""

    for key in [k for k, v in _bluearchive_cache.items() if now - v[0] >= BLUEARCHIVE_CACHE_TTL]:
        _bluearchive_cache.pop(key, None)

    while len(_bluearchive_cache) >= BLUEARCHIVE_CACHE_MAX_ENTRIES:
        oldest = min(_bluearchive_cache, key=lambda key: _bluearchive_cache[key][0])
        _bluearchive_cache.pop(oldest, None)


@router.post(
    "/version",
    tags=["Get"],
    summary="获取后端git版本信息",
    response_model=VersionOut,
    status_code=200,
)
async def get_git_version() -> VersionOut:

    try:
        is_latest, commit_hash, commit_time = await Config.get_git_version()
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_git_version失败: {type(e).__name__}: {e}"
        )
        return VersionOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            if_need_update=False,
            current_time="unknown",
            current_hash="unknown",
        )
    return VersionOut(
        if_need_update=not is_latest,
        current_time=commit_time,
        current_hash=commit_hash,
    )


@router.post(
    "/combox/stage",
    tags=["Get"],
    summary="获取关卡号下拉框信息",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_stage_combox(
    stage: GetStageIn = Body(..., description="关卡号类型"),
) -> ComboBoxOut:

    try:
        raw_data = await Config.get_stage_info(stage.type)
        data = (
            [ComboBoxItem(**item) for item in raw_data if isinstance(item, dict)]
            if raw_data
            else []
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_stage_combox失败: {type(e).__name__}: {e}"
        )
        return ComboBoxOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", data=[]
        )
    return ComboBoxOut(data=data)


@router.post(
    "/combox/script",
    tags=["Get"],
    summary="获取脚本下拉框信息",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_script_combox() -> ComboBoxOut:

    try:
        raw_data = await Config.get_script_combox()
        data = [ComboBoxItem(**item) for item in raw_data] if raw_data else []
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_script_combox失败: {type(e).__name__}: {e}"
        )
        return ComboBoxOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", data=[]
        )
    return ComboBoxOut(data=data)


@router.post(
    "/combox/task",
    tags=["Get"],
    summary="获取可选任务下拉框信息",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_task_combox() -> ComboBoxOut:

    try:
        raw_data = await Config.get_task_combox()
        data = [ComboBoxItem(**item) for item in raw_data] if raw_data else []
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_task_combox失败: {type(e).__name__}: {e}"
        )
        return ComboBoxOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", data=[]
        )
    return ComboBoxOut(data=data)


@router.post(
    "/combox/plan",
    tags=["Get"],
    summary="获取可选计划下拉框信息",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_plan_combox(plan: PlanComboxIn = Body(...)) -> ComboBoxOut:

    try:
        raw_data = await Config.get_plan_combox(plan.consumer)
        data = [ComboBoxItem(**item) for item in raw_data] if raw_data else []
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_plan_combox失败: {type(e).__name__}: {e}"
        )
        return ComboBoxOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", data=[]
        )
    return ComboBoxOut(data=data)


@router.post(
    "/combox/emulator",
    tags=["Get"],
    summary="获取可选模拟器下拉框信息",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_emulator_combox() -> ComboBoxOut:

    try:
        raw_data = await Config.get_emulator_combox()
        data = [ComboBoxItem(**item) for item in raw_data] if raw_data else []
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_emulator_combox失败: {type(e).__name__}: {e}"
        )
        return ComboBoxOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", data=[]
        )
    return ComboBoxOut(data=data)


@router.post(
    "/combox/emulator/devices",
    tags=["Get"],
    summary="获取可选模拟器多开实例下拉框信息",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_emulator_devices_combox(
    emulator: EmulatorDeleteIn = Body(...),
) -> ComboBoxOut:
    try:
        raw_data = await Config.get_emulator_devices_combox(emulator.emulatorId)
        data = [ComboBoxItem(**item) for item in raw_data] if raw_data else []
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_emulator_devices_combox失败: {type(e).__name__}: {e}"
        )
        return ComboBoxOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", data=[]
        )
    return ComboBoxOut(data=data)


@router.post(
    "/notice/get",
    tags=["Get"],
    summary="获取通知信息",
    response_model=NoticeOut,
    status_code=200,
)
async def get_notice_info() -> NoticeOut:

    try:
        if_need_show, data = await Config.get_notice()
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_notice_info失败: {type(e).__name__}: {e}"
        )
        return NoticeOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            if_need_show=False,
            data={},
        )
    return NoticeOut(if_need_show=if_need_show, data=data)


@router.post(
    "/notice/confirm",
    tags=["Action"],
    summary="确认通知",
    response_model=OutBase,
    status_code=200,
)
async def confirm_notice() -> OutBase:

    try:
        await Config.set("Data", "IfShowNotice", False)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"confirm_notice失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


# @router.post(
#     "/apps_info", summary="获取可下载应用信息", response_model=InfoOut, status_code=200
# )
# async def get_apps_info() -> InfoOut:

#     try:
#         data = await Config.get_server_info("apps_info")
#     except Exception as e:
#         return InfoOut(
#             code=500, status="error", message=f"{type(e).__name__}: {str(e)}", data={}
#         )
#     return InfoOut(data=data)


@router.post(
    "/webconfig",
    tags=["Get"],
    summary="获取配置分享中心的配置信息",
    response_model=InfoOut,
    status_code=200,
)
async def get_web_config() -> InfoOut:

    try:
        data = await Config.get_web_config()
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_web_config失败: {type(e).__name__}: {e}"
        )
        return InfoOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", data={}
        )
    return InfoOut(data={"WebConfig": data})


@router.post(
    "/get/overview",
    tags=["Get"],
    summary="信息总览",
    response_model=InfoOut,
    status_code=200,
)
async def get_overview() -> InfoOut:
    try:
        stage_by_server = {
            server: await Config.get_stage_info("Info", server=server)
            for server in (
                "Official",
                "Bilibili",
                "YoStarEN",
                "YoStarJP",
                "YoStarKR",
                "txwy",
            )
        }
        proxy = await Config.get_proxy_overview()
    except Exception as e:
        logger.opt(exception=True).warning(f"get_overview失败: {type(e).__name__}: {e}")
        return InfoOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data={
                "Stage": [],
                "Proxy": [],
            },
        )
    return InfoOut(
        data={
            "Stage": stage_by_server["Official"],
            "StageByServer": stage_by_server,
            "Proxy": proxy,
        }
    )


@router.post(
    "/bluearchive/activity",
    tags=["Get"],
    summary="获取碧蓝档案活动数据（Kivo 中转）",
    response_model=InfoOut,
    status_code=200,
)
async def get_bluearchive_activity(
    payload: BlueArchiveActivityIn = Body(...),
) -> InfoOut:
    """按服务器取回碧蓝档案的活动时间轴。

    这里只做转发：把 Kivo 的响应原样交给前端，筛选与格式转换都由前端完成。
    之所以要绕一道后端，是因为 Kivo 的接口校验 Origin，浏览器直连必定 403。
    """

    cache_key = f"{payload.line_type}:{payload.page}:{payload.page_size}"
    cached = _bluearchive_cache.get(cache_key)
    if cached is not None and time.time() - cached[0] < BLUEARCHIVE_CACHE_TTL:
        return InfoOut(data=cached[1])

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                KIVO_TIMELINE_URL,
                params={
                    "line_type": payload.line_type,
                    "page": payload.page,
                    "page_size": payload.page_size,
                },
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                    "Accept": "application/json",
                },
            )
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        logger.opt(exception=True).warning(
            f"获取碧蓝档案活动数据失败({payload.line_type}): {type(e).__name__}: {e}"
        )
        return InfoOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data={},
        )

    _prune_bluearchive_cache(time.time())
    _bluearchive_cache[cache_key] = (time.time(), data)
    return InfoOut(data=data)
