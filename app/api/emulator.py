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

from app.api.common import api_delete, api_get, api_patch, api_post
from app.core import Config, EmulatorManager
from app.models.common_contract import (
    IndexOrderPatch,
    OutBase,
    project_model,
    project_model_list,
    project_model_map,
)
from app.models.emulator_contract import (
    EmulatorActionBody,
    EmulatorConfigIndexItem,
    EmulatorCreateOut,
    EmulatorDetailOut,
    EmulatorDeviceStatusOut,
    EmulatorGetOut,
    EmulatorPatch,
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


async def _build_emulator_collection_out() -> EmulatorGetOut:
    index, data = await Config.get_emulator(None)
    return EmulatorGetOut(
        index=project_model_list(EmulatorConfigIndexItem, index),
        data=project_model_map(EmulatorRead, data),
    )


async def _build_emulator_detail_out(emulator_id: str) -> EmulatorDetailOut:
    _, data = await Config.get_emulator(emulator_id)
    projected = project_model_map(EmulatorRead, data)
    return EmulatorDetailOut(data=projected[emulator_id])


async def _build_emulator_create_out() -> EmulatorCreateOut:
    uid, config = await Config.add_emulator()
    return EmulatorCreateOut(
        id=str(uid),
        data=project_model(EmulatorRead, await config.toDict()),
    )


async def _update_emulator_config(emulator_id: str, data: EmulatorPatch) -> OutBase:
    await Config.update_emulator(emulator_id, data.model_dump(exclude_unset=True))
    return OutBase()


async def _delete_emulator_config(emulator_id: str) -> OutBase:
    await Config.del_emulator(emulator_id)
    return OutBase()


async def _build_emulator_status_out() -> EmulatorStatusOut:
    return EmulatorStatusOut(data=await EmulatorManager.get_status(None))


async def _build_emulator_device_status_out(
    emulator_id: str,
) -> EmulatorDeviceStatusOut:
    statuses = await EmulatorManager.get_status(emulator_id)
    return EmulatorDeviceStatusOut(data=statuses.get(emulator_id, {}))


async def _build_emulator_search_out() -> EmulatorSearchOut:
    from app.utils import search_all_emulators

    emulators = await search_all_emulators()
    return EmulatorSearchOut(data=project_model_list(EmulatorSearchResult, emulators))


@api_get(
    router,
    "",
    model_cls=EmulatorGetOut,
    index=[],
    data={},
    route_kwargs={
        "tags": ["Get"],
        "summary": "查询全部模拟器配置",
        "response_model": EmulatorGetOut,
        "status_code": 200,
    },
)
async def list_emulators() -> EmulatorGetOut:
    return await _build_emulator_collection_out()


@api_post(
    router,
    "",
    model_cls=EmulatorCreateOut,
    id="",
    data=EmulatorRead(),
    route_kwargs={
        "tags": ["Add"],
        "summary": "创建模拟器配置",
        "response_model": EmulatorCreateOut,
        "status_code": 200,
    },
)
async def create_emulator() -> EmulatorCreateOut:
    return await _build_emulator_create_out()


@api_patch(
    router,
    "/order",
    model_cls=OutBase,
    route_kwargs={
        "tags": ["Update"],
        "summary": "重新排序模拟器",
        "response_model": OutBase,
        "status_code": 200,
    },
)
async def reorder_emulator(body: IndexOrderPatch = Body(...)) -> OutBase:
    await Config.reorder_emulator(body.index_list)
    return OutBase()


@api_get(
    router,
    "/detected",
    model_cls=EmulatorSearchOut,
    data=[],
    route_kwargs={
        "tags": ["Get"],
        "summary": "搜索已安装的模拟器",
        "response_model": EmulatorSearchOut,
        "status_code": 200,
    },
)
async def detect_emulators() -> EmulatorSearchOut:
    return await _build_emulator_search_out()


@api_get(
    router,
    "/status",
    model_cls=EmulatorStatusOut,
    data={},
    route_kwargs={
        "tags": ["Get"],
        "summary": "查询全部模拟器状态",
        "response_model": EmulatorStatusOut,
        "status_code": 200,
    },
)
async def get_emulator_statuses() -> EmulatorStatusOut:
    return await _build_emulator_status_out()


@api_get(
    router,
    "/{emulator_id}",
    model_cls=EmulatorDetailOut,
    data=EmulatorRead(),
    route_kwargs={
        "tags": ["Get"],
        "summary": "查询单个模拟器配置",
        "response_model": EmulatorDetailOut,
        "status_code": 200,
    },
)
async def get_emulator(emulator_id: EmulatorIdPath) -> EmulatorDetailOut:
    return await _build_emulator_detail_out(emulator_id)


@api_patch(
    router,
    "/{emulator_id}",
    model_cls=OutBase,
    route_kwargs={
        "tags": ["Update"],
        "summary": "更新模拟器配置",
        "response_model": OutBase,
        "status_code": 200,
    },
)
async def update_emulator(
    emulator_id: EmulatorIdPath, data: EmulatorPatch = Body(...)
) -> OutBase:
    return await _update_emulator_config(emulator_id, data)


@api_delete(
    router,
    "/{emulator_id}",
    model_cls=OutBase,
    route_kwargs={
        "tags": ["Delete"],
        "summary": "删除模拟器配置",
        "response_model": OutBase,
        "status_code": 200,
    },
)
async def delete_emulator(emulator_id: EmulatorIdPath) -> OutBase:
    return await _delete_emulator_config(emulator_id)


@api_get(
    router,
    "/{emulator_id}/status",
    model_cls=EmulatorDeviceStatusOut,
    data={},
    route_kwargs={
        "tags": ["Get"],
        "summary": "查询单个模拟器状态",
        "response_model": EmulatorDeviceStatusOut,
        "status_code": 200,
    },
)
async def get_emulator_status(emulator_id: EmulatorIdPath) -> EmulatorDeviceStatusOut:
    return await _build_emulator_device_status_out(emulator_id)


@api_post(
    router,
    "/{emulator_id}/actions/{action}",
    model_cls=OutBase,
    route_kwargs={
        "tags": ["Action"],
        "summary": "执行模拟器动作",
        "response_model": OutBase,
        "status_code": 200,
    },
)
async def operate_emulator(
    emulator_id: EmulatorIdPath,
    action: EmulatorActionPath,
    body: EmulatorActionBody = Body(...),
) -> OutBase:
    await EmulatorManager.operate_emulator(action, emulator_id, body.index)
    return OutBase()
