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
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Body

from app.core import Config
from app.models.config import HSRConfig as RuntimeHSRConfig
from app.models.config import OkNteConfig as RuntimeOkNteConfig
from app.models.schema import *
from app.task.HSR.tools.external_locks import (
    HSRExternalPathBusyError,
    acquire_external_path_locks,
    resolve_external_lock_paths,
)

router = APIRouter(prefix="/api/scripts", tags=["脚本管理"])

# 原生配置器会话只由 API 进程持有；任务管理器直控会话仍由 HSRManager 管理。
_HSR_CONFIGURATOR_SESSIONS: dict[tuple[str, str], Any] = {}
_HSR_CONFIGURATOR_LEASES: dict[tuple[str, str], Any] = {}
_HSR_CONFIGURATOR_WATCHERS: dict[tuple[str, str], asyncio.Task[Any]] = {}


def _hsr_script_config(script_id: str):
    """Resolve an HSR script and reject cross-type IDs before domain access."""

    script_config = Config.ScriptConfig[uuid.UUID(script_id)]
    if not isinstance(script_config, RuntimeHSRConfig):
        raise TypeError("脚本配置类型错误, 不是 HSR 类型")
    return script_config


def _hsr_user_config(script_config: RuntimeHSRConfig, user_id: str):
    user_config = script_config.UserData[uuid.UUID(user_id)]
    return user_config


async def close_hsr_configurator_sessions() -> None:
    """关闭 API 进程持有的 HSR 原生配置器会话。

    主应用使用自定义 lifespan 时可在 shutdown 阶段显式调用本函数；保留
    为独立函数也便于测试和其他宿主挂载，不让已退出的 subprocess 对象泄漏。
    """

    sessions = list(_HSR_CONFIGURATOR_SESSIONS.items())
    leases = dict(_HSR_CONFIGURATOR_LEASES)
    watchers = list(_HSR_CONFIGURATOR_WATCHERS.values())
    _HSR_CONFIGURATOR_SESSIONS.clear()
    _HSR_CONFIGURATOR_LEASES.clear()
    _HSR_CONFIGURATOR_WATCHERS.clear()

    current_task = asyncio.current_task()
    for watcher in watchers:
        if watcher is current_task or watcher.done():
            continue
        watcher.cancel()
    for watcher in watchers:
        if watcher is current_task:
            continue
        try:
            await watcher
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    session_keys = {key for key, _session in sessions}
    for key, session in sessions:
        try:
            await session.close()
        except Exception:
            # 关闭阶段不应因单个原生进程异常阻塞宿主退出。
            pass
        finally:
            _release_hsr_external_lock(leases.get(key))
    # 防御启动/替换异常留下的 lease-only 条目；release 本身幂等。
    for key, lease in leases.items():
        if key not in session_keys:
            _release_hsr_external_lock(lease)


def _release_hsr_external_lock(lease: Any | None) -> None:
    """释放一个 HSR 外部路径租约；外部锁的 release 本身是幂等的。"""

    if lease is None:
        return
    try:
        lease.release()
    except Exception:
        # 进程退出/原生进程失败时也不能让清理路径中断。
        pass


async def _close_hsr_configurator_entry(
    key: tuple[str, str],
    *,
    session: Any | None = None,
    lease: Any | None = None,
) -> None:
    """关闭一个配置器并释放与其绑定的外部路径租约。"""

    registered_session = _HSR_CONFIGURATOR_SESSIONS.get(key)
    if session is None:
        session = registered_session
    if registered_session is session:
        _HSR_CONFIGURATOR_SESSIONS.pop(key, None)

    registered_lease = _HSR_CONFIGURATOR_LEASES.get(key)
    if lease is None:
        lease = registered_lease
    if registered_lease is lease:
        _HSR_CONFIGURATOR_LEASES.pop(key, None)

    watcher = _HSR_CONFIGURATOR_WATCHERS.pop(key, None)
    current_task = asyncio.current_task()
    if watcher is not None and watcher is not current_task and not watcher.done():
        watcher.cancel()
        try:
            await watcher
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    try:
        if session is not None:
            await session.close()
    finally:
        _release_hsr_external_lock(lease)


async def _watch_hsr_configurator_entry(
    key: tuple[str, str],
    session: Any,
    lease: Any,
) -> None:
    """观察原生配置器自然退出，及时释放其外部路径租约。"""

    try:
        wait = getattr(session, "wait", None)
        if callable(wait):
            await wait()
    except asyncio.CancelledError:
        return
    except Exception:
        # status/open/stop 的 envelope 仍负责报告状态；watcher 只负责收尾。
        return
    finally:
        if _HSR_CONFIGURATOR_SESSIONS.get(key) is session:
            _HSR_CONFIGURATOR_SESSIONS.pop(key, None)
        if _HSR_CONFIGURATOR_LEASES.get(key) is lease:
            _HSR_CONFIGURATOR_LEASES.pop(key, None)
        if _HSR_CONFIGURATOR_WATCHERS.get(key) is asyncio.current_task():
            _HSR_CONFIGURATOR_WATCHERS.pop(key, None)
        try:
            await session.close()
        except Exception:
            # 自然退出后的 watcher 不能留下未取出的 Task 异常；租约仍必须释放。
            pass
        finally:
            _release_hsr_external_lock(lease)


@router.on_event("shutdown")
async def _shutdown_hsr_configurator_sessions() -> None:
    """在标准 FastAPI router shutdown 生命周期中释放原生配置器。"""

    await close_hsr_configurator_sessions()


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
    lease = None

    try:
        script_config = _hsr_script_config(payload.scriptId)
        _hsr_user_config(script_config, payload.userId)
        m7a_path_str = str(
            script_config.get("M7A", "Path")
            or script_config.get("Info", "M7APath")
            or ""
        ).strip()
        if not m7a_path_str:
            raise ValueError("请先在脚本配置页配置三月七路径")

        m7a_config_path = Path(m7a_path_str) / "config.yaml"
        lease = await acquire_external_path_locks(
            resolve_external_lock_paths(script_config, ("M7A",)),
            wait=False,
        )
        write_snapshots, raw_items = read_m7a_abyss_snapshots(m7a_config_path)
        items = [AbyssSnapshotImportItem(**item) for item in raw_items]

        await Config.update_user(
            payload.scriptId,
            payload.userId,
            {"Abyss": {"Snapshots": json.dumps(write_snapshots, ensure_ascii=False)}},
        )
        _, user_data_dict = await Config.get_user(payload.scriptId, payload.userId)
        canonical_user_id = str(uuid.UUID(payload.userId))
        updated_user_data = HSRUserConfig(**user_data_dict[canonical_user_id])
    except HSRExternalPathBusyError as e:
        return AbyssSnapshotImportOut(
            code=409,
            status="error",
            message=f"导入三深渊快照失败: {type(e).__name__}: {e}",
            m7aConfigPath=str(m7a_config_path) if m7a_config_path else "",
            items=items,
            updatedUserData=HSRUserConfig(),
        )
    except Exception as e:
        return AbyssSnapshotImportOut(
            code=400
            if isinstance(e, (FileNotFoundError, ValueError, KeyError, TypeError))
            else 500,
            status="error",
            message=f"导入三深渊快照失败: {type(e).__name__}: {e}",
            m7aConfigPath=str(m7a_config_path) if m7a_config_path else "",
            items=items,
            updatedUserData=HSRUserConfig(),
        )
    finally:
        _release_hsr_external_lock(lease)

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
    """返回 M7A/SRA 原生副本字段；userId 仅校验归属，slot 为兼容参数。"""

    from app.task.HSR.tools.stage_provider import get_hsr_stage_options

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
    """返回 old dev 内置 HSR 的能力与原生适配器状态。"""

    try:
        if not scriptId:
            return HSRCapabilitiesOut(code=400, status="error", message="缺少 scriptId")
        script_config = _hsr_script_config(scriptId)
        from app.task.HSR.task_mapping import HSR_TASK_MODULES
        from app.task.HSR.tools.native_control import native_provider

        adapters: list[dict[str, Any]] = []
        configured: list[str] = []
        effective: list[str] = []
        for engine in ("M7A", "SRA"):
            provider = native_provider(engine)
            snapshot = provider.inspect(script_config).asdict()
            path = script_config.get(
                engine, "Path"
            ) or script_config.get("Info", f"{engine}Path")
            if path:
                configured.append(engine)
            engine_ready = bool(
                snapshot["configurator_ready"] or snapshot["direct_run_ready"]
            )
            # Registry effective 表示已配置且属于候代引擎；launcher/config
            # readiness 单独保留在 adapter.ready，不应让 UI 隐藏已配置引擎。
            if path:
                effective.append(engine)
            adapters.append(
                {
                    "engine": engine,
                    "display_name": "三月七助手" if engine == "M7A" else "StarRailAssistant",
                    "version": None,
                    "supported_modes": ["managed", "direct"],
                    "capabilities": {
                        "native_config": snapshot["configurator_ready"],
                        "direct_control": snapshot["direct_run_ready"],
                    },
                    "ready": engine_ready,
                    "ready_reason": (
                        None
                        if engine_ready
                        else snapshot["configurator_reason"]
                        or snapshot["direct_run_reason"]
                        or None
                    ),
                    "native_control": snapshot,
                }
            )
        effective_set = set(effective)
        tasks = []
        for module in HSR_TASK_MODULES:
            task_engines = [
                engine
                for engine in module.supported_scripts
                if engine in effective_set
            ]
            if not task_engines:
                continue
            strategies: dict[str, list[str]] = {}
            if "M7A" in task_engines:
                strategies["M7A"] = list(module.m7a_tasks)
            if "SRA" in task_engines:
                strategies["SRA"] = [module.sra_task] if module.sra_task else []
            tasks.append(
                {
                    "key": module.key,
                    "name": module.name,
                    "phase": module.category,
                    "description": module.description,
                    "engines": task_engines,
                    "strategies": strategies,
                }
            )
        data = HSRCapabilitiesData(
            revision="old-dev",
            # 候代引擎始终是双引擎；能力是否 available 仍按当前脚本
            # 至少配置一个路径判断，和插件 registry snapshot 保持一致。
            available=bool(configured),
            unavailable_reason=(
                None if configured else "请至少配置一个已加载的 HSR 引擎路径"
            ),
            candidate_engines=["M7A", "SRA"],
            configured_engines=configured,
            effective_engines=effective,
            supported_modes=["managed", "direct"],
            adapters=adapters,
            tasks=tasks,
            warnings=[],
        )
        return HSRCapabilitiesOut(data=data)
    except Exception as e:
        return HSRCapabilitiesOut(
            code=400 if isinstance(e, (ValueError, KeyError)) else 500,
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
    """返回原生动态字段；无可用原生配置时返回可解释的空表单。"""

    try:
        if not scriptId:
            return HSRManagedConfigOut(
                code=400, status="error", message="缺少 scriptId"
            )
        script_config = _hsr_script_config(scriptId)
        user_config = None
        if userId:
            user_config = _hsr_user_config(script_config, userId)
        from app.task.HSR.task_mapping import HSR_TASK_MODULES
        from app.task.HSR.tools.managed_config import list_managed_modules

        effective = [
            engine
            for engine in ("M7A", "SRA")
            if script_config.get(engine, "Path")
            or script_config.get("Info", f"{engine}Path")
        ]
        effective_set = set(effective)
        task_forms: dict[str, dict[str, dict[str, Any]]] = {
            module.key: {} for module in HSR_TASK_MODULES
        }
        warnings: list[str] = []
        for engine in effective:
            try:
                for module in list_managed_modules(engine, script_config, user_config):
                    task_forms[module.key][engine] = module.asdict()
            except (FileNotFoundError, ValueError, OSError) as exc:
                warnings.append(f"{engine} 动态托管字段不可用：{exc}")

        task_mapping: dict[str, str] = {}
        for module in HSR_TASK_MODULES:
            task_engines = [
                engine
                for engine in module.supported_scripts
                if engine in effective_set
            ]
            if not task_engines:
                continue
            mapped = script_config.get("TaskMapping", module.key)
            normalized = str(mapped).upper()
            task_mapping[module.key] = (
                normalized if normalized in task_engines else task_engines[0]
            )
        if user_config is not None:
            raw_mapping = user_config.get("Managed", "TaskMapping")
            try:
                user_mapping = json.loads(raw_mapping)
            except (TypeError, ValueError, json.JSONDecodeError):
                user_mapping = {}
            if isinstance(user_mapping, dict):
                for key, value in user_mapping.items():
                    normalized = str(value).upper()
                    module = next(
                        (item for item in HSR_TASK_MODULES if item.key == str(key)),
                        None,
                    )
                    available = (
                        [
                            engine
                            for engine in module.supported_scripts
                            if engine in effective_set
                        ]
                        if module is not None
                        else []
                    )
                    if normalized in available:
                        task_mapping[str(key)] = normalized

        tasks: list[dict[str, Any]] = []
        for module in HSR_TASK_MODULES:
            task_engines = [
                engine
                for engine in module.supported_scripts
                if engine in effective_set
            ]
            if not task_engines:
                continue
            forms = task_forms[module.key]
            tasks.append(
                {
                    "key": module.key,
                    "name": module.name,
                    "phase": module.category,
                    "description": module.description,
                    "engines": task_engines,
                    "strategies": {
                        engine: (
                            list(module.m7a_tasks)
                            if engine == "M7A"
                            else [module.sra_task]
                            if module.sra_task
                            else []
                        )
                        for engine in task_engines
                    },
                    "forms": forms,
                }
            )
        data = HSRManagedConfigData(
            revision="old-dev", tasks=tasks, task_mapping=task_mapping, warnings=warnings
        )
        return HSRManagedConfigOut(data=data)
    except Exception as e:
        return HSRManagedConfigOut(
            code=400 if isinstance(e, (ValueError, KeyError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
        )


@router.get(
    "/hsr/native-configs",
    tags=["HSR"],
    summary="获取 HSR 原生配置器状态",
    response_model=HSRNativeConfigOut,
    status_code=200,
)
async def get_hsr_native_configs_api(
    scriptId: str | None = None, engine: Literal["M7A", "SRA"] = "M7A"
) -> HSRNativeConfigOut:
    """仅检查启动器和配置文件路径，不读取配置内容。"""

    try:
        if not scriptId:
            return HSRNativeConfigOut(code=400, status="error", message="缺少 scriptId")
        script_config = _hsr_script_config(scriptId)
        from app.task.HSR.tools.native_control import native_provider

        data_dict = native_provider(engine).inspect(script_config).asdict()
        session = _HSR_CONFIGURATOR_SESSIONS.get((scriptId, engine))
        if session is not None:
            if not session.running:
                await _close_hsr_configurator_entry(
                    (scriptId, engine),
                    session=session,
                )
                session = None
            else:
                data_dict["running"] = True
                data_dict["pid"] = session.pid
        data = HSRNativeControlSnapshot(**data_dict)
        return HSRNativeConfigOut(data=data)
    except Exception as e:
        return HSRNativeConfigOut(
            code=400 if isinstance(e, (ValueError, KeyError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
        )


@router.get(
    "/hsr/native-config/status",
    tags=["HSR"],
    summary="获取 HSR 原生配置器状态",
    response_model=HSRNativeConfigOut,
    status_code=200,
)
async def get_hsr_native_status_api(
    scriptId: str | None = None, engine: Literal["M7A", "SRA"] = "M7A"
) -> HSRNativeConfigOut:
    return await get_hsr_native_configs_api(scriptId=scriptId, engine=engine)


@router.post(
    "/hsr/native-config/open",
    tags=["HSR"],
    summary="打开 HSR 原生配置器",
    response_model=HSRNativeConfigOut,
    status_code=200,
)
async def open_hsr_native_config_api(
    request: HSRNativeConfigActionIn = Body(...),
) -> HSRNativeConfigOut:
    lease = None
    session = None
    key = (request.scriptId, request.engine)

    async def _cleanup_failed_open() -> None:
        nonlocal lease
        if lease is None:
            return
        try:
            if session is not None or _HSR_CONFIGURATOR_SESSIONS.get(key) is not None:
                await _close_hsr_configurator_entry(
                    key,
                    session=session,
                    lease=lease,
                )
            else:
                _release_hsr_external_lock(lease)
        except BaseException:
            _release_hsr_external_lock(lease)
        finally:
            lease = None

    try:
        script_config = _hsr_script_config(request.scriptId)
        from app.task.HSR.tools.native_control import native_provider

        # 配置器与 HSRManager 共用同一组安装目录锁；同一事件循环中不等待，
        # 让 UI 能明确提示“任务/配置器占用中”，避免并发改写原生配置。
        previous = _HSR_CONFIGURATOR_SESSIONS.get(key)
        if previous is not None:
            await _close_hsr_configurator_entry(key, session=previous)
        paths = resolve_external_lock_paths(script_config, (request.engine,))
        lease = await acquire_external_path_locks(paths, wait=False)
        session = await native_provider(request.engine).open_configurator(
            script_config=script_config, log=lambda _message: None
        )
        _HSR_CONFIGURATOR_SESSIONS[key] = session
        _HSR_CONFIGURATOR_LEASES[key] = lease
        try:
            _HSR_CONFIGURATOR_WATCHERS[key] = asyncio.create_task(
                _watch_hsr_configurator_entry(key, session, lease)
            )
        except BaseException:
            _HSR_CONFIGURATOR_SESSIONS.pop(key, None)
            _HSR_CONFIGURATOR_LEASES.pop(key, None)
            try:
                await session.close()
            finally:
                _release_hsr_external_lock(lease)
            lease = None
            raise
        data_dict = native_provider(request.engine).inspect(script_config).asdict()
        data_dict["running"] = True
        data_dict["pid"] = session.pid
        # session/lease 已登记并由 watcher 持有；本地变量保留到 return 表达式
        # 完成，若响应模型构造失败，except 仍可统一关闭三张 registry 表。
        return HSRNativeConfigOut(data=HSRNativeControlSnapshot(**data_dict))
    except HSRExternalPathBusyError as e:
        await _cleanup_failed_open()
        return HSRNativeConfigOut(
            code=409, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    except (FileNotFoundError, KeyError, TypeError, ValueError, RuntimeError) as e:
        await _cleanup_failed_open()
        return HSRNativeConfigOut(
            code=400, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    except OSError as e:
        await _cleanup_failed_open()
        return HSRNativeConfigOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    except BaseException:
        await _cleanup_failed_open()
        raise


@router.post(
    "/hsr/native-config/stop",
    tags=["HSR"],
    summary="停止 HSR 原生配置器",
    response_model=HSRNativeStopOut,
    status_code=200,
)
async def stop_hsr_native_config_api(
    request: HSRNativeConfigActionIn = Body(...),
) -> HSRNativeStopOut:
    try:
        _hsr_script_config(request.scriptId)
        key = (request.scriptId, request.engine)
        session = _HSR_CONFIGURATOR_SESSIONS.get(key)
        await _close_hsr_configurator_entry(key, session=session)
        return HSRNativeStopOut(
            data=HSRNativeStopData(engine=request.engine, running=False, pid=None)
        )
    except (KeyError, TypeError, ValueError, RuntimeError, OSError) as e:
        return HSRNativeStopOut(
            code=400, status="error", message=f"{type(e).__name__}: {str(e)}"
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
    lease = None
    try:
        script_config = _hsr_script_config(request.scriptId)
        # 先校验用户归属，再让 provider 读取原生文件，避免无效请求触碰用户配置。
        _hsr_user_config(script_config, request.userId)
        # 原生 provider 负责选择和校验配置文件；这里仅保存加密快照元数据。
        from app.task.HSR.tools.native_control import native_provider

        # 导出期间同样需要与 HSRManager/配置器共享外部路径锁，避免读到
        # manager 恢复配置或配置器写盘过程中的中间态。
        paths = resolve_external_lock_paths(script_config, (request.engine,))
        lease = await acquire_external_path_locks(paths, wait=False)
        source_path, content = native_provider(request.engine).export_config(script_config)
        imported_at = datetime.now(timezone.utc).isoformat()
        await Config.update_user(
            request.scriptId,
            request.userId,
            {
                "Direct": {
                    f"{request.engine}Config": content,
                    f"{request.engine}ImportedAt": imported_at,
                    f"{request.engine}Source": str(source_path),
                }
            },
        )
        return HSRDirectConfigImportOut(
            message=f"{request.engine} 原生配置已导入",
            data=HSRDirectConfigImportData(
                engine=request.engine,
                source=str(source_path),
                imported_at=imported_at,
                size=len(content.encode("utf-8")),
            ),
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
    finally:
        _release_hsr_external_lock(lease)


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
            get_all_config_info, build_fields_for_config, load_oknte_option_labels,
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
        import json

        # 写入用户配置目录
        mas_config_dir = _oknte_mas_config_dir(script_id, user_id)
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
        import json

        # 写入用户配置目录
        mas_config_dir = _oknte_mas_config_dir(script_id, user_id)
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
