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

"""HSR 配置恢复服务：MAS 用户字段池 / M7A+SRA 原生配置池。

池函数显式收 :class:`~app.utils.config_restore.RestoreContext`，全部逻辑
自包含（守卫走 ``ctx.script_config.UserData``，路径走专项字段与引擎路径
解析），不依赖核心门面内部方法。备份文件级原语见同目录 ``backup_archive``。

mas 池 = **纯字段侧车**（HSR 无 per-user 目录，用户配置即字段）：MAS 用户
配置全量（Info/TaskSwitch/Stage/TaskOpt/Notify/Control/Managed/Direct
元数据，平铺键 ``组.键``；Info.Mode 仅预览；不收录加密凭据与快照内容、
Data 运行统计、子表）。恢复 = 回填 UserData。native 池 = M7A config.yaml +
SRA settings.json/cache.json/configs/（按 SRA appdata 根分桶）。
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
from .native_control import resolve_script_path
from .sra_runtime import get_sra_app_data_dir

logger = get_logger("HSR 配置恢复")

RESTORE_SCRIPT_NAME = "hsr"
"""专项统一名（文案参数化用）"""


def _user_guard(ctx: RestoreContext) -> None:
    """恢复守卫：目标用户必须存在，避免把字段回填进孤儿配置。"""

    if uuid.UUID(ctx.user_id) not in ctx.script_config.UserData:
        raise ValueError("HSR 用户不存在，请刷新后重试")


def _m7a_root(ctx: RestoreContext) -> Path | None:
    """M7A 安装根；未配置返回 ``None``。"""

    raw = resolve_script_path(ctx.script_config, "M7A")
    return Path(raw) if raw else None


def _sra_app_data(ctx: RestoreContext) -> Path:
    """SRA appdata 共享目录（恒存在）。"""

    return get_sra_app_data_dir()


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
    archive_mas_backup(
        ctx.script_id, ctx.user_id, read_overlay_values(user), force=True
    )
    restored = restore_mas_backup(ctx.script_id, ctx.user_id, ts)
    if restored:
        await user.update(group_overlay(restored))


async def _snapshot_mas(ctx: RestoreContext) -> dict:
    _user_guard(ctx)
    user = ctx.script_config.UserData[uuid.UUID(ctx.user_id)]
    dest = archive_mas_backup(ctx.script_id, ctx.user_id, read_overlay_values(user))
    times = list_mas_backups(ctx.script_id, ctx.user_id)
    return {"created": dest is not None, "time": times[0] if times else ""}


async def _list_native(ctx: RestoreContext) -> list[str]:
    return list_native_backups(_sra_app_data(ctx))


async def _preview_native(ctx: RestoreContext, ts: str) -> dict:
    return build_native_preview(_sra_app_data(ctx), ts)


async def _restore_native(ctx: RestoreContext, ts: str) -> object:
    restore_native_backup(_m7a_root(ctx), _sra_app_data(ctx), ts)


async def _snapshot_native(ctx: RestoreContext) -> dict:
    dest = archive_native_backup(_m7a_root(ctx), _sra_app_data(ctx))
    times = list_native_backups(_sra_app_data(ctx))
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
