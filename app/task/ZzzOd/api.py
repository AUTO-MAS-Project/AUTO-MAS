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
"""脚本管理：ZZZ-OD 路由与端点专用模型。"""

from typing import (
    Any,
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

from app.core import Config
from app.models.schema import (
    ComboBoxItem,
    OutBase,
)
from app.utils import get_logger


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


def _zzzod_instances_response(instances: list[dict]) -> ZzzOdInstancesOut:
    """把服务层实例列表包装为统一响应（供直控实例管理各操作复用）。"""

    data = [ZzzOdInstanceOut(**item) for item in instances]
    return ZzzOdInstancesOut(
        code=200,
        status="success",
        message=f"共 {len(data)} 个实例",
        data=data,
    )


router = APIRouter()
logger = get_logger("脚本管理 API")


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
        from app.task.ZzzOd import api_service as zzzod_api

        data = [
            ZzzOdCatalogItemOut(**item)
            for item in zzzod_api.get_task_catalog(Config, scriptId)
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
        from app.task.ZzzOd import api_service as zzzod_api

        data = await zzzod_api.save_native_config(
            Config,
            script_id=script.scriptId,
            instance_idx=script.instanceIdx,
            account=script.account,
            tasks=[t.model_dump() for t in script.tasks]
            if script.tasks is not None
            else None,
            instance_run=script.instanceRun,
            launch_args=script.launchArgs.model_dump()
            if script.launchArgs is not None
            else None,
            after_done=script.afterDone,
        )
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
