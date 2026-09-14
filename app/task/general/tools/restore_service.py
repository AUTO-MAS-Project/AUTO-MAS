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

"""通用脚本配置恢复服务：MAS 用户配置副本池 / 脚本原生配置池。

- ``mas`` 池（用户级）：该用户的 ``ConfigFile`` 目录副本（General 恒按
  用户隔离，无 MAA 式 owner 解耦），恢复 = 整目录回写；MAS 编辑页字段
  不注入原生配置，无侧车、无字段回填。
- ``native`` 池（脚本级）：用户自填的 ``Script.ConfigPath``（Folder 整
  目录 / File 单文件两态），按物理配置根指纹分桶，恢复前强制存底当前。

归档时机：manager ``prepare``（任务级 native 一次）、运行/会话下发前
（AutoProxy / ScriptConfig）、编辑界面进入（native）/ 退出（mas）由前端
``ensure`` 触发。预览为文件清单粒度（配置格式任意透传），详细内容经
「查看详细配置」（viewOnly 会话）在脚本 GUI 里查看。
"""

import uuid
from pathlib import Path

from app.utils import get_logger
from app.utils.config_restore import ConfigRestorePool, RestoreContext

from .backup_archive import (
    archive_mas_backup,
    archive_native_backup,
    build_file_list_preview,
    get_mas_backup_dir,
    get_native_backup_dir,
    list_mas_backups,
    list_native_backups,
    mas_config_dir,
    restore_mas_backup,
    restore_native_backup,
)

logger = get_logger("通用脚本配置恢复")

RESTORE_SCRIPT_NAME = "general"
"""专项统一名（文案参数化用）"""


def _user_guard(ctx: RestoreContext) -> None:
    """恢复守卫：目标用户必须存在，避免把配置恢复进孤儿目录。"""

    if uuid.UUID(ctx.user_id) not in ctx.script_config.UserData:
        raise ValueError("通用脚本用户不存在，请刷新后重试")


def _native_config_path(ctx: RestoreContext) -> Path | None:
    """脚本原生配置路径（``Script.ConfigPath``）；未配置返回 ``None``。"""

    raw = str(ctx.script_config.get("Script", "ConfigPath") or "").strip()
    return Path(raw) if raw else None


def _native_config_mode(ctx: RestoreContext) -> str:
    """配置路径模式（``Script.ConfigPathMode``：Folder / File）。"""

    return str(ctx.script_config.get("Script", "ConfigPathMode") or "Folder")


async def _list_mas(ctx: RestoreContext) -> list[str]:
    return list_mas_backups(ctx.script_id, ctx.user_id)


async def _preview_mas(ctx: RestoreContext, ts: str) -> dict:
    backup_dir = get_mas_backup_dir(ctx.script_id, ctx.user_id, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    return build_file_list_preview(backup_dir)


async def _restore_mas(ctx: RestoreContext, ts: str) -> object:
    _user_guard(ctx)
    restore_mas_backup(
        ctx.script_id, ctx.user_id, ts, mas_config_dir(ctx.script_id, ctx.user_id)
    )


async def _snapshot_mas(ctx: RestoreContext) -> dict:
    _user_guard(ctx)
    dest = archive_mas_backup(
        ctx.script_id, ctx.user_id, mas_config_dir(ctx.script_id, ctx.user_id)
    )
    times = list_mas_backups(ctx.script_id, ctx.user_id)
    return {"created": dest is not None, "time": times[0] if times else ""}


async def _list_native(ctx: RestoreContext) -> list[str]:
    config_path = _native_config_path(ctx)
    return list_native_backups(config_path) if config_path is not None else []


async def _preview_native(ctx: RestoreContext, ts: str) -> dict:
    config_path = _native_config_path(ctx)
    if config_path is None:
        return {"files": []}
    backup_dir = get_native_backup_dir(config_path, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    return build_file_list_preview(backup_dir)


async def _restore_native(ctx: RestoreContext, ts: str) -> object:
    config_path = _native_config_path(ctx)
    if config_path is None:
        raise ValueError("请先设置脚本配置路径")
    restore_native_backup(config_path, _native_config_mode(ctx), ts)


async def _snapshot_native(ctx: RestoreContext) -> dict:
    config_path = _native_config_path(ctx)
    dest = (
        archive_native_backup(config_path, _native_config_mode(ctx))
        if config_path is not None
        else None
    )
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
