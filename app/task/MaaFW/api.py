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
"""脚本管理：MaaFW 路由与端点专用模型。"""

from typing import (
    Any,
    Dict,
    List,
    Literal,
    Optional,
)

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import (
    BaseModel,
    Field,
)

from app.models.schema import (
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
)
from app.task.MaaFW.api_service import agent_env as maafw_agent_env_api
from app.task.MaaFW.api_service import embedded as maafw_embedded_api
from app.task.MaaFW.api_service import interface as maafw_interface_api
from app.task.MaaFW.api_service import shell_instances as maafw_shell_instances_api
from app.task.MaaFW.api_service import update as maafw_update_api
from app.utils import get_logger


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


router = APIRouter()
logger = get_logger("脚本管理 API")


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


@router.get(
    "/maafw/icon",
    tags=["MaaFW"],
    summary="读取 MFW 脚本的项目图标",
    response_class=FileResponse,
)
async def get_maafw_script_icon(
    scriptId: str = Query(..., description="MFW 脚本 ID"),
) -> FileResponse:
    """脚本列表的头像：项目 interface 顶层 ``icon`` 指的图片。

    取不到（项目还没导入、没写 icon、文件不在）一律 404，前端回退到类型图标。
    项目更新可能原地换掉图标而地址不变，所以带 ``no-cache``，让浏览器每次凭 ETag 确认。
    """

    try:
        file_path = await maafw_interface_api.maafw_script_icon_file(scriptId)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(file_path, headers={"Cache-Control": "no-cache"})
