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

"""ZZZ-OD 配置恢复服务：MAS 用户槽池 / 一条龙原生配置池（声明式池）。

池声明只提供**专项知识**（归档什么 + 放哪里 + 恢复语义 + 定制预览），
``list`` / ``snapshot`` / ``read_file`` / ``files`` 兜底预览全部由基座
（``app.utils.common.config.restore``）从 ``files`` + ``backup_root`` 声明派生。
备份文件级原语见同目录 ``backup_archive``。

恢复与预览由专项 recovery 服务持有；池函数只装配配置集合与落盘能力，
文件级归档与替换继续复用通用基座。

mas 池 = 绑定槽目录整份 + 信息字段快照（mas_user_info.yml，内存 YAML）；
归档前先物化本页账号+编排进槽（账号/编排只存在 UserData，槽要注入才带，
不物化会漏）。池按槽分桶（``mas/{slot:02d}``）。onedragon 池 = 一条龙
原生配置（one_dragon.yml 原件 + 原生实例目录，排除 MAS 槽），按物理安装
根指纹分桶。
"""

import uuid
from pathlib import Path

from app.utils.common.config import restore as _utils_config_restore

from ..api_service import get_service


def _mas_user(ctx: _utils_config_restore.RestoreContext):
    """守卫 + 用户配置对象（恢复/归档前的「用户不存在」守卫）。"""

    uid = uuid.UUID(ctx.user_id)
    if uid not in ctx.script_config.UserData:
        raise ValueError("用户不存在")
    return uid, ctx.script_config.UserData[uid]


def _script_root(ctx: _utils_config_restore.RestoreContext) -> Path | None:
    """一条龙安装根目录（原始路径，不校验哨兵）；未配置返回 ``None``。"""

    raw = str(ctx.script_config.Info.RootPath or "").strip()
    return Path(raw) if raw else None


def _mas_slot(ctx: _utils_config_restore.RestoreContext) -> int | None:
    """当前用户绑定的槽 idx；未绑定（<=0）返回 ``None``。"""

    _, user_cfg = _mas_user(ctx)
    slot = int(user_cfg.Info.SlotIdx or -1)
    return slot if slot > 0 else None


# ══════════════════ mas 池（声明式 + 专项预览/恢复） ══════════════════


async def _mas_files(
    ctx: _utils_config_restore.RestoreContext,
) -> dict[str, "Path | str"] | None:
    """归档内容 = 绑定槽目录整份 + 信息字段快照（内存 YAML）。

    归档前先物化本页账号+编排进槽（不物化会漏、
    恢复会把本页字段清空）；未绑定槽、安装路径未配置或槽目录缺失时返回
    ``None``（无可归档内容）。
    """

    from app.task.ZzzOd.tools import (
        collect_mas_files,
        collect_mas_user_info,
        instance_dir,
        materialize_user_fields,
    )

    slot = _mas_slot(ctx)
    root = _script_root(ctx)
    if slot is None or root is None:
        return None
    slot_dir = instance_dir(root, slot)
    if not slot_dir.is_dir():
        return None
    _, user_cfg = _mas_user(ctx)
    materialize_user_fields(slot_dir, user_cfg)
    return collect_mas_files(slot_dir, collect_mas_user_info(user_cfg)) or None


async def _mas_root(ctx: _utils_config_restore.RestoreContext) -> Path | None:
    from app.task.ZzzOd.tools import mas_backup_root

    slot = _mas_slot(ctx)
    if slot is None:
        return None
    return mas_backup_root(ctx.script_id, slot)


async def _preview_mas(ctx: _utils_config_restore.RestoreContext, ts: str) -> dict:
    return get_service(ctx.config).recovery.get_backup_preview(
        ctx.script_id, ctx.user_id, ts, target="mas"
    )


async def _restore_mas(ctx: _utils_config_restore.RestoreContext, ts: str) -> None:
    await get_service(ctx.config).recovery.restore_backup(
        ctx.script_id, ctx.user_id, ts, target="mas", force=ctx.force
    )


# ══════════════════ onedragon 池（声明式 + 专项预览/恢复） ══════════════════


async def _onedragon_files(
    ctx: _utils_config_restore.RestoreContext,
) -> dict[str, Path] | None:
    """归档内容 = 一条龙原生配置文件集（排除 MAS 槽；缺失返回 ``None``）。"""

    from app.task.ZzzOd.tools import collect_onedragon_files

    root = _script_root(ctx)
    if root is None:
        return None
    return collect_onedragon_files(root) or None


async def _onedragon_root(ctx: _utils_config_restore.RestoreContext) -> Path | None:
    from app.task.ZzzOd.tools import onedragon_backup_root

    root = _script_root(ctx)
    if root is None:
        return None
    return onedragon_backup_root(root)


async def _preview_onedragon(
    ctx: _utils_config_restore.RestoreContext, ts: str
) -> dict:
    return get_service(ctx.config).recovery.get_backup_preview(
        ctx.script_id, ctx.user_id, ts, target="onedragon"
    )


async def _restore_onedragon(
    ctx: _utils_config_restore.RestoreContext, ts: str
) -> None:
    await get_service(ctx.config).recovery.restore_backup(
        ctx.script_id, ctx.user_id, ts, target="onedragon", force=ctx.force
    )


RESTORE_POOLS = [
    _utils_config_restore.ConfigRestorePool(
        key="mas",
        kind="user",
        mas_base="user_only",
        files=_mas_files,
        backup_root=_mas_root,
        preview=_preview_mas,
        restore=_restore_mas,
    ),
    _utils_config_restore.ConfigRestorePool(
        key="onedragon",
        kind="script",
        files=_onedragon_files,
        backup_root=_onedragon_root,
        preview=_preview_onedragon,
        restore=_restore_onedragon,
    ),
]
