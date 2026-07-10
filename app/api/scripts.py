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
import importlib
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import FileResponse

from app.core import Config
from app.models.schema import *
from app.task.Ok.common.provider import ok_script_mas_config_dir
from app.task.Ok.providers import detect_ok_script_provider
from app.task.Ok.providers.okww import OKWW_PROVIDER

router = APIRouter(prefix="/api/scripts", tags=["脚本管理"])


def _ok_script_config_file_path(config_dir: Path, filename: str) -> Path:
    file_path = Path(filename)
    if (
        file_path.name != filename
        or file_path.is_absolute()
        or ".." in file_path.parts
    ):
        raise ValueError("配置文件名非法")
    return config_dir / filename


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        import json

        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _write_json_file_atomic(path: Path, data: dict[str, Any]) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")
    tmp_path.replace(path)


def _copy_tree_atomic(source_dir: Path, target_dir: Path) -> None:
    """通过临时目录初始化用户配置，避免留下半份配置。"""

    if not source_dir.is_dir():
        return

    target_dir.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = target_dir.with_name(target_dir.name + ".tmp")
    shutil.rmtree(tmp_dir, ignore_errors=True)
    shutil.copytree(source_dir, tmp_dir)
    shutil.rmtree(target_dir, ignore_errors=True)
    tmp_dir.rename(target_dir)


def _ensure_okww_user_config_defaults(config_dir: Path, source_dir: Path | None) -> None:
    if source_dir is None or not source_dir.is_dir():
        return
    from app.task.Okww.config_schema import get_all_config_info

    config_dir.mkdir(parents=True, exist_ok=True)
    for info in get_all_config_info():
        filename = str(info["filename"])
        source_path = source_dir / filename
        if not source_path.is_file():
            continue
        current_path = _ok_script_config_file_path(config_dir, filename)
        source_data = _read_json_file(source_path)
        current_data = _read_json_file(current_path)
        merged_data = {**source_data, **current_data}
        if merged_data != current_data:
            _write_json_file_atomic(current_path, merged_data)


def _resolve_ok_script_provider(script_id: str):
    """读取当前通用 ok-script 脚本并解析其项目 provider。"""

    script_config = Config.ScriptConfig[uuid.UUID(script_id)]
    if type(script_config).__name__ != "OkefConfig":
        raise ValueError("指定脚本不是 ok-script 项目")

    root_path = Path(str(script_config.get("Info", "RootPath") or ""))
    provider = detect_ok_script_provider(
        root_path,
        script_config.get("Info", "ResourceName"),
    )
    if provider is None:
        raise ValueError("当前 ok-script 项目尚未适配")
    return script_config, root_path, provider


def _load_ok_script_schema(provider):
    """按 provider 载入隔离的配置 schema 实现。"""

    schema_module = importlib.import_module(provider.config_schema_module)
    return (
        getattr(schema_module, "build_fields_for_config"),
        getattr(schema_module, provider.config_info_loader),
        getattr(schema_module, f"load_{provider.resource_name.replace('-', '')}_option_labels"),
    )


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
    return [
        MaaFWAgentEnvInfo(
            childExec=agent.childExec,
            executable=agent.executable,
            runtimeKind=agent.runtimeKind,
            isolatedVenvPath=agent.isolatedVenvPath,
            fallbackReason=agent.fallbackReason,
        )
        for agent in agent_plans
    ]


SCRIPT_BOOK = {
    "MaaConfig": MaaConfig,
    "SrcConfig": SrcConfig,
    "MaaEndConfig": MaaEndConfig,
    "M9AConfig": M9AConfig,
    "MaaFWConfig": MaaFWConfig,
    "GeneralConfig": GeneralConfig,
    "OkwwConfig": OkwwConfig,
    "OkefConfig": OkefConfig,
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
    "OkefConfig": OkefUserConfig,
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
    "/user/import-m7a-abyss-snapshot",
    tags=["Update"],
    summary="从 M7A config.yaml 导入三深渊快照",
    response_model=AbyssSnapshotImportOut,
    status_code=200,
)
async def import_m7a_abyss_snapshot(
    payload: UserImportAbyssSnapshotIn = Body(...),
) -> AbyssSnapshotImportOut:
    """从 M7A config.yaml 读取三深渊白名单字段，写入指定 HSR 用户配置。"""
    import json

    from app.task.HSR.tools.m7a_config import read_m7a_abyss_snapshots

    items: list[AbyssSnapshotImportItem] = []
    m7a_config_path: Path | None = None

    try:
        script_config = Config.ScriptConfig[uuid.UUID(payload.scriptId)]
        m7a_path_str = str(script_config.get("Info", "M7APath") or "").strip()
        if not m7a_path_str:
            raise ValueError("请先在脚本配置页配置三月七路径")

        m7a_config_path = Path(m7a_path_str) / "config.yaml"
        write_snapshots, raw_items = read_m7a_abyss_snapshots(m7a_config_path)
        items = [AbyssSnapshotImportItem(**item) for item in raw_items]

        await Config.update_user(
            payload.scriptId,
            payload.userId,
            {"Abyss": {"Snapshots": json.dumps(write_snapshots, ensure_ascii=False)}},
        )
        _, user_data_dict = await Config.get_user(payload.scriptId, payload.userId)
        updated_user_data = HSRUserConfig(**user_data_dict)
    except Exception as e:
        return AbyssSnapshotImportOut(
            code=400 if isinstance(e, (FileNotFoundError, ValueError)) else 500,
            status="error",
            message=f"导入三深渊快照失败: {type(e).__name__}: {e}",
            m7aConfigPath=str(m7a_config_path) if m7a_config_path else "",
            items=items,
            updatedUserData=HSRUserConfig(),
        )

    success_count = len(items)
    return AbyssSnapshotImportOut(
        code=200,
        status="success",
        message=f"已从 M7A config.yaml 导入 {success_count}/3 个三深渊快照",
        m7aConfigPath=str(m7a_config_path),
        items=items,
        updatedUserData=updated_user_data,
    )


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
    from app.task.MaaFW.interface_loader import (
        MaaFWInterfaceLoadError,
        load_interface_model_cached,
    )
    from app.task.MaaFW.interface_preview import build_maafw_interface_preview_data

    try:
        root_path = Path(payload.path).resolve()
        interface = load_interface_model_cached(root_path)
        data = build_maafw_interface_preview_data(root_path, interface)
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
        message=f"已读取 MaaFW 项目 {data.project.name}，共 {len(data.tasks)} 个任务",
        data=data,
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
    from app.task.MaaFW.interface_loader import (
        MaaFWInterfaceLoadError,
        load_interface_model_cached,
    )
    from app.task.MaaFW.project_updater import update_maafw_project_if_needed
    from app.task.MaaFW.runner import prepare_maafw_agent_python_envs

    logs: list[str] = []
    current_version = ""

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
        if type(script_config).__name__ != "MaaFWConfig":
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

        project_path_raw = str(script_config.get("Info", "Path") or "").strip()
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
        interface_model = load_interface_model_cached(project_path)
        current_version = interface_model.version or ""

        mirror_cdk = (
            script_config.get("Update", "MirrorChyanCDK")
            or Config.get("Update", "MirrorChyanCDK")
        )
        channel = script_config.get("Update", "Channel") or Config.get("Update", "Channel")
        update_result = await update_maafw_project_if_needed(
            project_path,
            interface_model,
            mirror_cdk=mirror_cdk,
            channel=channel,
            proxy=Config.proxy,
            send_log=append_log,
        )

        if update_result.updated:
            refreshed_interface = load_interface_model_cached(
                project_path,
                force_reload=True,
            )
            append_log("MaaFW 项目已更新，准备 Agent Python 环境")
            await asyncio.to_thread(
                prepare_maafw_agent_python_envs,
                project_path,
                refreshed_interface,
                send_log=append_log,
            )

        return MaaFWProjectUpdateOut(
            message=update_result.message,
            data=MaaFWProjectUpdateData(
                checked=update_result.checked,
                updated=update_result.updated,
                currentVersion=update_result.current_version,
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
    payload: MaaFWAgentEnvPrepareIn = Body(...),
) -> MaaFWAgentEnvPrepareOut:
    """Prepare MaaFW Runner and agent Python envs before starting tasks."""

    from app.task.MaaFW.interface_loader import (
        MaaFWInterfaceLoadError,
        load_interface_model_cached,
    )
    from app.task.MaaFW.AutoProxy import prepare_maafw_runner_env
    from app.task.MaaFW.runner import prepare_maafw_agent_python_envs

    logs: list[str] = []
    root_path: Path | None = None
    agent_plans: list[Any] = []
    try:
        root_path = Path(payload.path).resolve()
        interface = load_interface_model_cached(root_path)
        await asyncio.to_thread(
            prepare_maafw_runner_env,
            root_path,
            send_log=logs.append,
        )
        agent_plans = await asyncio.to_thread(
            prepare_maafw_agent_python_envs,
            root_path,
            interface,
            send_log=logs.append,
        )
        agents = _build_maafw_agent_env_info_items(agent_plans)
        data = MaaFWAgentEnvPrepareData(
            path=str(root_path),
            agentCount=len(agents),
            agents=agents,
            logs=logs,
        )
    except MaaFWInterfaceLoadError as e:
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
    from app.task.MaaFW.interface_loader import (
        MaaFWInterfaceLoadError,
        load_interface_model_cached,
    )
    from app.task.MaaFW.window_service import (
        list_desktop_windows,
        match_controller_windows,
    )

    try:
        root_path = Path(payload.path).resolve()
        interface = load_interface_model_cached(root_path)
        controllers = _select_maafw_window_controllers(
            interface,
            payload.controllerName,
        )
        desktop_windows = list_desktop_windows()
        windows: list[MaaFWDesktopWindowInfo] = []
        for controller in controllers:
            for window in match_controller_windows(controller, desktop_windows):
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
) -> HSRStageOptionsOut:
    """按体力执行脚本返回 M7A / SRA 原生副本字段。"""

    from app.task.HSR.tools.stage_provider import get_hsr_stage_options

    try:
        if not scriptId:
            return HSRStageOptionsOut(
                code=400,
                status="error",
                message="缺少 scriptId",
            )

        script_config = Config.ScriptConfig[uuid.UUID(scriptId)]
        data = HSRStageOptionsData(**get_hsr_stage_options(script_config, engine))
        option_count = sum(
            len(category.options)
            for category in data.categories
        )
        return HSRStageOptionsOut(
            message=f"共 {option_count} 个 HSR 体力副本选项",
            data=data,
        )
    except Exception as e:
        return HSRStageOptionsOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
        )


@router.post(
    "/okww/configs/list",
    tags=["OKWW"],
    summary="获取 OK-WW 配置文件列表及 schema",
    status_code=200,
)
async def get_okww_configs_list(script_id: str, user_id: str):
    """
    获取 OK-WW 配置文件列表及 schema 定义。
    读写用户配置目录（data/{script_id}/{user_id}/ConfigFile/），
    若为空则自动从 ok-ww configs 目录初始化默认配置。

    Args:
        script_id: OK-WW 脚本 ID
        user_id: 用户 ID

    Returns:
        dict: 包含配置文件列表和 schema 的响应
    """
    try:
        import json
        from app.task.Okww.config_schema import (
            get_all_config_info, build_fields_for_config, load_okww_option_labels,
        )

        script_config = Config.ScriptConfig[uuid.UUID(script_id)]

        # 从 ok-ww 安装目录加载翻译 → option_labels
        root_path = script_config.get("Info", "RootPath")
        option_labels = load_okww_option_labels(root_path) if root_path else {}

        # 详细模式：每个用户独立持有一份 OK-WW 配置。
        mas_config_dir = ok_script_mas_config_dir(script_id, user_id)

        # ok-ww 源配置目录（从 RootPath 派生，用于自动初始化）
        okww_configs_dir = Path(root_path) / OKWW_PROVIDER.config_dir if root_path else None

        # 自动补齐默认配置：保留用户已有值，只补缺失文件和字段
        _ensure_okww_user_config_defaults(mas_config_dir, okww_configs_dir)

        configs_info = get_all_config_info()

        # 读取 per-user JSON 配置，通过 build_fields_for_config 构建字段列表
        result = []
        for info in configs_info:
            filename = info["filename"]
            filepath = mas_config_dir / filename
            current_data: dict[str, Any] = {}
            if filepath.exists():
                try:
                    current_data = json.loads(filepath.read_text(encoding="utf-8"))
                except Exception:
                    pass

            # 核心：JSON 自动发现字段 + 选项映射 + 翻译标签
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
    "/okww/configs/batch-update",
    tags=["OKWW"],
    summary="批量更新 OK-WW 配置文件",
    status_code=200,
)
async def batch_update_okww_configs(
    script_id: str = Body(...),
    user_id: str = Body(...),
    configs: dict = Body(...),
):
    """
    批量更新 OK-WW 配置文件

    Args:
        script_id: OK-WW 脚本 ID
        user_id: 用户 ID
        configs: { filename: data } 格式的配置数据

    Returns:
        dict: 操作结果
    """
    try:
        import json

        # 写入用户配置目录
        mas_config_dir = ok_script_mas_config_dir(script_id, user_id)
        mas_config_dir.mkdir(parents=True, exist_ok=True)

        updated_files = []
        for filename, data in configs.items():
            filepath = _ok_script_config_file_path(mas_config_dir, filename)
            existing_data = {}
            if filepath.exists():
                with open(filepath, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
            existing_data.update(data)
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=4)
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


@router.post(
    "/ok-script/configs/list",
    tags=["ok-script"],
    summary="获取 ok-script 配置文件列表和 schema",
    status_code=200,
)
async def get_ok_script_configs_list(script_id: str, user_id: str):
    """根据当前 provider 获取隔离的用户配置文件和 schema。"""
    try:
        import json

        _, root_path, provider = _resolve_ok_script_provider(script_id)
        build_fields_for_config, get_config_info, load_option_labels = (
            _load_ok_script_schema(provider)
        )

        option_labels = load_option_labels(root_path)
        mas_config_dir = ok_script_mas_config_dir(script_id, user_id)
        source_configs_dir = provider.config_path(root_path)

        need_init = not mas_config_dir.exists() or not any(mas_config_dir.iterdir())
        if need_init and source_configs_dir.is_dir():
            await asyncio.to_thread(
                _copy_tree_atomic,
                source_configs_dir,
                mas_config_dir,
            )

        configs_info = (
            get_config_info(mas_config_dir)
            if provider.config_info_uses_directory
            else get_config_info()
        )
        result = []
        for info in configs_info:
            filename = info["filename"]
            filepath = mas_config_dir / filename
            current_data: dict[str, Any] = {}
            if filepath.exists():
                try:
                    current_data = json.loads(filepath.read_text(encoding="utf-8"))
                except Exception:
                    pass

            fields = build_fields_for_config(filename, current_data, option_labels)
            result.append(
                {
                    **info,
                    "fieldCount": len(fields),
                    "fields": fields,
                    "currentData": current_data,
                }
            )

        return {
            "code": 200,
            "status": "success",
            "message": f"共 {len(result)} 个配置文件",
            "data": result,
            "optionLabels": option_labels,
            "configPath": str(mas_config_dir),
            "provider": provider.build_client_metadata(),
        }
    except ValueError as e:
        return {
            "code": 400,
            "status": "error",
            "message": str(e),
            "data": [],
        }
    except Exception as e:
        return {
            "code": 500,
            "status": "error",
            "message": f"{type(e).__name__}: {str(e)}",
            "data": [],
        }


@router.post(
    "/ok-script/configs/batch-update",
    tags=["ok-script"],
    summary="批量更新 ok-script 配置文件",
    status_code=200,
)
async def batch_update_ok_script_configs(
    script_id: str = Body(...),
    user_id: str = Body(...),
    configs: dict = Body(...),
):
    """批量更新当前 provider 对应的用户配置 JSON。"""
    try:
        import json

        _resolve_ok_script_provider(script_id)
        mas_config_dir = ok_script_mas_config_dir(script_id, user_id)
        mas_config_dir.mkdir(parents=True, exist_ok=True)

        updated_files = []
        for filename, data in configs.items():
            if not isinstance(data, dict):
                raise ValueError(f"配置文件 {filename} 的内容必须是对象")
            filepath = _ok_script_config_file_path(mas_config_dir, filename)
            existing_data = {}
            if filepath.exists():
                with open(filepath, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
            existing_data.update(data)
            _write_json_file_atomic(filepath, existing_data)
            updated_files.append(filename)

        return {
            "code": 200,
            "status": "success",
            "message": f"已更新 {len(updated_files)} 个配置文件",
            "data": updated_files,
        }
    except ValueError as e:
        return {
            "code": 400,
            "status": "error",
            "message": str(e),
        }
    except Exception as e:
        return {
            "code": 500,
            "status": "error",
            "message": f"{type(e).__name__}: {str(e)}",
        }


@router.post(
    "/okef/configs/list",
    tags=["OKEF"],
    summary="获取 ok-script 配置文件列表和 schema（兼容入口）",
    status_code=200,
)
async def get_okef_configs_list(script_id: str, user_id: str):
    """保留旧 OK-EF API 路径，内部统一走 ok-script provider。"""

    return await get_ok_script_configs_list(script_id, user_id)


@router.post(
    "/okef/configs/batch-update",
    tags=["OKEF"],
    summary="批量更新 ok-script 配置文件（兼容入口）",
    status_code=200,
)
async def batch_update_okef_configs(
    script_id: str = Body(...),
    user_id: str = Body(...),
    configs: dict = Body(...),
):
    """保留旧 OK-EF API 路径，内部统一走 ok-script provider。"""

    return await batch_update_ok_script_configs(script_id, user_id, configs)
