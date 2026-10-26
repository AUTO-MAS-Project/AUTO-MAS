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
import uuid
from pathlib import Path
from typing import (
    Annotated,
    Any,
    Dict,
    List,
    Literal,
    Optional,
    Union,
)

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import (
    BaseModel,
    Field,
    model_validator,
)

import app.models.config as _config_models
from app.config.wire import ConfigInput, ConfigPayload, config_contract
from app.core import Config
from app.core import emulator2 as emulator2_service
from app.core.game_calendar import SCRIPT_CALENDAR_GAMES
from app.models.config import BetterGIConfig as RuntimeBetterGIConfig
from app.models.config import MaaEndConfig as RuntimeMaaEndConfig
from app.models.config import OkNteConfig as RuntimeOkNteConfig
from app.models.config import OkwwConfig as RuntimeOkwwConfig
from app.models.config import WhimboxConfig as RuntimeWhimboxConfig
from app.models.schema import (
    ComboBoxItem,
    ComboBoxOut,
    HSRCapabilitiesData,
    HSRCloudLoginData,
    HSRManagedConfigData,
    HSRSRAProfilesData,
    HSRStageOptionsData,
    HSRUpdateData,
    MaaFWAgentEnvPrepareData,
    MaaFWEmbeddedSourceItem,
    MaaFWEmbeddedStatusData,
    MaaFWGamePackageData,
    MaaFWInterfacePreviewData,
    MaaFWMirrorCdkData,
    MaaFWProjectUpdateData,
    MaaFWShellInstanceImportItem,
    MaaFWShellInstanceItem,
    OutBase,
    WebhookDeleteIn,
    WebhookGetIn,
    WebhookInBase,
    WebhookIndexItem,
)
from app.models.schema import (
    WebhookCreateOut as SharedWebhookCreateOut,
)
from app.models.schema import (
    WebhookGetOut as SharedWebhookGetOut,
)
from app.models.schema import (
    WebhookUpdateIn as SharedWebhookUpdateIn,
)
from app.services import ConfigCenterError
from app.services.endfield_launcher import discover_launcher_exe
from app.services.wuthering_waves import resolve_wuthering_waves_process_path
from app.task.MAA.tools.update_credentials import query_takeover_cdk
from app.task.MaaFW.api_service import agent_env as maafw_agent_env_api
from app.task.MaaFW.api_service import embedded as maafw_embedded_api
from app.task.MaaFW.api_service import interface as maafw_interface_api
from app.task.MaaFW.api_service import shell_instances as maafw_shell_instances_api
from app.task.MaaFW.api_service import update as maafw_update_api
from app.task.MSS.api_service import defense_status as mss_defense_status
from app.task.Whimbox.tools.upstream import WheelAssetsConfigSurface
from app.utils import get_logger
from app.utils.io import ConfigCorruptedError

BAAHConfig = ConfigPayload[_config_models.BAAHConfig]
BAAHConfigInput = ConfigInput[_config_models.BAAHConfig]
BAAHUserConfig = ConfigPayload[_config_models.BAAHUserConfig]
BAAHUserConfigInput = ConfigInput[_config_models.BAAHUserConfig]
BetterGIConfig = ConfigPayload[_config_models.BetterGIConfig]
BetterGIConfigInput = ConfigInput[_config_models.BetterGIConfig]
BetterGIUserConfig = ConfigPayload[_config_models.BetterGIUserConfig]
BetterGIUserConfigInput = ConfigInput[_config_models.BetterGIUserConfig]
GeneralConfig = ConfigPayload[_config_models.GeneralConfig]
GeneralConfigInput = ConfigInput[_config_models.GeneralConfig]
GeneralUserConfig = ConfigPayload[_config_models.GeneralUserConfig]
GeneralUserConfigInput = ConfigInput[_config_models.GeneralUserConfig]
HSRConfig = ConfigPayload[_config_models.HSRConfig]
HSRConfigInput = ConfigInput[_config_models.HSRConfig]
HSRUserConfig = ConfigPayload[_config_models.HSRUserConfig]
HSRUserConfigInput = ConfigInput[_config_models.HSRUserConfig]
M9AConfig = ConfigPayload[_config_models.M9AConfig]
M9AConfigInput = ConfigInput[_config_models.M9AConfig]
M9AUserConfig = ConfigPayload[_config_models.M9AUserConfig]
M9AUserConfigInput = ConfigInput[_config_models.M9AUserConfig]
MSSConfig = ConfigPayload[_config_models.MSSConfig]
MSSConfigInput = ConfigInput[_config_models.MSSConfig]
MSSUserConfig = ConfigPayload[_config_models.MSSUserConfig]
MSSUserConfigInput = ConfigInput[_config_models.MSSUserConfig]
MaaConfig = ConfigPayload[_config_models.MaaConfig]
MaaConfigInput = ConfigInput[_config_models.MaaConfig]
MaaEndConfig = ConfigPayload[_config_models.MaaEndConfig]
MaaEndConfigInput = ConfigInput[_config_models.MaaEndConfig]
MaaEndUserConfig = ConfigPayload[_config_models.MaaEndUserConfig]
MaaEndUserConfigInput = ConfigInput[_config_models.MaaEndUserConfig]
MaaFWConfig = ConfigPayload[_config_models.MaaFWConfig]
MaaFWConfigInput = ConfigInput[_config_models.MaaFWConfig]
MaaFWUserConfig = ConfigPayload[_config_models.MaaFWUserConfig]
MaaFWUserConfigInput = ConfigInput[_config_models.MaaFWUserConfig]
MaaUserConfig = ConfigPayload[_config_models.MaaUserConfig]
MaaUserConfigInput = ConfigInput[_config_models.MaaUserConfig]
OkNteConfig = ConfigPayload[_config_models.OkNteConfig]
OkNteConfigInput = ConfigInput[_config_models.OkNteConfig]
OkNteUserConfig = ConfigPayload[_config_models.OkNteUserConfig]
OkNteUserConfigInput = ConfigInput[_config_models.OkNteUserConfig]
OkwwConfig = ConfigPayload[_config_models.OkwwConfig]
OkwwConfigInput = ConfigInput[_config_models.OkwwConfig]
OkwwUserConfig = ConfigPayload[_config_models.OkwwUserConfig]
OkwwUserConfigInput = ConfigInput[_config_models.OkwwUserConfig]
SrcConfig = ConfigPayload[_config_models.SrcConfig]
SrcConfigInput = ConfigInput[_config_models.SrcConfig]
SrcUserConfig = ConfigPayload[_config_models.SrcUserConfig]
SrcUserConfigInput = ConfigInput[_config_models.SrcUserConfig]
Webhook = ConfigPayload[_config_models.Webhook]
WebhookInput = ConfigInput[_config_models.Webhook]
WebhookGetOut = SharedWebhookGetOut[Webhook]
WebhookCreateOut = SharedWebhookCreateOut[Webhook]
WebhookUpdateIn = SharedWebhookUpdateIn[WebhookInput]

WhimboxConfig = ConfigPayload[_config_models.WhimboxConfig]
WhimboxConfigInput = ConfigInput[_config_models.WhimboxConfig]
WhimboxUserConfig = ConfigPayload[_config_models.WhimboxUserConfig]
WhimboxUserConfigInput = ConfigInput[_config_models.WhimboxUserConfig]
ZzzOdConfig = ConfigPayload[_config_models.ZzzOdConfig]
ZzzOdConfigInput = ConfigInput[_config_models.ZzzOdConfig]
ZzzOdUserConfig = ConfigPayload[_config_models.ZzzOdUserConfig]
ZzzOdUserConfigInput = ConfigInput[_config_models.ZzzOdUserConfig]


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


class MssDefenseStatusIn(BaseModel):
    scriptId: str = Field(..., min_length=1, description="MSS 脚本 ID")
    userId: str = Field(..., min_length=1, description="用户 ID")


class MssDefenseStatusData(BaseModel):
    """个人版「灾变防线」这一期的状态：用户页拿它显示「本期未打 / 已打」。"""

    enabled: bool = Field(
        default=False,
        description="个人版总开关（Function.IfPersonalMss）开着吗；没开时用户页连这一块都不渲染",
    )
    period: str = Field(
        default="", description="当前这一期的开始时刻；取不到官网公告时为空"
    )
    known: bool = Field(
        default=False, description="这一期认得出来吗（取不到官网公告时为 false）"
    )
    done: bool = Field(default=False, description="这一期已经打过")
    armed: bool = Field(default=False, description="已经排进队列、在等这一轮的结果")
    failedDays: List[str] = Field(
        default_factory=list, description="这一期编排过但没跑成的日子"
    )
    givenUp: bool = Field(default=False, description="失败日攒够了，这一期不再自动编排")


class MssDefenseStatusOut(OutBase):
    data: MssDefenseStatusData = Field(default_factory=MssDefenseStatusData)


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


class BetterGICustomGroupOut(BaseModel):
    """BetterGI 一条龙自定义配置组（非内置 8 组）"""

    name: str = Field(..., description="配置组名称")
    enabled: bool = Field(..., description="启用状态")


class BetterGICustomGroupsOut(OutBase):
    data: List[BetterGICustomGroupOut] = Field(
        default_factory=list, description="一条龙自定义配置组列表"
    )


class BetterGIOneDragonSettingsOut(OutBase):
    """BetterGI 一条龙设置项（右栏按任务分组展示/编辑）"""

    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="一条龙设置项键值（camelCase，与 BGI 一条龙 JSON 顶层一致）",
    )


class BetterGIOneDragonSettingsIn(BaseModel):
    """BetterGI 一条龙设置项写入请求"""

    scriptId: str = Field(..., description="所属脚本ID")
    userId: str = Field(..., description="所属用户ID")
    configName: str = Field(..., description="一条龙配置名")
    groupName: str = Field(
        default="",
        description="右栏当前编辑的内置任务组名（战斗4项 Plan 路由用；空或非战斗组时不做 Plan 路由）",
    )
    settings: Dict[str, Any] = Field(
        default_factory=dict, description="要覆盖写入的设置项（camelCase 键）"
    )


class BetterGIGlobalDomainSettingsOut(OutBase):
    """BetterGI 全局 config.json 的「秘境刷取配置」段（autoDomainConfig/autoArtifactSalvageConfig）"""

    data: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "秘境刷取配置键值（camelCase 扁平键：specifyResinUse/originalResinUseCount/"
            "condensedResinUseCount/transientResinUseCount/fragileResinUseCount/"
            "autoArtifactSalvage/maxArtifactStar/rewardRecognitionEnabled）"
        ),
    )


class BetterGIGlobalDomainSettingsIn(BaseModel):
    """BetterGI 秘境刷取配置写入请求（per-user 副本；userId 为空时原生来源 BGI 全局 config.json）"""

    scriptId: str = Field(..., description="所属脚本ID")
    userId: Optional[str] = Field(
        default="", description="所属用户ID（空=写 BGI 全局实配）"
    )
    groupName: str = Field(
        default="",
        description="右栏当前编辑的实例组名（形如 自动秘境-3；战斗4项按此做逐实例 Plan 路由，空则回落到基名）",
    )
    settings: Dict[str, Any] = Field(
        default_factory=dict,
        description="要覆盖写入的秘境刷取配置键值（camelCase 扁平键）",
    )


class BetterGIGlobalStygianSettingsOut(OutBase):
    """BetterGI 全局 config.json 的「自动幽境危战」段（autoStygianOnslaughtConfig）"""

    data: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "幽境危战设置键值（camelCase 扁平键：bossNum/fightTeamName/strategyName/"
            "specifyResinUse/originalResinUseCount/condensedResinUseCount/"
            "transientResinUseCount/fragileResinUseCount/autoArtifactSalvage）"
        ),
    )


class BetterGIGlobalStygianSettingsIn(BaseModel):
    """BetterGI 幽境危战设置写入请求（per-user 副本；userId 为空时原生来源 BGI 全局 config.json）"""

    scriptId: str = Field(..., description="所属脚本ID")
    userId: Optional[str] = Field(
        default="", description="所属用户ID（空=写 BGI 全局实配）"
    )
    groupName: str = Field(
        default="",
        description="右栏当前编辑的实例组名（形如 自动幽境危战-3；战斗4项按此做逐实例 Plan 路由，空则回落到基名）",
    )
    settings: Dict[str, Any] = Field(
        default_factory=dict,
        description="要覆盖写入的幽境危战设置键值（camelCase 扁平键）",
    )


class BetterGIDomainCatalogItem(BaseModel):
    """BetterGI 每周秘境可选秘境目录项（来源：官方 tp.json，唯一数据源）"""

    name: str = Field(
        ..., description="秘境名称（与 BGI 传送点/每周秘境 DomainName 一致）"
    )
    region: str = Field(default="", description="所在地区")
    category: str = Field(
        default="",
        description="tp.json 的 domain type（BlessDomain/ForgeryDomain/MasteryDomain）",
    )
    rewards: List[str] = Field(
        default_factory=list,
        description="三档奖励物品名（顺序即 BGI 领奖序号 1/2/3；圣遗物秘境为套装两件）",
    )


class BetterGIDomainCatalogOut(OutBase):
    """BetterGI 每周秘境秘境候选 + 每秘境三档奖励物"""

    data: List[BetterGIDomainCatalogItem] = Field(
        default_factory=list, description="秘境目录列表"
    )
    source: Optional[str] = Field(
        default=None, description="数据来源文件绝对路径（缺省为空）"
    )


class BetterGIScriptGroupDetailOut(OutBase):
    """BetterGI 配置组 json 详情（per-user 副本 → BGI 实配）"""

    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="配置组 json 内容（含 name/index/config/projects，projects 为执行顺序）",
    )


class BetterGIScriptGroupSaveIn(BaseModel):
    """BetterGI 配置组 json 写入请求（保存到 per-user 副本，不触碰 BGI 同名实配）"""

    scriptId: str = Field(..., description="所属脚本ID")
    userId: str = Field(..., description="所属用户ID")
    name: str = Field(..., description="配置组名（文件名）")
    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="要保存的完整配置组 json（projects 数组为新顺序与各项目设置）",
    )


class BetterGIScriptSettingsUiOut(OutBase):
    """BetterGI 某 JsScript 脚本目录 settings.json 的 UI 定义（双击项目设置弹窗渲染用）"""

    data: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="settings.json UI 定义数组（name/type/label/options/default）",
    )


class BetterGIScriptReadmeOut(OutBase):
    """BetterGI 某 JsScript 脚本目录的 README 内容（双击弹窗「脚本说明」标签展示用）"""

    data: str = Field(default="", description="README 纯文本内容（缺失时为空字符串）")


class BetterGIPathingNode(BaseModel):
    """BetterGI AutoPathing 目录树节点"""

    name: str = Field(..., description="目录名")
    dirs: List["BetterGIPathingNode"] = Field(
        default_factory=list, description="子目录"
    )
    files: List[str] = Field(
        default_factory=list, description="该目录下路径文件名(不含 .json)"
    )


class BetterGIPathingTreeOut(OutBase):
    """BetterGI 地图追踪目录树（{RootPath}/User/AutoPathing 的递归结构）"""

    root: Optional[str] = Field(default=None, description="AutoPathing 绝对目录")
    dirs: List[BetterGIPathingNode] = Field(
        default_factory=list, description="顶层目录树"
    )


class BetterGIScriptDirsOut(OutBase):
    """BetterGI 常用目录与可执行文件绝对路径"""

    repoDir: Optional[str] = Field(default=None, description="脚本仓库检出目录")
    jsScriptDir: Optional[str] = Field(default=None, description="JS 脚本目录")
    autoPathingDir: Optional[str] = Field(default=None, description="地图追踪任务目录")
    oneDragonDir: Optional[str] = Field(default=None, description="一条龙配置目录")
    scriptGroupDir: Optional[str] = Field(default=None, description="配置组目录")
    keyMouseScriptDir: Optional[str] = Field(
        default=None, description="键鼠脚本（录制）目录"
    )
    autoFightDir: Optional[str] = Field(
        default=None,
        description="自动战斗策略目录（User/AutoFight，*.txt / *.json 各算一份策略）",
    )
    exePath: Optional[str] = Field(default=None, description="BetterGI 主程序路径")


class ZzzOdInstanceOut(BaseModel):
    """zzz-od 实例（账号）信息"""

    idx: int = Field(..., description="实例下标（config/{idx:02d} 目录）")
    name: str = Field(..., description="实例名称")
    active: bool = Field(..., description="是否为当前活跃实例")
    active_in_od: bool = Field(..., description="是否参与「全部实例」模式的一条龙")
    force_login_before_run: bool = Field(
        default=False,
        description="运行前切换账号（一条龙原生能力：运行到该实例前强制登录其账号）",
    )


class ZzzOdInstancesOut(OutBase):
    data: List[ZzzOdInstanceOut] = Field(..., description="实例列表")


class ZzzOdInstanceAddIn(BaseModel):
    """直控：新建一条龙实例（分配最小空闲槽并注册）"""

    scriptId: str = Field(..., description="所属脚本ID")
    name: str = Field(..., description="实例名称（必填，创建后可在重命名中修改）")


class ZzzOdInstanceRenameIn(BaseModel):
    """直控：重命名实例（只改注册表 name，实例目录不变）"""

    scriptId: str = Field(..., description="所属脚本ID")
    instanceIdx: int = Field(..., description="目标实例下标")
    name: str = Field(..., description="新实例名称")


class ZzzOdInstanceFlagIn(BaseModel):
    """直控：切换实例是否参与「全部实例」运行模式（active_in_od）"""

    scriptId: str = Field(..., description="所属脚本ID")
    instanceIdx: int = Field(..., description="目标实例下标")
    activeInOd: bool = Field(..., description="是否参与「全部实例」模式")


class ZzzOdInstanceActiveIn(BaseModel):
    """直控：把所选实例设为当前活跃（「仅运行当前」运行的就是它）"""

    scriptId: str = Field(..., description="所属脚本ID")
    instanceIdx: int = Field(..., description="目标实例下标")


class ZzzOdInstanceForceLoginIn(BaseModel):
    """直控：切换实例「运行前切换账号」（一条龙原生能力，MAS 不干涉）"""

    scriptId: str = Field(..., description="所属脚本ID")
    instanceIdx: int = Field(..., description="目标实例下标")
    forceLogin: bool = Field(..., description="是否开启运行前切换账号")


class ZzzOdInstanceRunModeIn(BaseModel):
    """直控：设置运行实例（one_dragon.yml 全局 instance_run，与编辑所选实例无关）"""

    scriptId: str = Field(..., description="所属脚本ID")
    instanceRun: str = Field(
        ...,
        description="运行实例取值（仅运行当前/全部实例；后端白名单校验，非法取值拒绝）",
    )


class ZzzOdInstanceDeleteIn(BaseModel):
    """直控：删除实例（注册表条目 + 实例目录，受 MAS 绑定槽保护）"""

    scriptId: str = Field(..., description="所属脚本ID")
    instanceIdx: int = Field(..., description="目标实例下标")


class ZzzOdSlotOwnerOut(BaseModel):
    """实例槽的 MAS 归属（哪个脚本的哪个用户占着这个号）"""

    scriptId: str = Field(..., description="所属脚本ID")
    userId: str = Field(..., description="用户ID（恢复槽时用它指认目标用户）")
    scriptName: str = Field(..., description="所属脚本名称")
    userName: str = Field(..., description="用户名称")
    base: str = Field(
        ..., description="该用户的 base 来源（shared/independent/native）"
    )


class ZzzOdSlotOut(BaseModel):
    """实例槽总览行（原生实例 / MAS 绑定槽 / 无主残留）"""

    idx: int = Field(..., description="槽下标（config/{idx:02d}）")
    kind: Literal["native", "mas", "orphan"] = Field(
        ...,
        description="槽类别（native=一条龙原生实例 / mas=有 MAS 用户绑定 / orphan=无主残留）",
    )
    has_dir: bool = Field(
        ..., description="盘上是否已有该槽目录（只配了用户没跑过的槽没有目录）"
    )
    size: int = Field(default=0, description="槽目录占用字节数（无目录为 0）")
    owners: List[ZzzOdSlotOwnerOut] = Field(
        default_factory=list, description="绑定该槽的 MAS 用户（可为多个脚本）"
    )


class ZzzOdSlotsOut(OutBase):
    data: List[ZzzOdSlotOut] = Field(..., description="实例槽总览")


class ZzzOdSlotCleanIn(BaseModel):
    """手动清理无主实例槽（先归档进回收池再删目录）"""

    scriptId: str = Field(..., description="所属脚本ID")


class ZzzOdSlotCleanOut(OutBase):
    data: List[int] = Field(..., description="实际回收的槽下标")


class ZzzOdRecycleEntryOut(BaseModel):
    """回收池条目（槽内容或该槽 MAS 备份池的一份快照）"""

    slot: int = Field(..., description="槽下标")
    kind: Literal["slot", "mas"] = Field(
        ..., description="条目类别（slot=槽目录快照 / mas=MAS 备份池快照）"
    )
    ts: str = Field(..., description="快照时间戳（归档目录名）")
    files: int = Field(..., description="快照内文件数")
    size: int = Field(..., description="快照占用字节数")
    path: str = Field(..., description="归档目录的绝对路径（可在文件管理器打开）")


class ZzzOdRecycleOut(OutBase):
    data: List[ZzzOdRecycleEntryOut] = Field(..., description="回收池条目")


class ZzzOdRecycleClearIn(BaseModel):
    """清空实例槽回收池（只清 recycle 池，不碰配置恢复池）"""

    scriptId: str = Field(..., description="所属脚本ID")


class ZzzOdRecycleClearOut(OutBase):
    data: int = Field(..., description="删除的条目数")


class ZzzOdRecycleRestoreIn(BaseModel):
    """把回收池里的一条槽快照恢复给某个 MAS 用户（现有用户或新建用户）"""

    scriptId: str = Field(..., description="所属脚本ID")
    slot: int = Field(..., description="快照所属槽下标（回收条目的槽号）")
    ts: str = Field(..., description="快照时间戳")
    targetUser: str | None = Field(
        default=None, description="恢复给该用户的绑定槽（现有用户 uid）"
    )
    newUserName: str | None = Field(
        default=None, description="新建一个用户并把内容恢复到它的槽（用户名称）"
    )


class ZzzOdCatalogItemOut(BaseModel):
    """一条龙任务目录项（静态解析应用注册信息）"""

    app_id: str = Field(..., description="应用ID")
    app_name: str = Field(..., description="应用中文名")
    default_group: bool = Field(..., description="是否为 zzz-od 默认一条龙任务")
    configurable: bool = Field(
        default=False, description="是否支持在 MAS 侧直接配置（任务卡片 ⚙ 弹出设置）"
    )
    jump: bool = Field(
        default=False,
        description="是否提供跳转一条龙主界面配置（复杂配置引导进原生 GUI）",
    )
    priority: int = Field(..., description="原生排序权重（小者在前）")


class ZzzOdCatalogOut(OutBase):
    data: List[ZzzOdCatalogItemOut] = Field(..., description="任务目录")


class ZzzOdAppConfigFieldOut(BaseModel):
    """任务级配置字段（元数据 + 当前值）

    type 决定前端渲染方式：select 下拉 / bool 开关 / number 数字 /
    plan_list 计划列表（columns 行内字段元数据 + newItem 新增行默认值）。
    """

    field: str = Field(..., description="配置字段名（app yml 中的键）")
    title: str = Field(..., description="展示标题")
    type: str = Field(
        default="select", description="字段类型：select/bool/number/team/plan_list"
    )
    value: Optional[Any] = Field(
        default=None, description="当前值（plan_list 为计划列表）"
    )
    options: List[ComboBoxItem] = Field(default_factory=list, description="可选项列表")
    columns: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="plan_list 行内字段元数据（field/title/type/options/showWhen；showWhen 为条件 dict 或条件列表，条件含 not 取反）",
    )
    newItem: Optional[Dict[str, Any]] = Field(
        default=None, description="plan_list 新增行的默认值"
    )


class ZzzOdAppConfigOut(OutBase):
    appId: str = Field(..., description="应用ID")
    fields: List[ZzzOdAppConfigFieldOut] = Field(..., description="配置字段列表")


class ZzzOdMissionNameOut(BaseModel):
    """副本字典关卡项"""

    name: str = Field(..., description="关卡名（配置取值）")
    display: str = Field(..., description="关卡展示名")


class ZzzOdMissionTypeOut(BaseModel):
    """副本字典类型项"""

    name: str = Field(..., description="类型名（配置取值）")
    display: str = Field(..., description="类型展示名")
    missions: List[ZzzOdMissionNameOut] = Field(
        default_factory=list, description="关卡列表"
    )


class ZzzOdTrainCategoryOut(BaseModel):
    """「训练」tab 副本分类（体力刷本/恶名狩猎级联选项）"""

    name: str = Field(..., description="分类名（配置取值）")
    label: str = Field(..., description="分类展示名")
    mission_types: List[ZzzOdMissionTypeOut] = Field(
        default_factory=list, description="类型列表"
    )


class ZzzOdTaskOptionsOut(OutBase):
    """任务计划的动态选项（静态读取安装目录，与一条龙原生 GUI 同源）"""

    appId: str = Field(..., description="应用ID")
    trainCategories: List[ZzzOdTrainCategoryOut] = Field(
        default_factory=list, description="「训练」tab 副本级联树"
    )
    lostVoidMissions: List[str] = Field(
        default_factory=list, description="迷失之地图层列表"
    )
    autoBattle: List[ComboBoxItem] = Field(
        default_factory=list, description="配队方案选项"
    )
    challenge: List[ComboBoxItem] = Field(
        default_factory=list, description="迷失之地挑战配置选项"
    )


class ZzzOdAppConfigSaveIn(BaseModel):
    """保存任务级配置（字段白名单校验后写入绑定槽；直控可指定原生实例）"""

    scriptId: str = Field(..., description="所属脚本ID")
    userId: str = Field(..., description="目标用户ID")
    appId: str = Field(..., description="应用ID")
    values: Dict[str, Any] = Field(
        ..., description="字段名 → 值（plan_list 为计划列表）"
    )
    instanceIdx: Optional[int] = Field(
        default=None,
        description="直控模式：直接写入的原生实例下标（缺省写入用户绑定槽）",
    )


class ZzzOdTeamItemOut(BaseModel):
    """预备编队条目（team.yml；成员为游戏内识别结果，MAS 不编辑）"""

    idx: int = Field(..., description="编队在列表中的下标")
    name: str = Field(..., description="编队名称（与游戏内编队名一致）")
    autoBattle: str = Field(..., description="绑定的配队方案（自动战斗配置名）")
    agents: List[str] = Field(default_factory=list, description="成员代理人ID列表")


class ZzzOdTeamsOut(OutBase):
    """预备编队列表 + 配队方案/代理人选项"""

    teams: List[ZzzOdTeamItemOut] = Field(..., description="编队列表（固定 20 个）")
    autoBattle: List[ComboBoxItem] = Field(..., description="配队方案选项")
    agentOptions: List[ComboBoxItem] = Field(
        default_factory=list, description="代理人选项（label=名称，value=agent_id）"
    )


class ZzzOdTeamsSaveIn(BaseModel):
    """整表保存预备编队（名称 + 绑定配队方案 + 成员 agent_id_list）"""

    scriptId: str = Field(..., description="所属脚本ID")
    userId: str = Field(..., description="目标用户ID")
    teams: List[Dict[str, Any]] = Field(
        ..., description="编队列表（name/autoBattle/agent_id_list）"
    )
    instanceIdx: Optional[int] = Field(
        default=None,
        description="直控模式：直接写入的原生实例下标（缺省写入用户绑定槽）",
    )


class ZzzOdTeamsSaveOut(OutBase):
    """保存后的编队列表"""

    teams: List[ZzzOdTeamItemOut] = Field(..., description="编队列表")


class ConfigBackupItemOut(BaseModel):
    """配置备份条目"""

    time: str = Field(..., description="备份时间戳（目录名，如 20260910-104500）")
    base: Optional[str] = Field(
        default=None,
        description="备份时点的 base 来源（shared/independent/native）；无标注（旧版备份或未声明来源）为 null",
    )


class ConfigBackupListOut(OutBase):
    data: List[ConfigBackupItemOut] = Field(..., description="备份列表（时间倒序）")
    base: Optional[str] = Field(
        default=None,
        description="当前 base 来源（shared/independent/native）；无来源概念（非 base 专项）为 null",
    )


class ConfigBackupRestoreIn(BaseModel):
    """把指定备份恢复到目标位置（target 取值由专项池定义）"""

    scriptId: str = Field(..., description="所属脚本ID")
    userId: str = Field(..., description="目标用户ID")
    time: str = Field(..., description="备份时间戳")
    target: str = Field(
        ...,
        description="恢复目标（如 zzz-od 的 mas/onedragon、ok-nte 的 mas/native）；非法值返回 400",
    )
    force: bool = Field(
        default=False,
        description="源配置损坏时是否强制恢复（False 时返回 409 由前端二次确认，True 跳过损坏文件相关的保护步骤）",
    )


class ConfigBackupRestoreOut(OutBase):
    target: str = Field(..., description="实际执行的恢复目标")


class ConfigBackupEnsureIn(BaseModel):
    """按需归档目标池当前配置（编辑界面进入/退出时机，指纹去重）"""

    scriptId: str = Field(..., description="所属脚本ID")
    userId: str = Field(..., description="目标用户ID")
    target: str = Field(..., description="归档目标（取值由专项池定义）")


class ConfigBackupEnsureOut(OutBase):
    created: bool = Field(
        ..., description="本次是否新建了归档（False=指纹无变化跳过或无可归档内容）"
    )
    time: str = Field(..., description="最新备份时间戳（无任何备份为空串）")


class ConfigBackupPreviewOut(OutBase):
    """备份配置摘要（预览用，纯读不恢复；载荷结构由专项定义）"""

    time: str = Field(..., description="备份时间戳")
    target: str = Field(..., description="备份类别")
    data: dict = Field(
        ...,
        description="专项预览载荷（如 zzz-od 的 info/account/tasks/instances 或 ok-nte 的 files）",
    )


class ConfigBackupFileOut(OutBase):
    """备份内文本文件内容（只读；路径限归档内相对路径，防穿越）"""

    time: str = Field(..., description="备份时间戳")
    target: str = Field(..., description="备份类别")
    path: str = Field(..., description="归档内相对路径（如 M7A/config.yaml）")
    size: int = Field(..., description="文件字节数")
    content: str = Field(
        ...,
        description="文本内容（utf-8 兼容 BOM 读取，无法解码部分以替换符呈现；超出大小上限返回 400）",
    )


class ZzzOdNativeAccountField(BaseModel):
    """直控编辑的账号字段（强绑定 zzz-od 原生 game_account.yml）。"""

    key: str = Field(..., description="game_account.yml 字段名")
    title: str = Field(..., description="展示标题")
    value: Optional[str] = Field(default=None, description="当前值（读自实例原生配置）")
    options: List[ComboBoxItem] = Field(
        default_factory=list, description="可选项列表（空=自由输入）"
    )


class ZzzOdNativeLaunchArgs(BaseModel):
    """直控编辑的一条龙游戏启动参数（强绑定 zzz-od 原生 game.yml）。"""

    launch_argument: bool = Field(
        ..., description="启动参数总开关（关闭时一条龙启动游戏不带任何参数）"
    )
    screen_size: Literal["1920x1080", "2560x1440", "3840x2160"] = Field(
        ..., description="窗口尺寸"
    )
    full_screen: Literal["0", "1"] = Field(..., description="全屏模式：0=窗口化 1=全屏")
    popup_window: bool = Field(..., description="无边框窗口（-popupwindow）")
    dx12: bool = Field(
        ..., description="DX12 启动（写回时把 -use-d3d12 合并进高级参数）"
    )
    monitor: Literal["1", "2", "3", "4"] = Field(..., description="显示器序号")
    launch_argument_advance: str = Field(
        ..., description="高级参数（原样透传给一条龙拼接，上游不解析）"
    )


class ZzzOdNativeTaskOut(BaseModel):
    """原生来源任务编排条目（原生 app_list 与目录合并后的可选项）。"""

    app_id: str = Field(..., description="应用ID")
    app_name: str = Field(..., description="应用中文名")
    enabled: bool = Field(..., description="是否启用（原生编排状态）")
    default_group: bool = Field(..., description="是否为 zzz-od 默认一条龙任务")
    configurable: bool = Field(
        default=False, description="是否支持在 MAS 侧直接配置（任务卡片 ⚙ 弹出设置）"
    )
    jump: bool = Field(
        default=False,
        description="是否提供跳转一条龙主界面配置（复杂配置引导进原生 GUI）",
    )
    priority: int = Field(..., description="原生排序权重（小者在前）")


class ZzzOdNativeConfigOut(OutBase):
    """直控模式：所选实例的完整原生配置（账号字段 + 任务编排 + 运行实例）。"""

    instanceIdx: int = Field(..., description="当前选择的实例下标")
    instanceName: str = Field(..., description="实例名称")
    account: List[ZzzOdNativeAccountField] = Field(
        ..., description="账号配置字段（game_account.yml）"
    )
    tasks: List[ZzzOdNativeTaskOut] = Field(
        ..., description="任务编排（app_id/enabled/顺序，与目录合并后的可选项）"
    )
    instanceRun: str = Field(
        ...,
        description="运行实例（one_dragon.yml instance_run 原值：仅运行当前/全部实例）",
    )
    afterDone: str = Field(
        ...,
        description="游戏结束后操作（one_dragon.yml after_done 原值：无/关闭游戏/关机）",
    )
    launchArgs: Optional[ZzzOdNativeLaunchArgs] = Field(
        default=None, description="游戏启动参数（game.yml，缺失字段合并上游默认值）"
    )


class ZzzOdNativeTaskIn(BaseModel):
    """原生来源任务编排条目（保存用：app_id + 启用状态）。"""

    app_id: str = Field(..., description="应用ID")
    enabled: bool = Field(..., description="是否启用")


class ZzzOdNativeConfigIn(BaseModel):
    """直控模式：保存所选实例的原生配置（可选增量，缺省字段不写回）。"""

    scriptId: str = Field(..., description="所属脚本ID")
    instanceIdx: int = Field(..., description="目标实例下标（写入其原生配置）")
    account: Optional[Dict[str, str]] = Field(
        default=None, description="账号字段名 → 值（白名单过滤；缺省不写回）"
    )
    tasks: Optional[List[ZzzOdNativeTaskIn]] = Field(
        default=None,
        description="任务编排（顺序即执行顺序；缺省不写回）",
    )
    instanceRun: Optional[str] = Field(
        default=None,
        description="运行实例（仅运行当前/全部实例，白名单校验后写回 one_dragon.yml；缺省不写回）",
    )
    afterDone: Optional[str] = Field(
        default=None,
        description="游戏结束后操作（无/关闭游戏/关机，白名单校验后写回 one_dragon.yml；缺省不写回）",
    )
    launchArgs: Optional[ZzzOdNativeLaunchArgs] = Field(
        default=None, description="游戏启动参数（缺省不写回）"
    )


class ZzzOdLauncherOut(OutBase):
    """ZZZ-OD 启动器可用性（独立配置侧切换原始/集成启动器用）"""

    original_available: bool = Field(
        ..., description="原始启动器（OneDragon-Launcher.exe）是否已安装"
    )
    integrated_available: bool = Field(
        ..., description="集成启动器（OneDragon-RuntimeLauncher.exe）是否已安装"
    )


class ZzzOdImportIn(BaseModel):
    """基于一条龙已有实例快速生成当前用户配置（覆盖本用户账号与任务编排）。"""

    scriptId: str = Field(..., description="所属脚本ID")
    userId: str = Field(..., description="目标用户ID（独立的用户级配置）")
    instanceIdx: int = Field(
        ..., description="来源母版实例下标（读取该实例的账号信息与已启用任务编排）"
    )


class ZzzOdImportOut(OutBase):
    """导入结果：来源实例的账号字段与已启用任务编排已写入本用户，前端随后重新拉取用户数据。"""

    instanceIdx: int = Field(..., description="来源实例下标（失败为 -1）")
    instanceName: str = Field(..., description="来源实例名称")
    importedAccountCount: int = Field(
        ..., description="本次回填的账号字段数（仅非空值）"
    )
    importedTaskCount: int = Field(..., description="本次导入的已启用任务数")
    slot: int = Field(
        ..., description="用户绑定槽 idx（未绑定时 -1，此时无槽内容可备份）"
    )


class MaaEndEssenceTargetGroup(BaseModel):
    value: str = Field(..., description="武器类型标识")
    label: str = Field(..., description="武器类型展示名")
    options: List[ComboBoxItem] = Field(..., description="该类型可选武器")


class MaaEndAutoCollectGroup(BaseModel):
    value: str = Field(..., description="上游路线选项名")
    label: str = Field(..., description="采集分类展示名")
    region: str = Field(..., description="上游地区开关名，旧版为空")
    regionLabel: str = Field(..., description="地区展示名")
    configKey: Literal["AutoCollectRoutes", "AutoCollectCommonRoutes"] = Field(
        ..., description="用户路线配置字段"
    )
    options: List[ComboBoxItem] = Field(..., description="该分类的动态路线")
    defaultCases: list[str] = Field(..., description="上游默认路线")


class MaaEndLauncherPathOut(OutBase):
    """MaaEnd 启动器路径识别结果（供前端自动识别与落盘）"""

    launcher_path: str = Field(
        ..., description="由游戏客户端路径识别到的启动器 Launcher.exe 完整路径"
    )


class MaaEndInventoryOptions(BaseModel):
    description: str = Field(..., description="上游库存目标填写说明")
    inputs: list[ComboBoxItem] = Field(..., description="上游库存目标输入字段")
    claimModes: list[ComboBoxItem] = Field(..., description="上游库存任务领取方式")


class MaaEndOptionsOut(OutBase):
    inventory: MaaEndInventoryOptions | None = Field(
        default=None, description="上游库存目标选项，旧版不支持时为空"
    )
    launchGameControllers: list[str] = Field(
        default_factory=list, description="支持 MaaEnd 原生启动的控制器"
    )
    gameSettingControllers: list[str] = Field(
        default_factory=list, description="支持独立游戏显示设置的控制器"
    )
    projectName: str = Field(default="mxu", description="MaaEnd 资源声明的项目名称")
    projectVersion: str = Field(default="", description="MaaEnd 资源声明的项目版本")
    autoCollectGroups: List[MaaEndAutoCollectGroup] = Field(
        default_factory=list, description="MaaEnd 自动采集地区与分类"
    )
    originalResolution: Optional[str] = Field(
        default=None, description="从游戏 Unity 注册表读取的原始分辨率"
    )
    originalDisplayType: Optional[Literal["Window", "Fullscreen"]] = Field(
        default=None, description="从游戏注册表读取的原始显示模式"
    )
    controllers: List[ComboBoxItem] = Field(..., description="MaaEnd 控制器选项")
    controllerTypes: dict[str, str] = Field(..., description="控制器协议类型映射")
    essenceLocations: List[ComboBoxItem] = Field(
        ..., description="MaaEnd 基质刷取地点选项"
    )
    essenceMenus: List[ComboBoxItem] = Field(..., description="MaaEnd 基质刷取模式选项")
    essenceTargetWeaponGroups: List[MaaEndEssenceTargetGroup] = Field(
        ..., description="MaaEnd 基质目标武器分组"
    )


class ScriptIndexItem(BaseModel):
    uid: str = Field(..., description="唯一标识符")
    type: Literal[
        "MaaConfig",
        "GeneralConfig",
        "OkwwConfig",
        "OkNteConfig",
        "SrcConfig",
        "MaaEndConfig",
        "M9AConfig",
        "MaaFWConfig",
        "HSRConfig",
        "BetterGIConfig",
        "ZzzOdConfig",
        "BAAHConfig",
        "WhimboxConfig",
        "MSSConfig",
    ] = Field(..., description="配置类型")

    activityGame: str | None = Field(
        default=None, description="对应的游戏活动标识，无游戏归属时为空"
    )


class UserIndexItem(BaseModel):
    uid: str = Field(..., description="唯一标识符")
    type: Literal[
        "MaaUserConfig",
        "GeneralUserConfig",
        "OkwwUserConfig",
        "OkNteUserConfig",
        "SrcUserConfig",
        "MaaEndUserConfig",
        "M9AUserConfig",
        "MaaFWUserConfig",
        "HSRUserConfig",
        "BetterGIUserConfig",
        "ZzzOdUserConfig",
        "BAAHUserConfig",
        "WhimboxUserConfig",
        "MSSUserConfig",
    ] = Field(..., description="配置类型")


class BetterGIGameInfoOut(OutBase):
    """BetterGI 游戏客户端信息（用户页透传展示）"""

    installPath: Optional[str] = Field(
        default=None, description="生效游戏路径（用户级优先，否则 BGI 全局配置）"
    )
    globalPath: Optional[str] = Field(
        default=None, description="BetterGI 全局配置的游戏路径原值"
    )
    channel: Optional[Literal["官服", "B服", "国际服"]] = Field(
        default=None, description="识别到的客户端渠道，无法识别为 null"
    )
    source: Optional[Literal["用户", "全局"]] = Field(
        default=None, description="生效路径来源"
    )


class OkwwClientPathOut(OutBase):
    """OK-WW 客户端路径解码结果（仅用于前端展示）"""

    client_path: str = Field(..., description="解码得到的鸣潮客户端 exe 完整路径")


class WhimboxTaskCatalogItem(BaseModel):
    """任务目录条目：一条龙步骤开关（上游三件套机械转换）"""

    key: str = Field(default=..., description="上游配置键")
    display: str = Field(default=..., description="显示名（上游模板 description）")
    section: str = Field(default=..., description="上游配置节")


class WhimboxOptionCatalogItem(BaseModel):
    """任务目录条目：一条龙目标/参数字段（上游三件套机械转换）"""

    key: str = Field(default=..., description="上游配置键")
    display: str = Field(default=..., description="显示名（上游模板 description）")
    section: str = Field(default=..., description="上游配置节")
    field_type: str = Field(
        default=..., description="控件类型：bool/int/select/multi_select/text"
    )
    options: List[str] = Field(default_factory=list, description="值域候选")
    default: Optional[Union[bool, int, float, str, List[str]]] = Field(
        default=None, description="上游模板默认值（布尔语义已归一为 bool）"
    )


class WhimboxTaskCatalogData(BaseModel):
    """任务目录数据：步骤开关 + 参数字段 + 上游版本提示"""

    steps: List[WhimboxTaskCatalogItem] = Field(
        default_factory=list, description="一条龙步骤开关（键集与顺序来自上游模板）"
    )
    options: List[WhimboxOptionCatalogItem] = Field(
        default_factory=list, description="一条龙目标/参数字段"
    )
    upstream_version: str = Field(default="", description="奇想盒后端版本（dist-info）")


class WhimboxTaskCatalogOut(OutBase):
    """任务目录响应"""

    data: WhimboxTaskCatalogData = Field(default_factory=WhimboxTaskCatalogData)


class HSRStageOptionsOut(OutBase):
    data: Optional[HSRStageOptionsData] = Field(
        default=None, description="HSR 体力副本动态选项"
    )


class HSRCapabilitiesOut(OutBase):
    data: Optional[HSRCapabilitiesData] = Field(default=None, description="HSR 能力")


class HSRUpdateIn(BaseModel):
    scriptId: str = Field(..., description="HSR 脚本配置 ID")
    engine: Literal["M7A", "SRA"] = Field(..., description="要操作的外部脚本引擎")
    action: Literal["check", "apply"] = Field(
        default="check", description="check 只查版本；apply 查完就装"
    )


class HSRUpdateOut(OutBase):
    data: Optional[HSRUpdateData] = Field(default=None, description="更新结果")


class HSRCloudLoginIn(BaseModel):
    scriptId: str = Field(..., description="HSR 脚本配置 ID")
    userId: str = Field(..., description="要登录云·星穹铁道的用户 ID")


class HSRCloudLoginOut(OutBase):
    data: Optional[HSRCloudLoginData] = Field(default=None, description="登录结果")


class HSRManagedConfigOut(OutBase):
    data: Optional[HSRManagedConfigData] = Field(default=None, description="托管配置")


class HSRSRAProfilesOut(OutBase):
    data: Optional[HSRSRAProfilesData] = Field(
        default=None, description="SRA 配置档案列表"
    )


class MaaFWInterfacePreviewIn(BaseModel):
    path: str = Field(default="", description="MaaFW 项目根目录，应包含 interface.json")
    scriptId: Optional[str] = Field(
        default=None,
        description="给了脚本 ID 就按脚本解析有效根（内嵌副本优先），忽略 path",
    )


class MaaFWGamePackageIn(BaseModel):
    path: str = Field(..., description="MaaFW 项目根目录，应包含 interface.json")
    resource: str = Field(..., description="要按哪个 resource 的 pipeline 推断包名")
    scriptId: Optional[str] = Field(
        default=None,
        description="MaaFW 脚本 ID；给出时按脚本解析有效根（内嵌脚本读副本），path 只兜底",
    )


class MaaFWGamePackageOut(OutBase):
    data: Optional[MaaFWGamePackageData] = Field(
        default=None, description="包名推断结果"
    )


class MaaFWInterfacePreviewOut(OutBase):
    data: Optional[MaaFWInterfacePreviewData] = Field(
        default=None, description="MaaFW interface 预览数据"
    )


class MaaFWEmbeddedIn(BaseModel):
    scriptId: str = Field(..., min_length=1, description="MFW 脚本 ID")


class MaaFWEmbeddedReimportIn(BaseModel):
    scriptId: str = Field(..., min_length=1, description="MFW 脚本 ID")
    sourcePath: str = Field(
        ..., min_length=1, description="新的来源目录，会写入 Info.Path"
    )


class MaaFWEmbeddedCloneIn(BaseModel):
    scriptId: str = Field(
        ..., min_length=1, description="要建副本的 MFW 脚本 ID（新脚本）"
    )
    sourceScriptId: str = Field(
        ...,
        min_length=1,
        description="从这个 MFW 脚本的副本克隆（同一项目再建一个脚本）",
    )


class MaaFWEmbeddedSourcesIn(BaseModel):
    scriptId: Optional[str] = Field(
        default=None,
        description="要排除的脚本 ID（给已有脚本列候选时传；新建脚本对话框里还没有脚本，不传）",
    )


class MaaFWEmbeddedSourcesOut(OutBase):
    data: List[MaaFWEmbeddedSourceItem] = Field(
        default_factory=list, description="有健康副本的其它 MFW 脚本"
    )


class MaaFWEmbeddedStatusOut(OutBase):
    data: Optional[MaaFWEmbeddedStatusData] = Field(
        default=None, description="内嵌状态"
    )


class MaaFWShellInstancesIn(BaseModel):
    scriptId: str = Field(..., min_length=1, description="MFW 脚本 ID")
    path: Optional[str] = Field(
        default=None,
        description="只扫这个目录（键位弹窗「选择其他目录」用，不写回脚本配置）；不传时先扫来源目录再扫内嵌副本",
    )


class MaaFWShellInstancesOut(OutBase):
    data: List[MaaFWShellInstanceItem] = Field(
        default_factory=list, description="项目目录里找到的外壳配置实例"
    )


class MaaFWShellInstanceImportIn(BaseModel):
    scriptId: str = Field(..., min_length=1, description="MFW 脚本 ID")
    instanceIds: List[str] = Field(
        ..., min_length=1, description="要导入的实例 ID，每个建一个用户"
    )


class MaaFWShellInstanceApplyIn(BaseModel):
    scriptId: str = Field(..., min_length=1, description="MFW 脚本 ID")
    userId: str = Field(..., min_length=1, description="要覆盖任务队列的用户 ID")
    instanceId: str = Field(..., min_length=1, description="从哪份外壳实例导入")
    path: Optional[str] = Field(
        default=None,
        description="实例从哪个目录列出来的就传哪个（弹窗「选择其他目录」选的）；不传时先来源目录再内嵌副本，与列表同一口径",
    )


class MaaFWShellInstanceImportOut(OutBase):
    data: List[MaaFWShellInstanceImportItem] = Field(
        default_factory=list, description="逐个实例的导入结果，顺序同请求"
    )


class MaaFWShellInstanceApplyData(BaseModel):
    """覆盖到已有用户的结果：除了逐项成败与跳过项，还带实际写进用户配置的任务快照。

    界面直接拿它刷新本地状态，不用再回头拉一次用户配置——那样会把用户还没保存的其它改动
    一起冲掉。快照与 ``info`` 都是写入漏斗处理之后的样子（特调整理、密码加密），与读用户配置
    拿到的一致。
    """

    result: Optional[MaaFWShellInstanceImportItem] = Field(
        default=None,
        description="这次覆盖的结果；失败原因在 result.error 里，连结果是空的（找不到用户 / 实例）时为 null",
    )
    snapshot: Optional[Dict[str, Any]] = Field(
        default=None,
        description="实际写进用户配置的任务快照；失败时为空",
    )
    info: Dict[str, Any] = Field(
        default_factory=dict,
        description="写入时特调一并改掉的用户信息字段（如 M9A 把切换账号收进 Account）；没有为空",
    )


class MaaFWShellInstanceApplyOut(OutBase):
    data: MaaFWShellInstanceApplyData = Field(
        default_factory=MaaFWShellInstanceApplyData,
        description="覆盖结果与任务快照",
    )


class MaaFWProjectUpdateIn(BaseModel):
    scriptId: str = Field(..., min_length=1, description="MaaFW 脚本 ID")
    action: Literal["check", "apply"] = Field(
        default="check",
        description="check 仅检查是否有新版本；apply 触发实际更新",
    )


class MaaFWProjectUpdateOut(OutBase):
    data: Optional[MaaFWProjectUpdateData] = Field(
        default=None, description="MaaFW 项目更新结果"
    )


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


class MaaFWMirrorCdkIn(BaseModel):
    scriptId: str = Field(..., min_length=1, description="MaaFW 脚本 ID")
    cdk: str = Field(
        default="",
        description="要查询的 Mirror 酱 CDK（编辑页输入框当前值，可能还没落盘）；只走请求体，不进日志",
    )


class MaaFWMirrorCdkOut(OutBase):
    data: Optional[MaaFWMirrorCdkData] = Field(
        default=None, description="Mirror 酱 CDK 状态"
    )


class MaaFWAgentEnvPrepareIn(BaseModel):
    path: str = Field(default="", description="MFW 项目根目录，应包含 interface.json")
    scriptId: Optional[str] = Field(
        default=None,
        description="脚本 ID；内嵌脚本按它解析副本目录，此时 path 可留空",
    )
    force: bool = Field(
        default=False,
        description="忽略指纹缓存强制重新准备，供用户手动重试使用",
    )


class MaaFWAgentEnvPrepareOut(OutBase):
    data: Optional[MaaFWAgentEnvPrepareData] = Field(
        default=None, description="MFW 运行环境准备结果"
    )


class ScriptCreateIn(BaseModel):
    type: Literal[
        "MAA",
        "SRC",
        "General",
        "Okww",
        "OkNte",
        "MaaEnd",
        "M9A",
        "MaaFW",
        "HSR",
        "BetterGI",
        "ZzzOd",
        "BAAH",
        "Whimbox",
        "MSS",
    ] = Field(
        ...,
        description="脚本类型: MAA脚本, 通用脚本, OK-WW脚本, OK-NTE脚本, SRC脚本, MaaEnd脚本, M9A脚本, MaaFW脚本, HSR脚本, BetterGI脚本, ZZZ-OD脚本, BAAH脚本, 奇想盒脚本, MSS脚本",
    )
    scriptId: str | None = Field(
        default=None, description="直接从该脚本ID复制创建, 仅在复制创建时使用"
    )


class ScriptCreateOut(OutBase):
    scriptId: str = Field(..., description="新创建的脚本ID")
    data: Union[
        MaaConfig,
        SrcConfig,
        GeneralConfig,
        OkwwConfig,
        OkNteConfig,
        MaaEndConfig,
        M9AConfig,
        MaaFWConfig,
        HSRConfig,
        BetterGIConfig,
        ZzzOdConfig,
        BAAHConfig,
        WhimboxConfig,
        MSSConfig,
    ] = Field(..., description="脚本配置数据")


class ScriptGetIn(BaseModel):
    scriptId: Optional[str] = Field(
        default=None, description="脚本ID, 未携带时表示获取所有脚本数据"
    )


class ScriptGetOut(OutBase):
    index: List[ScriptIndexItem] = Field(..., description="脚本索引列表")
    data: Dict[
        str,
        Union[
            MaaConfig,
            SrcConfig,
            GeneralConfig,
            OkwwConfig,
            OkNteConfig,
            MaaEndConfig,
            M9AConfig,
            MaaFWConfig,
            HSRConfig,
            BetterGIConfig,
            ZzzOdConfig,
            BAAHConfig,
            WhimboxConfig,
            MSSConfig,
        ],
    ] = Field(..., description="脚本数据字典, key来自于index列表的uid")


class ScriptUpdateIn(BaseModel):
    scriptId: str = Field(..., description="脚本ID")
    data: Union[
        MaaConfigInput,
        SrcConfigInput,
        GeneralConfigInput,
        OkwwConfigInput,
        OkNteConfigInput,
        MaaEndConfigInput,
        M9AConfigInput,
        MaaFWConfigInput,
        HSRConfigInput,
        BetterGIConfigInput,
        ZzzOdConfigInput,
        BAAHConfigInput,
        WhimboxConfigInput,
        MSSConfigInput,
    ] = Field(..., description="脚本更新数据")

    @model_validator(mode="before")
    @classmethod
    def select_config_contract(cls, value):
        """按目标配置选输入类型，避免联合类型丢弃其他专项的同组字段。"""
        if not isinstance(value, dict) or not isinstance(value.get("data"), dict):
            return value
        try:
            target = Config.ScriptConfig[value["scriptId"]]
        except (KeyError, ValueError, TypeError, AttributeError):
            return value
        payload = config_contract(type(target), mode="input").model_validate(
            value["data"]
        )
        return {**value, "data": payload}


class ScriptDeleteIn(BaseModel):
    scriptId: str = Field(..., description="脚本ID")


class MaaDepotStageCandidatesBatchIn(BaseModel):
    script: ScriptDeleteIn
    itemIds: List[Annotated[str, Field(min_length=1, max_length=64)]] = Field(
        ..., min_length=1, max_length=256, description="需要查询候选关卡的物品ID"
    )


class MaaDepotStageCandidatesBatchOut(OutBase):
    data: Dict[str, List[ComboBoxItem]] = Field(
        default_factory=dict, description="按物品ID分组的候选关卡，未找到候选时为空列表"
    )


class ScriptReorderIn(BaseModel):
    indexList: List[str] = Field(..., description="脚本ID列表, 按新顺序排列")


class ScriptShareInspectIn(BaseModel):
    scriptId: str = Field(..., description="脚本ID")
    config_name: str = Field(..., min_length=1, max_length=64, description="配置名称")


class ScriptTemplateImportIn(BaseModel):
    scriptId: str = Field(..., description="脚本ID")
    configKey: str = Field(..., description="配置中心配置标识")
    versionNo: Optional[int] = Field(
        default=None, ge=1, description="版本号, 为空表示已发布的最新版本"
    )


class ScriptUploadIn(BaseModel):
    scriptId: str = Field(..., description="脚本ID")
    config_name: str = Field(..., min_length=1, max_length=64, description="配置名称")
    description: str = Field(..., min_length=1, max_length=500, description="描述")
    acknowledged: bool = Field(
        default=False, description="是否已确认分享前检查出的隐私风险项"
    )


class ShareRiskItem(BaseModel):
    field: str = Field(..., description="存在风险的配置项")
    reason: str = Field(..., description="风险说明")


class ShareInspectOut(OutBase):
    risks: List[ShareRiskItem] = Field(
        default_factory=list, description="分享前检查出的隐私风险项"
    )


class UserInBase(BaseModel):
    scriptId: str = Field(..., description="所属脚本ID")


class ScriptConfigImportIn(UserInBase):
    userId: Optional[str] = Field(
        default=None, description="用户ID, 未携带时导入到脚本级配置文件"
    )


class UserConfigDirIn(UserInBase):
    userId: str = Field(..., description="用户ID")


class UserConfigDirOut(OutBase):
    path: Optional[str] = Field(default=None, description="用户配置目录绝对路径")


class UserGetIn(UserInBase):
    userId: Optional[str] = Field(
        default=None, description="用户ID, 未携带时表示获取所有用户数据"
    )


class UserGetOut(OutBase):
    index: List[UserIndexItem] = Field(..., description="用户索引列表")
    data: Dict[
        str,
        Union[
            MaaUserConfig,
            SrcUserConfig,
            GeneralUserConfig,
            OkwwUserConfig,
            OkNteUserConfig,
            MaaEndUserConfig,
            M9AUserConfig,
            MaaFWUserConfig,
            HSRUserConfig,
            BetterGIUserConfig,
            ZzzOdUserConfig,
            BAAHUserConfig,
            WhimboxUserConfig,
            MSSUserConfig,
        ],
    ] = Field(..., description="用户数据字典, key来自于index列表的uid")


class UserCreateOut(OutBase):
    userId: str = Field(..., description="新创建的用户ID")
    data: Union[
        MaaUserConfig,
        SrcUserConfig,
        GeneralUserConfig,
        OkwwUserConfig,
        OkNteUserConfig,
        MaaEndUserConfig,
        M9AUserConfig,
        MaaFWUserConfig,
        HSRUserConfig,
        BetterGIUserConfig,
        ZzzOdUserConfig,
        BAAHUserConfig,
        WhimboxUserConfig,
        MSSUserConfig,
    ] = Field(..., description="用户配置数据")


class UserUpdateIn(UserInBase):
    userId: str = Field(..., description="用户ID")
    data: Union[
        MaaUserConfigInput,
        SrcUserConfigInput,
        GeneralUserConfigInput,
        OkwwUserConfigInput,
        OkNteUserConfigInput,
        MaaEndUserConfigInput,
        M9AUserConfigInput,
        MaaFWUserConfigInput,
        HSRUserConfigInput,
        BetterGIUserConfigInput,
        ZzzOdUserConfigInput,
        BAAHUserConfigInput,
        WhimboxUserConfigInput,
        MSSUserConfigInput,
    ] = Field(..., description="用户更新数据")

    @model_validator(mode="before")
    @classmethod
    def select_config_contract(cls, value):
        """按目标配置选输入类型，避免联合类型丢弃其他专项的同组字段。"""
        if not isinstance(value, dict) or not isinstance(value.get("data"), dict):
            return value
        try:
            target = Config.ScriptConfig[value["scriptId"]].UserData[value["userId"]]
        except (KeyError, ValueError, TypeError, AttributeError):
            return value
        payload = config_contract(type(target), mode="input").model_validate(
            value["data"]
        )
        return {**value, "data": payload}


class UserDeleteIn(UserInBase):
    userId: str = Field(..., description="用户ID")


class UserReorderIn(UserInBase):
    indexList: List[str] = Field(..., description="用户ID列表, 按新顺序排列")


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


router = APIRouter(prefix="/api/scripts", tags=["脚本管理"])
logger = get_logger("脚本管理 API")


def _bettergi_script_config(script_id: str):
    """Resolve a BetterGI script and reject cross-type IDs before domain access."""

    script_config = Config.ScriptConfig[uuid.UUID(script_id)]
    if not isinstance(script_config, RuntimeBetterGIConfig):
        raise TypeError("脚本配置类型错误, 不是 BetterGI 类型")
    return script_config


def _bettergi_user_id(script_config: RuntimeBetterGIConfig, user_id: str):
    """Validate that a BetterGI user exists before domain access."""

    try:
        script_config.UserData[uuid.UUID(user_id)]
    except KeyError:
        raise ValueError("用户不存在或无权访问该配置")


def _bettergi_root(script_config: RuntimeBetterGIConfig) -> Path:
    """目录选项查询需要已配置的安装目录。"""
    root = script_config.Info.RootPath
    if root is None:
        raise ValueError("请先设置 BetterGI 脚本安装目录")
    return root


def _bettergi_user_config(script_config: RuntimeBetterGIConfig, user_id: str):
    """Resolve a BetterGI user config and reject unknown IDs before domain access."""

    user_config = script_config.UserData[uuid.UUID(user_id)]
    return user_config


def _whimbox_script_config(script_id: str):
    """Resolve a Whimbox script and reject cross-type IDs before domain access."""

    script_config = Config.ScriptConfig[uuid.UUID(script_id)]
    if not isinstance(script_config, RuntimeWhimboxConfig):
        raise TypeError("脚本配置类型错误, 不是奇想盒类型")
    return script_config


def _read_combat_from_plan(
    script_config, user_id: str, group: str, source: str, data: dict
) -> dict:
    """把战斗组 Plan 里的设置反查回右栏键，合并进读取结果（回显）。"""
    from app.task.BetterGI.tools import one_dragon_plan

    target_group = _combat_target_group(source, group)
    mapping = one_dragon_plan.RIGHTBAR_TO_PLAN.get(
        one_dragon_plan.resolve_base_name(target_group)
    )
    if not mapping:
        return data
    user_config = _bettergi_user_config(script_config, user_id)
    plan_json = user_config.OneDragon.Plan or ""
    data.update(
        one_dragon_plan.extract_rightbar_from_plan(plan_json, target_group) or {}
    )
    # 还原 weekly 嵌套结构为平铺右栏键（供前端周表回显）
    steps = one_dragon_plan.parse_one_dragon_plan(plan_json) if plan_json else []
    target = next((s for s in steps if s.get("name") == target_group), None)
    if target:
        data.update(
            one_dragon_plan.flatten_weekly_struct(
                target_group, target.get("settings") or {}
            )
        )
    # 「开启每日地脉花」未配置（Plan 无该键，如新用户）时默认开启：与种子模板的
    # 「每日耗尽模式」标准状态一致；用户选过每周模式则 Plan 已有显式 false，不受影响。
    if target_group == "自动地脉花":
        data.setdefault("leyLineDailyEnabled", True)
    return data


def _route_combat_to_plan(
    script_config,
    user_id: str,
    group: str,
    settings: dict,
    source: str,
) -> tuple[dict, "str | None"]:
    """战斗4项右栏设置：可映射字段翻译后写入 OneDragon.Plan（执行层参数源）。

    原生侧**保留全量字段**（双写）：执行层只接管「Plan 中有该组步骤且队列中启用」
    的战斗组，其余战斗组仍走原生一条龙 / 全局 config.json，必须能读到最新值；
    已被接管的组会从一条龙副本剔除，多写的原生值不会被消费。

    返回 ``(原生字段, 新 Plan JSON 或 None)``。非战斗组 / 无可映射键时返回
    ``(settings, None)``，调用方按原逻辑写原生存储即可。
    """
    from app.task.BetterGI.tools import one_dragon_plan

    target_group = _combat_target_group(source, group)
    mapping = one_dragon_plan.RIGHTBAR_TO_PLAN.get(
        one_dragon_plan.resolve_base_name(target_group)
    )
    if not mapping or not settings:
        return settings, None
    plan_settings = {k: v for k, v in settings.items() if k in mapping}
    extra = one_dragon_plan.extract_weekly_struct(target_group, settings)
    if not plan_settings and not extra:
        return settings, None
    user_config = _bettergi_user_config(script_config, user_id)
    plan_json = user_config.OneDragon.Plan or ""
    new_plan = one_dragon_plan.merge_rightbar_into_plan(
        plan_json, target_group, plan_settings, extra=extra or None
    )
    return settings, new_plan


def _combat_target_group(source: str, group: str) -> str:
    """确定右栏设置归属的战斗组（支持同一战斗组的多个独立实例）。

    优先采用前端传入的**实例组名**（形如 ``自动幽境危战-3``、``自动秘境-3``）：
    同一战斗组可配多个实例，各自独立保存/回显设置。未传组名（或组名不是内置
    战斗组）时按 source 固定映射（globalStygian→自动幽境危战、globalDomain→
    自动秘境），兼容不带 groupName 的调用方与旧数据。
    """
    from app.task.BetterGI.tools import one_dragon_plan

    if group and one_dragon_plan.resolve_base_name(group):
        return group
    return {"globalStygian": "自动幽境危战", "globalDomain": "自动秘境"}.get(
        source, group
    )


def _oknte_script_config(script_id: str) -> tuple[uuid.UUID, RuntimeOkNteConfig]:
    script_uid = uuid.UUID(script_id)
    script_config = Config.ScriptConfig[script_uid]
    if not isinstance(script_config, RuntimeOkNteConfig):
        raise ValueError("脚本配置类型错误, 不是 OK-NTE 类型")
    return script_uid, script_config


def _oknte_mas_config_dir(script_id: str, user_id: str) -> Path:
    from app.task.OkNte.tools.backup_archive import ensure_quick_config_dir

    script_uid, script_config = _oknte_script_config(script_id)
    user_uid = uuid.UUID(user_id)
    if user_uid not in script_config.UserData:
        raise ValueError("OK-NTE 用户不存在，请刷新后重试")
    if script_config.is_locked:
        raise ValueError("OK-NTE 正在运行，请结束任务后编辑")
    return ensure_quick_config_dir(str(script_uid), str(user_uid), script_config)


def _oknte_config_file_path(config_dir: Path, filename: str) -> Path:
    file_path = Path(filename)
    if file_path.name != filename or file_path.is_absolute() or ".." in file_path.parts:
        raise ValueError("配置文件名非法")
    return config_dir / filename


SCRIPT_BOOK = {
    "MaaConfig": MaaConfig,
    "SrcConfig": SrcConfig,
    "MaaEndConfig": MaaEndConfig,
    "M9AConfig": M9AConfig,
    "MaaFWConfig": MaaFWConfig,
    "GeneralConfig": GeneralConfig,
    "OkwwConfig": OkwwConfig,
    "OkNteConfig": OkNteConfig,
    "HSRConfig": HSRConfig,
    "BetterGIConfig": BetterGIConfig,
    "ZzzOdConfig": ZzzOdConfig,
    "BAAHConfig": BAAHConfig,
    "WhimboxConfig": WhimboxConfig,
    "MSSConfig": MSSConfig,
}
USER_BOOK = {
    "MaaConfig": MaaUserConfig,
    "SrcConfig": SrcUserConfig,
    "MaaEndConfig": MaaEndUserConfig,
    "M9AConfig": M9AUserConfig,
    "MaaFWConfig": MaaFWUserConfig,
    "GeneralConfig": GeneralUserConfig,
    "OkwwConfig": OkwwUserConfig,
    "OkNteConfig": OkNteUserConfig,
    "HSRConfig": HSRUserConfig,
    "BetterGIConfig": BetterGIUserConfig,
    "ZzzOdConfig": ZzzOdUserConfig,
    "BAAHConfig": BAAHUserConfig,
    "WhimboxConfig": WhimboxUserConfig,
    "MSSConfig": MSSUserConfig,
}


@router.post(
    "/add",
    tags=["Add"],
    summary="添加脚本",
    response_model=ScriptCreateOut,
    status_code=200,
)
async def add_script(script: ScriptCreateIn = Body(...)) -> ScriptCreateOut:

    try:
        uid, config = await Config.add_script(script.type, script.scriptId)
        data = SCRIPT_BOOK[type(config).__name__](
            **config.model_dump(context={"audience": "api"})
        )
    except Exception as e:
        logger.opt(exception=True).warning(f"add_script失败: {type(e).__name__}: {e}")
        return ScriptCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            scriptId="",
            data=GeneralConfig(**{}),
        )
    return ScriptCreateOut(scriptId=str(uid), data=data)


@router.post(
    "/get",
    tags=["Get"],
    summary="查询脚本配置信息",
    response_model=ScriptGetOut,
    status_code=200,
)
async def get_script(script: ScriptGetIn = Body(...)) -> ScriptGetOut:

    try:
        index, data = await Config.get_script(script.scriptId)
        activity_games = {
            config.__name__: game for config, game in SCRIPT_CALENDAR_GAMES.items()
        }
        index = [
            ScriptIndexItem(**item, activityGame=activity_games.get(item["type"]))
            for item in index
        ]
        data = {
            uid: SCRIPT_BOOK[next((_.type for _ in index if _.uid == uid), "General")](
                **cfg
            )
            for uid, cfg in data.items()
        }
    except Exception as e:
        logger.opt(exception=True).warning(f"get_script失败: {type(e).__name__}: {e}")
        return ScriptGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            index=[],
            data={},
        )
    return ScriptGetOut(index=index, data=data)


@router.post(
    "/update",
    tags=["Update"],
    summary="更新脚本配置信息",
    response_model=OutBase,
    status_code=200,
)
async def update_script(script: ScriptUpdateIn = Body(...)) -> OutBase:

    try:
        data = script.data.model_dump(exclude_unset=True)
        # 魔改 AVD 目前只支持 MaaFW 和 MAA：别的脚本选魔改 AVD 设备，保存时就拦下
        refusal = await emulator2_service.mod_avd_binding_error(script.scriptId, data)
        if refusal:
            return OutBase(code=500, status="error", message=refusal)
        await Config.update_script(script.scriptId, data)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"update_script失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.get(
    "/okww/client-path",
    tags=["Get"],
    summary="解码鸣潮启动器，返回客户端 exe 路径",
    response_model=OkwwClientPathOut,
    status_code=200,
)
async def get_okww_client_path_api(scriptId: str) -> OkwwClientPathOut:
    """解码鸣潮启动器记录，返回客户端 exe 完整路径（仅直启模式的前端展示用）。

    任务期的启动与自动更新链路由后端自行解码，不经过本端点。
    """

    try:
        script_config = Config.ScriptConfig[uuid.UUID(scriptId)]
        if not isinstance(script_config, RuntimeOkwwConfig):
            raise TypeError("脚本配置类型错误, 不是 OK-WW 类型")
        launcher_path = Path(str(script_config.Game.Path or "").strip())
        client_path = resolve_wuthering_waves_process_path(launcher_path)
        return OkwwClientPathOut(
            code=200,
            status="success",
            message="",
            client_path=client_path.as_posix(),
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_okww_client_path_api失败: {type(e).__name__}: {e}"
        )
        return OkwwClientPathOut(
            code=(
                400
                if isinstance(e, (ValueError, KeyError, TypeError, FileNotFoundError))
                else 500
            ),
            status="error",
            # message 直接展示给用户，不带异常类名前缀（类名只进上面的日志）
            message=str(e),
            client_path="",
        )


@router.get(
    "/maaend/launcher-path",
    tags=["Get"],
    summary="从终末地客户端路径识别官方启动器路径",
    response_model=MaaEndLauncherPathOut,
    status_code=200,
)
async def get_maaend_launcher_path_api(scriptId: str) -> MaaEndLauncherPathOut:
    """按脚本的终末地客户端路径识别启动器 Launcher.exe（前端「自动识别」用）。

    只回答「在哪」：不改配置；识别不到时返回 400 与说明，由前端提示手动选择。
    """

    try:
        script_uid = uuid.UUID(scriptId)
        script_config = Config.ScriptConfig[script_uid]
        if not isinstance(script_config, RuntimeMaaEndConfig):
            raise TypeError("脚本配置类型错误, 不是 MaaEnd 类型")
        client_exe = Path(str(script_config.Game.Path or "").strip())
        if not client_exe.is_file():
            raise ValueError("请先选择终末地客户端 Endfield.exe，再自动识别启动器")
        launcher_path = discover_launcher_exe(client_exe)
        if launcher_path is None:
            raise ValueError(
                "未能从游戏客户端路径识别到终末地官方启动器, "
                "请手动选择终末地启动器的可执行文件（.exe）"
            )
        return MaaEndLauncherPathOut(
            code=200,
            status="success",
            message="",
            launcher_path=launcher_path.as_posix(),
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_maaend_launcher_path_api失败: {type(e).__name__}: {e}"
        )
        return MaaEndLauncherPathOut(
            code=(
                400
                if isinstance(e, (ValueError, KeyError, TypeError, FileNotFoundError))
                else 500
            ),
            status="error",
            # message 直接展示给用户，不带异常类名前缀（类名只进上面的日志）
            message=str(e),
            launcher_path="",
        )


@router.post(
    "/delete",
    tags=["Delete"],
    summary="删除脚本",
    response_model=OutBase,
    status_code=200,
)
async def delete_script(script: ScriptDeleteIn = Body(...)) -> OutBase:

    try:
        await Config.del_script(script.scriptId)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"delete_script失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/order",
    tags=["Update"],
    summary="重新排序脚本",
    response_model=OutBase,
    status_code=200,
)
async def reorder_script(script: ScriptReorderIn = Body(...)) -> OutBase:

    try:
        await Config.reorder_script(script.indexList)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"reorder_script失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/import/web",
    tags=["Update"],
    summary="从配置中心导入脚本配置",
    response_model=OutBase,
    status_code=200,
)
async def import_script_from_web(script: ScriptTemplateImportIn = Body(...)) -> OutBase:

    try:
        await Config.import_script_from_share(
            script.scriptId, config_key=script.configKey, version_no=script.versionNo
        )
    except ConfigCenterError as e:
        return OutBase(code=500, status="error", message=str(e))
    except Exception as e:
        logger.opt(exception=True).warning(
            f"import_script_from_web失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/share/inspect",
    tags=["Get"],
    summary="分享前检查脚本配置中的隐私风险",
    response_model=ShareInspectOut,
    status_code=200,
)
async def inspect_script_share(
    script: ScriptShareInspectIn = Body(...),
) -> ShareInspectOut:

    try:
        _, risks = await Config.build_share_config(
            script.scriptId, config_name=script.config_name
        )
    except Exception as e:
        return ShareInspectOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return ShareInspectOut(risks=[ShareRiskItem(**_) for _ in risks])


@router.post(
    "/Upload/web",
    tags=["Action"],
    summary="分享脚本配置到配置中心",
    response_model=OutBase,
    status_code=200,
)
async def upload_script_to_web(script: ScriptUploadIn = Body(...)) -> OutBase:

    try:
        await Config.upload_script_to_share(
            script.scriptId,
            config_name=script.config_name,
            description=script.description,
            acknowledged=script.acknowledged,
        )
    except ConfigCenterError as e:
        return OutBase(code=500, status="error", message=str(e))
    except Exception as e:
        logger.opt(exception=True).warning(
            f"upload_script_to_web失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/config/import",
    tags=["Action"],
    summary="从脚本目录导入配置文件",
    response_model=OutBase,
    status_code=200,
)
async def import_script_config_file(
    config: ScriptConfigImportIn = Body(...),
) -> OutBase:

    try:
        await Config.import_script_config_file(config.scriptId, config.userId)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"import_script_config_file失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase(message="脚本配置文件已导入")


@router.post(
    "/maaend/options",
    tags=["Get"],
    summary="获取 MaaEnd 动态选项",
    response_model=MaaEndOptionsOut,
    status_code=200,
)
async def get_maaend_options(options: ScriptDeleteIn = Body(...)) -> MaaEndOptionsOut:
    try:
        data = await Config.get_maaend_options(options.scriptId)
        return MaaEndOptionsOut(
            launchGameControllers=data["launchGameControllers"],
            gameSettingControllers=data["gameSettingControllers"],
            projectName=data["projectName"],
            projectVersion=data["projectVersion"],
            inventory=data.get("inventory"),
            autoCollectGroups=[
                MaaEndAutoCollectGroup(**item)
                for item in data.get("autoCollectGroups", [])
            ],
            originalResolution=data.get("originalResolution"),
            originalDisplayType=data.get("originalDisplayType"),
            controllers=[ComboBoxItem(**item) for item in data["controllers"]],
            controllerTypes=data["controllerTypes"],
            essenceLocations=[
                ComboBoxItem(**item) for item in data["essenceLocations"]
            ],
            essenceMenus=[
                ComboBoxItem(**item) for item in data.get("essenceMenus", [])
            ],
            essenceTargetWeaponGroups=[
                MaaEndEssenceTargetGroup(
                    value=item["value"],
                    label=item["label"],
                    options=[ComboBoxItem(**option) for option in item["options"]],
                )
                for item in data.get("essenceTargetWeaponGroups", [])
            ],
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_maaend_options失败: {type(e).__name__}: {e}"
        )
        return MaaEndOptionsOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            controllers=[],
            controllerTypes={},
            essenceLocations=[],
            essenceMenus=[],
            essenceTargetWeaponGroups=[],
        )


@router.post(
    "/user/get",
    tags=["Get"],
    summary="查询用户",
    response_model=UserGetOut,
    status_code=200,
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
        logger.opt(exception=True).warning(f"get_user失败: {type(e).__name__}: {e}")
        return UserGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            index=[],
            data={},
        )
    return UserGetOut(index=index, data=data)


@router.post(
    "/user/config-dir",
    tags=["Get"],
    summary="获取用户配置目录",
    response_model=UserConfigDirOut,
    status_code=200,
)
async def get_user_config_dir(user: UserConfigDirIn = Body(...)) -> UserConfigDirOut:

    try:
        user_config_dir = await Config.get_user_config_dir(user.scriptId, user.userId)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_user_config_dir失败: {type(e).__name__}: {e}"
        )
        return UserConfigDirOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            path="",
        )
    return UserConfigDirOut(message="用户配置目录获取成功", path=str(user_config_dir))


@router.post(
    "/user/add",
    tags=["Add"],
    summary="添加用户",
    response_model=UserCreateOut,
    status_code=200,
)
async def add_user(user: UserInBase = Body(...)) -> UserCreateOut:

    try:
        uid, config = await Config.add_user(user.scriptId)
        data = USER_BOOK[type(Config.ScriptConfig[uuid.UUID(user.scriptId)]).__name__](
            **config.model_dump(context={"audience": "api"})
        )
    except FileNotFoundError as e:
        return UserCreateOut(
            code=409,
            status="error",
            message=str(e),
            userId="",
            data=GeneralUserConfig(**{}),
        )
    except Exception as e:
        logger.opt(exception=True).warning(f"add_user失败: {type(e).__name__}: {e}")
        return UserCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            userId="",
            data=GeneralUserConfig(**{}),
        )
    return UserCreateOut(userId=str(uid), data=data)


@router.post(
    "/user/update",
    tags=["Update"],
    summary="更新用户配置信息",
    response_model=OutBase,
    status_code=200,
)
async def update_user(user: UserUpdateIn = Body(...)) -> OutBase:
    data = user.data.model_dump(exclude_unset=True)

    # 队列是唯一真相源：落盘 OneDragon.Queue 时，清理 Plan 中不再被引用的战斗实例
    # （前端删除队列行只改 Queue，Plan 对应实例会残留成孤儿）。仅当 patch 含 Queue 时触发，
    # 避免其它字段保存误伤；被关闭（enabled=false）但仍在队列的行其实例保留。
    od = data.get("OneDragon") if isinstance(data, dict) else None
    if isinstance(od, dict) and "Queue" in od:
        try:
            from app.task.BetterGI.tools import one_dragon_plan

            script_cfg = Config.ScriptConfig[uuid.UUID(user.scriptId)]
            uc = script_cfg.UserData[uuid.UUID(user.userId)]
            plan = uc.OneDragon.Plan or ""
            groups = uc.OneDragon.Groups or []
            new_plan = one_dragon_plan.prune_plan_to_queue(plan, od["Queue"], groups)
            if new_plan != plan:
                od["Plan"] = new_plan
            # 录制（KeyMouse）加入队列：提前生成 per-user 配置组副本（含单 KeyMouse 项目），
            # 使右栏项目编辑能读到录制内容、运行时可被物化，避免「一条龙里没有内容」。
            try:
                from app.task.BetterGI.tools import one_dragon as _od

                _root = Path(str(script_cfg.Info.RootPath or "")).expanduser()
                _queue = _od.parse_one_dragon_queue(od["Queue"])
                _od.ensure_keymouse_groups(
                    _root,
                    user.scriptId,
                    user.userId,
                    [e.get("name") for e in _queue if isinstance(e, dict)],
                )
            except Exception:  # pragma: no cover - 兜底：生成失败不应阻断保存
                import logging

                logging.getLogger(__name__).warning(
                    "为队列中的录制生成配置组副本失败（已忽略）", exc_info=True
                )
        except Exception as e:  # pragma: no cover - 兜底：同步失败不应阻断保存
            import logging

            logging.getLogger(__name__).warning(
                "队列变更同步清理 Plan 孤儿实例失败（已忽略）: %s", e
            )

    try:
        await Config.update_user(user.scriptId, user.userId, data)
    except Exception as e:
        logger.opt(exception=True).warning(f"update_user失败: {type(e).__name__}: {e}")
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/user/delete",
    tags=["Delete"],
    summary="删除用户",
    response_model=OutBase,
    status_code=200,
)
async def delete_user(user: UserDeleteIn = Body(...)) -> OutBase:

    try:
        await Config.del_user(user.scriptId, user.userId)
    except Exception as e:
        logger.opt(exception=True).warning(f"delete_user失败: {type(e).__name__}: {e}")
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/user/order",
    tags=["Update"],
    summary="重新排序用户",
    response_model=OutBase,
    status_code=200,
)
async def reorder_user(user: UserReorderIn = Body(...)) -> OutBase:

    try:
        await Config.reorder_user(user.scriptId, user.indexList)
    except Exception as e:
        logger.opt(exception=True).warning(f"reorder_user失败: {type(e).__name__}: {e}")
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


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
    "/webhook/get",
    tags=["Get"],
    summary="查询 webhook 配置",
    response_model=WebhookGetOut,
    status_code=200,
)
async def get_webhook(webhook: WebhookGetIn = Body(...)) -> WebhookGetOut:

    try:
        index, data = await Config.get_webhook(
            webhook.scriptId, webhook.userId, webhook.webhookId
        )
        index = [WebhookIndexItem(**_) for _ in index]
        data = {uid: Webhook(**cfg) for uid, cfg in data.items()}
    except Exception as e:
        logger.opt(exception=True).warning(f"get_webhook失败: {type(e).__name__}: {e}")
        return WebhookGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            index=[],
            data={},
        )
    return WebhookGetOut(index=index, data=data)


@router.post(
    "/webhook/add",
    tags=["Add"],
    summary="添加webhook项",
    response_model=WebhookCreateOut,
    status_code=200,
)
async def add_webhook(webhook: WebhookInBase = Body(...)) -> WebhookCreateOut:

    try:
        uid, config = await Config.add_webhook(webhook.scriptId, webhook.userId)
        data = Webhook(**config.model_dump(context={"audience": "api"}))
    except Exception as e:
        logger.opt(exception=True).warning(f"add_webhook失败: {type(e).__name__}: {e}")
        return WebhookCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            webhookId="",
            data=Webhook(**{}),
        )
    return WebhookCreateOut(webhookId=str(uid), data=data)


@router.post(
    "/webhook/update",
    tags=["Update"],
    summary="更新webhook项",
    response_model=OutBase,
    status_code=200,
)
async def update_webhook(webhook: WebhookUpdateIn = Body(...)) -> OutBase:

    try:
        await Config.update_webhook(
            webhook.scriptId,
            webhook.userId,
            webhook.webhookId,
            webhook.data.model_dump(exclude_unset=True),
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"update_webhook失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/webhook/delete",
    tags=["Delete"],
    summary="删除webhook项",
    response_model=OutBase,
    status_code=200,
)
async def delete_webhook(webhook: WebhookDeleteIn = Body(...)) -> OutBase:

    try:
        await Config.del_webhook(webhook.scriptId, webhook.userId, webhook.webhookId)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"delete_webhook失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/maafw/embedded/status",
    tags=["MaaFW"],
    summary="查看 MFW 脚本的内嵌副本状态",
    response_model=MaaFWEmbeddedStatusOut,
    status_code=200,
)
async def get_maafw_embedded_status(
    payload: MaaFWEmbeddedIn = Body(...),
) -> MaaFWEmbeddedStatusOut:
    reply = await maafw_embedded_api.get_embedded_status(payload.scriptId)
    return MaaFWEmbeddedStatusOut(**reply.out_fields())


@router.post(
    "/maafw/embedded/reimport",
    tags=["MaaFW"],
    summary="按来源目录导入（或重新导入）副本",
    response_model=MaaFWEmbeddedStatusOut,
    status_code=200,
)
async def reimport_maafw_embedded(
    payload: MaaFWEmbeddedReimportIn = Body(...),
) -> MaaFWEmbeddedStatusOut:
    """脚本页选目录就是走这里：第一次是导入，之后是换来源或按当前来源重导。

    导入成功才把来源写进 Info.Path；失败时旧副本与旧来源都原样不动。
    """

    reply = await maafw_embedded_api.reimport_embedded(
        payload.scriptId, payload.sourcePath
    )
    return MaaFWEmbeddedStatusOut(**reply.out_fields())


@router.post(
    "/maafw/embedded/sync",
    tags=["MaaFW"],
    summary="立即从来源目录同步（跟随来源目录 / 源码形态）",
    response_model=MaaFWEmbeddedStatusOut,
    status_code=200,
)
async def sync_maafw_embedded(
    payload: MaaFWEmbeddedIn = Body(...),
) -> MaaFWEmbeddedStatusOut:
    """脚本页「立即同步」：按当前来源目录强制重导进脚本的私有渠道，不看签名。

    只在跟随来源目录（开发者模式或源码形态）时可用；脚本运行中、项目正在更新或被占用时拒绝。
    ``message`` 是给用户看的结果：变了哪些文件 / 内容未变化。
    """

    reply = await maafw_embedded_api.sync_embedded(payload.scriptId)
    return MaaFWEmbeddedStatusOut(**reply.out_fields())


@router.post(
    "/maafw/embedded/sources",
    tags=["MaaFW"],
    summary="列出可作为克隆来源的其它 MFW 脚本",
    response_model=MaaFWEmbeddedSourcesOut,
    status_code=200,
)
async def list_maafw_embedded_sources(
    payload: MaaFWEmbeddedSourcesIn = Body(default_factory=MaaFWEmbeddedSourcesIn),
) -> MaaFWEmbeddedSourcesOut:
    """新建脚本对话框里「复用已有脚本的项目」的候选：有健康副本的 MFW / M9A 脚本。

    新建时脚本还没建出来，所以不要求 ``scriptId``；传了就把它自己排除掉。
    """

    reply = await maafw_embedded_api.list_embedded_sources(payload.scriptId)
    return MaaFWEmbeddedSourcesOut(**reply.out_fields())


@router.post(
    "/maafw/embedded/clone",
    tags=["MaaFW"],
    summary="从另一个 MFW 脚本的副本克隆，同一项目再建一个脚本",
    response_model=MaaFWEmbeddedStatusOut,
    status_code=200,
)
async def clone_maafw_embedded(
    payload: MaaFWEmbeddedCloneIn = Body(...),
) -> MaaFWEmbeddedStatusOut:
    """同一个项目要开第二、第三个脚本（不同模拟器并行跑）时走这里，不用再选目录
    重新投影，来源目录已经删了也能建。

    副本从源脚本的副本硬链接克隆（运行时、模型与其它副本共用，只多小文件），
    ``Info.Path`` 与 ``Embedded.*`` 沿用源脚本的记录；类型随项目（M9A 项目 → M9A）。
    用户、任务队列与运行设置不带——那是「复制脚本」的事。
    """
    # docstring 会进 OpenAPI 生成物，保持原文；现行的载荷 + 视图口径见 clone_embedded。

    reply = await maafw_embedded_api.clone_embedded(
        payload.scriptId, payload.sourceScriptId
    )
    return MaaFWEmbeddedStatusOut(**reply.out_fields())


@router.post(
    "/maafw/shell-instances",
    tags=["MaaFW"],
    summary="列出项目目录里外壳（MFAAvalonia / MXU / MFW-PyQt6）保存的配置实例",
    response_model=MaaFWShellInstancesOut,
    status_code=200,
)
async def list_maafw_shell_instances(
    payload: MaaFWShellInstancesIn = Body(...),
) -> MaaFWShellInstancesOut:
    """新建脚本引导最后一步用：外壳里配好的每份实例都可以导入成一个用户。只读外壳文件。"""

    reply = await maafw_shell_instances_api.list_shell_instances(
        payload.scriptId, payload.path
    )
    return MaaFWShellInstancesOut(**reply.out_fields())


@router.post(
    "/maafw/mss/defense-status",
    tags=["MaaFW"],
    summary="个人版「灾变防线」这一期的状态",
    response_model=MssDefenseStatusOut,
    status_code=200,
)
async def get_mss_defense_status(
    payload: MssDefenseStatusIn = Body(...),
) -> MssDefenseStatusOut:
    """MSS 用户页显示「本期灾变防线打了没」。只读，不改任何配置。

    「这一期」由后端按官网那一篇公告的开始时刻算，前端不复刻同一套口径。
    """

    data = await mss_defense_status(payload.scriptId, payload.userId)
    return MssDefenseStatusOut(data=MssDefenseStatusData(**data))


@router.post(
    "/maafw/shell-instances/import",
    tags=["MaaFW"],
    summary="把选中的外壳配置实例导入成用户",
    response_model=MaaFWShellInstanceImportOut,
    status_code=200,
)
async def import_maafw_shell_instances(
    payload: MaaFWShellInstanceImportIn = Body(...),
) -> MaaFWShellInstanceImportOut:
    """每个实例建一个用户：用户名取实例名，任务队列与任务选项一起导入。

    逐个实例独立处理，失败原因与当前项目里对不上而跳过的任务 / 选项写在各项结果里。
    """

    reply = await maafw_shell_instances_api.import_shell_instances(
        payload.scriptId, payload.instanceIds
    )
    return MaaFWShellInstanceImportOut(**reply.out_fields())


@router.post(
    "/maafw/shell-instances/apply",
    tags=["MaaFW"],
    summary="把一份外壳配置的任务队列覆盖到已有用户",
    response_model=MaaFWShellInstanceApplyOut,
    status_code=200,
)
async def apply_maafw_shell_instance(
    payload: MaaFWShellInstanceApplyIn = Body(...),
) -> MaaFWShellInstanceApplyOut:
    """脚本已经建好之后又在外壳里调过队列时，把那份队列与选项再同步到某个用户。

    与「导入成用户」共用同一套换算，所以当前项目里对不上的任务 / 选项同样会被跳过并列在结果里。
    覆盖的是任务队列与任务选项，用户名不动。
    """

    reply = await maafw_shell_instances_api.apply_shell_instance_to_user(
        payload.scriptId, payload.userId, payload.instanceId, payload.path
    )
    return MaaFWShellInstanceApplyOut(**reply.out_fields())


@router.post(
    "/maafw/game-package",
    tags=["MaaFW"],
    summary="按所选 resource 推断 MFW 项目的安卓游戏包名",
    response_model=MaaFWGamePackageOut,
    status_code=200,
)
async def resolve_maafw_game_package(
    payload: MaaFWGamePackageIn = Body(...),
) -> MaaFWGamePackageOut:
    """脚本编辑页读完 interface / 切换 resource 时调用，把推出来的包名直接填进表单。

    只看 resource 的 pipeline，不带用户任务的 pipeline_override（编辑脚本时还没有
    运行计划）；推不出或多个候选都按原样返回，由前端决定不填。
    """

    reply = await maafw_interface_api.resolve_project_game_package(
        payload.scriptId, payload.path, payload.resource
    )
    return MaaFWGamePackageOut(**reply.out_fields())


@router.post(
    "/maafw/preview",
    tags=["MaaFW"],
    summary="预览 MFW interface",
    response_model=MaaFWInterfacePreviewOut,
    status_code=200,
)
async def preview_maafw_interface(
    payload: MaaFWInterfacePreviewIn = Body(...),
) -> MaaFWInterfacePreviewOut:
    """读取 MaaFW 项目 interface，并返回 controller/resource/task 摘要。"""

    reply = await maafw_interface_api.preview_project_interface(
        payload.scriptId, payload.path
    )
    return MaaFWInterfacePreviewOut(**reply.out_fields())


@router.post(
    "/maafw/update",
    tags=["MaaFW"],
    summary="检查或执行 MFW 项目更新",
    response_model=MaaFWProjectUpdateOut,
    status_code=200,
)
async def update_maafw_project(
    payload: MaaFWProjectUpdateIn = Body(...),
) -> MaaFWProjectUpdateOut:
    """按脚本 ``Update.*`` 配置检查或应用 MaaFW 项目目录更新。

    ``action=check`` 只读取 interface 版本与更新源元数据，返回是否有新版本；
    ``action=apply`` 触发下载并原地应用更新包。失败时返回明确 ``message``。
    """

    reply = await maafw_update_api.update_project(payload.scriptId, payload.action)
    return MaaFWProjectUpdateOut(**reply.out_fields())


@router.post(
    "/mirror-cdk",
    tags=["Get"],
    summary="查询脚本生效的 Mirror 酱 CDK 状态",
    response_model=ScriptMirrorCdkOut,
)
async def query_script_mirror_cdk(payload: ScriptMirrorCdkIn) -> ScriptMirrorCdkOut:
    """校验编辑框草稿；MAA 专用 CDK 留空时按接管规则查询全局 CDK。"""
    using_global = not payload.cdk.strip()
    try:
        result = await query_takeover_cdk(payload.cdk)
    except Exception as error:
        logger.warning(f"脚本 Mirror 酱 CDK 查询失败: {type(error).__name__}")
        return ScriptMirrorCdkOut(
            data=ScriptMirrorCdkData(status="error", usingGlobalCdk=using_global)
        )
    return ScriptMirrorCdkOut(
        data=ScriptMirrorCdkData(
            status=result.status,
            expiredTime=result.expired_time,
            usingGlobalCdk=using_global,
        )
    )


@router.post(
    "/maafw/mirror-cdk",
    tags=["MaaFW"],
    summary="查询 MFW 项目的 Mirror 酱 CDK 状态",
    response_model=MaaFWMirrorCdkOut,
    status_code=200,
)
async def query_maafw_mirror_cdk(
    payload: MaaFWMirrorCdkIn = Body(...),
) -> MaaFWMirrorCdkOut:
    """脚本编辑页 CDK 输入框下那行小字：CDK 还剩多久到期，或者为什么不能用。

    带着 CDK 按「当前版本 = 最新版本」查一次 Mirror 酱，服务端只校验 CDK、不签发下载地址，
    不占当日下载额度。CDK 只放在请求体里。项目不支持或查询失败也按成功返回对应状态。
    """

    reply = await maafw_update_api.query_mirror_cdk(payload.scriptId, payload.cdk)
    return MaaFWMirrorCdkOut(**reply.out_fields())


@router.post(
    "/maafw/agent-env/prepare",
    tags=["MaaFW"],
    summary="预备 MFW 运行环境",
    response_model=MaaFWAgentEnvPrepareOut,
    status_code=200,
)
async def prepare_maafw_agent_env(
    payload: MaaFWAgentEnvPrepareIn = Body(...),
) -> MaaFWAgentEnvPrepareOut:
    """按项目 interface 预备 Runner 运行时与各 agent 的 Python 环境。

    在项目引导里读到 interface 之后调用，把首次运行才会付出的下载与建环境
    成本提前到配置阶段。与 ``/maafw/update`` 一样是同步端点：整个准备过程
    在请求内完成，首次冷启动可能耗时数分钟。

    编辑页每打开一次就会调一次，所以先比一遍项目输入指纹：项目没更新过、上次
    准备的环境也还在盘上，就直接还回上次的结果，不再取锁起进程。用户手动重试
    时前端带 ``force``，跳过这层缓存。
    """

    reply = await maafw_agent_env_api.prepare_agent_env(
        payload.scriptId, payload.path, payload.force
    )
    return MaaFWAgentEnvPrepareOut(**reply.out_fields())


@router.get(
    "/hsr/stage-options",
    tags=["HSR"],
    summary="获取 HSR 体力副本动态选项",
    response_model=HSRStageOptionsOut,
    status_code=200,
)
async def get_hsr_stage_options_api(
    scriptId: str | None = None,
    engine: Literal["M7A", "SRA"] = "M7A",
    userId: str | None = None,
    slot: Literal["main", "eow"] = "main",
) -> HSRStageOptionsOut:
    """返回 M7A/SRA 原生副本字段。

    ``userId`` 仅用于校验用户归属；``slot`` 是兼容参数，动态选项当前
    按引擎统一返回，不按 slot 生成不同结果。
    """

    from app.task.HSR import api_service as hsr_api

    reply = await hsr_api.get_stage_options(scriptId, engine, userId)
    return HSRStageOptionsOut(**reply.out_fields())


@router.get(
    "/bettergi/strategies",
    tags=["BetterGI"],
    summary="获取 BetterGI 自动战斗策略选项",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_bettergi_strategies_api(scriptId: str) -> ComboBoxOut:
    """返回 BetterGI 可用自动战斗策略：内置「根据队伍自动选择」+ ``{RootPath}/User/AutoFight/*.txt``、``*.json`` 文件名。"""

    try:
        script_config = _bettergi_script_config(scriptId)
        root = _bettergi_root(script_config)
        from app.task.BetterGI.tools import one_dragon

        names = one_dragon.list_auto_boss_strategies(root)
        data = [ComboBoxItem(label=n, value=n) for n in names]
        return ComboBoxOut(
            code=200,
            status="success",
            message=f"共 {len(data)} 个自动战斗策略选项",
            data=data,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_bettergi_strategies_api失败: {type(e).__name__}: {e}"
        )
        return ComboBoxOut(
            code=400
            if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
        )


@router.get(
    "/bettergi/one-dragon/custom-groups",
    tags=["BetterGI"],
    summary="获取 BetterGI 一条龙自定义配置组",
    response_model=BetterGICustomGroupsOut,
    status_code=200,
)
async def get_bettergi_custom_groups_api(
    scriptId: str, userId: str = "", configName: str = "", useMasConfig: bool = False
) -> BetterGICustomGroupsOut:
    """返回指定一条龙配置里的自定义配置组（非内置 8 组）及其启用状态，供前端表格自动加载。

    ``useMasConfig=True``（用户独立配置）时以 per-user 副本为权威源（固定「MAS独立配置」
    槽位名，副本缺失按内置模板），返回该用户将写入槽位的自定义组；``userId`` 必填。
    否则（非独立模式用 BGI 原生配置）读取 BGI ``{configName}`` 实配的自定义组。
    """

    try:
        script_config = _bettergi_script_config(scriptId)
        root = _bettergi_root(script_config)
        from app.task.BetterGI.tools import one_dragon

        if useMasConfig:
            if not userId:
                raise ValueError("用户独立配置下必须提供 userId")
            _bettergi_user_id(script_config, userId)
            items = one_dragon.list_user_custom_groups(
                root, scriptId, userId, one_dragon.launch_slot_name()
            )
        else:
            items = one_dragon.list_custom_groups(
                root, one_dragon.resolve_config_name(configName)
            )
        data = [BetterGICustomGroupOut(**item) for item in items]
        return BetterGICustomGroupsOut(
            code=200,
            status="success",
            message=f"共 {len(data)} 个自定义配置组",
            data=data,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_bettergi_custom_groups_api失败: {type(e).__name__}: {e}"
        )
        return BetterGICustomGroupsOut(
            code=400
            if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
        )


@router.get(
    "/baah/config-names",
    tags=["BAAH"],
    summary="获取 BAAH 配置文件名列表",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_baah_config_names_api(scriptId: str) -> ComboBoxOut:
    """返回 BAAH 配置目录下已有的配置文件名（不含 ``.json`` 后缀）。"""

    try:
        data = [
            ComboBoxItem(label=name, value=name)
            for name in Config.get_baah_config_names(scriptId)
        ]
        return ComboBoxOut(
            code=200,
            status="success",
            message=f"共 {len(data)} 份 BAAH 配置",
            data=data,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_baah_config_names_api失败: {type(e).__name__}: {e}"
        )
        return ComboBoxOut(
            code=400
            if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
        )


@router.get(
    "/bettergi/one-dragon/configs",
    tags=["BetterGI"],
    summary="获取 BetterGI 一条龙配置名列表",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_bettergi_one_dragon_configs_api(scriptId: str) -> ComboBoxOut:
    """返回 BetterGI 可选一条龙配置名：{RootPath}/User/OneDragon/*.json 文件名（默认配置置顶）。"""

    try:
        script_config = _bettergi_script_config(scriptId)
        root = _bettergi_root(script_config)
        from app.task.BetterGI.tools import one_dragon

        names = one_dragon.list_one_dragon_configs(root)
        data = [ComboBoxItem(label=n, value=n) for n in names]
        return ComboBoxOut(
            code=200,
            status="success",
            message=f"共 {len(data)} 个一条龙配置",
            data=data,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_bettergi_one_dragon_configs_api失败: {type(e).__name__}: {e}"
        )
        return ComboBoxOut(
            code=400
            if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
        )


@router.get(
    "/bettergi/js-scripts",
    tags=["BetterGI"],
    summary="获取 BetterGI 可用自定义 JS 脚本列表",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_bettergi_js_scripts_api(scriptId: str) -> ComboBoxOut:
    """返回 BetterGI 可执行自定义 JS 脚本候选。

    ``label`` 为 ``manifest.json`` 的中文显示名（目录名常为英文，如
    ``AAA-Artifacts-Bulk-Supply`` → 「AAA狗粮批发」）；``value`` 为脚本**目录名**
    （BetterGI 一条龙按目录名定位任务，落库与执行都用它）。
    供一条龙「添加配置组」弹窗作为候选（贴 JS 标签）选择。
    """

    try:
        script_config = _bettergi_script_config(scriptId)
        root = _bettergi_root(script_config)
        from app.task.BetterGI.tools import one_dragon

        items = one_dragon.list_js_scripts(root)
        data = [ComboBoxItem(label=display, value=folder) for folder, display in items]
        return ComboBoxOut(
            code=200,
            status="success",
            message=f"共 {len(data)} 个自定义 JS 脚本",
            data=data,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_bettergi_js_scripts_api失败: {type(e).__name__}: {e}"
        )
        return ComboBoxOut(
            code=400
            if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
        )


@router.get(
    "/bettergi/key-mouse-scripts",
    tags=["BetterGI"],
    summary="获取 BetterGI 可用键鼠脚本（录制）列表",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_bettergi_key_mouse_scripts_api(scriptId: str) -> ComboBoxOut:
    """返回 BetterGI 键鼠脚本（录制）候选。

    ``label`` 与 ``value`` 同为 {RootPath}/User/KeyMouseScript/*.json 的文件名（即脚本名）。
    供一条龙「添加配置组」弹窗的「录制」标签页作为候选（贴录制标签）选择。
    """

    try:
        script_config = _bettergi_script_config(scriptId)
        root = _bettergi_root(script_config)
        from app.task.BetterGI.tools import one_dragon

        names = one_dragon.list_key_mouse_scripts(root)
        data = [ComboBoxItem(label=name, value=name) for name in names]
        return ComboBoxOut(
            code=200,
            status="success",
            message=f"共 {len(data)} 个键鼠脚本",
            data=data,
        )
    except Exception as e:
        return ComboBoxOut(
            code=400
            if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
        )


@router.get(
    "/bettergi/script-groups",
    tags=["BetterGI"],
    summary="获取 BetterGI 可用配置组列表",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_bettergi_script_groups_api(
    scriptId: str, userId: str = ""
) -> ComboBoxOut:
    """返回 BetterGI 配置组候选：BGI ``User/ScriptGroup/*.json`` 文件名；带 userId 时并集该用户 per-user 副本名。

    BetterGI 的「配置组」（GUI 中可加入一条龙的自定义任务组）以独立 json 保存于
    ``User/ScriptGroup``，文件名（不含 ``.json``）即组名，与一条龙 TaskDefinitions
    的引用名一致。每次调用实时扫描，供「添加配置组」弹窗「配置组」标签页展示。

    ``userId`` 非空时把该用户的 per-user ScriptGroup 副本名一并并入（副本是 MAS
    独立配置的权威内容源，复制自 JS/路径等来源的新组也只存在于副本目录，需要能被
    识别/展示为配置组）。
    """

    try:
        script_config = _bettergi_script_config(scriptId)
        root = _bettergi_root(script_config)
        from app.task.BetterGI.tools import one_dragon

        names = one_dragon.list_script_groups(root)
        if userId:
            _bettergi_user_id(script_config, userId)
            copy_names = one_dragon.list_user_script_group_names(scriptId, userId)
            merged: list[str] = []
            for name in (*copy_names, *names):
                if name and name not in merged:
                    merged.append(name)
            names = merged
        data = [ComboBoxItem(label=name, value=name) for name in names]
        return ComboBoxOut(
            code=200,
            status="success",
            message=f"共 {len(data)} 个配置组",
            data=data,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_bettergi_script_groups_api失败: {type(e).__name__}: {e}"
        )
        return ComboBoxOut(
            code=400
            if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
        )


@router.get(
    "/bettergi/script-group/detail",
    tags=["BetterGI"],
    summary="获取 BetterGI 配置组 json 详情（per-user 副本优先）",
    response_model=BetterGIScriptGroupDetailOut,
    status_code=200,
)
async def get_bettergi_script_group_detail_api(
    scriptId: str, userId: str, name: str
) -> BetterGIScriptGroupDetailOut:
    """返回某用户的配置组 json（per-user 副本 → BGI 实配的种子顺序）。

    右栏「配置组」标签页选中 scriptgroup 时，据此列出其 json 内 ``projects`` 的
    每个项目；也供 JS/路径等单项目组展示（项目名=组名）。
    """

    try:
        script_config = _bettergi_script_config(scriptId)
        _bettergi_user_id(script_config, userId)
        root = _bettergi_root(script_config)
        from app.task.BetterGI.tools import one_dragon

        data = one_dragon.read_user_script_group(root, scriptId, userId, name)
        if not data:
            return BetterGIScriptGroupDetailOut(
                code=404,
                status="error",
                message=f"配置组 {name} 不存在或内容为空",
                data={},
            )
        return BetterGIScriptGroupDetailOut(
            code=200,
            status="success",
            message=f"配置组 {name} 读取成功",
            data=data,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_bettergi_script_group_detail_api失败: {type(e).__name__}: {e}"
        )
        return BetterGIScriptGroupDetailOut(
            code=400
            if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data={},
        )


@router.get(
    "/bettergi/script-settings-ui",
    tags=["BetterGI"],
    summary="获取 BetterGI 某 JsScript 脚本目录的 settings.json UI 定义",
    response_model=BetterGIScriptSettingsUiOut,
    status_code=200,
)
async def get_bettergi_script_settings_ui_api(
    scriptId: str, folder: str
) -> BetterGIScriptSettingsUiOut:
    """返回某脚本目录（User/JsScript/{folder}/）的 settings.json UI 定义数组。

    双击配置组内某项目（其 folderName 即脚本目录名）时，前端据此渲染设置弹窗表单。
    """

    try:
        script_config = _bettergi_script_config(scriptId)
        root = _bettergi_root(script_config)
        from app.task.BetterGI.tools import one_dragon

        ui = one_dragon.list_script_settings_ui(root, folder)
        return BetterGIScriptSettingsUiOut(
            code=200,
            status="success",
            message=f"脚本 {folder} 共 {len(ui)} 个设置项",
            data=ui,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_bettergi_script_settings_ui_api失败: {type(e).__name__}: {e}"
        )
        return BetterGIScriptSettingsUiOut(
            code=400
            if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
        )


@router.get(
    "/bettergi/script-readme",
    tags=["BetterGI"],
    summary="获取 BetterGI 某 JsScript 脚本目录的 README 内容",
    response_model=BetterGIScriptReadmeOut,
    status_code=200,
)
async def get_bettergi_script_readme_api(
    scriptId: str, folder: str
) -> BetterGIScriptReadmeOut:
    """返回某脚本目录（User/JsScript/{folder}/）的 README 纯文本。

    双击配置组内某项目设置弹窗的「脚本说明」标签页展示。
    """

    try:
        script_config = _bettergi_script_config(scriptId)
        root = _bettergi_root(script_config)
        from app.task.BetterGI.tools import one_dragon

        text = one_dragon.read_script_readme(root, folder)
        return BetterGIScriptReadmeOut(
            code=200,
            status="success",
            message="已读取脚本说明" if text else "该脚本无说明文件",
            data=text,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_bettergi_script_readme_api失败: {type(e).__name__}: {e}"
        )
        return BetterGIScriptReadmeOut(
            code=400
            if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data="",
        )


@router.get(
    "/bettergi/dirs",
    tags=["BetterGI"],
    summary="获取 BetterGI 常用目录（脚本仓库 / JsScript / AutoPathing）",
    response_model=BetterGIScriptDirsOut,
    status_code=200,
)
async def get_bettergi_script_dirs_api(scriptId: str) -> BetterGIScriptDirsOut:
    """返回 BetterGI 三个常用目录的绝对路径，供「添加配置组」弹窗的打开目录按钮使用。"""

    try:
        script_config = _bettergi_script_config(scriptId)
        root = _bettergi_root(script_config)
        from app.task.BetterGI.tools import one_dragon

        dirs = one_dragon.resolve_script_dirs(root)
        return BetterGIScriptDirsOut(
            code=200,
            status="success",
            message="目录解析成功",
            repoDir=dirs.get("repo"),
            jsScriptDir=dirs.get("jsScript"),
            autoPathingDir=dirs.get("autoPathing"),
            oneDragonDir=dirs.get("oneDragon"),
            scriptGroupDir=dirs.get("scriptGroup"),
            keyMouseScriptDir=dirs.get("keyMouseScript"),
            autoFightDir=dirs.get("autoFight"),
            exePath=dirs.get("exe"),
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_bettergi_script_dirs_api失败: {type(e).__name__}: {e}"
        )
        return BetterGIScriptDirsOut(
            code=400
            if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            repoDir=None,
            jsScriptDir=None,
            autoPathingDir=None,
            oneDragonDir=None,
            scriptGroupDir=None,
            keyMouseScriptDir=None,
            autoFightDir=None,
            exePath=None,
        )


@router.get(
    "/bettergi/auto-pathing-tree",
    tags=["BetterGI"],
    summary="获取 BetterGI 地图追踪目录树",
    response_model=BetterGIPathingTreeOut,
    status_code=200,
)
async def get_bettergi_auto_pathing_tree_api(scriptId: str) -> BetterGIPathingTreeOut:
    """返回 BetterGI 地图追踪目录树：{RootPath}/User/AutoPathing 的递归结构。

    节点：``{name, dirs, files}``，``files`` 为路径文件名（不含 ``.json``、含相对目录前缀），
    全局唯一。供「添加配置组」弹窗「地图追踪」标签页左树右表浏览。
    """

    try:
        script_config = _bettergi_script_config(scriptId)
        root = _bettergi_root(script_config)
        from app.task.BetterGI.tools import one_dragon

        root_dir, tree = one_dragon.build_auto_pathing_tree(root)
        return BetterGIPathingTreeOut(
            code=200,
            status="success",
            message="地图追踪目录树加载成功",
            root=root_dir,
            dirs=[BetterGIPathingNode(**node) for node in tree],
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_bettergi_auto_pathing_tree_api失败: {type(e).__name__}: {e}"
        )
        return BetterGIPathingTreeOut(
            code=400
            if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            root=None,
            dirs=[],
        )


@router.get(
    "/bettergi/one-dragon/settings",
    tags=["BetterGI"],
    summary="获取 BetterGI 一条龙设置项（右栏按任务分组展示）",
    response_model=BetterGIOneDragonSettingsOut,
    status_code=200,
)
async def get_bettergi_one_dragon_settings_api(
    scriptId: str, userId: str, configName: str = "", groupName: str = ""
) -> BetterGIOneDragonSettingsOut:
    """返回某用户一条龙配置的设置项（per-user 副本 → BGI 实配 → 内置模板的种子顺序）。

    供右栏按任务分组渲染并回显该任务在 BGI 一条龙里的可设置字段。
    ``groupName`` 为右栏当前编辑的内置组名，战斗 4 项 Plan 回显按其查映射，
    缺省/不匹配时跳过 Plan 回显。
    """

    try:
        script_config = _bettergi_script_config(scriptId)
        _bettergi_user_id(script_config, userId)
        root = _bettergi_root(script_config)
        from app.task.BetterGI.tools import one_dragon

        data = one_dragon.read_user_one_dragon_settings(
            root, scriptId, userId, configName
        )
        # 战斗4项：用 Plan 中的执行层参数回显右栏（原生副本已不再存这些字段）。
        # 第三参必须传 groupName（内置组名），传 configName 会导致 Plan 回显失效。
        data = _read_combat_from_plan(script_config, userId, groupName, "dragon", data)
        return BetterGIOneDragonSettingsOut(
            code=200,
            status="success",
            message=f"共 {len(data)} 项一条龙设置",
            data=data,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_bettergi_one_dragon_settings_api失败: {type(e).__name__}: {e}"
        )
        return BetterGIOneDragonSettingsOut(
            code=400
            if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data={},
        )


@router.post(
    "/bettergi/one-dragon/settings",
    tags=["BetterGI"],
    summary="保存 BetterGI 一条龙设置项到 per-user 副本",
    response_model=OutBase,
    status_code=200,
)
async def save_bettergi_one_dragon_settings_api(
    req: BetterGIOneDragonSettingsIn = Body(...),
) -> OutBase:
    """把右栏编辑的设置项写回该用户一条龙配置副本（不触碰 BGI 同名实配）。"""

    try:
        script_config = _bettergi_script_config(req.scriptId)
        _bettergi_user_id(script_config, req.userId)
        root = _bettergi_root(script_config)
        from app.task.BetterGI.tools import one_dragon

        # 战斗4项：可映射字段仅写 Plan，不可映射字段（如每周秘境表）仍落原生副本。
        # 注意第三参是「右栏当前编辑的内置组名」（前端 groupName），绝不能传 configName——
        # RIGHTBAR_TO_PLAN 按组名（自动秘境/自动地脉花…）查映射，传配置名会导致
        # Plan 路由静默失效，周表/每日行等白名单外键（StrategyName/leyLineDailyEnabled/
        # team/country/LeyLineDefault* 等）全部丢弃。
        native_leftover, new_plan = _route_combat_to_plan(
            script_config, req.userId, req.groupName, req.settings, "dragon"
        )
        if new_plan is not None:
            user_config = _bettergi_user_config(script_config, req.userId)
            await user_config.update(
                type(user_config).model_validate({"OneDragon": {"Plan": new_plan}}),
                check_visibility=False,
            )
        if native_leftover:
            one_dragon.write_user_one_dragon_settings(
                root, req.scriptId, req.userId, req.configName, native_leftover
            )
        return OutBase(
            code=200,
            status="success",
            message=f"已保存 {len(req.settings)} 项一条龙设置",
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"save_bettergi_one_dragon_settings_api失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=400
            if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
        )


@router.post(
    "/bettergi/one-dragon/plan/step-enabled",
    tags=["BetterGI"],
    summary="设置一条龙 Plan 某步骤的启用状态（按实例名，支持 基名-后缀）",
    response_model=OutBase,
    status_code=200,
)
async def set_one_dragon_plan_step_enabled(
    scriptId: str = Query(...),
    userId: str = Query(...),
    name: str = Query(...),
    enabled: bool = Query(True),
) -> OutBase:
    """按步骤名翻转 Plan 中某战斗实例的启用状态（同组多实例各自独立启停）。

    步骤名由行实例 uid 决定（形如 ``自动秘境`` / ``自动秘境-3``），与前端展示用的
    「后名」解耦，改名不会丢设置。本接口只写 Plan（不改原生副本文件），但它是前端
    队列行的启停开关：运行时 build_combat_steps 按 step.enabled 决定是否纳入执行层，
    且 AutoProxy 会把 Plan 中配过实例的战斗组整体从原生副本剔除——因此 enabled=false
    的最终语义是「本次不跑」，而不是「退回原生一条龙跑」。

    步骤不存在时（刚另存为/复制出来的新实例）先创建再设启用——否则开关只改前端、
    后端无步骤可写，刷新后回退。
    """
    from app.task.BetterGI.tools import one_dragon_plan

    try:
        script_config = _bettergi_script_config(scriptId)
        _bettergi_user_id(script_config, userId)
        user_config = _bettergi_user_config(script_config, userId)
        plan = one_dragon_plan.parse_one_dragon_plan(user_config.OneDragon.Plan or "")
        target = next((s for s in plan if s.get("name") == name), None)
        if target is None:
            plan.append(
                {
                    "uid": uuid.uuid4().hex[:12],
                    "kind": "builtin",
                    "name": name,
                    "enabled": enabled,
                    "settings": {},
                }
            )
        else:
            target["enabled"] = enabled
        await user_config.update(
            type(user_config).model_validate(
                {"OneDragon": {"Plan": one_dragon_plan.plan_to_json(plan)}}
            ),
            check_visibility=False,
        )
        return OutBase(
            code=200,
            status="success",
            message=f"已更新步骤 {name} 启用={enabled}",
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"set_one_dragon_plan_step_enabled失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=400
            if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
        )


@router.get(
    "/bettergi/global-domain/settings",
    tags=["BetterGI"],
    summary="获取 BetterGI 全局 config.json 的秘境刷取配置段",
    response_model=BetterGIGlobalDomainSettingsOut,
    status_code=200,
)
async def get_bettergi_global_domain_settings_api(
    scriptId: str, userId: str = "", groupName: str = ""
) -> BetterGIGlobalDomainSettingsOut:
    """返回秘境刷取配置（领奖树脂/分解圣遗物/奖励识别）。

    ``userId`` 非空时以该用户 per-user 副本为权威源（副本缺失回退 BGI 全局实配），
    使独立配置下每个用户的秘境刷取设置互不影响；``userId`` 为空（原生来源模式）读
    BGI 全局 config.json（autoDomainConfig/autoArtifactSalvageConfig，camelCase）。
    """

    try:
        script_config = _bettergi_script_config(scriptId)
        if userId:
            _bettergi_user_id(script_config, userId)
        root = _bettergi_root(script_config)
        from app.task.BetterGI.tools import one_dragon

        data = (
            one_dragon.read_user_global_domain_settings(root, scriptId, userId)
            if userId
            else one_dragon.read_global_domain_settings(root)
        )
        # 战斗4项（自动秘境）的可映射字段（领奖树脂/分解圣遗物/奖励识别等）在 Plan 中回显
        if userId:
            data = _read_combat_from_plan(
                script_config, userId, groupName, "globalDomain", data
            )
        return BetterGIGlobalDomainSettingsOut(
            code=200,
            status="success",
            message=f"共 {len(data)} 项秘境刷取配置",
            data=data,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_bettergi_global_domain_settings_api失败: {type(e).__name__}: {e}"
        )
        return BetterGIGlobalDomainSettingsOut(
            code=400
            if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data={},
        )


@router.post(
    "/bettergi/global-domain/settings",
    tags=["BetterGI"],
    summary="保存 BetterGI 全局 config.json 的秘境刷取配置段",
    response_model=OutBase,
    status_code=200,
)
async def save_bettergi_global_domain_settings_api(
    req: BetterGIGlobalDomainSettingsIn = Body(...),
) -> OutBase:
    """把右栏秘境刷取配置写回 per-user 副本；userId 为空（原生来源模式）写 BGI 全局 config.json。"""

    try:
        script_config = _bettergi_script_config(req.scriptId)
        root = _bettergi_root(script_config)
        from app.task.BetterGI.tools import one_dragon

        if req.userId:
            _bettergi_user_id(script_config, req.userId)
            # 战斗4项（自动秘境）可映射字段仅写 Plan；maxArtifactStar 等全局共享字段仍落副本
            native_leftover, new_plan = _route_combat_to_plan(
                script_config, req.userId, req.groupName, req.settings, "globalDomain"
            )
            if new_plan is not None:
                user_config = _bettergi_user_config(script_config, req.userId)
                await user_config.update(
                    type(user_config).model_validate({"OneDragon": {"Plan": new_plan}}),
                    check_visibility=False,
                )
            if native_leftover:
                one_dragon.write_user_global_domain_settings(
                    req.scriptId, req.userId, native_leftover
                )
        else:
            one_dragon.write_global_domain_settings(root, req.settings)
        return OutBase(
            code=200,
            status="success",
            message=f"已保存 {len(req.settings)} 项秘境刷取配置",
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"save_bettergi_global_domain_settings_api失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=400
            if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
        )


@router.get(
    "/bettergi/global-stygian/settings",
    tags=["BetterGI"],
    summary="获取 BetterGI 全局 config.json 的自动幽境危战设置段",
    response_model=BetterGIGlobalStygianSettingsOut,
    status_code=200,
)
async def get_bettergi_global_stygian_settings_api(
    scriptId: str, userId: str = "", groupName: str = ""
) -> BetterGIGlobalStygianSettingsOut:
    """返回自动幽境危战设置（刷取战场/战斗队伍/战斗策略/次数与树脂）。

    ``userId`` 非空时以该用户 per-user 副本为权威源（副本缺失回退 BGI 全局实配），
    使独立配置下每个用户的幽境设置互不影响；``userId`` 为空（原生来源模式）读
    BGI 全局 config.json（autoStygianOnslaughtConfig 段，camelCase）。
    """

    try:
        script_config = _bettergi_script_config(scriptId)
        if userId:
            _bettergi_user_id(script_config, userId)
        root = _bettergi_root(script_config)
        from app.task.BetterGI.tools import one_dragon

        data = (
            one_dragon.read_user_global_stygian_settings(root, scriptId, userId)
            if userId
            else one_dragon.read_global_stygian_settings(root)
        )
        # 战斗4项（自动幽境危战）全部字段在 Plan 中回显
        if userId:
            data = _read_combat_from_plan(
                script_config, userId, groupName, "globalStygian", data
            )
        return BetterGIGlobalStygianSettingsOut(
            code=200,
            status="success",
            message=f"共 {len(data)} 项幽境危战设置",
            data=data,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_bettergi_global_stygian_settings_api失败: {type(e).__name__}: {e}"
        )
        return BetterGIGlobalStygianSettingsOut(
            code=400
            if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data={},
        )


@router.post(
    "/bettergi/global-stygian/settings",
    tags=["BetterGI"],
    summary="保存 BetterGI 全局 config.json 的自动幽境危战设置段",
    response_model=OutBase,
    status_code=200,
)
async def save_bettergi_global_stygian_settings_api(
    req: BetterGIGlobalStygianSettingsIn = Body(...),
) -> OutBase:
    """把右栏自动幽境危战设置写回 per-user 副本；userId 为空（原生来源模式）写 BGI 全局 config.json。"""

    try:
        script_config = _bettergi_script_config(req.scriptId)
        root = _bettergi_root(script_config)
        from app.task.BetterGI.tools import one_dragon

        if req.userId:
            _bettergi_user_id(script_config, req.userId)
            # 战斗4项（自动幽境危战）全部字段仅写 Plan，不再落全局副本
            native_leftover, new_plan = _route_combat_to_plan(
                script_config, req.userId, req.groupName, req.settings, "globalStygian"
            )
            if new_plan is not None:
                user_config = _bettergi_user_config(script_config, req.userId)
                await user_config.update(
                    type(user_config).model_validate({"OneDragon": {"Plan": new_plan}}),
                    check_visibility=False,
                )
            if native_leftover:
                one_dragon.write_user_global_stygian_settings(
                    req.scriptId, req.userId, native_leftover
                )
        else:
            one_dragon.write_global_stygian_settings(root, req.settings)
        return OutBase(
            code=200,
            status="success",
            message=f"已保存 {len(req.settings)} 项幽境危战设置",
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"save_bettergi_global_stygian_settings_api失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=400
            if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
        )


@router.get(
    "/bettergi/domain-catalog",
    tags=["BetterGI"],
    summary="获取 BetterGI 每周秘境候选与每秘境三档奖励物",
    response_model=BetterGIDomainCatalogOut,
    status_code=200,
)
async def get_bettergi_domain_catalog_api(
    scriptId: str,
) -> BetterGIDomainCatalogOut:
    """返回 BetterGI 每周秘境可选秘境目录与分档奖励物。

    数据源：官方传送点 tp.json（GameTask/AutoTrackPath/Assets/tp.json）中
    Bless/Forgery/Mastery 三类 Domain 点（含奖励物）；tp.json 缺失或为空时返回空目录。
    供「每周秘境」表格的秘境/奖励下拉联动使用（奖励仍按 BGI 语义存 0~3 序号）。
    """

    try:
        script_config = _bettergi_script_config(scriptId)
        root = _bettergi_root(script_config)
        from app.task.BetterGI.tools import one_dragon

        source, items = one_dragon.scan_domain_catalog(root)
        data = [BetterGIDomainCatalogItem(**item) for item in items]
        return BetterGIDomainCatalogOut(
            code=200,
            status="success",
            message=f"共 {len(data)} 个秘境",
            data=data,
            source=source or None,
        )
    except Exception as e:
        return BetterGIDomainCatalogOut(
            code=400
            if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
            source=None,
        )


@router.post(
    "/bettergi/script-group/save",
    tags=["BetterGI"],
    summary="保存 BetterGI 配置组 json 到 per-user 副本",
    response_model=OutBase,
    status_code=200,
)
async def save_bettergi_script_group_api(
    req: BetterGIScriptGroupSaveIn = Body(...),
) -> OutBase:
    """把右栏编辑后的配置组 json（项目顺序 + 各项目 jsScriptSettingsObject）写回
    该用户的 per-user 副本（``data/{script}/{user}/ScriptGroup/{name}.json``）。

    「路径」类引用（名字含 ``/``）不能作文件名，落盘到 ``per_user_copy_name`` 的确定性别名
    （右栏把路径项加成多项目配置组后需要载体）。不触碰 BetterGI 全局
    ``User/ScriptGroup/{name}.json`` 同名实配。
    """

    try:
        script_config = _bettergi_script_config(req.scriptId)
        _bettergi_user_id(script_config, req.userId)
        root = _bettergi_root(script_config)
        from app.task.BetterGI.tools import one_dragon

        projects = (req.data or {}).get("projects")
        if not isinstance(projects, list):
            raise ValueError("projects 必须为数组（按执行顺序的项目列表）")
        out = one_dragon.write_user_script_group(
            root, req.scriptId, req.userId, req.name, req.data
        )
        if out is None:
            # 名为空等无可写内容的情况：按成功返回，不把「配置组名非法」弹给用户
            return OutBase(
                code=200,
                status="success",
                message=f"{req.name} 无需保存副本",
            )
        return OutBase(
            code=200,
            status="success",
            message=f"已保存配置组 {req.name}（共 {len(projects)} 个项目）到用户配置",
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"save_bettergi_script_group_api失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=400
            if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
        )


@router.get(
    "/zzzod/instances",
    tags=["ZZZ-OD"],
    summary="获取 zzz-od 实例（账号）列表",
    response_model=ZzzOdInstancesOut,
    status_code=200,
)
async def get_zzzod_instances_api(scriptId: str) -> ZzzOdInstancesOut:
    """返回 zzz-od 实例列表（供「快速导入」选择来源实例）。"""

    try:
        data = [
            ZzzOdInstanceOut(**item) for item in Config.get_zzzod_instances(scriptId)
        ]
        return ZzzOdInstancesOut(
            code=200,
            status="success",
            message=f"共 {len(data)} 个实例",
            data=data,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_zzzod_instances_api失败: {type(e).__name__}: {e}"
        )
        return ZzzOdInstancesOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
        )


def _zzzod_instances_response(instances: list[dict]) -> ZzzOdInstancesOut:
    """把服务层实例列表包装为统一响应（供直控实例管理各操作复用）。"""

    data = [ZzzOdInstanceOut(**item) for item in instances]
    return ZzzOdInstancesOut(
        code=200,
        status="success",
        message=f"共 {len(data)} 个实例",
        data=data,
    )


@router.post(
    "/zzzod/instances/add",
    tags=["ZZZ-OD"],
    summary="新建一条龙实例（直控实例管理）",
    response_model=ZzzOdInstancesOut,
    status_code=200,
)
async def add_zzzod_instance_api(
    body: ZzzOdInstanceAddIn = Body(...),
) -> ZzzOdInstancesOut:
    """创建实例（最小空闲槽，避开原生与跨脚本 MAS 绑定槽），返回更新后的实例列表。"""

    try:
        return _zzzod_instances_response(
            Config.add_zzzod_instance(body.scriptId, body.name)
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"add_zzzod_instance_api失败: {type(e).__name__}: {e}"
        )
        return ZzzOdInstancesOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
        )


@router.post(
    "/zzzod/instances/rename",
    tags=["ZZZ-OD"],
    summary="重命名一条龙实例（直控实例管理）",
    response_model=ZzzOdInstancesOut,
    status_code=200,
)
async def rename_zzzod_instance_api(
    body: ZzzOdInstanceRenameIn = Body(...),
) -> ZzzOdInstancesOut:
    """只改注册表 name（实例目录不变），返回更新后的实例列表。"""

    try:
        return _zzzod_instances_response(
            Config.rename_zzzod_instance(body.scriptId, body.instanceIdx, body.name)
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"rename_zzzod_instance_api失败: {type(e).__name__}: {e}"
        )
        return ZzzOdInstancesOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
        )


@router.post(
    "/zzzod/instances/active-in-od",
    tags=["ZZZ-OD"],
    summary="切换实例是否参与「全部实例」运行（直控实例管理）",
    response_model=ZzzOdInstancesOut,
    status_code=200,
)
async def set_zzzod_instance_active_in_od_api(
    body: ZzzOdInstanceFlagIn = Body(...),
) -> ZzzOdInstancesOut:
    """切换 active_in_od 标志位，返回更新后的实例列表。"""

    try:
        return _zzzod_instances_response(
            Config.set_zzzod_instance_active_in_od(
                body.scriptId, body.instanceIdx, body.activeInOd
            )
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"set_zzzod_instance_active_in_od_api失败: {type(e).__name__}: {e}"
        )
        return ZzzOdInstancesOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
        )


@router.post(
    "/zzzod/instances/set-active",
    tags=["ZZZ-OD"],
    summary="把所选实例设为当前活跃（直控「选择即运行」）",
    response_model=ZzzOdInstancesOut,
    status_code=200,
)
async def set_zzzod_active_instance_api(
    body: ZzzOdInstanceActiveIn = Body(...),
) -> ZzzOdInstancesOut:
    """把目标实例设为注册表 active（其余清 False），返回更新后的实例列表。"""

    try:
        return _zzzod_instances_response(
            Config.set_zzzod_instance_active(body.scriptId, body.instanceIdx)
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"set_zzzod_active_instance_api失败: {type(e).__name__}: {e}"
        )
        return ZzzOdInstancesOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
        )


@router.post(
    "/zzzod/instances/force-login",
    tags=["ZZZ-OD"],
    summary="切换实例「运行前切换账号」（直控实例管理；一条龙原生能力）",
    response_model=ZzzOdInstancesOut,
    status_code=200,
)
async def set_zzzod_instance_force_login_api(
    body: ZzzOdInstanceForceLoginIn = Body(...),
) -> ZzzOdInstancesOut:
    """切换实例条目的 force_login_before_run（一条龙自己消费），返回更新后的实例列表。"""

    try:
        return _zzzod_instances_response(
            Config.set_zzzod_instance_force_login(
                body.scriptId, body.instanceIdx, body.forceLogin
            )
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"set_zzzod_instance_force_login_api失败: {type(e).__name__}: {e}"
        )
        return ZzzOdInstancesOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
        )


@router.post(
    "/zzzod/instances/run-mode",
    tags=["ZZZ-OD"],
    summary="设置运行实例（原生来源；one_dragon.yml 全局 instance_run）",
    response_model=OutBase,
    status_code=200,
)
async def set_zzzod_instance_run_mode_api(
    body: ZzzOdInstanceRunModeIn = Body(...),
) -> OutBase:
    """白名单校验后写回全局 instance_run（与直控页当前编辑哪个实例无关）。"""

    try:
        Config.set_zzzod_instance_run_mode(body.scriptId, body.instanceRun)
        return OutBase()
    except Exception as e:
        logger.opt(exception=True).warning(
            f"set_zzzod_instance_run_mode_api失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
        )


@router.post(
    "/zzzod/instances/delete",
    tags=["Delete"],
    summary="删除一条龙实例（直控实例管理；受 MAS 绑定槽保护）",
    response_model=ZzzOdInstancesOut,
    status_code=200,
)
async def delete_zzzod_instance_api(
    body: ZzzOdInstanceDeleteIn = Body(...),
) -> ZzzOdInstancesOut:
    """删除注册表条目与实例目录，返回更新后的实例列表。"""

    try:
        return _zzzod_instances_response(
            Config.delete_zzzod_instance(body.scriptId, body.instanceIdx)
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"delete_zzzod_instance_api失败: {type(e).__name__}: {e}"
        )
        return ZzzOdInstancesOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
        )


@router.get(
    "/zzzod/slots",
    tags=["ZZZ-OD"],
    summary="获取实例槽总览（原生实例 / MAS 绑定槽 / 无主残留）",
    response_model=ZzzOdSlotsOut,
    status_code=200,
)
async def get_zzzod_slots_api(scriptId: str) -> ZzzOdSlotsOut:
    """槽目录是 MAS 分配在一条龙安装目录里的，注册表与 GUI 都看不到。

    这份对照表用于诊断「槽目录数与用户数对不上」（绑定但没跑过的槽没有目录）
    与定位无主残留。
    """

    try:
        # 阻塞 IO 在 Config.get_zzzod_slots 内放线程执行，懒导入留在事件循环
        data = [ZzzOdSlotOut(**item) for item in await Config.get_zzzod_slots(scriptId)]
        return ZzzOdSlotsOut(
            code=200,
            status="success",
            message=f"共 {len(data)} 个实例槽",
            data=data,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_zzzod_slots_api失败: {type(e).__name__}: {e}"
        )
        return ZzzOdSlotsOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
        )


@router.post(
    "/zzzod/slots/clean",
    tags=["Delete"],
    summary="清理无主实例槽（先归档进回收池再删目录）",
    response_model=ZzzOdSlotCleanOut,
    status_code=200,
)
async def clean_zzzod_slots_api(
    body: ZzzOdSlotCleanIn = Body(...),
) -> ZzzOdSlotCleanOut:
    """原生实例与被任一 ZzzOd 用户绑定的槽一律不动，返回实际回收的槽号。"""

    try:
        removed = await Config.clean_zzzod_slots(body.scriptId)
        return ZzzOdSlotCleanOut(
            code=200,
            status="success",
            message=f"已回收 {len(removed)} 个实例槽",
            data=removed,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"clean_zzzod_slots_api失败: {type(e).__name__}: {e}"
        )
        return ZzzOdSlotCleanOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
        )


@router.get(
    "/zzzod/recycle",
    tags=["ZZZ-OD"],
    summary="获取实例槽回收池（被删用户/脚本留下的槽内容与备份池快照）",
    response_model=ZzzOdRecycleOut,
    status_code=200,
)
async def get_zzzod_recycle_api(scriptId: str) -> ZzzOdRecycleOut:
    """槽目录按安装根指纹归池，跨脚本共享；只有 ``kind=slot`` 的条目可恢复。"""

    try:
        data = [
            ZzzOdRecycleEntryOut(**item)
            for item in await Config.get_zzzod_recycle(scriptId)
        ]
        return ZzzOdRecycleOut(
            code=200,
            status="success",
            message=f"共 {len(data)} 条回收记录",
            data=data,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_zzzod_recycle_api失败: {type(e).__name__}: {e}"
        )
        return ZzzOdRecycleOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
        )


@router.post(
    "/zzzod/recycle/clear",
    tags=["Delete"],
    summary="清空实例槽回收池（删除后不可找回，不碰配置恢复池）",
    response_model=ZzzOdRecycleClearOut,
    status_code=200,
)
async def clear_zzzod_recycle_api(
    body: ZzzOdRecycleClearIn = Body(...),
) -> ZzzOdRecycleClearOut:
    """只删 recycle 池；onedragon 原生池与 mas 配置恢复池不受影响。"""

    try:
        count = await Config.clear_zzzod_recycle(body.scriptId)
        return ZzzOdRecycleClearOut(
            code=200,
            status="success",
            message=f"已清空回收池（{count} 条）",
            data=count,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"clear_zzzod_recycle_api失败: {type(e).__name__}: {e}"
        )
        return ZzzOdRecycleClearOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=0,
        )


@router.post(
    "/zzzod/recycle/restore",
    tags=["Delete"],
    summary="把回收池里的槽快照恢复给某个 MAS 用户（现有用户或新建用户，先存底）",
    response_model=OutBase,
    status_code=200,
)
async def restore_zzzod_recycle_api(
    body: ZzzOdRecycleRestoreIn = Body(...),
) -> OutBase:
    """恢复的落点是**用户的绑定槽**（``targetUser`` 指定现有用户，或
    ``newUserName`` 新建一个用户）——只物化内容而不建立绑定的恢复没有出口，
    MAS 下次运行不会认领它。目标用户已有绑定槽时覆盖其内容，恢复前先存底。
    """

    try:
        slot, user_name = await Config.restore_zzzod_recycle(
            body.scriptId,
            body.slot,
            body.ts,
            target_user=body.targetUser,
            new_user_name=body.newUserName,
        )
        return OutBase(
            code=200,
            status="success",
            message=f"已恢复到用户「{user_name}」的槽 {slot:02d}（快照 {body.ts}）",
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"restore_zzzod_recycle_api失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
        )


@router.get(
    "/zzzod/teams",
    tags=["ZZZ-OD"],
    summary="获取预备编队列表（名称 + 绑定配队方案）",
    response_model=ZzzOdTeamsOut,
    status_code=200,
)
async def get_zzzod_teams_api(
    scriptId: str,
    userId: str,
    instanceIdx: int | None = None,
) -> ZzzOdTeamsOut:
    """读绑定槽（直控传 instanceIdx 读原生实例）的 team.yml（固定 20 个编队）。"""

    try:
        data = await Config.get_zzzod_teams(scriptId, userId, instance_idx=instanceIdx)
        return ZzzOdTeamsOut(
            code=200,
            status="success",
            message="操作成功",
            teams=[ZzzOdTeamItemOut(**t) for t in data["teams"]],
            autoBattle=data["autoBattle"],
            agentOptions=data["agentOptions"],
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_zzzod_teams_api失败: {type(e).__name__}: {e}"
        )
        return ZzzOdTeamsOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            teams=[],
            autoBattle=[],
        )


@router.post(
    "/zzzod/teams/save",
    tags=["ZZZ-OD"],
    summary="整表保存预备编队（名称 + 绑定配队方案；成员按行保留）",
    response_model=ZzzOdTeamsSaveOut,
    status_code=200,
)
async def save_zzzod_teams_api(
    script: ZzzOdTeamsSaveIn = Body(...),
) -> ZzzOdTeamsSaveOut:
    """直控传 instanceIdx 直接写原生实例，缺省写用户绑定槽。"""

    try:
        saved = await Config.save_zzzod_teams(
            script.scriptId,
            script.userId,
            script.teams,
            instance_idx=script.instanceIdx,
        )
        return ZzzOdTeamsSaveOut(
            code=200,
            status="success",
            message="编队已保存",
            teams=[
                ZzzOdTeamItemOut(
                    idx=i,
                    name=str(item.get("name") or ""),
                    autoBattle=str(item.get("auto_battle") or ""),
                    agents=[str(a) for a in item.get("agent_id_list") or []],
                )
                for i, item in enumerate(saved)
            ],
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"save_zzzod_teams_api失败: {type(e).__name__}: {e}"
        )
        return ZzzOdTeamsSaveOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            teams=[],
        )


@router.get(
    "/zzzod/catalog",
    tags=["ZZZ-OD"],
    summary="获取一条龙任务目录",
    response_model=ZzzOdCatalogOut,
    status_code=200,
)
async def get_zzzod_catalog_api(scriptId: str) -> ZzzOdCatalogOut:
    """静态解析安装目录下的应用注册信息，供用户配置渲染任务卡片中文名。"""

    try:
        # 统一走 _zzzod_root 哨兵校验（空串在此解析成 cwd 的边界被封住）
        root = Config.get_zzzod_root(scriptId)
        from app.task.ZzzOd.tools import (
            get_task_app_fields,
            get_task_app_jump,
            list_app_catalog,
        )

        data = [
            ZzzOdCatalogItemOut(
                **item,
                configurable=get_task_app_fields(str(item["app_id"])) is not None,
                jump=get_task_app_jump(str(item["app_id"])),
            )
            for item in list_app_catalog(root)
        ]
        return ZzzOdCatalogOut(
            code=200,
            status="success",
            message=f"共 {len(data)} 个任务",
            data=data,
        )
    except Exception as e:
        return ZzzOdCatalogOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
        )


@router.get(
    "/zzzod/app-config",
    tags=["ZZZ-OD"],
    summary="获取任务级配置（字段元数据 + 当前值）",
    response_model=ZzzOdAppConfigOut,
    status_code=200,
)
async def get_zzzod_app_config_api(
    scriptId: str,
    userId: str,
    appId: str,
    instanceIdx: int | None = None,
) -> ZzzOdAppConfigOut:
    """返回任务可配置字段、选项与当前值（直控传 instanceIdx 读原生实例，否则读绑定槽）。"""

    try:
        data = await Config.get_zzzod_app_config(
            scriptId, userId, appId, instance_idx=instanceIdx
        )
        return ZzzOdAppConfigOut(
            code=200,
            status="success",
            message="操作成功",
            appId=data["appId"],
            fields=[ZzzOdAppConfigFieldOut(**f) for f in data["fields"]],
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_zzzod_app_config_api失败: {type(e).__name__}: {e}"
        )
        return ZzzOdAppConfigOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            appId=appId,
            fields=[],
        )


@router.get(
    "/zzzod/options",
    tags=["ZZZ-OD"],
    summary="获取任务计划的动态选项（副本级联树/配队方案/挑战配置）",
    response_model=ZzzOdTaskOptionsOut,
    status_code=200,
)
async def get_zzzod_task_options_api(scriptId: str, appId: str) -> ZzzOdTaskOptionsOut:
    """静态读取安装目录（compendium 数据 + 配置目录扫描），与一条龙原生 GUI 选项同源。"""

    try:
        data = await Config.get_zzzod_task_options(scriptId, appId)
        return ZzzOdTaskOptionsOut(
            code=200,
            status="success",
            message="操作成功",
            appId=data["appId"],
            trainCategories=data["trainCategories"],
            lostVoidMissions=data["lostVoidMissions"],
            autoBattle=data["autoBattle"],
            challenge=data["challenge"],
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_zzzod_task_options_api失败: {type(e).__name__}: {e}"
        )
        return ZzzOdTaskOptionsOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            appId=appId,
        )


@router.post(
    "/zzzod/app-config/save",
    tags=["ZZZ-OD"],
    summary="保存任务级配置（绑定槽；直控传 instanceIdx 直接写原生实例）",
    response_model=ZzzOdAppConfigOut,
    status_code=200,
)
async def save_zzzod_app_config_api(
    script: ZzzOdAppConfigSaveIn = Body(...),
) -> ZzzOdAppConfigOut:
    """字段白名单校验后写入 per-app YAML（缺省写用户绑定槽，原生来源写指定原生实例）。"""

    try:
        data = await Config.save_zzzod_app_config(
            script.scriptId,
            script.userId,
            script.appId,
            script.values,
            instance_idx=script.instanceIdx,
        )
        return ZzzOdAppConfigOut(
            code=200,
            status="success",
            message="配置已保存",
            appId=script.appId,
            fields=[
                ZzzOdAppConfigFieldOut(
                    field=str(k), title=str(k), value=str(v), options=[]
                )
                for k, v in data.items()
            ],
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"save_zzzod_app_config_api失败: {type(e).__name__}: {e}"
        )
        return ZzzOdAppConfigOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            appId=script.appId,
            fields=[],
        )


@router.get(
    "/bettergi/game-info",
    tags=["BetterGI"],
    summary="获取游戏客户端信息（路径 + 渠道，用户页透传展示）",
    response_model=BetterGIGameInfoOut,
    status_code=200,
)
async def get_bettergi_game_info_api(
    scriptId: str, detectPath: str = ""
) -> BetterGIGameInfoOut:
    """读取 BetterGI 配置的游戏路径并识别客户端渠道（官服/B服/国际服）。

    ``detectPath`` 非空时对该路径做渠道识别（用户自填路径的即时标注），
    为空时返回生效路径（用户级优先，否则 BGI 全局配置）及其渠道。
    """

    try:
        script_config = _bettergi_script_config(scriptId)
        root = _bettergi_root(script_config)
        from app.task.BetterGI.tools import game_info

        data = game_info.read_game_info(root, detectPath)
        return BetterGIGameInfoOut(
            code=200,
            status="success",
            message="操作成功",
            installPath=data["installPath"],
            globalPath=data["globalPath"],
            channel=data["channel"],
            source=data["source"],
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_bettergi_game_info_api失败: {type(e).__name__}: {e}"
        )
        return BetterGIGameInfoOut(
            code=400
            if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
        )


@router.get(
    "/zzzod/native-config",
    tags=["ZZZ-OD"],
    summary="获取实例原生配置（直控页面表单数据）",
    response_model=ZzzOdNativeConfigOut,
    status_code=200,
)
async def get_zzzod_native_config_api(
    scriptId: str, instanceIdx: int
) -> ZzzOdNativeConfigOut:
    """读取所选实例 game_account.yml 与 _group.yml（含默认值合并与任务目录并入）。"""

    try:
        data = await Config.get_zzzod_native_config(scriptId, instanceIdx)
        return ZzzOdNativeConfigOut(
            code=200,
            status="success",
            message="操作成功",
            instanceIdx=data["instanceIdx"],
            instanceName=data["instanceName"],
            account=[ZzzOdNativeAccountField(**f) for f in data["account"]],
            tasks=[ZzzOdNativeTaskOut(**t) for t in data["tasks"]],
            instanceRun=data["instanceRun"],
            launchArgs=ZzzOdNativeLaunchArgs(**data["launchArgs"]),
            afterDone=data["afterDone"],
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_zzzod_native_config_api失败: {type(e).__name__}: {e}"
        )
        return ZzzOdNativeConfigOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            instanceIdx=instanceIdx,
            instanceName="",
            account=[],
            tasks=[],
            instanceRun="仅运行当前",
            afterDone="无",
        )


@router.post(
    "/zzzod/native-config/save",
    tags=["ZZZ-OD"],
    summary="保存实例原生配置（原生来源模式直接写回一条龙原始 YAML）",
    response_model=ZzzOdNativeConfigOut,
    status_code=200,
)
async def save_zzzod_native_config_api(
    script: ZzzOdNativeConfigIn = Body(...),
) -> ZzzOdNativeConfigOut:
    """白名单过滤后写回所选实例 game_account.yml、_group.yml、instance_run 与 after_done，随后回读最新数据。"""

    try:
        await Config.save_zzzod_native_config(
            script.scriptId,
            script.instanceIdx,
            script.account,
            [t.model_dump() for t in script.tasks]
            if script.tasks is not None
            else None,
            script.instanceRun,
            script.launchArgs.model_dump() if script.launchArgs is not None else None,
            script.afterDone,
        )
        data = await Config.get_zzzod_native_config(script.scriptId, script.instanceIdx)
        return ZzzOdNativeConfigOut(
            code=200,
            status="success",
            message="配置已保存到一条龙原生配置",
            instanceIdx=data["instanceIdx"],
            instanceName=data["instanceName"],
            account=[ZzzOdNativeAccountField(**f) for f in data["account"]],
            tasks=[ZzzOdNativeTaskOut(**t) for t in data["tasks"]],
            instanceRun=data["instanceRun"],
            afterDone=data["afterDone"],
            launchArgs=ZzzOdNativeLaunchArgs(**data["launchArgs"]),
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"save_zzzod_native_config_api失败: {type(e).__name__}: {e}"
        )
        return ZzzOdNativeConfigOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            instanceIdx=script.instanceIdx,
            instanceName="",
            account=[],
            tasks=[],
            instanceRun="仅运行当前",
            afterDone=script.afterDone or "无",
        )


@router.get(
    "/zzzod/launchers",
    tags=["ZZZ-OD"],
    summary="获取一条龙两种启动器的安装情况与默认项",
    response_model=ZzzOdLauncherOut,
    status_code=200,
)
async def get_zzzod_launchers_api(scriptId: str) -> ZzzOdLauncherOut:
    """渲染「启动器」下拉用（native/shared 两态通用）：未安装的启动器选项禁用变灰。"""

    try:
        data = Config.get_zzzod_launchers(scriptId)
        return ZzzOdLauncherOut(code=200, status="success", message="", **data)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_zzzod_launchers_api失败: {type(e).__name__}: {e}"
        )
        return ZzzOdLauncherOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            original_available=False,
            integrated_available=False,
        )


@router.post(
    "/zzzod/import",
    tags=["ZZZ-OD"],
    summary="基于一条龙已有实例快速生成当前用户配置（覆盖前自动归档当前配置）",
    response_model=ZzzOdImportOut,
    status_code=200,
)
async def import_zzzod_config_api(
    script: ZzzOdImportIn = Body(...),
) -> ZzzOdImportOut:
    """把来源实例的账号信息与已启用任务编排写入本用户；覆盖前强制归档当前 MAS 槽配置，
    导入前状态可在「配置恢复」中找回。"""

    try:
        data = await Config.import_zzzod_config(
            script.scriptId, script.userId, script.instanceIdx
        )
        return ZzzOdImportOut(
            code=200,
            status="success",
            message="已基于所选实例生成用户配置",
            **data,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"import_zzzod_config_api失败: {type(e).__name__}: {e}"
        )
        return ZzzOdImportOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            instanceIdx=-1,
            instanceName="",
            importedAccountCount=0,
            importedTaskCount=0,
            slot=-1,
        )


@router.get(
    "/hsr/capabilities",
    tags=["HSR"],
    summary="获取内置 HSR 能力快照",
    response_model=HSRCapabilitiesOut,
    status_code=200,
)
async def get_hsr_capabilities_api(scriptId: str | None = None) -> HSRCapabilitiesOut:
    """返回内置 HSR 的能力快照，不暴露原生编辑器会话。"""

    from app.task.HSR import api_service as hsr_api

    reply = await hsr_api.get_capabilities(scriptId)
    return HSRCapabilitiesOut(**reply.out_fields())


@router.post(
    "/hsr/update",
    tags=["HSR"],
    summary="检查或执行 HSR 外部脚本更新",
    response_model=HSRUpdateOut,
    status_code=200,
)
async def post_hsr_update_api(data: HSRUpdateIn) -> HSRUpdateOut:
    """手动检查或安装 M7A / SRA 的更新。

    自动更新只在任务正常跑完后触发（``Update.AutoUpdateMode = AfterRun``），
    这个接口是唯一不必等一轮任务就能更新的入口。
    """

    from app.task.HSR import api_service as hsr_api

    reply = await hsr_api.update_engine(data.scriptId, data.engine, data.action)
    return HSRUpdateOut(**reply.out_fields())


@router.post(
    "/hsr/cloud-login",
    tags=["HSR"],
    summary="为 HSR 用户登录云·星穹铁道",
    response_model=HSRCloudLoginOut,
    status_code=200,
)
async def post_hsr_cloud_login_api(data: HSRCloudLoginIn) -> HSRCloudLoginOut:
    """起该用户的云浏览器并用三月七的 ``game`` 任务等用户在窗口里登录。

    阻塞到三月七退出为止（最长为登录等待 + 最长排队 + 余量），与正在运行的
    任务互斥：脚本运行中或三月七目录被占用时返回 409。成功后写
    ``Cloud.LastLogin``。
    """

    from app.task.HSR import api_service as hsr_api

    reply = await hsr_api.cloud_login(data.scriptId, data.userId)
    return HSRCloudLoginOut(**reply.out_fields())


@router.get(
    "/hsr/managed-config",
    tags=["HSR"],
    summary="获取 HSR 托管配置字段",
    response_model=HSRManagedConfigOut,
    status_code=200,
)
async def get_hsr_managed_config_api(
    scriptId: str | None = None, userId: str | None = None
) -> HSRManagedConfigOut:
    """返回原生动态托管字段。

    传了用户 ID 时先做归属校验，再按该用户的配置来源决定表单读哪份计划：
    「脚本」读脚本共享计划，「用户」读该用户自己的计划；不传用户 ID 时读
    脚本共享计划。响应的 ``plan_owner`` 指明保存目标。
    """

    from app.task.HSR import api_service as hsr_api

    reply = await hsr_api.get_managed_config(scriptId, userId)
    return HSRManagedConfigOut(**reply.out_fields())


@router.get(
    "/hsr/sra-profiles",
    tags=["HSR"],
    summary="获取 HSR 可选的 SRA 配置档案",
    response_model=HSRSRAProfilesOut,
    status_code=200,
)
async def get_hsr_sra_profiles_api(scriptId: str | None = None) -> HSRSRAProfilesOut:
    """列出 ``%APPDATA%/SRA/configs`` 下的配置档案，并标出脚本当前生效的那份。"""

    from app.task.HSR import api_service as hsr_api

    reply = await hsr_api.get_sra_profiles(scriptId)
    return HSRSRAProfilesOut(**reply.out_fields())


@router.get(
    "/whimbox/task-catalog",
    tags=["Whimbox"],
    summary="获取奇想盒一条龙任务目录",
    response_model=WhimboxTaskCatalogOut,
    status_code=200,
)
async def get_whimbox_task_catalog_api(
    scriptId: str | None = None,
) -> WhimboxTaskCatalogOut:
    """下发一条龙任务目录（步骤开关 + 目标/参数字段）。

    字段定义与值域从上游安装目录三件套（default_config / setting_options /
    material）运行时机械转换，MAS 发版不管理；上游升级后下次读取自动生效。
    """

    try:
        if not scriptId:
            return WhimboxTaskCatalogOut(
                code=400, status="error", message="缺少 scriptId"
            )
        script_config = _whimbox_script_config(scriptId)
        surface = WheelAssetsConfigSurface(Path(str(script_config.Info.RootPath or "")))
        install_error = surface.check_install()
        if install_error:
            return WhimboxTaskCatalogOut(
                code=400, status="error", message=install_error
            )
        catalog = surface.read_catalog()
        data = WhimboxTaskCatalogData(
            steps=[
                WhimboxTaskCatalogItem(key=s.key, display=s.display, section=s.section)
                for s in catalog.steps
            ],
            options=[
                WhimboxOptionCatalogItem(
                    key=o.key,
                    display=o.display,
                    section=o.section,
                    field_type=o.field_type,
                    options=list(o.options),
                    default=o.default,
                )
                for o in catalog.options
            ],
            upstream_version=catalog.upstream_version,
        )
        return WhimboxTaskCatalogOut(
            message=f"共 {len(data.steps)} 个步骤, {len(data.options)} 个参数字段",
            data=data,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_whimbox_task_catalog_api失败: {type(e).__name__}: {e}"
        )
        return WhimboxTaskCatalogOut(
            code=400
            if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
        )


@router.post(
    "/oknte/configs/list",
    tags=["OKNTE"],
    summary="获取 OK-NTE 配置文件列表及 schema",
    status_code=200,
)
async def get_oknte_configs_list(script_id: str, user_id: str):
    """
    获取 OK-NTE 配置文件列表及 schema 定义。
    读写用户快速配置目录，首次从已有来源初始化，不修改来源文件。

    Args:
        script_id: OK-NTE 脚本 ID
        user_id: 用户 ID

    Returns:
        dict: 包含配置文件列表和 schema 的响应
    """
    try:
        import json

        from app.task.OkNte.config_schema import (
            build_fields_for_config,
            get_all_config_info,
            load_oknte_option_labels,
        )

        _, script_config = _oknte_script_config(script_id)

        # 从 ok-nte 安装目录加载翻译 → option_labels
        root_path = script_config.Info.RootPath
        option_labels = load_oknte_option_labels(root_path) if root_path else {}

        # 面板与来源分别保存；切换来源不重置面板。
        mas_config_dir = _oknte_mas_config_dir(script_id, user_id)

        configs_info = get_all_config_info()
        if script_config.Script.ConfigPathMode == "File":
            config_path = script_config.Script.ConfigPath
            if config_path is None:
                raise ValueError("ConfigPath未配置，请检查路径设置")
            filename = config_path.name
            configs_info = [
                info for info in configs_info if info["filename"] == filename
            ]

        # 读取 per-user JSON 配置，通过 build_fields_for_config 构建字段列表
        result = []
        for info in configs_info:
            filename = info["filename"]
            filepath = _oknte_config_file_path(mas_config_dir, filename)
            current_data: dict[str, Any] = {}
            parse_error = False
            if filepath.exists():
                try:
                    current_data = json.loads(filepath.read_text(encoding="utf-8"))
                except Exception as e:
                    # 解析失败按空数据构建字段, 但要让前端知道这份配置没读出来
                    parse_error = True
                    logger.warning(
                        f"OkNte 配置解析失败: {filepath}: {type(e).__name__}: {e}"
                    )

            fields = build_fields_for_config(filename, current_data, option_labels)

            result.append(
                {
                    **info,
                    "fields": fields,
                    "currentData": current_data,
                    "parseError": parse_error,
                }
            )

        return {
            "code": 200,
            "status": "success",
            "message": f"共 {len(result)} 个配置文件",
            "data": result,
            "optionLabels": option_labels,
            "configPath": str(mas_config_dir) if mas_config_dir else None,
        }
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_oknte_configs_list失败: {type(e).__name__}: {e}"
        )
        return {
            "code": 500,
            "status": "error",
            "message": f"{type(e).__name__}: {str(e)}",
            "data": [],
        }


@router.post(
    "/oknte/configs/batch-update",
    tags=["OKNTE"],
    summary="批量更新 OK-NTE 配置文件",
    status_code=200,
)
async def batch_update_oknte_configs(
    script_id: str = Body(...),
    user_id: str = Body(...),
    configs: dict = Body(...),
):
    """
    批量更新 OK-NTE 配置文件

    Args:
        script_id: OK-NTE 脚本 ID
        user_id: 用户 ID
        configs: { filename: data } 格式的配置数据

    Returns:
        dict: 操作结果
    """
    try:
        from app.task.OkNte.config_schema import update_oknte_config_data

        # 写入用户配置目录
        mas_config_dir = _oknte_mas_config_dir(script_id, user_id)
        mas_config_dir.mkdir(parents=True, exist_ok=True)
        _, script_config = _oknte_script_config(script_id)
        if script_config.Script.ConfigPathMode == "File":
            config_path = script_config.Script.ConfigPath
            if config_path is None:
                raise ValueError("ConfigPath未配置，请检查路径设置")
            filename = config_path.name
            if set(configs) - {filename}:
                raise ValueError("单文件模式只能编辑所选配置文件")

        updated_files = []
        for filename, data in configs.items():
            filepath = _oknte_config_file_path(mas_config_dir, filename)
            update_oknte_config_data(filepath, data)
            updated_files.append(filename)

        return {
            "code": 200,
            "status": "success",
            "message": f"已更新 {len(updated_files)} 个配置文件",
            "data": updated_files,
        }
    except Exception as e:
        logger.opt(exception=True).warning(
            f"batch_update_oknte_configs失败: {type(e).__name__}: {e}"
        )
        return {
            "code": 500,
            "status": "error",
            "message": f"{type(e).__name__}: {str(e)}",
        }


@router.get(
    "/backup/list",
    tags=["Backup"],
    summary="列出配置备份（时间倒序；target 取值由专项定义，非法值返回 400）",
    response_model=ConfigBackupListOut,
    status_code=200,
)
async def list_config_backups_api(
    scriptId: str, userId: str, target: str
) -> ConfigBackupListOut:
    """返回 ``items``（``time`` + 备份时点来源标注 ``base``，倒序）与当前
    来源 ``base``（仅三态池，供前端跨来源提示）；非法 target 返回 400。"""

    try:
        data = await Config.list_config_backups(scriptId, userId, target)
        return ConfigBackupListOut(
            code=200,
            status="success",
            message=f"共 {len(data['items'])} 份备份",
            base=data["base"],
            data=[ConfigBackupItemOut(**item) for item in data["items"]],
        )
    except Exception as e:
        logger.opt(exception=True).warning(f"配置备份列表查询失败: {e}")
        return ConfigBackupListOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
        )


@router.post(
    "/backup/ensure",
    tags=["Backup"],
    summary="按需归档目标池当前配置（指纹去重，无变化跳过；编辑界面进入/退出时机调用）",
    response_model=ConfigBackupEnsureOut,
    status_code=200,
)
async def ensure_config_backup_api(
    script: ConfigBackupEnsureIn = Body(...),
) -> ConfigBackupEnsureOut:
    """target 取值由专项池定义（如 zzz-od 的 mas/onedragon、ok-nte 的 mas/native）。"""

    try:
        data = await Config.ensure_config_backup(
            script.scriptId, script.userId, target=script.target
        )
        return ConfigBackupEnsureOut(
            code=200,
            status="success",
            message="",
            **data,
        )
    except ConfigCorruptedError as e:
        # 源配置损坏：message 用原文（含损坏位置）直达用户，前端编辑页会透传
        logger.opt(exception=True).warning(f"配置按需归档失败（源配置损坏）: {e}")
        return ConfigBackupEnsureOut(
            code=400,
            status="error",
            message=str(e),
            created=False,
            time="",
        )
    except Exception as e:
        logger.opt(exception=True).warning(f"配置按需归档失败: {e}")
        return ConfigBackupEnsureOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            created=False,
            time="",
        )


@router.post(
    "/backup/restore",
    tags=["Backup"],
    summary="把指定备份恢复到目标位置（恢复前自动存底当前配置，误恢复可找回）",
    response_model=ConfigBackupRestoreOut,
    status_code=200,
)
async def restore_config_backup_api(
    script: ConfigBackupRestoreIn = Body(...),
) -> ConfigBackupRestoreOut:
    """恢复语义由专项池定义：脚本原生池恢复到脚本本体，MAS 用户池恢复到
    用户配置并按需回填前端表单。备份来自其他配置来源（脚本级/用户级）时
    由服务层把配置来源切回备份时点再恢复；提示由前端据备份列表与当前
    来源比对给出。"""

    try:
        data = await Config.restore_config_backup(
            script.scriptId,
            script.userId,
            script.time,
            target=script.target,
            force=script.force,
        )
        return ConfigBackupRestoreOut(
            code=200,
            status="success",
            message=f"已恢复备份 {script.time}",
            target=data["target"],
        )
    except ConfigCorruptedError as e:
        # 源配置损坏：带损坏位置返回 409，前端弹二次确认后携带 force 重试
        logger.opt(exception=True).warning(f"配置备份恢复被拦截（源配置损坏）: {e}")
        return ConfigBackupRestoreOut(
            code=409,
            status="error",
            message=str(e),
            target=script.target,
        )
    except Exception as e:
        logger.opt(exception=True).warning(f"配置备份恢复失败: {e}")
        return ConfigBackupRestoreOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            target=script.target,
        )


@router.get(
    "/backup/preview",
    tags=["Backup"],
    summary="读取指定备份的配置摘要（纯读不恢复，供「预览配置」快速展示）",
    response_model=ConfigBackupPreviewOut,
    status_code=200,
)
async def get_config_backup_preview_api(
    scriptId: str, userId: str, time: str, target: str
) -> ConfigBackupPreviewOut:
    """data 载荷结构由专项定义（前端按 target 消费）；非法 target 返回 400。"""

    try:
        data = await Config.get_config_backup_preview(
            scriptId, userId, time, target=target
        )
        return ConfigBackupPreviewOut(
            code=200,
            status="success",
            message="",
            **data,
        )
    except Exception as e:
        logger.opt(exception=True).warning(f"配置备份预览失败: {e}")
        return ConfigBackupPreviewOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            time=time,
            target=target,
            data={},
        )


@router.get(
    "/backup/file",
    tags=["Backup"],
    summary="只读读取指定备份内一个文本文件（预览「查看原始文件」用，路径限归档内）",
    response_model=ConfigBackupFileOut,
    status_code=200,
)
async def get_config_backup_file_api(
    scriptId: str, userId: str, time: str, target: str, path: str
) -> ConfigBackupFileOut:
    """路径越界/文件超限/池未实现查看能力均返回 400，message 说明原因。"""

    try:
        data = await Config.get_config_backup_file(
            scriptId, userId, time, target=target, path=path
        )
        return ConfigBackupFileOut(
            code=200,
            status="success",
            message="",
            **data,
        )
    except Exception as e:
        logger.opt(exception=True).warning(f"配置备份文件读取失败: {e}")
        return ConfigBackupFileOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            time=time,
            target=target,
            path=path,
            size=0,
            content="",
        )


@router.get(
    "/maafw/asset",
    tags=["MaaFW"],
    summary="读取 MFW 项目内的图片资源",
    response_class=FileResponse,
)
async def get_maafw_asset(
    root: str = Query(..., description="MFW 项目根目录"),
    path: str = Query(..., description="项目根目录内的相对图片路径"),
) -> FileResponse:
    """把 MFW 项目目录内的图片按需读给前端。

    任务说明（interface 的 ``doc`` / ``description``）是 markdown，里面的图片写的是
    **项目内相对路径**，浏览器没法直接读本地文件，必须由后端转一手。

    前端侧对应 ``buildMaaFWAssetUrl``：它已经拦掉了绝对路径、UNC、上跳与远程 URL，
    但那只是省一次往返，安全边界在这里 —— 请求可以绕过前端直接打过来。
    """

    try:
        file_path = maafw_interface_api.maafw_asset_file_path(root, path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileResponse(file_path)


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
        )
        return MaaCopilotAnalyzeOut(**result)
    except ValueError as exc:
        return MaaCopilotAnalyzeOut(code=400, status="error", message=str(exc))
    except Exception:
        logger.opt(exception=True).warning("作业练度分析失败")
        return MaaCopilotAnalyzeOut(
            code=500, status="error", message="作业分析失败，请检查账号绑定和网络后重试"
        )
