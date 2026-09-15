#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License
#   as published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.
#
#   Contact: DLmaster_361@163.com

"""HSR 配置恢复服务：MAS 用户字段池 / M7A+SRA 原生配置池（声明式池）。

池声明只提供**专项知识**（归档什么 + 放哪里 + 恢复语义 + 定制预览），
``list`` / ``snapshot`` / ``read_file`` / ``files`` 兜底全部由基座
（``app.utils.config_restore``）从 ``files`` + ``backup_root`` 声明派生。
备份文件级原语见同目录 ``backup_archive``。

mas 池 = **纯字段侧车**（HSR 无 per-user 目录，用户配置即字段）：MAS 用户
配置全量（Info/TaskSwitch/Stage/TaskOpt/Notify/Control/Managed/Direct
元数据，平铺键 ``组.键``；Info.Mode 仅预览；不收录加密凭据与快照内容、
Data 运行统计、子表）。恢复 = 回填 UserData。native 池 = M7A config.yaml +
SRA settings.json/cache.json/configs/（按 SRA appdata 根分桶）。
"""

import json
import uuid
from pathlib import Path

from app.utils import get_logger
from app.utils.config_restore import ConfigRestorePool, RestoreContext

from .backup_archive import (
    OVERLAY_SIDECAR_NAME,
    archive_mas_backup,
    build_native_preview,
    build_overlay_preview,
    collect_native_files,
    get_mas_backup_dir,
    group_overlay,
    mas_backup_root,
    native_backup_root,
    read_overlay_sidecar,
    read_overlay_values,
    restore_mas_backup,
    restore_native_backup,
)
from .native_control import resolve_script_path
from .sra_runtime import get_sra_app_data_dir

logger = get_logger("HSR 配置恢复")


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


# ══════════════════ mas 池（声明式 + 定制预览/恢复） ══════════════════


async def _mas_files(ctx: RestoreContext) -> dict[str, str] | None:
    """归档内容 = 页面核心字段侧车（内存 JSON，免临时文件）。"""

    _user_guard(ctx)
    user = ctx.script_config.UserData[uuid.UUID(ctx.user_id)]
    overlay = read_overlay_values(user)
    if not overlay:
        return None
    return {OVERLAY_SIDECAR_NAME: json.dumps(overlay, ensure_ascii=False, indent=2)}


async def _mas_root(ctx: RestoreContext) -> Path:
    return mas_backup_root(ctx.script_id, ctx.user_id)


async def _preview_mas(ctx: RestoreContext, ts: str) -> dict:
    backup_dir = get_mas_backup_dir(ctx.script_id, ctx.user_id, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    overlay = read_overlay_sidecar(backup_dir)
    return build_overlay_preview(overlay) if overlay else {"sections": []}


async def _restore_mas(ctx: RestoreContext, ts: str) -> None:
    _user_guard(ctx)
    user = ctx.script_config.UserData[uuid.UUID(ctx.user_id)]
    overlay = read_overlay_values(user)
    if overlay:
        archive_mas_backup(ctx.script_id, ctx.user_id, overlay, force=True)
    restored = restore_mas_backup(ctx.script_id, ctx.user_id, ts)
    if restored:
        await user.update(group_overlay(restored))


# ══════════════════ native 池（声明式 + 定制预览/恢复） ══════════════════


async def _native_files(ctx: RestoreContext) -> dict[str, Path] | None:
    """归档内容 = 两引擎原生配置文件集（缺失项跳过，全缺失返回 None）。"""

    return collect_native_files(_m7a_root(ctx), _sra_app_data(ctx)) or None


async def _native_root(ctx: RestoreContext) -> Path:
    return native_backup_root(_sra_app_data(ctx))


async def _preview_native(ctx: RestoreContext, ts: str) -> dict:
    return build_native_preview(_sra_app_data(ctx), ts)


async def _restore_native(ctx: RestoreContext, ts: str) -> None:
    restore_native_backup(_m7a_root(ctx), _sra_app_data(ctx), ts)


RESTORE_POOLS = [
    ConfigRestorePool(
        key="mas",
        kind="user",
        mas_mode="sidecar_only",
        files=_mas_files,
        backup_root=_mas_root,
        preview=_preview_mas,
        restore=_restore_mas,
    ),
    ConfigRestorePool(
        key="native",
        kind="script",
        files=_native_files,
        backup_root=_native_root,
        preview=_preview_native,
        restore=_restore_native,
    ),
]
