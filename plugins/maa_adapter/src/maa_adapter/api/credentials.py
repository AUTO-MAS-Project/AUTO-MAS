from typing import (
    Literal,
)

from auto_mas_core.host.models_schema import (
    OutBase,
)
from auto_mas_core.host.utils import get_logger
from fastapi import APIRouter
from pydantic import (
    BaseModel,
    Field,
)

router = APIRouter()
logger = get_logger("MAA API")


class ScriptMirrorCdkIn(BaseModel):
    type: Literal["MAA"] = Field(..., description="托管类型，决定凭据回退规则")
    cdk: str = Field(
        default="", repr=False, description="待校验的 CDK；留空回退全局 CDK"
    )


class ScriptMirrorCdkData(BaseModel):
    status: str
    expiredTime: int | None = Field(default=None, description="到期时间（unix 秒）")
    usingGlobalCdk: bool = Field(..., description="是否按专用 CDK 留空规则使用全局 CDK")


class ScriptMirrorCdkOut(OutBase):
    data: ScriptMirrorCdkData


@router.post(
    "/mirror-cdk",
    tags=["Get"],
    summary="查询脚本生效的 Mirror 酱 CDK 状态",
    response_model=ScriptMirrorCdkOut,
)
async def query_script_mirror_cdk(payload: ScriptMirrorCdkIn) -> ScriptMirrorCdkOut:
    """校验编辑框草稿；MAA 专用 CDK 留空时按接管规则查询全局 CDK。"""
    import maa_adapter.updates.credentials_api as maa_api

    result, using_global = await maa_api.query_mirror_cdk(payload.cdk)
    return ScriptMirrorCdkOut(
        data=ScriptMirrorCdkData(
            status=result.status,
            expiredTime=result.expired_time,
            usingGlobalCdk=using_global,
        )
    )
