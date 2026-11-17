from typing import (
    List,
    Literal,
)

from auto_mas_core.host.models_schema import (
    ComboBoxItem,
    ComboBoxOut,
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


class MaaCopilotSourceIn(BaseModel):
    source: Literal["all", "author", "set", "copilot"] = "all"
    query: str = Field(
        default="", max_length=500, description="作者、作业集或单份作业的编号/分享链接"
    )
    action: Literal["load", "refresh", "status"] = "load"


class MaaCopilotSourceOut(OutBase):
    running: bool = False
    loaded: int = 0
    total: int = 0
    count: int = 0
    updatedAt: int = Field(default=0, description="作业数据或快照的生成时间，Unix 秒")
    downloadedAt: int = Field(
        default=0, description="本机下载或在线同步完成时间，Unix 秒"
    )
    dataSource: Literal["data-center", "github", "copilot", "unknown"] = "unknown"
    available: bool = False
    error: str = ""


class MaaCopilotAuthorsIn(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=100)


class MaaCopilotAnalyzeIn(BaseModel):
    scriptId: str
    userId: str
    bindingKey: str = Field(
        default="",
        max_length=128,
        description="分析预期的森空岛绑定，账号组与角色编号组合",
    )
    source: Literal["all", "author", "set", "copilot"] = "all"
    query: str = Field(default="", max_length=500)
    coverage: int = Field(
        default=90, ge=1, le=100, description="期望覆盖有可解析要求的作业百分比"
    )
    requireModules: bool = True
    ignoreLevelGaps: bool = Field(
        default=False, description="忽略精英阶段已达标干员的等级差距"
    )


class MaaCopilotGoal(BaseModel):
    kind: Literal["elite", "skill", "mastery", "module"]
    target_id: str
    to_level: int


class MaaCopilotOperator(BaseModel):
    operatorId: str
    name: str
    owned: bool
    optional: bool = False
    demand: int = 0
    currentElite: int = 0
    currentLevel: int = 0
    targetElite: int = 0
    targetLevel: int = 0
    manualLevel: bool = False
    goals: List[MaaCopilotGoal] = Field(default_factory=list)


class MaaCopilotAssignment(BaseModel):
    id: int
    title: str
    stage: str
    author: str
    state: Literal["ready", "training", "missing", "unknown"]
    missingOperators: List[str] = Field(default_factory=list)
    missingAlternatives: List[List[str]] = Field(default_factory=list)
    gaps: List[str] = Field(default_factory=list)
    plannedReady: bool = False


class MaaCopilotAnalyzeOut(OutBase):
    bindingKey: str = ""
    total: int = 0
    analyzable: int = 0
    ready: int = 0
    trainable: int = 0
    projectedReady: int = 0
    missing: int = 0
    unknown: int = 0
    stageCount: int = 0
    capturedAt: int = 0
    updatedAt: int = 0
    operators: List[MaaCopilotOperator] = Field(default_factory=list)
    assignments: List[MaaCopilotAssignment] = Field(default_factory=list)


@router.post(
    "/maa/copilot/source",
    tags=["Get"],
    summary="加载或同步作业站公开数据",
    response_model=MaaCopilotSourceOut,
)
async def load_maa_copilot_source(request: MaaCopilotSourceIn) -> MaaCopilotSourceOut:
    import maa_adapter.cultivate.copilot_service as maa_api

    try:
        return MaaCopilotSourceOut(
            **await maa_api.get_copilot_source(
                request.source, request.query, action=request.action
            )
        )
    except ValueError as exc:
        return MaaCopilotSourceOut(code=400, status="error", message=str(exc))


@router.post(
    "/maa/copilot/authors",
    tags=["Get"],
    summary="搜索作业站作者",
    response_model=ComboBoxOut,
)
async def search_maa_copilot_authors(request: MaaCopilotAuthorsIn) -> ComboBoxOut:
    import maa_adapter.cultivate.copilot_service as maa_api

    try:
        entries = await maa_api.search_copilot_authors(request.keyword)
        return ComboBoxOut(data=[ComboBoxItem(**item) for item in entries])
    except Exception:
        logger.warning("作业站作者搜索失败")
        return ComboBoxOut(
            code=400, status="error", message="作者搜索失败，请检查网络后重试", data=[]
        )


@router.post(
    "/maa/copilot/analyze",
    tags=["Get"],
    summary="比较作业练度并建议培养目标（不落库）",
    response_model=MaaCopilotAnalyzeOut,
)
async def analyze_maa_copilot_training(
    request: MaaCopilotAnalyzeIn,
) -> MaaCopilotAnalyzeOut:
    import maa_adapter.cultivate.copilot_service as maa_api

    try:
        result = await maa_api.analyze_copilot_training(
            request.scriptId,
            request.userId,
            binding_key=request.bindingKey,
            source=request.source,
            query=request.query,
            coverage=request.coverage,
            require_modules=request.requireModules,
            ignore_level_gaps=request.ignoreLevelGaps,
        )
        return MaaCopilotAnalyzeOut(**result)
    except ValueError as exc:
        return MaaCopilotAnalyzeOut(code=400, status="error", message=str(exc))
    except Exception:
        logger.opt(exception=True).warning("作业练度分析失败")
        return MaaCopilotAnalyzeOut(
            code=500, status="error", message="作业分析失败，请检查账号绑定和网络后重试"
        )
