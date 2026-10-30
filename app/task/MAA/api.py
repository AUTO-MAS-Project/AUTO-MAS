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
"""脚本管理：MAA 路由与端点专用模型。"""

from typing import (
    Annotated,
    Dict,
    List,
    Literal,
    Optional,
)

from fastapi import APIRouter, Body
from pydantic import (
    BaseModel,
    Field,
)

from app.models.schema import (
    ComboBoxItem,
    ComboBoxOut,
    OutBase,
    ScriptDeleteIn,
    UserDeleteIn,
    UserInBase,
)
from app.utils import get_logger


class CultivatePreviewIn(BaseModel):
    scriptId: str = Field(..., description="脚本ID")
    userId: str = Field(..., description="用户ID")
    targets: str = Field(
        ..., description="养成目标 JSON（与 Task.CultivateTargets 同构）"
    )


class CultivatePreviewItem(BaseModel):
    itemId: str = Field(..., description="物品ID")
    name: str = Field(..., description="物品名称")
    count: int = Field(..., description="需求数量（保有量目标）")
    stage: Optional[str] = Field(
        default=None, description="推荐关卡；刷取计划条目有值，材料需求/不可获取类为空"
    )
    expectedSanity: Optional[float] = Field(
        default=None,
        description="刷取该条目到保有量目标的期望理智；固定产出关不可估算，为空",
    )


class CultivateOperatorProgression(BaseModel):
    """单个目标干员的当前练度（编辑器"当前等级 → 目标等级"展示用）。"""

    operatorId: str = Field(..., description="干员 ID")
    source: str = Field(
        ..., description="练度来源（skland/local/manual）；default 表示无实测数据"
    )
    elite: int = Field(..., description="当前精英化阶段 0-2")
    level: int = Field(..., description="当前干员等级")
    skillLevel: Optional[int] = Field(
        default=None, description="当前普通技能等级 1-7；未观测时为空"
    )
    masteries: Dict[str, int] = Field(
        default_factory=dict, description="当前专精等级（skillId → 0-3）"
    )
    modules: Dict[str, int] = Field(
        default_factory=dict, description="当前模组等级（uniEquipId → 0-3）"
    )


class CultivatePreviewOut(OutBase):
    stages: List[CultivatePreviewItem] = Field(
        ..., description="刷取计划（按推荐关执行的材料条目）"
    )
    demands: List[CultivatePreviewItem] = Field(
        ..., description="全量材料需求（已含合成折算）"
    )
    unobtainable: List[CultivatePreviewItem] = Field(
        ..., description="不可获取材料（需游戏内另行获取）"
    )
    totalExpectedSanity: Optional[float] = Field(
        default=None,
        description="可估算刷取条目的期望理智合计（不含固定产出关）；无可估算条目时为空",
    )
    hasProgression: bool = Field(
        ..., description="练度数据是否可用（本地识别档案或森空岛快照）"
    )
    progressions: List[CultivateOperatorProgression] = Field(
        default_factory=list,
        description="目标干员当前练度；source=default 表示无实测数据（按 0 估算）",
    )
    hasInventory: bool = Field(..., description="是否存在仓库识别档案")


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


class MaaDepotInventoryOut(OutBase):
    data: List[ComboBoxItem] = Field(
        ..., description="库存选项（label=数量字符串，value=物品ID）"
    )
    recognizedAt: Optional[str] = Field(
        None, description="最近识别时间（本地 ISO 格式）；无法确定识别时间时为 None"
    )


class MaaCultivateGoalOptionItem(BaseModel):
    value: str = Field(..., description="目标 ID（专精=skillId，模组=uniEquipId）")
    label: str = Field(..., description="目标名称（模组带分支码）")
    maxLevel: int = Field(default=0, description="可达档位上限（按非空消耗档数）")
    skillIndex: Optional[int] = Field(
        default=None, description="技能原始序号；模组为空"
    )


class MaaCultivateOperatorOptionItem(BaseModel):
    value: str = Field(..., description="干员 ID")
    label: str = Field(..., description="干员名")
    rarity: int = Field(default=0, description="稀有度")
    profession: str = Field(default="", description="职业")
    maxElite: int = Field(
        default=0, description="精英化可达档位上限（1/2/3★ 与上游缺数据者恒 0）"
    )
    maxSkillLevel: int = Field(
        default=0, description="普通技能可达等级上限；0 表示无消耗数据"
    )
    dataMissing: bool = Field(
        default=False,
        description="有精英化体系但需求数据缺失（区别于 1/2/3★ 结构上不设精英化）",
    )
    skills: List[MaaCultivateGoalOptionItem] = Field(
        default_factory=list,
        description="专精目标选项（value=skillId，label=技能名）",
    )
    modules: List[MaaCultivateGoalOptionItem] = Field(
        default_factory=list,
        description="模组目标选项（value=uniEquipId，label=模组名（分支））",
    )


class MaaCultivateOperatorsOut(OutBase):
    data: List[MaaCultivateOperatorOptionItem] = Field(
        default_factory=list, description="干员目录（含目标编辑用名称目录）"
    )


class MaaCultivateImportIn(BaseModel):
    scriptId: str = Field(..., description="脚本ID")
    content: str = Field(..., description="明日方舟工具箱导出至 MAA 的养成目标 JSON")


class MaaCultivateImportSkippedItem(BaseModel):
    error: Literal[
        "format",
        "empty",
        "operator",
        "ambiguous",
        "elite",
        "skill",
        "mastery",
        "unsupported",
    ] = Field(..., description="可本地化的导入错误类型")
    index: int = Field(..., description="跳过条目的序号，从 1 开始")
    name: str = Field(default="", description="跳过条目的干员名称")


class MaaCultivateImportOut(MaaCultivateOperatorsOut):
    targets: str = Field(default="[]", description="转换后的现有养成目标 JSON，不落库")
    skipped: List[MaaCultivateImportSkippedItem] = Field(
        default_factory=list, description="无法导入而跳过的条目，不影响其余目标"
    )
    error: Optional[str] = Field(default=None, description="可本地化的导入错误类型")
    index: Optional[int] = Field(default=None, description="出错条目的序号，从 1 开始")
    name: str = Field(default="", description="出错条目的干员名称")


class MaaDepotStageCandidatesBatchIn(BaseModel):
    script: ScriptDeleteIn
    itemIds: List[Annotated[str, Field(min_length=1, max_length=64)]] = Field(
        ..., min_length=1, max_length=256, description="需要查询候选关卡的物品ID"
    )


class MaaDepotStageCandidatesBatchOut(OutBase):
    data: Dict[str, List[ComboBoxItem]] = Field(
        default_factory=dict, description="按物品ID分组的候选关卡，未找到候选时为空列表"
    )


class UserSetIn(UserInBase):
    userId: str = Field(..., description="用户ID")
    jsonFile: str = Field(..., description="JSON文件路径, 用于导入自定义基建文件")


class UserInfrastPlanSelectIn(BaseModel):
    scriptId: str = Field(..., description="脚本ID")
    userId: str = Field(..., description="用户ID")
    index: int = Field(default=-1, ge=-1, description="基建班次索引（-1=按时段自动）")


class UserInfrastPlanSelectOut(OutBase):
    index: int = Field(..., description="当前基建班次索引（-1=按时段自动）")


class UserInfrastPlanComboxItem(BaseModel):
    label: str = Field(..., description="班次展示名")
    value: str = Field(..., description="班次索引, 即 MAA PlanSelect 值")
    period: Optional[str] = Field(default=None, description="时段文本, 无时段为 None")


class UserInfrastPlanComboxOut(OutBase):
    state: Literal["period", "rotate", "mixed", "empty"] = Field(
        ..., description="排班表时段形态（mixed=时段不一致不可用）"
    )
    data: List[UserInfrastPlanComboxItem] = Field(..., description="班次选项")


class ScriptMirrorCdkIn(BaseModel):
    type: Literal["MAA"] = Field(..., description="脚本类型，决定凭据回退规则")
    cdk: str = Field(
        default="", repr=False, description="待校验的 CDK；留空回退全局 CDK"
    )


class ScriptMirrorCdkData(BaseModel):
    status: str
    expiredTime: int | None = Field(default=None, description="到期时间（unix 秒）")
    usingGlobalCdk: bool = Field(..., description="是否按专用 CDK 留空规则使用全局 CDK")


class ScriptMirrorCdkOut(OutBase):
    data: ScriptMirrorCdkData


router = APIRouter()
logger = get_logger("脚本管理 API")


@router.post(
    "/user/infrastructure",
    tags=["Update"],
    summary="导入基建配置文件",
    response_model=OutBase,
    status_code=200,
)
async def import_infrastructure(user: UserSetIn = Body(...)) -> OutBase:

    try:
        from app.task.MAA import api_service as maa_api

        await maa_api.set_infrastructure(user.scriptId, user.userId, user.jsonFile)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"import_infrastructure失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/user/infrastructure/plan-select",
    tags=["Update"],
    summary="设置基建班次",
    response_model=UserInfrastPlanSelectOut,
    status_code=200,
)
async def set_infrast_plan_select(
    user: UserInfrastPlanSelectIn = Body(...),
) -> UserInfrastPlanSelectOut:
    try:
        from app.task.MAA import api_service as maa_api

        index = await maa_api.set_infrast_plan_select(
            user.scriptId, user.userId, user.index
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"set_infrast_plan_select失败: {type(e).__name__}: {e}"
        )
        return UserInfrastPlanSelectOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", index=-1
        )
    return UserInfrastPlanSelectOut(index=index)


@router.post(
    "/user/infrastructure/plan-select/get",
    tags=["Get"],
    summary="获取当前基建班次",
    response_model=UserInfrastPlanSelectOut,
    status_code=200,
)
async def get_infrast_plan_select(
    user: UserDeleteIn = Body(...),
) -> UserInfrastPlanSelectOut:
    try:
        from app.task.MAA import api_service as maa_api

        index = await maa_api.get_infrast_plan_select(user.scriptId, user.userId)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_infrast_plan_select失败: {type(e).__name__}: {e}"
        )
        return UserInfrastPlanSelectOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", index=-1
        )
    return UserInfrastPlanSelectOut(index=index)


@router.post(
    "/user/combox/infrastructure",
    tags=["Get"],
    summary="用户自定义基建排班可选项",
    response_model=UserInfrastPlanComboxOut,
    status_code=200,
)
async def get_user_combox_infrastructure(
    user: UserDeleteIn = Body(...),
) -> UserInfrastPlanComboxOut:

    try:
        from app.task.MAA import api_service as maa_api

        result = await maa_api.get_user_combox_infrastructure(
            user.scriptId, user.userId
        )
        data = [UserInfrastPlanComboxItem(**item) for item in result["data"]]
        state = result["state"]
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_user_combox_infrastructure失败: {type(e).__name__}: {e}"
        )
        return UserInfrastPlanComboxOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            state="empty",
            data=[],
        )
    return UserInfrastPlanComboxOut(state=state, data=data)


@router.post(
    "/maa/depot/items",
    tags=["Get"],
    summary="MAA 库存保持物品可选项",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_maa_depot_items(script: ScriptDeleteIn = Body(...)) -> ComboBoxOut:

    try:
        from app.task.MAA import api_service as maa_api

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
        from app.task.MAA import api_service as maa_api

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
        from app.task.MAA import api_service as maa_api

        data = await maa_api.get_depot_stage_candidates_batch(
            script_id=request.script.scriptId, item_ids=request.itemIds
        )
        return MaaDepotStageCandidatesBatchOut(data=data)
    except Exception as e:
        return MaaDepotStageCandidatesBatchOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )


@router.post(
    "/maa/depot/inventory",
    tags=["Get"],
    summary="MAA 仓库库存（当前用户档案；label=数量字符串，value=物品ID）",
    response_model=MaaDepotInventoryOut,
    status_code=200,
)
async def get_maa_depot_inventory(
    script: ScriptDeleteIn = Body(...), userId: str = Body(...)
) -> MaaDepotInventoryOut:

    try:
        from app.task.MAA import api_service as maa_api

        raw_data, recognized_at = await maa_api.get_depot_inventory(
            script.scriptId, userId
        )
        data = [ComboBoxItem(**item) for item in raw_data]
    except Exception as e:
        return MaaDepotInventoryOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", data=[]
        )
    return MaaDepotInventoryOut(data=data, recognizedAt=recognized_at)


@router.post(
    "/maa/cultivate/skland/bindings",
    tags=["Get"],
    summary="森空岛绑定角色列表（遍历已配置森空岛凭据的签到账号组，明日方舟）",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_maa_cultivate_skland_bindings() -> ComboBoxOut:

    try:
        from app.task.MAA import api_service as maa_api

        raw_data = await maa_api.get_cultivate_skland_bindings()
        data = [ComboBoxItem(**item) for item in raw_data]
    except Exception as e:
        return ComboBoxOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", data=[]
        )
    return ComboBoxOut(data=data)


@router.post(
    "/maa/cultivate/operators",
    tags=["Get"],
    summary="MAA 干员养成选择器目录（含技能/模组名称目录，稀有度降序）",
    response_model=MaaCultivateOperatorsOut,
    status_code=200,
)
async def get_maa_cultivate_operators(
    script: ScriptDeleteIn = Body(...), userId: str = Body(...)
) -> MaaCultivateOperatorsOut:

    try:
        from app.task.MAA import api_service as maa_api

        raw_data = await maa_api.get_cultivate_operators(script.scriptId, userId)
        data = [MaaCultivateOperatorOptionItem(**item) for item in raw_data]
    except Exception as e:
        return MaaCultivateOperatorsOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", data=[]
        )
    return MaaCultivateOperatorsOut(data=data)


@router.post(
    "/maa/cultivate/refresh",
    tags=["Update"],
    summary="手动刷新 MAA 养成材料数据与干员目录",
    response_model=OutBase,
    status_code=200,
)
async def refresh_maa_cultivate_data(request: ScriptDeleteIn) -> OutBase:
    from app.task.MAA.tools.cultivate.yituliu import YituliuDataError

    try:
        from app.task.MAA import api_service as maa_api

        await maa_api.refresh_cultivate_data(request.scriptId)
        return OutBase()
    except YituliuDataError as e:
        logger.warning(f"养成数据源刷新失败: {e}")
        return OutBase(code=503, status="error", message="养成数据源不可用")
    except OSError as e:
        logger.warning(f"养成数据缓存写入失败: {e}")
        return OutBase(code=507, status="error", message="养成数据缓存写入失败")
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )


@router.post(
    "/maa/cultivate/import",
    tags=["Get"],
    summary="校验并转换 MAA 剪贴板养成目标（不落库）",
    response_model=MaaCultivateImportOut,
    status_code=200,
)
async def parse_maa_cultivate_import(
    request: MaaCultivateImportIn = Body(...),
) -> MaaCultivateImportOut:
    from app.task.MAA import api_service as maa_api
    from app.task.MAA.tools.cultivate import CultivateImportError

    try:
        result = await maa_api.parse_cultivate_import(request.scriptId, request.content)
    except CultivateImportError as exc:
        return MaaCultivateImportOut(
            code=400,
            status="error",
            message="养成目标导入校验失败",
            error=exc.reason,
            index=exc.index,
            name=exc.name,
        )
    except Exception as exc:
        logger.opt(exception=True).warning(f"parse_maa_cultivate_import失败: {exc}")
        return MaaCultivateImportOut(
            code=500, status="error", message="养成导入数据不可用", error="catalog"
        )
    return MaaCultivateImportOut(
        targets=result["targets"],
        data=[MaaCultivateOperatorOptionItem(**item) for item in result["data"]],
        skipped=[MaaCultivateImportSkippedItem(**item) for item in result["skipped"]],
    )


@router.post(
    "/maa/cultivate/preview",
    tags=["Get"],
    summary="MAA 养成计划预览（纯计算不落库）",
    response_model=CultivatePreviewOut,
    status_code=200,
)
async def get_maa_cultivate_preview(
    preview: CultivatePreviewIn = Body(...),
) -> CultivatePreviewOut:

    try:
        from app.task.MAA import api_service as maa_api

        data = await maa_api.get_cultivate_preview(
            preview.scriptId, preview.userId, preview.targets
        )
    except Exception as e:
        return CultivatePreviewOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            stages=[],
            demands=[],
            unobtainable=[],
            progressions=[],
            hasProgression=False,
            hasInventory=False,
        )
    return CultivatePreviewOut(
        stages=data["stages"],
        demands=data["demands"],
        unobtainable=data["unobtainable"],
        totalExpectedSanity=data.get("totalExpectedSanity"),
        progressions=[
            CultivateOperatorProgression(**item)
            for item in data.get("progressions", [])
        ],
        hasProgression=bool(data.get("availability", {}).get("has_progression")),
        hasInventory=bool(data.get("availability", {}).get("has_inventory")),
    )


@router.post(
    "/maa/copilot/source",
    tags=["Get"],
    summary="加载或同步作业站公开数据",
    response_model=MaaCopilotSourceOut,
)
async def load_maa_copilot_source(request: MaaCopilotSourceIn) -> MaaCopilotSourceOut:
    from app.task.MAA import api_service as maa_api

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
    from app.task.MAA import api_service as maa_api

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
    from app.task.MAA import api_service as maa_api

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


@router.post(
    "/mirror-cdk",
    tags=["Get"],
    summary="查询脚本生效的 Mirror 酱 CDK 状态",
    response_model=ScriptMirrorCdkOut,
)
async def query_script_mirror_cdk(payload: ScriptMirrorCdkIn) -> ScriptMirrorCdkOut:
    """校验编辑框草稿；MAA 专用 CDK 留空时按接管规则查询全局 CDK。"""
    from app.task.MAA import api_service as maa_api

    result, using_global = await maa_api.query_mirror_cdk(payload.cdk)
    return ScriptMirrorCdkOut(
        data=ScriptMirrorCdkData(
            status=result.status,
            expiredTime=result.expired_time,
            usingGlobalCdk=using_global,
        )
    )
