#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, version 3 or (at your option)
#   any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""MaaFW 配置恢复服务：MAS 用户字段池 / MaaFW 项目配置池。

池函数显式收 :class:`~app.utils.config_restore.RestoreContext`，全部逻辑
自包含（守卫与 owner 解析走 ``ctx.script_config.UserData``，路径走专项
字段），不依赖核心门面内部方法。备份文件级原语见同目录 ``backup_archive``。

mas 池 = **纯字段侧车**（MaaFW 无 per-user 目录，用户配置是字段）：
Info（Mode 仅预览 / IfQuickConfig / Account / Controller / Resource）+
Task（SelectedPreset / TaskSnapshot）+ Device 段。恢复 = 回填 UserData。
池恒按用户分桶。native 池 = MaaFW 项目 ``config/`` + ``interface.json``，
按物理项目根指纹分桶（脚本级共享、跨脚本复用）。
"""

import uuid
from pathlib import Path

from app.utils import get_logger
from app.utils.config_restore import ConfigRestorePool, RestoreContext

from .backup_archive import (
    archive_mas_backup,
    archive_native_backup,
    build_native_preview,
    build_overlay_preview,
    get_mas_backup_dir,
    group_overlay,
    list_mas_backups,
    list_native_backups,
    read_overlay_sidecar,
    read_overlay_values,
    restore_mas_backup,
    restore_native_backup,
)

logger = get_logger("MaaFW 配置恢复")

RESTORE_SCRIPT_NAME = "maafw"
"""专项统一名（文案参数化用）"""


def _user_guard(ctx: RestoreContext) -> None:
    """恢复守卫：目标用户必须存在，避免把字段回填进孤儿配置。"""

    if uuid.UUID(ctx.user_id) not in ctx.script_config.UserData:
        raise ValueError("MaaFW 用户不存在，请刷新后重试")


def _project_path(ctx: RestoreContext) -> Path | None:
    """MaaFW 项目根目录（含 interface.json）；未配置脚本路径返回 ``None``。"""

    raw = str(ctx.script_config.get("Info", "Path") or "").strip()
    return Path(raw) if raw else None


async def _list_mas(ctx: RestoreContext) -> list[str]:
    return list_mas_backups(ctx.script_id, ctx.user_id)


async def _preview_mas(ctx: RestoreContext, ts: str) -> dict:
    backup_dir = get_mas_backup_dir(ctx.script_id, ctx.user_id, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    overlay = read_overlay_sidecar(backup_dir)
    if overlay is None:
        return {"sections": []}
    return build_overlay_preview(overlay)


async def _restore_mas(ctx: RestoreContext, ts: str) -> object:
    _user_guard(ctx)
    user = ctx.script_config.UserData[uuid.UUID(ctx.user_id)]
    # 恢复前把当前字段终态存底（force），误恢复可找回
    archive_mas_backup(
        ctx.script_id, ctx.user_id, read_overlay_values(user), force=True
    )
    restored = restore_mas_backup(ctx.script_id, ctx.user_id, ts)
    if restored:
        await user.update(group_overlay(restored))


async def _snapshot_mas(ctx: RestoreContext) -> dict:
    _user_guard(ctx)
    user = ctx.script_config.UserData[uuid.UUID(ctx.user_id)]
    dest = archive_mas_backup(
        ctx.script_id, ctx.user_id, read_overlay_values(user)
    )
    times = list_mas_backups(ctx.script_id, ctx.user_id)
    return {"created": dest is not None, "time": times[0] if times else ""}


async def _list_native(ctx: RestoreContext) -> list[str]:
    project_path = _project_path(ctx)
    if project_path is None:
        return []
    return list_native_backups(project_path)


async def _preview_native(ctx: RestoreContext, ts: str) -> dict:
    project_path = _project_path(ctx)
    if project_path is None:
        return {"sections": []}
    return build_native_preview(project_path, ts)


async def _restore_native(ctx: RestoreContext, ts: str) -> object:
    project_path = _project_path(ctx)
    if project_path is None:
        raise ValueError("请先设置 MaaFW 项目路径")
    restore_native_backup(project_path, ts)


async def _snapshot_native(ctx: RestoreContext) -> dict:
    project_path = _project_path(ctx)
    dest = archive_native_backup(project_path) if project_path is not None else None
    times = list_native_backups(project_path) if project_path is not None else []
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
