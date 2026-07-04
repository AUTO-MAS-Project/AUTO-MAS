import uuid

from fastapi import APIRouter

from app.core import Config
from app.models.script_api import ScriptTypeGetOut

router = APIRouter(prefix="/api/script-types", tags=["脚本类型"])


@router.post("/get", summary="获取脚本类型描述", response_model=ScriptTypeGetOut)
async def get_script_types() -> ScriptTypeGetOut:
    try:
        data = await Config.get_script_type_descriptors()
    except Exception as e:
        return ScriptTypeGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {e}",
            data=[],
        )
    return ScriptTypeGetOut(data=data)

