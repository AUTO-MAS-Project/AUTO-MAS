#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public
#   License along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""OK-NTE 配置恢复池声明：备份工具函数 + 用户守卫，供基座统一分发。

池函数显式收 :class:`~app.utils.config_restore.RestoreContext`，全部逻辑
自包含（守卫走 ``ctx.script_config.UserData``，路径/模式走专项字段），不
依赖核心门面内部方法。备份文件级原语见同目录 ``backup_archive``。
"""

import uuid
from pathlib import Path

from app.task.OkNte.config_schema import (
    DAILY_ROUTINE_CONFIGS_FILE,
    DAILY_ROUTINE_TASK_FILE,
    load_oknte_option_labels,
)
from app.utils.config_restore import ConfigRestorePool

from .backup_archive import (
    archive_mas_backup,
    archive_native_backup,
    build_backup_file_summary,
    get_mas_backup_dir,
    get_native_backup_dir,
    list_mas_backups,
    list_native_backups,
    mas_config_dir,
    restore_mas_backup,
    restore_native_backup,
)

RESTORE_SCRIPT_NAME = "ok-nte"
"""专项统一名（文案参数化用）"""


def _user_guard(ctx) -> None:
    """恢复守卫：目标用户必须存在，避免把配置恢复进孤儿目录。"""

    if uuid.UUID(ctx.user_id) not in ctx.script_config.UserData:
        raise ValueError("OK-NTE 用户不存在，请刷新后重试")


def _native_config_path(ctx) -> tuple[Path | None, str]:
    """原生配置路径与模式（Folder/File）；未配置路径返回 None。"""

    raw = str(ctx.script_config.get("Script", "ConfigPath") or "").strip()
    mode = str(ctx.script_config.get("Script", "ConfigPathMode") or "Folder")
    return (Path(raw) if raw else None, mode)


async def _list_mas(ctx) -> list[str]:
    return list_mas_backups(ctx.script_id, ctx.user_id)


async def _list_native(ctx) -> list[str]:
    config_path, _ = _native_config_path(ctx)
    if config_path is None:
        return []
    return list_native_backups(config_path)


def _preview_payload(ctx, ts: str, backup: Path | None) -> dict:
    """两个目标池内容同构（ok-nte JSON 配置文件集）：预览只给任务配置两件套
    （日常任务流程 + 日常子任务配置，即 MAS 编辑页「任务配置」组，对齐一条龙
    的「编排清单」预览），其余文件经「查看详细配置」恢复后在 ok-nte GUI 里
    查看。

    载荷必须是 dict（通用预览响应模型的 ``data`` 字段），文件列表挂在
    ``files`` 键下，前端 ``#preview`` 插槽按 ``raw.files`` 消费。
    """

    if backup is None:
        raise ValueError(f"备份不存在: {ts}")
    root_path = str(ctx.script_config.get("Info", "RootPath") or "")
    labels = load_oknte_option_labels(root_path) if root_path else {}
    keep = (DAILY_ROUTINE_TASK_FILE, DAILY_ROUTINE_CONFIGS_FILE)
    files = [f for f in build_backup_file_summary(backup, labels) if f["name"] in keep]
    return {"files": files}


async def _preview_mas(ctx, ts: str) -> dict:
    return _preview_payload(ctx, ts, get_mas_backup_dir(ctx.script_id, ctx.user_id, ts))


async def _preview_native(ctx, ts: str) -> dict:
    config_path, _ = _native_config_path(ctx)
    if config_path is None:
        return {"files": []}
    return _preview_payload(ctx, ts, get_native_backup_dir(config_path, ts))


async def _restore_mas(ctx, ts: str) -> object:
    _user_guard(ctx)
    restore_mas_backup(
        ctx.script_id, ctx.user_id, ts, mas_config_dir(ctx.script_id, ctx.user_id)
    )


async def _restore_native(ctx, ts: str) -> object:
    config_path, mode = _native_config_path(ctx)
    if config_path is None:
        raise ValueError("请先设置 OK-NTE 配置路径")
    restore_native_backup(config_path, ts, mode)


async def _snapshot_mas(ctx) -> dict:
    dest = archive_mas_backup(
        ctx.script_id, ctx.user_id, mas_config_dir(ctx.script_id, ctx.user_id)
    )
    times = list_mas_backups(ctx.script_id, ctx.user_id)
    return {"created": dest is not None, "time": times[0] if times else ""}


async def _snapshot_native(ctx) -> dict:
    config_path, mode = _native_config_path(ctx)
    dest = archive_native_backup(config_path, mode) if config_path is not None else None
    times = list_native_backups(config_path) if config_path is not None else []
    return {"created": dest is not None, "time": times[0] if times else ""}


RESTORE_POOLS = [
    ConfigRestorePool(
        key="mas",
        kind="user",
        list_backups=_list_mas,
        preview=_preview_mas,
        restore=_restore_mas,
        snapshot=_snapshot_mas,
    ),
    ConfigRestorePool(
        key="native",
        kind="script",
        list_backups=_list_native,
        preview=_preview_native,
        restore=_restore_native,
        snapshot=_snapshot_native,
    ),
]
