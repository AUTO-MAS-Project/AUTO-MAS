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


from typing import Any, cast

from fastapi import APIRouter, Body
from pydantic import Field, TypeAdapter

from app.core import Config
from app.models.common_contract import (
    ApiModel,
    ComboBoxItem,
    ComboBoxOut,
    InfoOut,
    OutBase,
)
from app.api.common import error_out
from app.models.info_contract import (
    GetStageIn,
    NoticeOut,
    VersionOut,
)

router = APIRouter(prefix="/api/info", tags=["信息获取"])


class EmulatorIdBody(ApiModel):
    emulatorId: str = Field(..., description="模拟器 ID")

COMBOBOX_ITEMS_ADAPTER: TypeAdapter[list[ComboBoxItem]] = TypeAdapter(
    list[ComboBoxItem]
)


def _to_combobox_items(raw_data: object) -> list[ComboBoxItem]:
    return COMBOBOX_ITEMS_ADAPTER.validate_python(
        raw_data if isinstance(raw_data, list) else []
    )


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
        return error_out(
            VersionOut,
            e,
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
        raw_data = cast(object, await Config.get_stage_info(stage.type))
        data = _to_combobox_items(raw_data)
    except Exception as e:
        return error_out(ComboBoxOut, e, data=[])
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
        data = _to_combobox_items(raw_data)
    except Exception as e:
        return error_out(ComboBoxOut, e, data=[])
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
        data = _to_combobox_items(raw_data)
    except Exception as e:
        return error_out(ComboBoxOut, e, data=[])
    return ComboBoxOut(data=data)


@router.post(
    "/combox/plan",
    tags=["Get"],
    summary="获取可选计划下拉框信息",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_plan_combox() -> ComboBoxOut:
    try:
        raw_data = await Config.get_plan_combox()
        data = _to_combobox_items(raw_data)
    except Exception as e:
        return error_out(ComboBoxOut, e, data=[])
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
        data = _to_combobox_items(raw_data)
    except Exception as e:
        return error_out(ComboBoxOut, e, data=[])
    return ComboBoxOut(data=data)


@router.post(
    "/combox/emulator/devices",
    tags=["Get"],
    summary="获取可选模拟器多开实例下拉框信息",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_emulator_devices_combox(
    emulator: EmulatorIdBody = Body(...),
) -> ComboBoxOut:
    try:
        raw_data = cast(
            object, await Config.get_emulator_devices_combox(emulator.emulatorId)
        )
        data = _to_combobox_items(raw_data)
    except Exception as e:
        return error_out(ComboBoxOut, e, data=[])
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
        return error_out(NoticeOut, e, if_need_show=False, data={})
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
        return error_out(OutBase, e)
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
        return error_out(InfoOut, e, data={})
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
        raw_stage = cast(object, await Config.get_stage_info("Info"))
        stage = cast(dict[str, Any], raw_stage if isinstance(raw_stage, dict) else {})

        proxy = await Config.get_proxy_overview()
    except Exception as e:
        return error_out(InfoOut, e, data={"Stage": [], "Proxy": []})
    return InfoOut(data={"Stage": stage, "Proxy": proxy})
