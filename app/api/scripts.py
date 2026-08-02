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
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core import Config
from app.models.schema import *
router = APIRouter(prefix="/api/scripts", tags=["脚本管理"])


_MAAFW_IMAGE_SUFFIXES = {
    ".avif",
    ".bmp",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".png",
    ".svg",
    ".webp",
}


def _maafw_asset_file_path(root: str, asset_path: str) -> Path:
    root_path = Path(root).resolve()
    if not root_path.is_dir():
        raise ValueError("MaaFW 项目目录不存在")

    if not (root_path / "interface.json").is_file() and not (
        root_path / "interface.jsonc"
    ).is_file():
        raise ValueError("MaaFW asset root must be an interface project root")

    from automas_maafw_interface.service import MaaFWInterfaceService

    MaaFWInterfaceService().load(root_path)

    normalized_asset_path = asset_path.replace("\\", "/").strip()
    relative_path = Path(normalized_asset_path)
    if (
        not normalized_asset_path
        or relative_path.is_absolute()
        or ".." in relative_path.parts
    ):
        raise ValueError("MaaFW 资源路径非法")

    file_path = (root_path / relative_path).resolve()
    if root_path not in file_path.parents:
        raise ValueError("MaaFW 资源路径越界")
    if file_path.suffix.lower() not in _MAAFW_IMAGE_SUFFIXES:
        raise ValueError("仅支持 MaaFW 图片资源")
    if not file_path.is_file():
        raise FileNotFoundError("MaaFW 图片资源不存在")
    return file_path


def _build_maafw_agent_env_info_items(agent_plans: list[Any]) -> list[MaaFWAgentEnvInfo]:
    def read(agent: Any, key: str) -> Any:
        if isinstance(agent, dict):
            return agent.get(key)
        return getattr(agent, key, None)

    return [
        MaaFWAgentEnvInfo(
            childExec=read(agent, "childExec") or "",
            executable=read(agent, "executable") or "",
            runtimeKind=read(agent, "runtimeKind"),
            isolatedVenvPath=read(agent, "isolatedVenvPath"),
            fallbackReason=read(agent, "fallbackReason"),
        )
        for agent in agent_plans
    ]


SCRIPT_BOOK: dict[str, type[BaseModel]] = {
    "MaaConfig": MaaConfig,
    "SrcConfig": SrcConfig,
    "MaaEndConfig": MaaEndConfig,
    "M9AConfig": M9AConfig,
    "MaaFWConfig": MaaFWConfig,
    "GeneralConfig": GeneralConfig,
    "PluginScriptConfig": PluginScriptConfig,
}
USER_BOOK: dict[str, type[BaseModel]] = {
    "MaaConfig": MaaUserConfig,
    "SrcConfig": SrcUserConfig,
    "MaaEndConfig": MaaEndUserConfig,
    "M9AConfig": M9AUserConfig,
    "MaaFWConfig": MaaFWUserConfig,
    "GeneralConfig": GeneralUserConfig,
    "PluginScriptConfig": PluginUserConfig,
}


def _is_plugin_payload(payload: dict[str, Any]) -> bool:
    return isinstance(payload.get("PluginData"), dict) or payload.get("type") in {
        "PluginScriptConfig",
        "PluginUserConfig",
    }


def _is_plugin_type(type_key: str) -> bool:
    try:
        from app.core.script_types import script_type_registry

        return not script_type_registry.get(type_key).is_builtin
    except Exception:
        return False


def _script_schema_for_config(config: Any) -> type[BaseModel]:
    return SCRIPT_BOOK.get(type(config).__name__, PluginScriptConfig)


def _script_schema_for_payload(
    type_key: str, payload: dict[str, Any]
) -> type[BaseModel]:
    if _is_plugin_payload(payload) or _is_plugin_type(type_key):
        return PluginScriptConfig
    return SCRIPT_BOOK.get(type_key, GeneralConfig)


def _user_schema_for_script_config(config: Any) -> type[BaseModel]:
    return USER_BOOK.get(type(config).__name__, PluginUserConfig)


def _plugin_provider(type_key: str):
    try:
        from app.core.script_types import script_type_registry

        return script_type_registry.get(type_key)
    except Exception:
        return None


def _is_maafw_framework_script(script_config: Any) -> bool:
    """判定脚本配置是否属于 MaaFW 框架运行链路（含 M9A 等 pack 形态）。"""

    from app.core.script_types import script_type_registry

    # 插件形态脚本统一存为 PluginScriptConfig，类名不进注册表，
    # 必须按 Meta.PluginTypeKey 解析 provider，否则通用 MaaFW 项目会被误判。
    try:
        from app.models.plugin_script_config import PluginScriptConfig

        if isinstance(script_config, PluginScriptConfig):
            type_key = str(script_config.get("Meta", "PluginTypeKey") or "").strip()
            if not type_key:
                return False
            provider = script_type_registry.get(type_key)
            return provider.metadata.get("framework") == "maafw"
    except Exception:
        pass

    config_class_name = type(script_config).__name__
    try:
        provider = script_type_registry.get_by_script_config(script_config)
        return provider.metadata.get("framework") == "maafw"
    except Exception:
        # 注册表未就绪或类名未注册时，回退到已知 legacy 类名。
        return config_class_name in {"MaaFWConfig", "M9AConfig"}


async def _resolve_maafw_script_form(script_config: Any) -> dict[str, Any]:
    """解析 MaaFW 框架脚本的表单态配置（插件形态与 legacy 均适用）。

    插件形态脚本统一存为 PluginScriptConfig，真实配置在 PluginData.Config
    （JSON 字符串），须经 storage_to_form 解码后才有 Info.Path / Update.* 字段；
    legacy MaaFWConfig/M9AConfig 直接 toDict 即为表单态。
    """
    from app.models.plugin_script_config import PluginScriptConfig

    if isinstance(script_config, PluginScriptConfig):
        from app.core.script_config_codec import storage_to_form

        type_key = str(script_config.get("Meta", "PluginTypeKey") or "").strip()
        provider = _plugin_provider(type_key)
        if provider is None:
            raise RuntimeError(f"无法解析插件脚本类型: {type_key or '(空)'}")
        raw = script_config.get("PluginData", "Config")
        return await storage_to_form(provider, raw, "script")

    payload = await script_config.toDict()
    payload.pop("SubConfigsInfo", None)
    return payload


def _plugin_type_key_from_payload(payload: dict[str, Any]) -> str:
    meta = payload.get("Meta")
    if isinstance(meta, dict):
        raw_type_key = meta.get("PluginTypeKey")
        if isinstance(raw_type_key, str) and raw_type_key.strip():
            return raw_type_key.strip()
    return ""


def _script_index_type(index_type: str, payload: dict[str, Any]) -> str:
    """保留插件容器的稳定公开索引类型。"""

    _ = payload
    return index_type


def _user_index_type(index_type: str, script_config: Any) -> str:
    """保留插件容器的稳定公开索引类型。"""

    _ = script_config
    return index_type


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
        data = _script_schema_for_config(config)(**(await config.toDict()))
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
        index = [
            ScriptIndexItem(
                **{
                    **item,
                    "type": _script_index_type(
                        str(item.get("type") or ""),
                        data.get(item.get("uid"), {}),
                    ),
                }
            )
            for item in index
            if isinstance(item, dict)
        ]
        data = {
            uid: _script_schema_for_payload(
                next((_.type for _ in index if _.uid == uid), "General"),
                cfg,
            )(**cfg)
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
    "/user/get",
    tags=["Get"],
    summary="查询用户",
    response_model=UserGetOut,
    status_code=200,
)
async def get_user(user: UserGetIn = Body(...)) -> UserGetOut:

    try:
        index, data = await Config.get_user(user.scriptId, user.userId)
        script_config = Config.ScriptConfig[uuid.UUID(user.scriptId)]
        index = [
            UserIndexItem(
                **{
                    **item,
                    "type": _user_index_type(str(item.get("type") or ""), script_config),
                }
            )
            for item in index
            if isinstance(item, dict)
        ]
        schema_model = _user_schema_for_script_config(
            script_config
        )
        data = {
            uid: schema_model(**cfg)
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
        schema_model = _user_schema_for_script_config(
            Config.ScriptConfig[uuid.UUID(user.scriptId)]
        )
        data = schema_model(**(await config.toDict()))
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
    "/maafw/interface/preview",
    tags=["MaaFW"],
    summary="预览 MaaFW ProjectInterface",
    response_model=MaaFWInterfacePreviewOut,
    status_code=200,
)
async def preview_maafw_interface(
    payload: MaaFWInterfacePreviewIn = Body(...),
) -> MaaFWInterfacePreviewOut:
    """读取 MaaFW 项目目录中的 interface.json，返回 MAS UI 可消费的摘要。"""
    from automas_maafw_interface.loader import MaaFWInterfaceLoadError
    from automas_maafw_interface.service import MaaFWInterfaceService

    try:
        data = MaaFWInterfaceService().preview(Path(payload.path).resolve())
    except MaaFWInterfaceLoadError as e:
        return MaaFWInterfacePreviewOut(
            code=400,
            status="error",
            message=str(e),
            data=None,
        )
    except Exception as e:
        return MaaFWInterfacePreviewOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=None,
        )

    return MaaFWInterfacePreviewOut(
        message=f"已读取 MaaFW 项目 {data.project['name']}，共 {len(data.tasks)} 个任务",
        data=data.model_dump(mode="json"),
    )


@router.post(
    "/maafw/project/update",
    tags=["MaaFW"],
    summary="手动更新 MaaFW 项目资源",
    response_model=MaaFWProjectUpdateOut,
    status_code=200,
)
async def update_maafw_project(
    payload: MaaFWProjectUpdateIn = Body(...),
) -> MaaFWProjectUpdateOut:
    """按脚本更新配置手动检查并应用 MaaFW 项目资源更新。"""
    from automas_maafw_interface.loader import MaaFWInterfaceLoadError
    from automas_maafw_interface.service import MaaFWInterfaceService
    from automas_maafw_project_update.service import MaaFWProjectUpdateService
    from automas_maafw_runner.service import MaaFWRunnerService
    from automas_script_maafw.project_path import (
        release_project_path,
        try_reserve_project_path,
    )
    from app.core.ws import protocol as ws_protocol
    from app.core.ws.publisher import Publisher

    logs: list[str] = []
    current_version = ""
    update_loop = asyncio.get_running_loop()

    def publish_update_progress(progress: dict[str, Any]) -> None:
        """Bridge thread-safe updater callbacks onto the main WebSocket."""

        payload_data = {"scriptId": payload.scriptId, **dict(progress)}

        def schedule() -> None:
            asyncio.create_task(
                Publisher.send(
                    id=payload.scriptId,
                    type=ws_protocol.MAAFW_PROJECT_UPDATE_PROGRESS,
                    data=payload_data,
                )
            )

        update_loop.call_soon_threadsafe(schedule)

    def publish_environment_progress(progress: dict[str, Any]) -> None:
        """Forward warmup detail without turning a successful update into failure."""

        progress_data = dict(progress)
        if progress_data.get("stage") in {"completed", "failed"}:
            return
        publish_update_progress(
            {
                "phase": "preparing_environment",
                **progress_data,
            }
        )

    def publish_resource_update_progress(progress: dict[str, Any]) -> None:
        """Keep the updater's resource terminal distinct from the whole workflow."""

        progress_data = dict(progress)
        if (
            progress_data.get("stage") == "completed"
            and progress_data.get("status") == "updated"
        ):
            publish_update_progress(
                {
                    **progress_data,
                    "stage": "preparing_environment",
                    "status": "running",
                    "message": "项目资源已更新，正在准备运行环境",
                    "percent": 90.0,
                    "phase": "resource_applied",
                    "final": False,
                }
            )
            return
        if progress_data.get("stage") == "completed":
            progress_data["phase"] = "finalizing"
            progress_data["final"] = True
        publish_update_progress(progress_data)

    def append_log(message: str) -> None:
        timestamp = datetime.now().astimezone().strftime("%H:%M:%S")
        for line in str(message).splitlines() or [""]:
            logs.append(f"[{timestamp}] {line}")

    try:
        script_uuid = uuid.UUID(payload.scriptId)
    except ValueError as e:
        append_log(f"脚本 ID 无效: {e}")
        return MaaFWProjectUpdateOut(
            code=400,
            status="error",
            message=f"脚本 ID 无效: {e}",
            data=MaaFWProjectUpdateData(
                checked=False,
                updated=False,
                currentVersion=current_version,
                logs=logs,
            ),
        )

    try:
        script_config = Config.ScriptConfig[script_uuid]
        if not _is_maafw_framework_script(script_config):
            append_log("指定脚本不是 MaaFW 项目")
            return MaaFWProjectUpdateOut(
                code=400,
                status="error",
                message="指定脚本不是 MaaFW 项目",
                data=MaaFWProjectUpdateData(
                    checked=False,
                    updated=False,
                    currentVersion=current_version,
                    logs=logs,
                ),
            )

        # 插件形态脚本的 Info.Path/Update.* 藏在 PluginData.Config，需先解码成表单态
        script_form = await _resolve_maafw_script_form(script_config)
        info_group = script_form.get("Info")
        info_group = info_group if isinstance(info_group, dict) else {}
        update_group = script_form.get("Update")
        update_group = update_group if isinstance(update_group, dict) else {}

        project_path_raw = str(info_group.get("Path") or "").strip()
        if not project_path_raw:
            append_log("请先配置 MaaFW 项目目录")
            return MaaFWProjectUpdateOut(
                code=400,
                status="error",
                message="请先配置 MaaFW 项目目录",
                data=MaaFWProjectUpdateData(
                    checked=False,
                    updated=False,
                    currentVersion=current_version,
                    logs=logs,
                ),
            )

        project_path = Path(project_path_raw).resolve()
        reservation_key = await try_reserve_project_path(project_path)
        if reservation_key is None:
            append_log("MaaFW 项目正在运行或更新，请稍后重试")
            return MaaFWProjectUpdateOut(
                code=409,
                status="error",
                message="MaaFW 项目正在运行或更新，请稍后重试",
                data=MaaFWProjectUpdateData(
                    checked=False,
                    updated=False,
                    currentVersion=current_version,
                    logs=logs,
                ),
            )

        environment_warning = ""
        try:
            interface_model = MaaFWInterfaceService().load(project_path)
            current_version = interface_model.version or ""

            mirror_cdk = (
                update_group.get("MirrorChyanCDK")
                or Config.get("Update", "MirrorChyanCDK")
            )
            channel = update_group.get("Channel") or Config.get("Update", "Channel")
            source_config = None
            try:
                from automas_script_maafw.schema import build_source_config

                source_config = build_source_config(script_form)
            except Exception as e:
                append_log(
                    "读取脚本更新源配置失败，回退默认更新源: "
                    f"{type(e).__name__}: {e}"
                )
            update_result = await MaaFWProjectUpdateService().update_if_needed(
                project_path,
                interface_model,
                mirror_cdk=mirror_cdk,
                channel=channel,
                proxy=Config.proxy,
                send_log=append_log,
                source_config=source_config,
                progress=publish_resource_update_progress,
            )

            if update_result.updated:
                current_version = update_result.latest_version or current_version
                append_log(
                    "[完成] MaaFW 项目资源已更新"
                    + (f"至 {current_version}" if current_version else "")
                )
                try:
                    refreshed_interface = MaaFWInterfaceService().load(
                        project_path,
                        force_reload=True,
                    )
                except Exception as refresh_error:
                    environment_warning = (
                        "项目资源已更新，但新版 interface 重新读取失败；"
                        "请修复项目文件后重新进入: "
                        f"{type(refresh_error).__name__}: {refresh_error}"
                    )
                    append_log(f"[警告] {environment_warning}")
                    publish_update_progress(
                        {
                            "stage": "completed",
                            "status": "updated_with_environment_warning",
                            "message": environment_warning,
                            "percent": 100.0,
                            "phase": "finalizing",
                            "final": True,
                        }
                    )
                else:
                    installed_version = (
                        refreshed_interface.version or update_result.latest_version
                    )
                    current_version = installed_version or current_version
                    append_log("开始预热 MaaFW 实际运行环境")
                    publish_update_progress(
                        {
                            "stage": "preparing_environment",
                            "status": "running",
                            "message": "正在准备 MaaFW 实际运行环境",
                            "percent": None,
                        }
                    )
                    try:
                        await asyncio.to_thread(
                            MaaFWRunnerService().prepare_project_environment,
                            project_path,
                            refreshed_interface,
                            runtime_pool_root=Path.cwd()
                            / "config"
                            / "maafw_runtime_pool",
                            send_log=append_log,
                            progress=publish_environment_progress,
                        )
                    except Exception as env_error:
                        environment_warning = (
                            "项目资源已更新，但运行环境预热未完成: "
                            f"{type(env_error).__name__}: {env_error}"
                        )
                        append_log(f"[警告] {environment_warning}")
                        publish_update_progress(
                            {
                                "stage": "completed",
                                "status": "updated_with_environment_warning",
                                "message": environment_warning,
                                "percent": 100.0,
                                "phase": "finalizing",
                                "final": True,
                            }
                        )
                    else:
                        append_log("[完成] MaaFW 运行环境预热完成")
                        publish_update_progress(
                            {
                                "stage": "completed",
                                "status": "updated",
                                "message": "MaaFW project and runtime environment are ready",
                                "percent": 100.0,
                                "phase": "finalizing",
                                "final": True,
                            }
                        )
            elif getattr(update_result, "update_available", False):
                append_log(
                    "[完成] MaaFW 项目更新检查完成：已发现新版本，当前来源暂不可安装"
                )
            else:
                append_log("[完成] MaaFW 项目更新检查完成：当前已是最新版本")
        finally:
            await release_project_path(reservation_key)
            append_log("MaaFW 项目更新锁已释放")

        return MaaFWProjectUpdateOut(
            message=environment_warning or update_result.message,
            data=MaaFWProjectUpdateData(
                checked=update_result.checked,
                updated=update_result.updated,
                currentVersion=current_version or update_result.current_version,
                latestVersion=update_result.latest_version,
                source=update_result.source,
                logs=logs,
            ),
        )
    except KeyError:
        append_log("脚本不存在或已被删除")
        return MaaFWProjectUpdateOut(
            code=404,
            status="error",
            message="脚本不存在或已被删除",
            data=MaaFWProjectUpdateData(
                checked=False,
                updated=False,
                currentVersion=current_version,
                logs=logs,
            ),
        )
    except MaaFWInterfaceLoadError as e:
        append_log(f"MaaFW 项目更新失败: {e}")
        return MaaFWProjectUpdateOut(
            code=400,
            status="error",
            message=str(e),
            data=MaaFWProjectUpdateData(
                checked=False,
                updated=False,
                currentVersion=current_version,
                logs=logs,
            ),
        )
    except Exception as e:
        append_log(f"MaaFW 项目更新失败: {type(e).__name__}: {e}")
        return MaaFWProjectUpdateOut(
            code=500,
            status="error",
            message=f"MaaFW 项目更新失败: {type(e).__name__}: {e}",
            data=MaaFWProjectUpdateData(
                checked=False,
                updated=False,
                currentVersion=current_version,
                logs=logs,
            ),
        )


@router.post(
    "/maafw/agent-env/prepare",
    tags=["MaaFW"],
    summary="Prepare MaaFW runtime env",
    response_model=MaaFWAgentEnvPrepareOut,
    status_code=200,
)
async def prepare_maafw_agent_env(
    request: Request,
    payload: MaaFWAgentEnvPrepareIn = Body(...),
) -> MaaFWAgentEnvPrepareOut:
    """Prepare MaaFW Runner and agent Python envs before starting tasks."""

    from automas_maafw_interface.loader import MaaFWInterfaceLoadError
    from automas_maafw_interface.service import MaaFWInterfaceService
    from automas_maafw_runner.service import MaaFWRunnerService
    from automas_script_maafw.project_path import (
        release_project_path,
        try_reserve_project_path,
    )
    from app.core.ws import protocol as ws_protocol
    from app.core.ws.publisher import Publisher

    logs: list[str] = []
    root_path: Path | None = None
    agent_plans: list[Any] = []
    reservation_key: str | None = None
    prepare_terminal_published = False
    prepare_loop = asyncio.get_running_loop()
    progress_id = request.headers.get("X-MaaFW-Progress-Id", "").strip()[:128]

    def publish_prepare_progress(progress: dict[str, Any]) -> None:
        nonlocal prepare_terminal_published
        if not progress_id:
            return
        progress_data = dict(progress)
        if progress_data.get("stage") in {"completed", "failed"}:
            prepare_terminal_published = True
            progress_data.setdefault("final", True)
        payload_data = {
            "scriptId": progress_id,
            "project_path": str(root_path or payload.path),
            **progress_data,
        }

        def schedule() -> None:
            asyncio.create_task(
                Publisher.send(
                    id=progress_id,
                    type=ws_protocol.MAAFW_ENV_PREPARE_PROGRESS,
                    data=payload_data,
                )
            )

        prepare_loop.call_soon_threadsafe(schedule)

    try:
        root_path = Path(payload.path).resolve()
        reservation_key = await try_reserve_project_path(root_path)
        if reservation_key is None:
            message = "MaaFW 项目正在运行、更新或准备环境，请稍后重试"
            publish_prepare_progress(
                {
                    "stage": "failed",
                    "status": "busy",
                    "message": message,
                    "percent": None,
                }
            )
            return MaaFWAgentEnvPrepareOut(
                code=409,
                status="error",
                message=message,
                data=MaaFWAgentEnvPrepareData(
                    path=str(root_path),
                    agentCount=0,
                    agents=[],
                    logs=logs,
                ),
            )
        publish_prepare_progress(
            {
                "stage": "resolving",
                "status": "running",
                "message": "正在解析 MaaFW 项目运行环境",
                "percent": 2.0,
            }
        )
        interface = MaaFWInterfaceService().load(root_path)
        prepare_result = await asyncio.to_thread(
            MaaFWRunnerService().prepare_project_environment,
            root_path,
            interface,
            runtime_pool_root=Path.cwd() / "config" / "maafw_runtime_pool",
            send_log=logs.append,
            progress=publish_prepare_progress,
        )
        agent_result = prepare_result.get("agents")
        agent_result = agent_result if isinstance(agent_result, dict) else {}
        raw_agent_plans = agent_result.get("plans")
        agent_plans = raw_agent_plans if isinstance(raw_agent_plans, list) else []
        agents = _build_maafw_agent_env_info_items(agent_plans)
        data = MaaFWAgentEnvPrepareData(
            path=str(root_path),
            agentCount=len(agents),
            agents=agents,
            logs=logs,
        )
    except MaaFWInterfaceLoadError as e:
        if not prepare_terminal_published:
            publish_prepare_progress(
                {
                    "stage": "failed",
                    "status": "failed",
                    "message": str(e),
                    "percent": None,
                }
            )
        return MaaFWAgentEnvPrepareOut(
            code=400,
            status="error",
            message=str(e),
            data=MaaFWAgentEnvPrepareData(
                path=str(root_path or Path(payload.path)),
                agentCount=0,
                agents=[],
                logs=logs,
            ),
        )
    except Exception as e:
        agents = _build_maafw_agent_env_info_items(agent_plans)
        if not prepare_terminal_published:
            publish_prepare_progress(
                {
                    "stage": "failed",
                    "status": "failed",
                    "message": f"{type(e).__name__}: {e}",
                    "percent": None,
                }
            )
        return MaaFWAgentEnvPrepareOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=MaaFWAgentEnvPrepareData(
                path=str(root_path or Path(payload.path)),
                agentCount=len(agents),
                agents=agents,
                logs=logs,
            ),
        )
    finally:
        await release_project_path(reservation_key)

    return MaaFWAgentEnvPrepareOut(
        message=f"MaaFW runtime env prepared, agent count: {data.agentCount}",
        data=data,
    )


@router.get(
    "/maafw/asset",
    tags=["MaaFW"],
    summary="读取 MaaFW 本地图片资源",
    response_class=FileResponse,
    status_code=200,
)
async def get_maafw_asset(
    root: str = Query(..., description="MaaFW 项目根目录"),
    path: str = Query(..., description="相对 MaaFW 项目根目录的图片路径"),
) -> FileResponse:
    """读取 MaaFW interface 描述、任务、选项中引用的本地图片资源。"""

    try:
        file_path = _maafw_asset_file_path(root, path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return FileResponse(file_path)


def _select_maafw_window_controllers(interface, controller_name: str | None):
    controllers = [
        controller
        for controller in interface.controller
        if controller.type == "Win32"
    ]
    if not controller_name:
        return controllers

    controller = next(
        (
            item
            for item in interface.controller
            if item.name == controller_name
        ),
        None,
    )
    if controller is None:
        raise ValueError(f"未找到 controller: {controller_name}")
    if controller.type != "Win32":
        raise ValueError(f"controller {controller_name} 不是 PC 窗口类型")
    return [controller]


@router.post(
    "/maafw/windows/preview",
    tags=["MaaFW"],
    summary="扫描 MaaFW PC 客户端窗口",
    response_model=MaaFWWindowPreviewOut,
    status_code=200,
)
async def preview_maafw_windows(
    payload: MaaFWWindowPreviewIn = Body(...),
) -> MaaFWWindowPreviewOut:
    """按 interface.json 中的 Win32 窗口规则扫描本机桌面窗口。"""
    from automas_maafw_controller_win32.service import MaaFWWin32ControllerService
    from automas_maafw_interface.loader import MaaFWInterfaceLoadError
    from automas_maafw_interface.service import MaaFWInterfaceService

    try:
        root_path = Path(payload.path).resolve()
        interface = MaaFWInterfaceService().load(root_path)
        controllers = _select_maafw_window_controllers(
            interface,
            payload.controllerName,
        )
        win32_service = MaaFWWin32ControllerService()
        win32_windows = win32_service.list_windows()
        windows: list[MaaFWDesktopWindowInfo] = []
        for controller in controllers:
            controller_payload = controller.model_dump(mode="json", by_alias=True)
            for window in win32_service.match_controller_windows(
                controller_payload,
                win32_windows,
            ):
                windows.append(
                    MaaFWDesktopWindowInfo(
                        hWnd=window.hWnd,
                        className=window.className,
                        windowName=window.windowName,
                        controllerName=window.controllerName,
                        controllerType=window.controllerType,
                    )
                )
        data = MaaFWWindowPreviewData(
            path=str(root_path),
            controllerName=payload.controllerName,
            windows=windows,
        )
    except MaaFWInterfaceLoadError as e:
        return MaaFWWindowPreviewOut(
            code=400,
            status="error",
            message=str(e),
            data=None,
        )
    except ValueError as e:
        return MaaFWWindowPreviewOut(
            code=400,
            status="error",
            message=str(e),
            data=None,
        )
    except Exception as e:
        return MaaFWWindowPreviewOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=None,
        )

    return MaaFWWindowPreviewOut(
        message=f"已扫描到 {len(data.windows)} 个 MaaFW PC 客户端窗口",
        data=data,
    )
