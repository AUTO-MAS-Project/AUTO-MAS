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

"""ZZZ-OD 配置恢复池声明：薄委托门面公开方法，供基座统一分发。

池函数显式收 :class:`~app.utils.config_restore.RestoreContext`（不再闭包
捕获），绑定由基座 ``build_restore_service`` 统一完成。ZzzOd 的备份内部
业务（槽占用守卫、字段回填、预览构建）保留在 ``app.core.config`` 的门面
方法中（其实现依赖 ``_zzzod_user`` / ``_zzzod_root`` 等内部 helper），
本模块只做池声明与薄委托。
"""

import uuid

from app.utils.config_restore import ConfigRestorePool

RESTORE_SCRIPT_NAME = "一条龙"
"""专项统一名（文案参数化用）"""


async def _list_mas(ctx) -> list[str]:
    from app.task.ZzzOd.tools import list_mas_backups

    uid = uuid.UUID(ctx.user_id)
    if uid not in ctx.script_config.UserData:
        raise ValueError("用户不存在")
    slot = int(ctx.script_config.UserData[uid].get("Info", "SlotIdx") or -1)
    if slot <= 0:
        return []
    return list_mas_backups(ctx.script_id, slot)


async def _list_onedragon(ctx) -> list[str]:
    from app.task.ZzzOd.tools import list_onedragon_backups

    root = str(ctx.script_config.get("Info", "RootPath") or "").strip()
    if not root:
        return []
    return list_onedragon_backups(root)


async def _preview_mas(ctx, ts: str) -> dict:
    return ctx.config.get_zzzod_backup_preview(
        ctx.script_id, ctx.user_id, ts, target="mas"
    )


async def _preview_onedragon(ctx, ts: str) -> dict:
    return ctx.config.get_zzzod_backup_preview(
        ctx.script_id, ctx.user_id, ts, target="onedragon"
    )


async def _restore_mas(ctx, ts: str) -> object:
    return await ctx.config.restore_zzzod_backup(
        ctx.script_id, ctx.user_id, ts, target="mas"
    )


async def _restore_onedragon(ctx, ts: str) -> object:
    return await ctx.config.restore_zzzod_backup(
        ctx.script_id, ctx.user_id, ts, target="onedragon"
    )


async def _snapshot_mas(ctx) -> dict:
    return await ctx.config.ensure_zzzod_mas_backup(ctx.script_id, ctx.user_id)


async def _snapshot_onedragon(ctx) -> dict:
    return ctx.config.ensure_zzzod_direct_backup(ctx.script_id)


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
        key="onedragon",
        kind="script",
        list_backups=_list_onedragon,
        preview=_preview_onedragon,
        restore=_restore_onedragon,
        snapshot=_snapshot_onedragon,
    ),
]
