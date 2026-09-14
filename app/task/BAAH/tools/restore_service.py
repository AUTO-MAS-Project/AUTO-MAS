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

"""BAAH 配置恢复服务：MAS 用户字段侧车池 / BAAH 原生配置池（动态目标）。

- ``mas`` 池（用户级）：MAS 编辑页字段侧车（当前为元字段，预留扩展），
  恢复 = 回填 BAAHUserConfig（来源/快速配置排除）。
- ``native`` 池（脚本级）：按当前用户 ``ConfigName`` 动态解析的用户配置
  JSON + 软件配置，恢复前强制归档当前；恢复写到当前 ConfigName 指向的
  文件（覆盖语义）。

归档时机：AutoProxy 托管写入前（任务级，核心时机）、编辑界面进入
（native）/ 退出（mas）由前端 ``ensure`` 触发。BAAH 无遮罩会话，不提供
「查看详细配置」。
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
from .config_manager import CONFIG_DIR_NAME

logger = get_logger("BAAH 配置恢复")

RESTORE_SCRIPT_NAME = "baah"
"""专项统一名（文案参数化用）"""


def _user_guard(ctx: RestoreContext) -> None:
    """恢复守卫：目标用户必须存在，避免把字段回填进孤儿目录。"""

    if uuid.UUID(ctx.user_id) not in ctx.script_config.UserData:
        raise ValueError("BAAH 用户不存在，请刷新后重试")


def _config_name(ctx: RestoreContext) -> str:
    """当前用户的 BAAH 配置文件名（未填时抛错，由服务层转 400）。"""

    name = str(
        ctx.script_config.UserData[uuid.UUID(ctx.user_id)].get("Info", "ConfigName")
        or ""
    ).strip()
    if not name:
        raise ValueError("当前用户未填写 BAAH 配置文件名，请先在用户配置中填写")
    return name


def _config_dir(ctx: RestoreContext) -> str:
    """BAAH 配置目录（BAAHPath 派生；未配置脚本路径时抛错）。"""

    raw = str(ctx.script_config.get("Script", "BAAHPath") or "").strip()
    if not raw:
        raise ValueError("请先设置 BAAH 主程序路径")
    return str(Path(raw).parent / CONFIG_DIR_NAME)


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
        logger.info("用户 %s 的 MAS 字段已恢复备份 %s", ctx.user_id, ts)


async def _snapshot_mas(ctx: RestoreContext) -> dict:
    _user_guard(ctx)
    user = ctx.script_config.UserData[uuid.UUID(ctx.user_id)]
    dest = archive_mas_backup(ctx.script_id, ctx.user_id, read_overlay_values(user))
    times = list_mas_backups(ctx.script_id, ctx.user_id)
    return {"created": dest is not None, "time": times[0] if times else ""}


async def _list_native(ctx: RestoreContext) -> list[str]:
    return list_native_backups(_config_dir(ctx), ctx.user_id)


async def _preview_native(ctx: RestoreContext, ts: str) -> dict:
    return build_native_preview(_config_dir(ctx), ctx.user_id, ts)


async def _restore_native(ctx: RestoreContext, ts: str) -> object:
    _user_guard(ctx)
    restore_native_backup(_config_dir(ctx), _config_name(ctx), ctx.user_id, ts)


async def _snapshot_native(ctx: RestoreContext) -> dict:
    _user_guard(ctx)
    dest = archive_native_backup(_config_dir(ctx), _config_name(ctx), ctx.user_id)
    times = list_native_backups(_config_dir(ctx), ctx.user_id)
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
