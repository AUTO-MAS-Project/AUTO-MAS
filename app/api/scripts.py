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
from typing import Any, Literal

from fastapi import APIRouter, Body

from app.core import Config
from app.models.config import OkNteConfig as RuntimeOkNteConfig
from app.models.schema import *

router = APIRouter(prefix="/api/scripts", tags=["脚本管理"])


def _okww_mas_config_dir(script_id: str, user_id: str) -> Path:
    return Path.cwd() / "data" / script_id / user_id / "ConfigFile"


def _okww_config_file_path(config_dir: Path, filename: str) -> Path:
    file_path = Path(filename)
    if (
        file_path.name != filename
        or file_path.is_absolute()
        or ".." in file_path.parts
    ):
        raise ValueError("配置文件名非法")
    return config_dir / filename


def _oknte_script_config(script_id: str) -> tuple[uuid.UUID, RuntimeOkNteConfig]:
    script_uid = uuid.UUID(script_id)
    script_config = Config.ScriptConfig[script_uid]
    if not isinstance(script_config, RuntimeOkNteConfig):
        raise ValueError("脚本配置类型错误, 不是 OK-NTE 类型")
    return script_uid, script_config


def _oknte_mas_config_dir(script_id: str) -> Path:
    script_uid, _ = _oknte_script_config(script_id)
    return Path.cwd() / "data" / str(script_uid) / "Default" / "ConfigFile"


def _oknte_config_file_path(config_dir: Path, filename: str) -> Path:
    file_path = Path(filename)
    if (
        file_path.name != filename
        or file_path.is_absolute()
        or ".." in file_path.parts
    ):
        raise ValueError("配置文件名非法")
    return config_dir / filename


SCRIPT_BOOK = {
    "MaaConfig": MaaConfig,
    "SrcConfig": SrcConfig,
    "MaaEndConfig": MaaEndConfig,
    "M9AConfig": M9AConfig,
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
        loader = M9ATaskLoader(m9a_path)
        
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
        import shutil
        from app.task.Okww.config_schema import (
            get_all_config_info, build_fields_for_config, load_okww_option_labels,
        )

        script_config = Config.ScriptConfig[uuid.UUID(script_id)]

        # 从 ok-ww 安装目录加载翻译 → option_labels
        root_path = script_config.get("Info", "RootPath")
        option_labels = load_okww_option_labels(root_path) if root_path else {}

        # 详细模式：每个用户独立持有一份 OK-WW 配置。
        mas_config_dir = _okww_mas_config_dir(script_id, user_id)

        # ok-ww 源配置目录（用于自动初始化）
        raw_config_path = script_config.get("Script", "ConfigPath")
        okww_configs_dir = Path(raw_config_path) if raw_config_path else None
        if not okww_configs_dir or not okww_configs_dir.exists():
            if root_path:
                okww_configs_dir = Path(root_path) / "data" / "apps" / "ok-ww" / "working" / "configs"

        # 自动初始化：用户目录为空时从 ok-ww configs 复制默认配置
        need_init = not mas_config_dir.exists() or not any(mas_config_dir.iterdir())
        if need_init and okww_configs_dir and okww_configs_dir.is_dir():
            mas_config_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(okww_configs_dir, mas_config_dir, dirs_exist_ok=True)

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
    "/okww/configs/update",
    tags=["OKWW"],
    summary="更新 OK-WW 配置文件",
    status_code=200,
)
async def update_okww_config(
    script_id: str = Body(...),
    user_id: str = Body(...),
    filename: str = Body(...),
    data: dict = Body(...),
):
    """
    更新 OK-WW 配置文件

    Args:
        script_id: OK-WW 脚本 ID
        user_id: 用户 ID
        filename: 配置文件名（如 DailyTask.json）
        data: 要更新的配置数据

    Returns:
        dict: 操作结果
    """
    try:
        import json

        # 写入用户配置目录
        mas_config_dir = _okww_mas_config_dir(script_id, user_id)
        mas_config_dir.mkdir(parents=True, exist_ok=True)

        filepath = _okww_config_file_path(mas_config_dir, filename)

        # 读取现有配置
        existing_data = {}
        if filepath.exists():
            with open(filepath, "r", encoding="utf-8") as f:
                existing_data = json.load(f)

        # 合并更新
        existing_data.update(data)

        # 写入用户目录
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=4)

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
        mas_config_dir = _okww_mas_config_dir(script_id, user_id)
        mas_config_dir.mkdir(parents=True, exist_ok=True)

        updated_files = []
        for filename, data in configs.items():
            filepath = _okww_config_file_path(mas_config_dir, filename)
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
    "/oknte/configs/list",
    tags=["OKNTE"],
    summary="获取 OK-NTE 配置文件列表及 schema",
    status_code=200,
)
async def get_oknte_configs_list(script_id: str):
    """
    获取 OK-NTE 配置文件列表及 schema 定义。
    读写 per-user 配置目录（data/{script_id}/Default/ConfigFile/），
    若为空则自动从 ok-nte configs 目录初始化默认配置。

    Args:
        script_id: OK-NTE 脚本 ID

    Returns:
        dict: 包含配置文件列表和 schema 的响应
    """
    try:
        import json
        import shutil
        from app.task.OkNte.config_schema import (
            get_all_config_info, build_fields_for_config, load_oknte_option_labels,
        )

        _, script_config = _oknte_script_config(script_id)

        # 从 ok-nte 安装目录加载翻译 → option_labels
        root_path = script_config.get("Info", "RootPath")
        option_labels = load_oknte_option_labels(root_path) if root_path else {}

        # per-user 配置目录（始终使用 Default，因为配置编辑器是脚本级的）
        mas_config_dir = _oknte_mas_config_dir(script_id)

        # ok-nte 源配置目录（用于自动初始化）
        raw_config_path = script_config.get("Script", "ConfigPath")
        oknte_configs_dir = Path(raw_config_path) if raw_config_path else None
        if not oknte_configs_dir or not oknte_configs_dir.exists():
            if root_path:
                root = Path(root_path)
                packaged_dir = root / "data" / "apps" / "ok-nte" / "working" / "configs"
                source_dir = root / "configs"
                oknte_configs_dir = packaged_dir if packaged_dir.is_dir() else source_dir

        # 自动初始化：per-user 目录为空时从 ok-nte configs 复制默认配置
        need_init = not mas_config_dir.exists() or not any(mas_config_dir.iterdir())
        if need_init and oknte_configs_dir and oknte_configs_dir.is_dir():
            mas_config_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(oknte_configs_dir, mas_config_dir, dirs_exist_ok=True)

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
    filename: str = Body(...),
    data: dict = Body(...),
):
    """
    更新 OK-NTE 配置文件

    Args:
        script_id: OK-NTE 脚本 ID
        filename: 配置文件名（如 DailyTask.json）
        data: 要更新的配置数据

    Returns:
        dict: 操作结果
    """
    try:
        import json

        # 写入 per-user 配置目录
        mas_config_dir = _oknte_mas_config_dir(script_id)
        mas_config_dir.mkdir(parents=True, exist_ok=True)

        filepath = _oknte_config_file_path(mas_config_dir, filename)

        existing_data = {}
        if filepath.exists():
            with open(filepath, "r", encoding="utf-8") as f:
                existing_data = json.load(f)

        existing_data.update(data)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=4)

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
    configs: dict = Body(...),
):
    """
    批量更新 OK-NTE 配置文件

    Args:
        script_id: OK-NTE 脚本 ID
        configs: { filename: data } 格式的配置数据

    Returns:
        dict: 操作结果
    """
    try:
        import json

        # 写入 per-user 配置目录
        mas_config_dir = _oknte_mas_config_dir(script_id)
        mas_config_dir.mkdir(parents=True, exist_ok=True)

        updated_files = []
        for filename, data in configs.items():
            filepath = _oknte_config_file_path(mas_config_dir, filename)
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
