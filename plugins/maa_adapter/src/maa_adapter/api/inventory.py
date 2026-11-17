from typing import (
    Annotated,
    Dict,
    List,
    Optional,
)

from auto_mas_core.host.models_schema import (
    ComboBoxItem,
    ComboBoxOut,
    OutBase,
    ScriptDeleteIn,
)
from auto_mas_core.host.utils import get_logger
from fastapi import APIRouter, Body
from pydantic import (
    BaseModel,
    Field,
)

router = APIRouter()
logger = get_logger("MAA API")


class MaaDepotInventoryOut(OutBase):
    data: List[ComboBoxItem] = Field(
        ..., description="库存选项（label=数量字符串，value=物品ID）"
    )
    recognizedAt: Optional[str] = Field(
        None, description="最近识别时间（本地 ISO 格式）；无法确定识别时间时为 None"
    )


class MaaDepotStageCandidatesBatchIn(BaseModel):
    script: ScriptDeleteIn
    itemIds: List[Annotated[str, Field(min_length=1, max_length=64)]] = Field(
        ..., min_length=1, max_length=256, description="需要查询候选关卡的物品ID"
    )


class MaaDepotStageCandidatesBatchOut(OutBase):
    data: Dict[str, List[ComboBoxItem]] = Field(
        default_factory=dict, description="按物品ID分组的候选关卡，未找到候选时为空列表"
    )


@router.post(
    "/maa/depot/items",
    tags=["Get"],
    summary="MAA 库存保持物品可选项",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_maa_depot_items(script: ScriptDeleteIn = Body(...)) -> ComboBoxOut:

    try:
        import maa_adapter.cultivate.inventory as maa_api

        raw_data = await maa_api.get_depot_items(script.scriptId)
        data = [ComboBoxItem(**item) for item in raw_data]
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_maa_depot_items失败: {type(e).__name__}: {e}"
        )
        return ComboBoxOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", data=[]
        )
    return ComboBoxOut(data=data)


@router.post(
    "/maa/depot/stage/candidates",
    tags=["Get"],
    summary="MAA 库存保持关卡候选（掉落指定材料，按单件期望理智升序，label 为 xx 理智/件）",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_maa_depot_stage_candidates(
    script: ScriptDeleteIn = Body(...), itemId: str = Body(...)
) -> ComboBoxOut:

    try:
        import maa_adapter.cultivate.inventory as maa_api

        raw_data = await maa_api.get_depot_stage_candidates(script.scriptId, itemId)
        data = [ComboBoxItem(**item) for item in raw_data]
    except Exception as e:
        return ComboBoxOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", data=[]
        )
    return ComboBoxOut(data=data)


@router.post(
    "/maa/depot/stage/candidates/batch",
    tags=["Get"],
    summary="批量获取 MAA 库存保持关卡候选",
    response_model=MaaDepotStageCandidatesBatchOut,
    status_code=200,
)
async def get_maa_depot_stage_candidates_batch(
    request: MaaDepotStageCandidatesBatchIn,
) -> MaaDepotStageCandidatesBatchOut:
    try:
        import maa_adapter.cultivate.inventory as maa_api

        data = await maa_api.get_depot_stage_candidates_batch(
            script_id=request.script.scriptId, item_ids=request.itemIds
        )
        return MaaDepotStageCandidatesBatchOut(
            data={
                key: [ComboBoxItem(**item) for item in items]
                for key, items in data.items()
            }
        )
    except Exception as e:
        return MaaDepotStageCandidatesBatchOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )


@router.post(
    "/maa/depot/inventory",
    tags=["Get"],
    summary="MAA 仓库库存（当前账号档案；label=数量字符串，value=物品ID）",
    response_model=MaaDepotInventoryOut,
    status_code=200,
)
async def get_maa_depot_inventory(
    script: ScriptDeleteIn = Body(...), userId: str = Body(...)
) -> MaaDepotInventoryOut:

    try:
        import maa_adapter.cultivate.inventory as maa_api

        raw_data, recognized_at = await maa_api.get_depot_inventory(
            script.scriptId, userId
        )
        data = [ComboBoxItem(**item) for item in raw_data]
    except Exception as e:
        return MaaDepotInventoryOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
            recognizedAt=None,
        )
    return MaaDepotInventoryOut(data=data, recognizedAt=recognized_at)
