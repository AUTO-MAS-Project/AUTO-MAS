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
    "/version",
    summary="获取后端git版本信息",
    response_model=VersionOut,
    status_code=200,
)
async def get_git_version() -> VersionOut:

    try:
        is_latest, commit_hash, commit_time = await Config.get_git_version()
    except Exception as e:
        return VersionOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            if_need_update=False,
            current_hash="",
            current_time="",
            current_version="",
        )
    return VersionOut(
        if_need_update=not is_latest,
        current_hash=commit_hash,
        current_time=commit_time,
        current_version=Config.version(),
    )


@router.post(
    "/combox/stage",
    summary="获取关卡号下拉框信息",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_stage_combox(
    stage: GetStageIn = Body(..., description="关卡号类型")
) -> ComboBoxOut:

    try:
        raw_data = await Config.get_stage_info(stage.type)
        data = (
            [ComboBoxItem(**item) for item in raw_data if isinstance(item, dict)]
            if raw_data
            else []
        )
    except Exception as e:
        return ComboBoxOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", data=[]
        )
    return ComboBoxOut(data=data)


@router.post(
    "/combox/script",
    summary="获取脚本下拉框信息",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_script_combox() -> ComboBoxOut:

    try:
        raw_data = await Config.get_script_combox()
        data = [ComboBoxItem(**item) for item in raw_data] if raw_data else []
    except Exception as e:
        return ComboBoxOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", data=[]
        )
    return ComboBoxOut(data=data)


@router.post(
    "/combox/task",
    summary="获取可选任务下拉框信息",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_task_combox() -> ComboBoxOut:

    try:
        raw_data = await Config.get_task_combox()
        data = [ComboBoxItem(**item) for item in raw_data] if raw_data else []
    except Exception as e:
        return ComboBoxOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", data=[]
        )
    return ComboBoxOut(data=data)


@router.post(
    "/combox/plan",
    summary="获取可选计划下拉框信息",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_plan_combox() -> ComboBoxOut:

    try:
        raw_data = await Config.get_plan_combox()
        data = [ComboBoxItem(**item) for item in raw_data] if raw_data else []
    except Exception as e:
        return ComboBoxOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", data=[]
        )
    return ComboBoxOut(data=data)


@router.post(
    "/notice/get", summary="获取通知信息", response_model=NoticeOut, status_code=200
)
async def get_notice_info() -> NoticeOut:

    try:
        if_need_show, data = await Config.get_notice()
    except Exception as e:
        return NoticeOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            if_need_show=False,
            data={},
        )
    return NoticeOut(if_need_show=if_need_show, data=data)


@router.post(
    "/notice/confirm", summary="确认通知", response_model=OutBase, status_code=200
)
async def confirm_notice() -> OutBase:

    try:
        await Config.set("Data", "IfShowNotice", False)
    except Exception as e:
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
    "/startuptask",
    summary="获取启动时运行的队列ID",
    response_model=InfoOut,
    status_code=200,
)
async def get_startup_task() -> InfoOut:

    try:
        data = await Config.get_startup_task()
    except Exception as e:
        return InfoOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", data={}
        )
    return InfoOut(data={"queueIdList": data})


@router.post(
    "/webconfig",
    summary="获取配置分享中心的配置信息",
    response_model=InfoOut,
    status_code=200,
)
async def get_web_config() -> InfoOut:

    try:
        data = await Config.get_web_config()
    except Exception as e:
        return InfoOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", data={}
        )
    return InfoOut(data={"WebConfig": data})


@router.post(
    "/get/overview", summary="信息总览", response_model=InfoOut, status_code=200
)
async def get_overview() -> InfoOut:
    try:
        stage = await Config.get_stage_info("Info")
        proxy = await Config.get_proxy_overview()
    except Exception as e:
        return InfoOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data={"Stage": [], "Proxy": []},
        )
    return InfoOut(data={"Stage": stage, "Proxy": proxy})
