#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


from fastapi import APIRouter, Body
from app.core import Config, EmulatorManager
from app.models.schema import (
    OutBase,
    EmulatorConfig,
    EmulatorGetIn,
    EmulatorGetOut,
    EmulatorConfigIndexItem,
    EmulatorCreateOut,
    EmulatorUpdateIn,
    EmulatorDeleteIn,
    EmulatorReorderIn,
    EmulatorOperateIn,
    EmulatorStatusOut,
    EmulatorSearchOut,
    EmulatorSearchResult,
)

router = APIRouter(prefix="/api/emulator", tags=["模拟器管理"])


@router.post(
    "/get", summary="查询模拟器配置", response_model=EmulatorGetOut, status_code=200
)
async def get_emulator(emulator: EmulatorGetIn = Body(...)) -> EmulatorGetOut:
    try:
        index, data = await Config.get_emulator(emulator.emulatorId)
        index = [EmulatorConfigIndexItem(**_) for _ in index]
        data = {uid: EmulatorConfig(**cfg) for uid, cfg in data.items()}
    except Exception as e:
        return EmulatorGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            index=[],
            data={},
        )
    return EmulatorGetOut(index=index, data=data)


@router.post(
    "/add", summary="添加模拟器项", response_model=EmulatorCreateOut, status_code=200
)
async def add_emulator() -> EmulatorCreateOut:
    try:
        uid, config = await Config.add_emulator()
        data = EmulatorConfig(**(await config.toDict()))
    except Exception as e:
        return EmulatorCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            emulatorId="",
            data=EmulatorConfig(**{}),
        )
    return EmulatorCreateOut(emulatorId=str(uid), data=data)


@router.post("/update", summary="更新模拟器项", response_model=OutBase, status_code=200)
async def update_emulator(emulator: EmulatorUpdateIn = Body(...)) -> OutBase:
    try:
        await Config.update_emulator(
            emulator.emulatorId, emulator.data.model_dump(exclude_unset=True)
        )
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post("/delete", summary="删除模拟器项", response_model=OutBase, status_code=200)
async def delete_emulator(emulator: EmulatorDeleteIn = Body(...)) -> OutBase:
    try:
        await Config.del_emulator(emulator.emulatorId)
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/order", summary="重新排序模拟器项", response_model=OutBase, status_code=200
)
async def reorder_emulator(emulator: EmulatorReorderIn = Body(...)) -> OutBase:
    try:
        await Config.reorder_emulator(emulator.indexList)
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post("/operate", summary="操作模拟器", response_model=OutBase, status_code=200)
async def operation_emulator(emulator: EmulatorOperateIn = Body(...)) -> OutBase:
    try:
        await EmulatorManager.operate_emulator(
            emulator.operate, emulator.emulatorId, emulator.index
        )
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/status",
    summary="查询模拟器状态",
    response_model=EmulatorStatusOut,
    status_code=200,
)
async def get_status(emulator: EmulatorGetIn = Body(...)) -> EmulatorStatusOut:
    try:
        data = await EmulatorManager.get_status(emulator.emulatorId)
    except Exception as e:
        return EmulatorStatusOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", data={}
        )
    return EmulatorStatusOut(data=data)


@router.post(
    "/emulator/search",
    summary="搜索已安装的模拟器",
    response_model=EmulatorSearchOut,
    status_code=200,
)
async def search_emulators() -> EmulatorSearchOut:
    """自动搜索系统中已安装的模拟器"""
    try:
        from app.utils import search_all_emulators

        emulators = await search_all_emulators()
        results = [EmulatorSearchResult(**emulator) for emulator in emulators]
    except Exception as e:
        return EmulatorSearchOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            emulators=[],
        )
    return EmulatorSearchOut(emulators=results)
