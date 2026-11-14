from typing import (
    Dict,
    List,
    Literal,
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


class CultivatePreviewIn(BaseModel):
    scriptId: str = Field(..., description="托管ID")
    userId: str = Field(..., description="账号ID")
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
    scriptId: str = Field(..., description="托管ID")
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


@router.post(
    "/maa/cultivate/skland/bindings",
    tags=["Get"],
    summary="森空岛绑定角色列表（遍历已配置森空岛凭据的签到账号组，明日方舟）",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_maa_cultivate_skland_bindings() -> ComboBoxOut:

    try:
        import maa_adapter.cultivate.editor as maa_api

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
        import maa_adapter.cultivate.editor as maa_api

        raw_data = await maa_api.get_cultivate_operators(script.scriptId, userId)
        data = [
            MaaCultivateOperatorOptionItem.model_validate(item) for item in raw_data
        ]
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
    from maa_adapter.cultivate.yituliu import YituliuDataError

    try:
        import maa_adapter.cultivate.editor as maa_api

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
    import maa_adapter.cultivate.editor as maa_api
    from maa_adapter.cultivate import CultivateImportError

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
        data=[
            MaaCultivateOperatorOptionItem.model_validate(item)
            for item in result["data"]
        ],
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
        import maa_adapter.cultivate.editor as maa_api

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
