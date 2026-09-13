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

"""MAA 配置恢复池声明：两态 owner 解析 + 用户守卫，供基座统一分发。

池函数显式收 :class:`~app.utils.config_restore.RestoreContext`，全部逻辑
自包含（守卫与 owner 解析走 ``ctx.script_config.UserData``，路径走专项
字段），不依赖核心门面内部方法。备份文件级原语见同目录 ``backup_archive``。

mas 池 = 「MAA 为该用户维护的配置」（运行下发源 ConfigFile 目录副本）。
MAA 无覆盖层侧车需求：页面任务字段存 MAS 用户配置、运行时注入 gui.json，
不存在「页面字段不落盘在被备份文件」的问题（对比 ok-ww）。池恒按用户
分桶（侧车虽无，但脚本态多用户共享 Default 目录，各自快照仍需隔离）；
两态 owner（脚本=Default 共享目录、用户=独立目录）只决定归档/恢复目标
路径，与运行下发（AutoProxy ``set_maa``）同一套来源规则。
"""

import uuid
from pathlib import Path

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

RESTORE_SCRIPT_NAME = "maa"
"""专项统一名（文案参数化用）"""


def _user_guard(ctx) -> None:
    """恢复守卫：目标用户必须存在，避免把配置恢复进孤儿目录。"""

    if uuid.UUID(ctx.user_id) not in ctx.script_config.UserData:
        raise ValueError("MAA 用户不存在，请刷新后重试")


def _mas_owner(ctx) -> str | None:
    """当前用户的 MAS 配置目录 owner；无法解析时返回 ``None``。

    脚本态共享 ``Default``、用户态用当前用户目录，与 AutoProxy ``set_maa``
    的下发源同一套来源规则；用户不存在时无法判态，返回 ``None`` 让
    列表/预览为空（恢复/归档另有用户守卫）。MAA 为两态（无直控）。
    """

    try:
        uid = uuid.UUID(ctx.user_id)
        mode = ctx.script_config.UserData[uid].get("Info", "Mode")
    except (ValueError, KeyError, TypeError):
        return None
    return ctx.user_id if mode == "用户" else "Default"


def _native_config_path(ctx) -> Path | None:
    """MAA 安装目录 config/；未配置脚本路径返回 ``None``。"""

    raw = str(ctx.script_config.get("Info", "Path") or "").strip()
    return Path(raw) / "config" if raw else None


def _mas_dir_for_owner(ctx, owner: str) -> Path:
    """按两态 owner 求 MAS 配置目录（归档/恢复目标路径）。"""

    return mas_config_dir(ctx.script_id, owner)


def _preview_payload(ctx, ts: str, backup: Path | None) -> dict:
    """预览载荷：MAA 配置文件摘要（当前方案等稳定字段），其余经「查看
    详细配置」恢复后在 MAA GUI 里查看。

    载荷必须是 dict（通用预览响应模型的 ``data`` 字段），文件列表挂在
    ``files`` 键下，前端 ``#preview`` 插槽按 ``raw.files`` 消费。
    """

    if backup is None:
        raise ValueError(f"备份不存在: {ts}")
    return {"files": build_backup_file_summary(backup)}


async def _list_mas(ctx) -> list[str]:
    return list_mas_backups(ctx.script_id, ctx.user_id)


async def _list_native(ctx) -> list[str]:
    config_path = _native_config_path(ctx)
    if config_path is None:
        return []
    return list_native_backups(config_path)


async def _preview_mas(ctx, ts: str) -> dict:
    return _preview_payload(
        ctx, ts, get_mas_backup_dir(ctx.script_id, ctx.user_id, ts)
    )


async def _preview_native(ctx, ts: str) -> dict:
    config_path = _native_config_path(ctx)
    if config_path is None:
        return {"files": []}
    return _preview_payload(ctx, ts, get_native_backup_dir(config_path, ts))


async def _restore_mas(ctx, ts: str) -> object:
    _user_guard(ctx)
    owner = _mas_owner(ctx)
    if owner is None:
        raise ValueError("无法确定该用户的 MAS 配置目录，请刷新后重试")
    restore_mas_backup(
        ctx.script_id,
        ctx.user_id,
        ts,
        _mas_dir_for_owner(ctx, owner),
    )


async def _restore_native(ctx, ts: str) -> object:
    config_path = _native_config_path(ctx)
    if config_path is None:
        raise ValueError("请先设置 MAA 脚本路径")
    restore_native_backup(config_path, ts)


async def _snapshot_mas(ctx) -> dict:
    _user_guard(ctx)
    owner = _mas_owner(ctx)
    dest = (
        archive_mas_backup(
            ctx.script_id, ctx.user_id, _mas_dir_for_owner(ctx, owner)
        )
        if owner
        else None
    )
    times = list_mas_backups(ctx.script_id, ctx.user_id)
    return {"created": dest is not None, "time": times[0] if times else ""}


async def _snapshot_native(ctx) -> dict:
    config_path = _native_config_path(ctx)
    dest = archive_native_backup(config_path) if config_path is not None else None
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
