from fastapi import APIRouter, Body

from app.core import Config
from app.models.schema import OutBase
from app.models.script_api import (
    ScriptRecordCreateIn,
    ScriptRecordCreateOut,
    ScriptRecordDeleteIn,
    ScriptRecordGetIn,
    ScriptRecordGetOut,
    ScriptRecordReorderIn,
    ScriptRecordUpdateIn,
    ScriptUserRecordCreateIn,
    ScriptUserRecordCreateOut,
    ScriptUserRecordDeleteIn,
    ScriptUserRecordGetIn,
    ScriptUserRecordGetOut,
    ScriptUserRecordReorderIn,
    ScriptUserRecordUpdateIn,
)

router = APIRouter(prefix="/api/scripts2", tags=["通用脚本管理"])


@router.post("/add", summary="添加脚本", response_model=ScriptRecordCreateOut)
async def add_script(script: ScriptRecordCreateIn = Body(...)) -> ScriptRecordCreateOut:
    try:
        script_id, _ = await Config.add_script(script.type, script.scriptId)
        record = (await Config.get_script_records(str(script_id)))[0]
    except Exception as e:
        return ScriptRecordCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {e}",
            record={
                "id": "",
                "type": script.type,
                "name": "",
                "config": {},
                "schema": {},
                "editor_kind": "schema",
                "supported_modes": [],
                "icon": None,
                "docs_url": None,
                "user_count": 0,
            },
        )
    return ScriptRecordCreateOut(record=record)


@router.post("/get", summary="获取脚本", response_model=ScriptRecordGetOut)
async def get_script(script: ScriptRecordGetIn = Body(...)) -> ScriptRecordGetOut:
    try:
        records = await Config.get_script_records(script.scriptId)
    except Exception as e:
        return ScriptRecordGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {e}",
            records=[],
        )
    return ScriptRecordGetOut(records=records)


@router.post("/update", summary="更新脚本", response_model=OutBase)
async def update_script(script: ScriptRecordUpdateIn = Body(...)) -> OutBase:
    try:
        await Config.update_script(script.scriptId, script.config)
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {e}")
    return OutBase()


@router.post("/delete", summary="删除脚本", response_model=OutBase)
async def delete_script(script: ScriptRecordDeleteIn = Body(...)) -> OutBase:
    try:
        await Config.del_script(script.scriptId)
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {e}")
    return OutBase()


@router.post("/order", summary="脚本排序", response_model=OutBase)
async def reorder_script(script: ScriptRecordReorderIn = Body(...)) -> OutBase:
    try:
        await Config.reorder_script(script.indexList)
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {e}")
    return OutBase()


@router.post("/users/get", summary="获取用户", response_model=ScriptUserRecordGetOut)
async def get_users(user: ScriptUserRecordGetIn = Body(...)) -> ScriptUserRecordGetOut:
    try:
        records = await Config.get_user_records(user.scriptId, user.userId)
    except Exception as e:
        return ScriptUserRecordGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {e}",
            records=[],
        )
    return ScriptUserRecordGetOut(records=records)


@router.post("/users/add", summary="添加用户", response_model=ScriptUserRecordCreateOut)
async def add_user(user: ScriptUserRecordCreateIn = Body(...)) -> ScriptUserRecordCreateOut:
    try:
        user_id, _ = await Config.add_user(user.scriptId)
        record = (await Config.get_user_records(user.scriptId, str(user_id)))[0]
    except Exception as e:
        return ScriptUserRecordCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {e}",
            record={
                "id": "",
                "script_id": user.scriptId,
                "type": "",
                "name": "",
                "config": {},
                "schema": {},
            },
        )
    return ScriptUserRecordCreateOut(record=record)


@router.post("/users/update", summary="更新用户", response_model=OutBase)
async def update_user(user: ScriptUserRecordUpdateIn = Body(...)) -> OutBase:
    try:
        await Config.update_user(user.scriptId, user.userId, user.config)
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {e}")
    return OutBase()


@router.post("/users/delete", summary="删除用户", response_model=OutBase)
async def delete_user(user: ScriptUserRecordDeleteIn = Body(...)) -> OutBase:
    try:
        await Config.del_user(user.scriptId, user.userId)
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {e}")
    return OutBase()


@router.post("/users/order", summary="用户排序", response_model=OutBase)
async def reorder_user(user: ScriptUserRecordReorderIn = Body(...)) -> OutBase:
    try:
        await Config.reorder_user(user.scriptId, user.indexList)
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {e}")
    return OutBase()

