#   AUTO_MAA:A MAA Multi Account Management and Automation Tool
#   Copyright © 2024-2025 DLmaster361

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

from core import Config
from models.schema import *

router = APIRouter(prefix="/api/scripts", tags=["脚本管理"])


@router.post(
    "/add", summary="添加脚本", response_model=ScriptCreateOut, status_code=200
)
async def add_script(script: ScriptCreateIn = Body(...)) -> ScriptCreateOut:

    uid, config = await Config.add_script(script.type)
    return ScriptCreateOut(scriptId=str(uid), data=await config.toDict())


@router.post(
    "/get", summary="查询脚本配置信息", response_model=ScriptGetOut, status_code=200
)
async def get_scripts(script: ScriptGetIn = Body(...)) -> ScriptGetOut:

    try:
        index, data = await Config.get_script(script.scriptId)
    except Exception as e:
        return ScriptGetOut(code=500, status="error", message=str(e), index=[], data={})
    return ScriptGetOut(index=index, data=data)


@router.post(
    "/update", summary="更新脚本配置信息", response_model=OutBase, status_code=200
)
async def update_script(script: ScriptUpdateIn = Body(...)) -> OutBase:

    try:
        await Config.update_script(script.scriptId, script.data)
    except Exception as e:
        return OutBase(code=500, status="error", message=str(e))
    return OutBase()


@router.post("/delete", summary="删除脚本", response_model=OutBase, status_code=200)
async def delete_script(script: ScriptDeleteIn = Body(...)) -> OutBase:

    try:
        await Config.del_script(script.scriptId)
    except Exception as e:
        return OutBase(code=500, status="error", message=str(e))
    return OutBase()


@router.post("/order", summary="重新排序脚本", response_model=OutBase, status_code=200)
async def reorder_script(script: ScriptReorderIn = Body(...)) -> OutBase:

    try:
        await Config.reorder_script(script.indexList)
    except Exception as e:
        return OutBase(code=500, status="error", message=str(e))
    return OutBase()


@router.post(
    "/user/add", summary="添加用户", response_model=UserCreateOut, status_code=200
)
async def add_user(user: UserInBase = Body(...)) -> UserCreateOut:

    uid, config = await Config.add_user(user.scriptId)
    return UserCreateOut(userId=str(uid), data=await config.toDict())


@router.post(
    "/user/update", summary="更新用户配置信息", response_model=OutBase, status_code=200
)
async def update_user(user: UserUpdateIn = Body(...)) -> OutBase:

    try:
        await Config.update_user(user.scriptId, user.userId, user.data)
    except Exception as e:
        return OutBase(code=500, status="error", message=str(e))
    return OutBase()


@router.post(
    "/user/delete", summary="删除用户", response_model=OutBase, status_code=200
)
async def delete_user(user: UserDeleteIn = Body(...)) -> OutBase:

    try:
        await Config.del_user(user.scriptId, user.userId)
    except Exception as e:
        return OutBase(code=500, status="error", message=str(e))
    return OutBase()


@router.post(
    "/user/order", summary="重新排序用户", response_model=OutBase, status_code=200
)
async def reorder_user(user: UserReorderIn = Body(...)) -> OutBase:

    try:
        await Config.reorder_user(user.scriptId, user.indexList)
    except Exception as e:
        return OutBase(code=500, status="error", message=str(e))
    return OutBase()
