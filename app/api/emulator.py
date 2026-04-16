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


from typing import Annotated, Literal

from fastapi import APIRouter, Body, Path


from app.core import Config, EmulatorManager
from app.contracts.common_contract import (
    IndexOrderPatch,
    OutBase,
    dump_writable_data,
    project_model,
    project_model_list,
    project_model_map,
)
from app.contracts.emulator_contract import (
    EmulatorActionBody,
    EmulatorConfigIndexItem,
    EmulatorCreateOut,
    EmulatorDetailOut,
    EmulatorDeviceStatusOut,
    EmulatorGetOut,
    EmulatorRead,
    EmulatorSearchOut,
    EmulatorSearchResult,
    EmulatorStatusOut,
)

router = APIRouter(prefix="/api/emulator", tags=["模拟器管理"])

EmulatorIdPath = Annotated[str, Path(description="模拟器 ID")]
EmulatorActionPath = Annotated[
    Literal["open", "close", "show"],
    Path(description="模拟器动作"),
]


@router.get(
    "",
    tags=["Get"],
    summary="查询全部模拟器配置",
    response_model=EmulatorGetOut,
)
async def list_emulators() -> EmulatorGetOut:
    index, data = await Config.get_emulator(None)
    return EmulatorGetOut(
        index=project_model_list(EmulatorConfigIndexItem, index),
        data=project_model_map(EmulatorRead, data),
    )


@router.post(
    "",
    tags=["Add"],
    summary="创建模拟器配置",
    response_model=EmulatorCreateOut,
)
async def create_emulator() -> EmulatorCreateOut:
    uid, config = await Config.add_emulator()
    return EmulatorCreateOut(
        id=str(uid),
        data=project_model(EmulatorRead, await config.toDict()),
    )


@router.patch(
    "/order",
    tags=["Update"],
    summary="重新排序模拟器",
    response_model=OutBase,
)
async def reorder_emulator(body: IndexOrderPatch = Body(...)) -> OutBase:
    await Config.reorder_emulator(body.index_list)
    return OutBase()


@router.get(
    "/detected",
    tags=["Get"],
    summary="搜索已安装的模拟器",
    response_model=EmulatorSearchOut,
)
async def detect_emulators() -> EmulatorSearchOut:
    from app.utils import search_all_emulators

    emulators = await search_all_emulators()
    return EmulatorSearchOut(data=project_model_list(EmulatorSearchResult, emulators))


@router.get(
    "/status",
    tags=["Get"],
    summary="查询全部模拟器状态",
    response_model=EmulatorStatusOut,
)
async def get_emulator_statuses() -> EmulatorStatusOut:
    return EmulatorStatusOut(data=await EmulatorManager.get_status(None))


@router.get(
    "/{emulator_id}",
    tags=["Get"],
    summary="查询单个模拟器配置",
    response_model=EmulatorDetailOut,
)
async def get_emulator(emulator_id: EmulatorIdPath) -> EmulatorDetailOut:
    _, data = await Config.get_emulator(emulator_id)
    projected = project_model_map(EmulatorRead, data)
    return EmulatorDetailOut(data=projected[emulator_id])


@router.patch(
    "/{emulator_id}",
    tags=["Update"],
    summary="更新模拟器配置",
    response_model=OutBase,
)
async def update_emulator(
    emulator_id: EmulatorIdPath, data: EmulatorRead = Body(...)
) -> OutBase:
    await Config.update_emulator(emulator_id, dump_writable_data(data))
    return OutBase()


@router.delete(
    "/{emulator_id}",
    tags=["Delete"],
    summary="删除模拟器配置",
    response_model=OutBase,
)
async def delete_emulator(emulator_id: EmulatorIdPath) -> OutBase:
    await Config.del_emulator(emulator_id)
    return OutBase()


@router.get(
    "/{emulator_id}/status",
    tags=["Get"],
    summary="查询单个模拟器状态",
    response_model=EmulatorDeviceStatusOut,
)
async def get_emulator_status(emulator_id: EmulatorIdPath) -> EmulatorDeviceStatusOut:
    statuses = await EmulatorManager.get_status(emulator_id)
    return EmulatorDeviceStatusOut(data=statuses.get(emulator_id, {}))


@router.post(
    "/{emulator_id}/actions/{action}",
    tags=["Action"],
    summary="执行模拟器动作",
    response_model=OutBase,
)
async def operate_emulator(
    emulator_id: EmulatorIdPath,
    action: EmulatorActionPath,
    body: EmulatorActionBody = Body(...),
) -> OutBase:
    await EmulatorManager.operate_emulator(action, emulator_id, body.index)
    return OutBase()
