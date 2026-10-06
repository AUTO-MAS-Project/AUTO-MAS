#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright (c) 2024-2025 DLmaster361
#   Copyright (c) 2025 MoeSnowyFox
#   Copyright (c) 2025-2026 AUTO-MAS Team

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


from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Body
from pydantic import BaseModel, Field

from app.api import OutBase
from app.core import Config, TaskDispatcher
from app.core.history import history_store
from app.models.task import TaskMode

router = APIRouter(prefix="/api/info", tags=["信息获取"])


class InfoOut(OutBase):
    data: Dict[str, Any] = Field(..., description="收到的服务器数据")


class VersionOut(OutBase):
    if_need_update: bool = Field(..., description="后端代码是否需要更新")
    current_time: str = Field(..., description="后端代码当前时间戳")
    current_hash: str = Field(..., description="后端代码当前哈希值")


class NoticeOut(OutBase):
    if_need_show: bool = Field(..., description="是否需要显示公告")
    data: Dict[str, str] = Field(
        ..., description="公告信息, key为公告标题, value为公告内容"
    )


class ComboBoxItem(BaseModel):
    label: str = Field(..., description="展示值")
    value: Optional[str] = Field(..., description="实际值")
    supported_modes: Optional[List[TaskMode]] = Field(
        default=None, description="任务项支持的执行模式；非脚本项为空"
    )


class ComboBoxOut(OutBase):
    data: List[ComboBoxItem] = Field(..., description="下拉框选项")


class GetStageIn(BaseModel):
    type: Literal[
        "User",
        "Today",
        "ALL",
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ] = Field(
        ...,
        description="选择的日期类型, Today为当天, ALL为包含当天未开放关卡在内的所有项",
    )


class EmulatorDeleteIn(BaseModel):
    emulatorId: str = Field(..., description="游戏配置 uid")


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
        data = [
            ComboBoxItem(label=entry.info.name or str(uid), value=str(uid))
            for uid, entry in Config.ScriptConfig.items()
        ]
    except Exception as e:
        return ComboBoxOut(
            code=500, status="error", message=f"{type(e).__name__}: {e}", data=[]
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
        data = [
            ComboBoxItem(
                label=f"{entry.info.mode}:{uid}",
                value=str(uid),
                supported_modes=[entry.info.mode],
            )
            for uid, entry in TaskDispatcher.running_items()
        ]
    except Exception as e:
        return ComboBoxOut(
            code=500, status="error", message=f"{type(e).__name__}: {e}", data=[]
        )
    return ComboBoxOut(data=data)


@router.post(
    "/combox/plan",
    tags=["Get"],
    summary="获取可选计划下拉框信息",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_plan_combox(
    body: dict = Body(default_factory=dict),
) -> ComboBoxOut:
    try:
        script_type = (body or {}).get("scriptType") or (body or {}).get("script_type")
        data = []
        for uid, entry in Config.PlanConfig.items():
            if script_type and type(entry).__name__ != script_type:
                continue
            data.append(
                ComboBoxItem(label=entry.info.name or str(uid), value=str(uid))
            )
    except Exception as e:
        return ComboBoxOut(
            code=500, status="error", message=f"{type(e).__name__}: {e}", data=[]
        )
    return ComboBoxOut(data=data)


@router.post(
    "/combox/emulator",
    tags=["Get"],
    summary="获取可选游戏/模拟器下拉框信息",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_emulator_combox() -> ComboBoxOut:
    try:
        data = [
            ComboBoxItem(label=entry.info.name or str(uid), value=str(uid))
            for uid, entry in Config.GameConfig.items()
        ]
    except Exception as e:
        return ComboBoxOut(
            code=500, status="error", message=f"{type(e).__name__}: {e}", data=[]
        )
    return ComboBoxOut(data=data)


@router.post(
    "/combox/emulator/devices",
    tags=["Get"],
    summary="获取可选游戏多开实例下拉框信息",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_emulator_devices_combox(
    emulator: EmulatorDeleteIn = Body(...),
) -> ComboBoxOut:
    try:
        game = Config.GameConfig[UUID(emulator.emulatorId)]
        data = [
            ComboBoxItem(
                label=dev.info.name or str(dev.uid),
                value=str(dev.uid),
            )
            for dev in game.devices.values()
        ]
    except Exception as e:
        return ComboBoxOut(
            code=500, status="error", message=f"{type(e).__name__}: {e}", data=[]
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
        Config.setting.data.if_show_notice = False
        await Config.setting.commit()
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


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
        stage = await Config.get_stage_info("Info")
        proxy = history_store.get_overview()
    except Exception as e:
        return InfoOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data={"Stage": [], "Proxy": []},
        )
    return InfoOut(data={"Stage": stage, "Proxy": proxy})
