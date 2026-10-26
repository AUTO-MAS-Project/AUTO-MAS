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
"""脚本管理：BetterGI 路由与端点专用模型。"""

from typing import (
    Any,
    Dict,
    List,
    Literal,
    Optional,
)

from fastapi import APIRouter, Body, Query
from pydantic import (
    BaseModel,
    Field,
)

from app.models.schema import (
    ComboBoxItem,
    ComboBoxOut,
    OutBase,
)
from app.utils import get_logger


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


router = APIRouter()
logger = get_logger("脚本管理 API")


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
        from app.task.BetterGI import api_service as bettergi_api

        names = bettergi_api.list_strategies(scriptId)
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
        from app.task.BetterGI import api_service as bettergi_api

        items = bettergi_api.list_custom_groups(
            scriptId,
            user_id=userId,
            config_name=configName,
            use_mas_config=useMasConfig,
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
    "/bettergi/one-dragon/configs",
    tags=["BetterGI"],
    summary="获取 BetterGI 一条龙配置名列表",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_bettergi_one_dragon_configs_api(scriptId: str) -> ComboBoxOut:
    """返回 BetterGI 可选一条龙配置名：{RootPath}/User/OneDragon/*.json 文件名（默认配置置顶）。"""

    try:
        from app.task.BetterGI import api_service as bettergi_api

        names = bettergi_api.list_one_dragon_configs(scriptId)
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
        from app.task.BetterGI import api_service as bettergi_api

        items = bettergi_api.list_js_scripts(scriptId)
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
        from app.task.BetterGI import api_service as bettergi_api

        names = bettergi_api.list_key_mouse_scripts(scriptId)
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
        from app.task.BetterGI import api_service as bettergi_api

        names = bettergi_api.list_script_groups(scriptId, userId)
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
        from app.task.BetterGI import api_service as bettergi_api

        data = bettergi_api.read_script_group(scriptId, userId, name=name)
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
        from app.task.BetterGI import api_service as bettergi_api

        ui = bettergi_api.read_script_settings_ui(scriptId, folder)
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
        from app.task.BetterGI import api_service as bettergi_api

        text = bettergi_api.read_script_readme(scriptId, folder)
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
        from app.task.BetterGI import api_service as bettergi_api

        dirs = bettergi_api.resolve_script_dirs(scriptId)
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
        from app.task.BetterGI import api_service as bettergi_api

        root_dir, tree = bettergi_api.read_auto_pathing_tree(scriptId)
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
        from app.task.BetterGI import api_service as bettergi_api

        data = bettergi_api.read_one_dragon_settings(
            scriptId, userId, config_name=configName, group_name=groupName
        )
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
        from app.task.BetterGI import api_service as bettergi_api

        await bettergi_api.save_one_dragon_settings(
            req.scriptId,
            req.userId,
            config_name=req.configName,
            group_name=req.groupName,
            settings=req.settings,
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

    try:
        from app.task.BetterGI import api_service as bettergi_api

        await bettergi_api.set_plan_step_enabled(
            scriptId, userId, name=name, enabled=enabled
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
        from app.task.BetterGI import api_service as bettergi_api

        data = bettergi_api.read_global_domain_settings(
            scriptId, userId, group_name=groupName
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
        from app.task.BetterGI import api_service as bettergi_api

        await bettergi_api.save_global_domain_settings(
            req.scriptId, req.userId, group_name=req.groupName, settings=req.settings
        )
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
        from app.task.BetterGI import api_service as bettergi_api

        data = bettergi_api.read_global_stygian_settings(
            scriptId, userId, group_name=groupName
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
        from app.task.BetterGI import api_service as bettergi_api

        await bettergi_api.save_global_stygian_settings(
            req.scriptId, req.userId, group_name=req.groupName, settings=req.settings
        )
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
        from app.task.BetterGI import api_service as bettergi_api

        source, items = bettergi_api.read_domain_catalog(scriptId)
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
        from app.task.BetterGI import api_service as bettergi_api

        out, project_count = bettergi_api.save_script_group(
            req.scriptId, req.userId, name=req.name, data=req.data
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
            message=f"已保存配置组 {req.name}（共 {project_count} 个项目）到用户配置",
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
        from app.task.BetterGI import api_service as bettergi_api

        data = bettergi_api.read_game_info(scriptId, detectPath)
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
