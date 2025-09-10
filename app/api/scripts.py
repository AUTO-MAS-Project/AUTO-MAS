#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox

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


import uuid
from fastapi import APIRouter, Body

from app.core import Config
from app.models.schema import *

router = APIRouter(prefix="/api/scripts", tags=["脚本管理"])


SCRIPT_BOOK = {"MaaConfig": MaaConfig, "GeneralConfig": GeneralConfig}
USER_BOOK = {"MaaConfig": MaaUserConfig, "GeneralConfig": GeneralUserConfig}


@router.post(
    "/add", summary="添加脚本", response_model=ScriptCreateOut, status_code=200
)
async def add_script(script: ScriptCreateIn = Body(...)) -> ScriptCreateOut:

    try:
        uid, config = await Config.add_script(script.type)
        data = SCRIPT_BOOK[type(config).__name__](**(await config.toDict()))
    except Exception as e:
        return ScriptCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            scriptId="",
            data=GeneralConfig(**{}),
        )
    return ScriptCreateOut(scriptId=str(uid), data=data)


@router.post(
    "/get", summary="查询脚本配置信息", response_model=ScriptGetOut, status_code=200
)
async def get_scripts(script: ScriptGetIn = Body(...)) -> ScriptGetOut:

    try:
        index, data = await Config.get_script(script.scriptId)
        index = [ScriptIndexItem(**_) for _ in index]
        data = {
            uid: SCRIPT_BOOK[next((_.type for _ in index if _.uid == uid), "General")](
                **cfg
            )
            for uid, cfg in data.items()
        }
    except Exception as e:
        return ScriptGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            index=[],
            data={},
        )
    return ScriptGetOut(index=index, data=data)


@router.post(
    "/update", summary="更新脚本配置信息", response_model=OutBase, status_code=200
)
async def update_script(script: ScriptUpdateIn = Body(...)) -> OutBase:

    try:
        await Config.update_script(
            script.scriptId, script.data.model_dump(exclude_unset=True)
        )
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post("/delete", summary="删除脚本", response_model=OutBase, status_code=200)
async def delete_script(script: ScriptDeleteIn = Body(...)) -> OutBase:

    try:
        await Config.del_script(script.scriptId)
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post("/order", summary="重新排序脚本", response_model=OutBase, status_code=200)
async def reorder_script(script: ScriptReorderIn = Body(...)) -> OutBase:

    try:
        await Config.reorder_script(script.indexList)
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/import/file", summary="从文件加载脚本", response_model=OutBase, status_code=200
)
async def import_script_from_file(script: ScriptFileIn = Body(...)) -> OutBase:

    try:
        await Config.import_script_from_file(script.scriptId, script.jsonFile)
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/export/file", summary="导出脚本到文件", response_model=OutBase, status_code=200
)
async def export_script_to_file(script: ScriptFileIn = Body(...)) -> OutBase:

    try:
        await Config.export_script_to_file(script.scriptId, script.jsonFile)
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/import/web", summary="从网络加载脚本", response_model=OutBase, status_code=200
)
async def import_script_from_web(script: ScriptUrlIn = Body(...)) -> OutBase:

    try:
        await Config.import_script_from_web(script.scriptId, script.url)
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/Upload/web", summary="上传脚本配置到网络", response_model=OutBase, status_code=200
)
async def upload_script_to_web(script: ScriptUploadIn = Body(...)) -> OutBase:

    try:
        await Config.upload_script_to_web(
            script.scriptId, script.config_name, script.author, script.description
        )
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/user/get", summary="查询用户", response_model=UserGetOut, status_code=200
)
async def get_user(user: UserGetIn = Body(...)) -> UserGetOut:

    try:
        index, data = await Config.get_user(user.scriptId, user.userId)
        index = [UserIndexItem(**_) for _ in index]
        data = {
            uid: USER_BOOK[
                type(Config.ScriptConfig[uuid.UUID(user.scriptId)]).__name__
            ](**cfg)
            for uid, cfg in data.items()
        }
    except Exception as e:
        return UserGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            index=[],
            data={},
        )
    return UserGetOut(index=index, data=data)


@router.post(
    "/user/add", summary="添加用户", response_model=UserCreateOut, status_code=200
)
async def add_user(user: UserInBase = Body(...)) -> UserCreateOut:

    try:
        uid, config = await Config.add_user(user.scriptId)
        data = USER_BOOK[type(Config.ScriptConfig[uuid.UUID(user.scriptId)]).__name__](
            **(await config.toDict())
        )
    except Exception as e:
        return UserCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            userId="",
            data=GeneralUserConfig(**{}),
        )
    return UserCreateOut(userId=str(uid), data=data)


@router.post(
    "/user/update", summary="更新用户配置信息", response_model=OutBase, status_code=200
)
async def update_user(user: UserUpdateIn = Body(...)) -> OutBase:

    try:
        await Config.update_user(
            user.scriptId, user.userId, user.data.model_dump(exclude_unset=True)
        )
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/user/delete", summary="删除用户", response_model=OutBase, status_code=200
)
async def delete_user(user: UserDeleteIn = Body(...)) -> OutBase:

    try:
        await Config.del_user(user.scriptId, user.userId)
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/user/order", summary="重新排序用户", response_model=OutBase, status_code=200
)
async def reorder_user(user: UserReorderIn = Body(...)) -> OutBase:

    try:
        await Config.reorder_user(user.scriptId, user.indexList)
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/user/infrastructure",
    summary="导入基建配置文件",
    response_model=OutBase,
    status_code=200,
)
async def import_infrastructure(user: UserSetIn = Body(...)) -> OutBase:

    try:
        await Config.set_infrastructure(user.scriptId, user.userId, user.jsonFile)
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()
