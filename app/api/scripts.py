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


import asyncio
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Body

from app.core import Config
from app.models.config import HSRConfig as RuntimeHSRConfig
from app.models.config import MaaFWConfig as RuntimeMaaFWConfig
from app.models.config import OkNteConfig as RuntimeOkNteConfig
from app.models.schema import *
from app.task.MaaFW.tools.core.automas_maafw_interface.loader import (
    MaaFWInterfaceLoadError,
    load_interface_model,
)
from app.task.MaaFW.tools.core.automas_maafw_interface.preview import (
    build_interface_preview_data,
)
from app.task.MaaFW.tools.core.automas_maafw_project_update import (
    MaaFWProjectUpdateError,
    discover_maafw_project_update,
)
from app.task.MaaFW.tools.external import ShellFamily, detect_shell_family
from app.task.MaaFW.tools.project_updater import update_maafw_project_if_needed

router = APIRouter(prefix="/api/scripts", tags=["脚本管理"])


def _hsr_script_config(script_id: str):
    """Resolve an HSR script and reject cross-type IDs before domain access."""

    script_config = Config.ScriptConfig[uuid.UUID(script_id)]
    if not isinstance(script_config, RuntimeHSRConfig):
        raise TypeError("脚本配置类型错误, 不是 HSR 类型")
    return script_config


def _hsr_user_config(script_config: RuntimeHSRConfig, user_id: str):
    user_config = script_config.UserData[uuid.UUID(user_id)]
    return user_config


def _oknte_script_config(script_id: str) -> tuple[uuid.UUID, RuntimeOkNteConfig]:
    script_uid = uuid.UUID(script_id)
    script_config = Config.ScriptConfig[script_uid]
    if not isinstance(script_config, RuntimeOkNteConfig):
        raise ValueError("脚本配置类型错误, 不是 OK-NTE 类型")
    return script_uid, script_config


def _oknte_legacy_mas_config_dir(script_id: str) -> Path:
    script_uid, _ = _oknte_script_config(script_id)
    return Path.cwd() / "data" / str(script_uid) / "Default" / "ConfigFile"


def _oknte_mas_config_dir(script_id: str, user_id: str) -> Path:
    script_uid, _ = _oknte_script_config(script_id)
    user_uid = uuid.UUID(user_id)
    return Path.cwd() / "data" / str(script_uid) / str(user_uid) / "ConfigFile"


def _oknte_config_file_path(config_dir: Path, filename: str) -> Path:
    file_path = Path(filename)
    if (
        file_path.name != filename
        or file_path.is_absolute()
        or ".." in file_path.parts
    ):
        raise ValueError("配置文件名非法")
    return config_dir / filename


def _maafw_script_config(script_id: str) -> RuntimeMaaFWConfig:
    """Resolve a MaaFW script and reject cross-type IDs before domain access."""

    script_config = Config.ScriptConfig[uuid.UUID(script_id)]
    if not isinstance(script_config, RuntimeMaaFWConfig):
        raise TypeError("脚本配置类型错误, 不是 MaaFW 类型")
    return script_config


def _maafw_update_source_config(script_config: RuntimeMaaFWConfig) -> dict[str, str]:
    """按脚本级 Update.* 组装更新实现所需的 source_config。

    键名与 ``project_updater._compat_source_config`` 一致；留空字段代表
    「继承全局」，此处照原样透传，由更新实现层决定回退。

    额外注入 ``project_shell_hint``：GitHub 发行版常按 UI 外壳分包
    （如 M9A 同版本同时发 ``*-MFAA.zip`` 与 ``*-MXU.zip``），选包实现
    在项目名/平台收窄后需要外壳家族才能消歧。``fdde4d51`` 经服务层
    ``MaaFWProjectUpdateService.discover_update`` 注入该提示，当前 API
    直连 ``discover_maafw_project_update``，故在此按项目根目录识别。
    """

    source = str(script_config.get("Update", "Source") or "").strip()
    config = {
        "source": source,
        "package_source": source,
        "mirror_cdk": str(script_config.get("Update", "MirrorChyanCDK") or "").strip(),
        "channel": str(script_config.get("Update", "Channel") or "").strip(),
        "repo": str(script_config.get("Update", "GitHubRepo") or "").strip(),
        "tag": str(script_config.get("Update", "GitHubTag") or "").strip(),
        "asset_pattern": str(
            script_config.get("Update", "GitHubAssetPattern") or ""
        ).strip(),
    }
    project_path = str(script_config.get("Info", "Path") or "").strip()
    if project_path:
        shell_family = detect_shell_family(project_path)
        if shell_family is not ShellFamily.UNKNOWN:
            config["project_shell_hint"] = shell_family.value
    return config


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
        data = SCRIPT_BOOK[type(config).__name__](**(await config.toDict()))
    except Exception as e:
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
        index = [ScriptIndexItem(**_) for _ in index]
        data = {
            uid: SCRIPT_BOOK[next((_.type for _ in index if _.uid == uid), "General")](
                **cfg
            )
            for uid, cfg in data.items()
        }
    except Exception as e:
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
        await Config.update_script(
            script.scriptId, script.data.model_dump(exclude_unset=True)
        )
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


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
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/import/file",
    tags=["Update"],
    summary="从文件加载脚本配置",
    response_model=OutBase,
    status_code=200,
)
async def import_script_from_file(script: ScriptFileIn = Body(...)) -> OutBase:

    try:
        await Config.import_script_from_file(script.scriptId, script.jsonFile)
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/export/file",
    tags=["Action"],
    summary="导出脚本配置到文件",
    response_model=OutBase,
    status_code=200,
)
async def export_script_to_file(script: ScriptFileIn = Body(...)) -> OutBase:

    try:
        await Config.export_script_to_file(script.scriptId, script.jsonFile)
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/import/web",
    tags=["Update"],
    summary="从网络加载脚本配置",
    response_model=OutBase,
    status_code=200,
)
async def import_script_from_web(script: ScriptUrlIn = Body(...)) -> OutBase:

    try:
        await Config.import_script_from_web(script.scriptId, script.url)
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/Upload/web",
    tags=["Action"],
    summary="上传脚本配置到网络",
    response_model=OutBase,
    status_code=200,
)
async def upload_script_to_web(script: ScriptUploadIn = Body(...)) -> OutBase:

    try:
        await Config.upload_script_to_web(
            script.scriptId, script.config_name, script.author, script.description
        )
    except Exception as e:
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
            controllers=[ComboBoxItem(**item) for item in data["controllers"]],
            controllerTypes=data["controllerTypes"],
            essenceLocations=[
                ComboBoxItem(**item) for item in data["essenceLocations"]
            ],
        )
    except Exception as e:
        return MaaEndOptionsOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            controllers=[],
            controllerTypes={},
            essenceLocations=[],
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
        return UserGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            index=[],
            data={},
        )
    return UserGetOut(index=index, data=data)


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
            **(await config.toDict())
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

    try:
        await Config.update_user(
            user.scriptId, user.userId, user.data.model_dump(exclude_unset=True)
        )
    except Exception as e:
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
        await Config.set_infrastructure(user.scriptId, user.userId, user.jsonFile)
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/user/combox/infrastructure",
    tags=["Get"],
    summary="用户自定义基建排班可选项",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_user_combox_infrastructure(user: UserDeleteIn = Body(...)) -> ComboBoxOut:

    try:
        raw_data = await Config.get_user_combox_infrastructure(
            user.scriptId, user.userId
        )
        data = [ComboBoxItem(**item) for item in raw_data] if raw_data else []
    except Exception as e:
        return ComboBoxOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", data=[]
        )
    return ComboBoxOut(data=data)


@router.post(
    "/maa/depot/items",
    tags=["Get"],
    summary="MAA 库存保持物品可选项",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_maa_depot_items(script: ScriptDeleteIn = Body(...)) -> ComboBoxOut:

    try:
        raw_data = await Config.get_maa_depot_items(script.scriptId)
        data = [ComboBoxItem(**item) for item in raw_data]
    except Exception as e:
        return ComboBoxOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", data=[]
        )
    return ComboBoxOut(data=data)


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
        data = Webhook(**(await config.toDict()))
    except Exception as e:
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
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/webhook/order",
    tags=["Update"],
    summary="重新排序webhook项",
    response_model=OutBase,
    status_code=200,
)
async def reorder_webhook(webhook: WebhookReorderIn = Body(...)) -> OutBase:

    try:
        await Config.reorder_webhook(
            webhook.scriptId, webhook.userId, webhook.indexList
        )
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/maafw/preview",
    tags=["MaaFW"],
    summary="预览 MaaFW interface",
    response_model=MaaFWInterfacePreviewOut,
    status_code=200,
)
async def preview_maafw_interface(
    payload: MaaFWInterfacePreviewIn = Body(...),
) -> MaaFWInterfacePreviewOut:
    """读取 MaaFW 项目 interface，并返回 controller/resource/task 摘要。"""

    try:
        root_path = Path(payload.path).resolve()
        interface = await asyncio.to_thread(load_interface_model, root_path)
        preview = await asyncio.to_thread(
            build_interface_preview_data,
            root_path,
            interface,
        )
        data = MaaFWInterfacePreviewData.model_validate(
            preview.model_dump(mode="json")
        )
    except MaaFWInterfaceLoadError as exc:
        return MaaFWInterfacePreviewOut(
            code=400,
            status="error",
            message=str(exc),
            data=None,
        )
    except Exception as exc:
        return MaaFWInterfacePreviewOut(
            code=500,
            status="error",
            message=f"MaaFW interface 预览失败: {exc}",
            data=None,
        )

    return MaaFWInterfacePreviewOut(
        message=f"已读取 MaaFW 项目 {data.project.name}，共 {len(data.tasks)} 个任务",
        data=data,
    )


@router.post(
    "/maafw/update",
    tags=["MaaFW"],
    summary="检查或执行 MaaFW 项目更新",
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

    try:
        script_config = _maafw_script_config(payload.scriptId)
    except (KeyError, ValueError, TypeError) as exc:
        return MaaFWProjectUpdateOut(
            code=400, status="error", message=f"MaaFW 脚本无效: {exc}"
        )

    project_value = str(script_config.get("Info", "Path") or "").strip()
    if not project_value:
        return MaaFWProjectUpdateOut(
            code=400, status="error", message="请先设置 MaaFW 项目路径"
        )
    root_path = Path(project_value).resolve()
    if not root_path.is_dir():
        return MaaFWProjectUpdateOut(
            code=400,
            status="error",
            message="MaaFW 项目路径不是有效目录，请检查 Info.Path",
        )

    try:
        interface = await asyncio.to_thread(load_interface_model, root_path)
    except MaaFWInterfaceLoadError as exc:
        return MaaFWProjectUpdateOut(
            code=400, status="error", message=f"MaaFW interface 读取失败: {exc}"
        )
    except Exception as exc:
        return MaaFWProjectUpdateOut(
            code=500, status="error", message=f"MaaFW interface 读取失败: {exc}"
        )

    current_version = str(interface.version or "")
    source_config = _maafw_update_source_config(script_config)
    proxy = Config.proxy

    if payload.action == "check":
        try:
            discovery = await discover_maafw_project_update(
                interface,
                current_version=current_version,
                source_config=source_config,
                proxy=proxy,
            )
        except MaaFWProjectUpdateError as exc:
            return MaaFWProjectUpdateOut(
                code=400, status="error", message=f"MaaFW 更新检查失败: {exc}"
            )
        except Exception as exc:
            return MaaFWProjectUpdateOut(
                code=500, status="error", message=f"MaaFW 更新检查失败: {exc}"
            )

        if discovery is None:
            return MaaFWProjectUpdateOut(
                message=f"MaaFW 项目已是最新版本: {current_version or '未知'}",
                data=MaaFWProjectUpdateData(
                    checked=True, currentVersion=current_version
                ),
            )

        candidate_source = (
            discovery.candidate.source
            if discovery.candidate is not None
            else discovery.source
        )
        message = f"发现 MaaFW 项目新版本: {current_version or '未知'} -> {discovery.version}"
        if not discovery.installable and discovery.unavailable_reason:
            message = f"{message}（暂无可安装更新包: {discovery.unavailable_reason}）"
        return MaaFWProjectUpdateOut(
            message=message,
            data=MaaFWProjectUpdateData(
                checked=True,
                updateAvailable=True,
                installable=discovery.installable,
                currentVersion=current_version,
                latestVersion=discovery.version,
                source=candidate_source,
            ),
        )

    logs: list[str] = []
    try:
        result = await update_maafw_project_if_needed(
            root_path,
            interface,
            source=source_config["source"],
            mirror_cdk=source_config["mirror_cdk"],
            channel=source_config["channel"],
            github_repo=source_config["repo"],
            github_tag=source_config["tag"],
            github_asset_pattern=source_config["asset_pattern"],
            proxy=proxy,
            send_log=logs.append,
        )
    except MaaFWProjectUpdateError as exc:
        return MaaFWProjectUpdateOut(
            code=400, status="error", message=f"MaaFW 项目更新失败: {exc}"
        )
    except Exception as exc:
        return MaaFWProjectUpdateOut(
            code=500, status="error", message=f"MaaFW 项目更新失败: {exc}"
        )

    return MaaFWProjectUpdateOut(
        message=result.message or "MaaFW 项目更新完成",
        data=MaaFWProjectUpdateData(
            checked=result.checked,
            updated=result.updated,
            updateAvailable=result.update_available,
            installable=result.installable,
            currentVersion=result.current_version,
            latestVersion=result.latest_version,
            source=result.source,
        ),
    )


@router.post(
    "/m9a/tasks/available",
    tags=["M9A"],
    summary="获取 M9A 可用任务列表（排除 standalone 任务）",
    status_code=200,
)
async def get_m9a_available_tasks(script_id: str):
    """
    获取 M9A 可用任务列表（排除 standalone 任务）

    前端调用此接口获取可选择的任务列表，
    用于展示在用户编辑界面的任务选择区域。

    Args:
        script_id: M9A 脚本 ID

    Returns:
        dict: 包含任务列表的响应
    """
    from app.task.M9A.task_loader import M9ATaskLoader
    from pathlib import Path

    try:
        script_config = Config.ScriptConfig[uuid.UUID(script_id)]
        m9a_path = Path(script_config.get("Info", "Path"))
        loader = await asyncio.to_thread(M9ATaskLoader.get_cached, m9a_path)
        
        # 获取可用任务，并添加完整定义（包括 option 和 _option_definitions）
        available_tasks = loader.get_available_tasks()
        result_tasks = []
        
        for task in available_tasks:
            full_def = loader.get_full_definition(task["name"])
            if full_def:
                result_tasks.append(full_def)
        
        return {
            "code": 200,
            "status": "success",
            "message": f"共 {len(result_tasks)} 个可用任务",
            "data": result_tasks
        }
    except Exception as e:
        return {
            "code": 500,
            "status": "error",
            "message": f"{type(e).__name__}: {str(e)}",
            "data": []
        }


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

    try:
        if not scriptId:
            return HSRStageOptionsOut(
                code=400,
                status="error",
                message="缺少 scriptId",
            )

        script_config = _hsr_script_config(scriptId)
        if userId:
            _hsr_user_config(script_config, userId)
        from app.task.HSR.tools.api import build_stage_options

        data = HSRStageOptionsData(
            **build_stage_options(script_config, engine)
        )
        option_count = sum(len(category.options) for category in data.categories)
        return HSRStageOptionsOut(
            message=f"共 {option_count} 个 HSR 体力副本选项",
            data=data,
        )
    except Exception as e:
        return HSRStageOptionsOut(
            code=400
            if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
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

    try:
        if not scriptId:
            return HSRCapabilitiesOut(code=400, status="error", message="缺少 scriptId")
        script_config = _hsr_script_config(scriptId)
        from app.task.HSR.tools.api import build_capabilities

        data = HSRCapabilitiesData(**build_capabilities(script_config))
        return HSRCapabilitiesOut(data=data)
    except Exception as e:
        return HSRCapabilitiesOut(
            code=400
            if isinstance(e, (FileNotFoundError, OSError, RuntimeError, ValueError, KeyError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
        )


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
    """返回原生动态托管字段；用户 ID 只负责归属校验。"""

    try:
        if not scriptId:
            return HSRManagedConfigOut(
                code=400, status="error", message="缺少 scriptId"
            )
        script_config = _hsr_script_config(scriptId)
        user_config = None
        if userId:
            user_config = _hsr_user_config(script_config, userId)
        from app.task.HSR.tools.api import build_managed_config

        data = HSRManagedConfigData(
            **build_managed_config(script_config, user_config)
        )
        return HSRManagedConfigOut(data=data)
    except Exception as e:
        return HSRManagedConfigOut(
            code=400
            if isinstance(e, (FileNotFoundError, OSError, RuntimeError, ValueError, KeyError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
        )


@router.post(
    "/hsr/direct-config/import",
    tags=["HSR"],
    summary="导入 HSR 原生配置快照",
    response_model=HSRDirectConfigImportOut,
    status_code=200,
)
async def import_hsr_direct_config_api(
    request: HSRDirectConfigImportIn = Body(...),
) -> HSRDirectConfigImportOut:
    from app.task.HSR.tools.api import import_direct_config
    from app.task.HSR.tools.external_locks import HSRExternalPathBusyError

    try:
        script_config = _hsr_script_config(request.scriptId)
        # 先校验用户归属，再让 provider 读取原生文件，避免无效请求触碰用户配置。
        _hsr_user_config(script_config, request.userId)

        result = await import_direct_config(
            script_config,
            request.engine,
            script_id=request.scriptId,
            user_id=request.userId,
            update_user=Config.update_user,
        )
        return HSRDirectConfigImportOut(
            message=f"{request.engine} 原生配置已导入",
            data=HSRDirectConfigImportData(**result),
        )
    except HSRExternalPathBusyError as e:
        return HSRDirectConfigImportOut(
            code=409, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    except (FileNotFoundError, KeyError, TypeError, ValueError, RuntimeError) as e:
        return HSRDirectConfigImportOut(
            code=400, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    except OSError as e:
        return HSRDirectConfigImportOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
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
    读写用户配置目录（data/{script_id}/{user_id}/ConfigFile/），
    若为空则自动从 ok-nte configs 目录初始化默认配置。

    Args:
        script_id: OK-NTE 脚本 ID
        user_id: 用户 ID

    Returns:
        dict: 包含配置文件列表和 schema 的响应
    """
    try:
        import json
        import shutil
        from app.task.OkNte.config_schema import (
            get_all_config_info,
            build_fields_for_config,
            load_oknte_option_labels,
            ensure_oknte_daily_routine_configs,
        )

        _, script_config = _oknte_script_config(script_id)

        # 从 ok-nte 安装目录加载翻译 → option_labels
        root_path = script_config.get("Info", "RootPath")
        option_labels = load_oknte_option_labels(root_path) if root_path else {}

        # 用户配置目录；旧版 Default 目录仅作为升级后的初始化来源。
        mas_config_dir = _oknte_mas_config_dir(script_id, user_id)

        # ok-nte 源配置目录（用于自动初始化）
        legacy_config_dir = _oknte_legacy_mas_config_dir(script_id)
        oknte_configs_dir = (
            legacy_config_dir
            if legacy_config_dir.is_dir() and any(legacy_config_dir.iterdir())
            else None
        )
        if oknte_configs_dir is None:
            raw_config_path = script_config.get("Script", "ConfigPath")
            oknte_configs_dir = Path(raw_config_path) if raw_config_path else None
        if not oknte_configs_dir or not oknte_configs_dir.exists():
            if root_path:
                root = Path(root_path)
                packaged_dir = root / "data" / "apps" / "ok-nte" / "working" / "configs"
                source_dir = root / "configs"
                oknte_configs_dir = packaged_dir if packaged_dir.is_dir() else source_dir

        # 自动初始化：用户目录为空时从旧版共享目录或 ok-nte configs 复制默认配置
        need_init = not mas_config_dir.exists() or not any(mas_config_dir.iterdir())
        if need_init and oknte_configs_dir and oknte_configs_dir.is_dir():
            mas_config_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(oknte_configs_dir, mas_config_dir, dirs_exist_ok=True)
        mas_config_dir.mkdir(parents=True, exist_ok=True)
        ensure_oknte_daily_routine_configs(mas_config_dir)

        configs_info = get_all_config_info()

        # 读取 per-user JSON 配置，通过 build_fields_for_config 构建字段列表
        result = []
        for info in configs_info:
            filename = info["filename"]
            filepath = _oknte_config_file_path(mas_config_dir, filename)
            current_data: dict[str, Any] = {}
            if filepath.exists():
                try:
                    current_data = json.loads(filepath.read_text(encoding="utf-8"))
                except Exception:
                    pass

            fields = build_fields_for_config(filename, current_data, option_labels)

            result.append({
                **info,
                "fields": fields,
                "currentData": current_data,
            })

        return {
            "code": 200,
            "status": "success",
            "message": f"共 {len(result)} 个配置文件",
            "data": result,
            "optionLabels": option_labels,
            "configPath": str(mas_config_dir) if mas_config_dir else None,
        }
    except Exception as e:
        return {
            "code": 500,
            "status": "error",
            "message": f"{type(e).__name__}: {str(e)}",
            "data": [],
        }


@router.post(
    "/oknte/configs/update",
    tags=["OKNTE"],
    summary="更新 OK-NTE 配置文件",
    status_code=200,
)
async def update_oknte_config(
    script_id: str = Body(...),
    user_id: str = Body(...),
    filename: str = Body(...),
    data: dict = Body(...),
):
    """
    更新 OK-NTE 配置文件

    Args:
        script_id: OK-NTE 脚本 ID
        user_id: 用户 ID
        filename: 配置文件名（如 DailyTask.json）
        data: 要更新的配置数据

    Returns:
        dict: 操作结果
    """
    try:
        from app.task.OkNte.config_schema import update_oknte_config_data

        # 写入用户配置目录
        mas_config_dir = _oknte_mas_config_dir(script_id, user_id)
        mas_config_dir.mkdir(parents=True, exist_ok=True)

        filepath = _oknte_config_file_path(mas_config_dir, filename)

        existing_data = update_oknte_config_data(filepath, data)

        return {
            "code": 200,
            "status": "success",
            "message": f"配置文件 {filename} 已更新",
            "data": existing_data,
        }
    except Exception as e:
        return {
            "code": 500,
            "status": "error",
            "message": f"{type(e).__name__}: {str(e)}",
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
        return {
            "code": 500,
            "status": "error",
            "message": f"{type(e).__name__}: {str(e)}",
        }
