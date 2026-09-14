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

"""SRC 配置恢复服务：MAS 用户配置池 / SRC 原生配置池。

池函数显式收 :class:`~app.utils.config_restore.RestoreContext`，全部逻辑
自包含（守卫与 owner 解析走 ``ctx.script_config.UserData``，路径走专项
字段），不依赖核心门面内部方法。备份文件级原语见同目录 ``backup_archive``。

mas 池 = 「MAS 为该用户维护的全部配置」：ConfigFile 整目录 + 页面核心
字段侧车（Stage 段 + Info 的 Server/Mode，运行时才注入 src.json）。池恒
按用户分桶（侧车是用户级的）；owner（脚本=Default 共享目录、用户=独立
目录）只决定归档/恢复目标路径，与运行下发（AutoProxy ``set_src``）和
会话（ScriptConfigTask）同一套来源规则；直控用户无 MAS 配置目录，mas 池
对其为空。
"""

import shutil
import uuid
from pathlib import Path

from app.task.proxy_helpers import (
    CONFIG_SOURCE_DIRECT,
    CONFIG_SOURCE_SCRIPT,
    read_config_source,
)
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
    mas_config_dir,
    read_overlay_sidecar,
    read_overlay_values,
    restore_mas_backup,
    restore_native_backup,
)

logger = get_logger("SRC 配置恢复")

RESTORE_SCRIPT_NAME = "src"
"""专项统一名（文案参数化用）"""


def _user_guard(ctx: RestoreContext) -> None:
    """恢复守卫：目标用户必须存在，避免把配置恢复进孤儿目录。"""

    if uuid.UUID(ctx.user_id) not in ctx.script_config.UserData:
        raise ValueError("SRC 用户不存在，请刷新后重试")


def _mas_owner(ctx: RestoreContext) -> str | None:
    """当前用户的 MAS 配置目录 owner；直控/无法解析时返回 ``None``。

    与运行下发（AutoProxy ``set_src``）和会话（ScriptConfigTask）同一套
    来源规则：脚本态共享 ``Default``、用户态用当前用户目录；用户不存在时
    无法判态，返回 ``None`` 让列表/预览为空（恢复/归档另有用户守卫）。
    """

    try:
        uid = uuid.UUID(ctx.user_id)
        mode = read_config_source(
            ctx.script_config.UserData[uid], CONFIG_SOURCE_SCRIPT
        )
    except (ValueError, KeyError, TypeError):
        return None
    if mode == CONFIG_SOURCE_DIRECT:
        return None
    return ctx.user_id if mode == "用户" else "Default"


def _native_config_path(ctx: RestoreContext) -> Path | None:
    """SRC 安装目录 config/；未配置脚本路径返回 ``None``。"""

    raw = str(ctx.script_config.get("Info", "Path") or "").strip()
    return Path(raw) / "config" if raw else None


def _mas_dir_for_owner(ctx: RestoreContext, owner: str) -> Path:
    """按 owner 求 MAS 配置目录（归档/恢复目标路径）。"""

    return mas_config_dir(ctx.script_id, owner)


def _seed_mas_dir(ctx: RestoreContext, mas_dir: Path) -> None:
    """MAS 配置目录缺失时从 SRC 安装目录 config/ 播种。

    会话（ScriptConfigTask ``set_src``）本就会在目录缺配置文件时回灌，
    但那只发生在用户打开配置会话之后——播种让「进入编辑页 → 退出」的
    包络自第一次退出起就有现场可归档。不在 add_user 时播种：SRC 路径
    可晚于用户配置，播种失败不该挡建用户。
    """

    if mas_dir.is_dir() and any(mas_dir.iterdir()):
        return
    install_config = _native_config_path(ctx)
    if (
        install_config is None
        or not install_config.is_dir()
        or not any(install_config.iterdir())
    ):
        return
    shutil.copytree(install_config, mas_dir, dirs_exist_ok=True)
    logger.info(f"已从 SRC 本体播种 MAS 配置目录: {mas_dir}")


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
    owner = _mas_owner(ctx)
    if owner is None:
        raise ValueError("直控用户不使用 MAS 独立配置，无可恢复内容")
    user = ctx.script_config.UserData[uuid.UUID(ctx.user_id)]
    restored_overlay = restore_mas_backup(
        ctx.script_id,
        ctx.user_id,
        ts,
        _mas_dir_for_owner(ctx, owner),
        overlay=read_overlay_values(user),
    )
    if restored_overlay:
        # 页面核心字段回填（对齐 ok-ww 模式）：文件回滚的同时把页面关卡
        # 配置回到备份时点，否则旧表单值下次保存会静默覆盖回滚结果
        await user.update(group_overlay(restored_overlay))


async def _snapshot_mas(ctx: RestoreContext) -> dict:
    _user_guard(ctx)
    owner = _mas_owner(ctx)
    dest = None
    if owner:
        mas_dir = _mas_dir_for_owner(ctx, owner)
        _seed_mas_dir(ctx, mas_dir)
        dest = archive_mas_backup(
            ctx.script_id,
            ctx.user_id,
            mas_dir,
            overlay=read_overlay_values(
                ctx.script_config.UserData[uuid.UUID(ctx.user_id)]
            ),
        )
    times = list_mas_backups(ctx.script_id, ctx.user_id)
    return {"created": dest is not None, "time": times[0] if times else ""}


async def _list_native(ctx: RestoreContext) -> list[str]:
    config_path = _native_config_path(ctx)
    if config_path is None:
        return []
    return list_native_backups(config_path)


async def _preview_native(ctx: RestoreContext, ts: str) -> dict:
    config_path = _native_config_path(ctx)
    if config_path is None:
        return {"sections": []}
    return build_native_preview(config_path, ts)


async def _restore_native(ctx: RestoreContext, ts: str) -> object:
    config_path = _native_config_path(ctx)
    if config_path is None:
        raise ValueError("请先设置 SRC 脚本路径")
    restore_native_backup(config_path, ts, ctx.script_id)


async def _snapshot_native(ctx: RestoreContext) -> dict:
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
