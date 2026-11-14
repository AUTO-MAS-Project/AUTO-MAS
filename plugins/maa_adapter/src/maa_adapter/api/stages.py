"""由 MAA 插件注册的关卡选项及活动资源接口。"""

from typing import Literal

from auto_mas_core import Plugin
from auto_mas_core.host.models_schema import ComboBoxItem, ComboBoxOut, OutBase
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

StageKind = Literal[
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
]


class MaaStageOptionsIn(BaseModel):
    type: StageKind = "User"
    server: str = "Official"


class MaaResourceActivity(BaseModel):
    # 响应始终导出默认文本；显式声明输出必备键供生成客户端使用。
    model_config = ConfigDict(json_schema_extra={"required": ["Tip", "StageName"]})
    Tip: str = ""
    StageName: str = ""


class MaaStageActivity(MaaResourceActivity):
    model_config = ConfigDict(
        json_schema_extra={
            "required": [
                "Tip",
                "StageName",
                "UtcStartTime",
                "UtcExpireTime",
                "TimeZone",
            ]
        }
    )
    UtcStartTime: str
    UtcExpireTime: str
    TimeZone: int = 8


class MaaResourceItem(BaseModel):
    Display: str
    Value: str
    Drop: str
    DropName: str
    Activity: MaaResourceActivity


class MaaActivityItem(BaseModel):
    Display: str
    Value: str
    Drop: str
    DropName: str
    Activity: MaaStageActivity


class MaaStageOverview(BaseModel):
    Activity: list[MaaActivityItem]
    ActivityTemplate: list[Literal["material", "orundum"]]
    ActivityStatus: Literal["ready", "empty", "stale", "unavailable"]
    ActivityUpdatedAt: str
    Resource: list[MaaResourceItem]
    Options: list[ComboBoxItem]


class MaaStageOverviewOut(OutBase):
    data: dict[str, MaaStageOverview]


router = APIRouter(prefix="/api/plugin/maa_adapter/stages", tags=["MAA"])


@router.post(
    "/options", response_model=ComboBoxOut, openapi_extra={"x-auto-mas-mcp": True}
)
async def get_maa_stage_options(body: MaaStageOptionsIn) -> ComboBoxOut:
    """按关卡池和服务器读取插件缓存对应的选项，不将候选列表用作封闭枚举。"""
    service = Plugin.services.require("arknights.stage_info")
    return ComboBoxOut(
        data=[
            ComboBoxItem(**item)
            for item in await service(body.type, server=body.server)
        ]
    )


@router.post("/overview", response_model=MaaStageOverviewOut)
async def get_maa_stage_overview(refresh: bool = False) -> MaaStageOverviewOut:
    """返回插件维护的各区服关卡与活动信息，手动刷新时等待本次远端检查。"""
    service = Plugin.services.require("arknights.stage_overview")
    return MaaStageOverviewOut(data=await service(refresh=refresh))
