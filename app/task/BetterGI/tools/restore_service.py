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

"""BetterGI 配置恢复服务：MAS 用户配置池 / BetterGI 原生配置池（声明式池）。

池声明只提供**专项知识**（归档什么 + 放哪里 + 恢复语义 + 定制预览），
``list`` / ``snapshot`` / ``read_file`` / ``files`` 兜底全部由基座
（``app.utils.config_restore``）从 ``files`` + ``backup_root`` 声明派生。
备份文件级原语见同目录 ``backup_archive``。

mas 池 = 「MAS 为该用户维护的全部配置」：副本目录（OneDragon / ScriptGroup /
GlobalDomain，前端端点直接读写）+ 页面字段侧车（OneDragon 段 +
Task.OneDragonConfigName + Switch.Resource + Info.Base 仅预览）+ 共享来源的
脚本级编排侧车。池恒按用户分桶，副本与共享编排的恢复目标按同一来源 owner
解析（shared → 脚本级保留 id），对齐 Okww 的「池按用户、目标按 owner」。

native 池 = BetterGI 全局主配置 ``{RootPath}/User/config.json``（单文件，
按物理安装根指纹分桶）。
"""

import json
import uuid
from pathlib import Path

from app.utils import get_logger
from app.utils.config_restore import ConfigRestorePool, RestoreContext

from .backup_archive import (
    OVERLAY_SIDECAR_NAME,
    SHARED_ONEDRAGON_SIDECAR_NAME,
    _collect_mas_files,
    build_mas_preview,
    build_native_preview,
    collect_native_files,
    get_mas_backup_dir,
    group_overlay,
    mas_backup_root,
    native_backup_root,
    overlay_sidecar_content,
    read_overlay_sidecar,
    read_overlay_values,
    read_shared_onedragon_sidecar,
    restore_mas_backup,
    restore_native_backup,
)

logger = get_logger("BetterGI 配置恢复")


def _user_guard(ctx: RestoreContext) -> None:
    """恢复守卫：目标用户必须存在，避免把配置恢复进孤儿目录。"""

    if uuid.UUID(ctx.user_id) not in ctx.script_config.UserData:
        raise ValueError("BetterGI 用户不存在，请刷新后重试")


def _root_path(ctx: RestoreContext) -> Path | None:
    """BetterGI 安装根目录；未配置脚本路径返回 ``None``。"""

    raw = str(ctx.script_config.get("Info", "RootPath") or "").strip()
    return Path(raw) if raw else None


# ══════════════════ mas 池（声明式 + 定制预览/恢复） ══════════════════


def _owner(ctx: RestoreContext) -> str:
    """副本目录的 owner 维度：与运行时物化、接口读写同一口径。"""

    from . import script_source

    return script_source.owner_id(ctx.script_config, ctx.user_id)


async def _shared_one_dragon(ctx: RestoreContext) -> dict | None:
    """共享来源的脚本级编排；独立/原生来源（编排在用户自己那份）返回 ``None``。"""

    from . import script_source

    if not script_source.uses_script_source(ctx.script_config, ctx.user_id):
        return None
    try:
        section = (await ctx.script_config.toDict()).get("OneDragon")
    except Exception:  # pragma: no cover - 读取失败按「无共享段」处理
        return None
    return section if isinstance(section, dict) else None


async def _mas_files(ctx: RestoreContext) -> dict[str, Path | str] | None:
    """归档内容 = 副本文件集（按来源 owner）+ 页面字段侧车 + 共享编排侧车。"""

    _user_guard(ctx)
    files: dict[str, Path | str] = dict(_collect_mas_files(ctx.script_id, _owner(ctx)))
    overlay = read_overlay_values(ctx.script_config.UserData[uuid.UUID(ctx.user_id)])
    if overlay:
        files[OVERLAY_SIDECAR_NAME] = overlay_sidecar_content(overlay)
    # 共享来源的编排存在脚本级配置里、不在副本目录，单独随归档存底
    shared = await _shared_one_dragon(ctx)
    if shared is not None:
        files[SHARED_ONEDRAGON_SIDECAR_NAME] = json.dumps(
            shared, ensure_ascii=False, indent=2
        )
    return files or None


async def _mas_root(ctx: RestoreContext) -> Path:
    return mas_backup_root(ctx.script_id, ctx.user_id)


async def _preview_mas(ctx: RestoreContext, ts: str) -> dict:
    backup_dir = get_mas_backup_dir(ctx.script_id, ctx.user_id, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    overlay = read_overlay_sidecar(backup_dir)
    return build_mas_preview(backup_dir, overlay)


async def _restore_mas(ctx: RestoreContext, ts: str) -> None:
    _user_guard(ctx)
    user = ctx.script_config.UserData[uuid.UUID(ctx.user_id)]
    restored_overlay = restore_mas_backup(
        ctx.script_id,
        ctx.user_id,
        ts,
        overlay=read_overlay_values(user),
        owner=_owner(ctx),
        shared_one_dragon=await _shared_one_dragon(ctx),
    )
    if restored_overlay:
        # 页面字段回填（对齐 ok-ww 模式）：副本回滚的同时把页面配置回到
        # 备份时点，否则旧表单值下次保存会静默覆盖回滚结果
        await user.update(group_overlay(restored_overlay))
    # 共享来源的编排回填到脚本级段；独立/原生来源的编排随侧车字段回到用户配置
    backup_dir = get_mas_backup_dir(ctx.script_id, ctx.user_id, ts)
    restored_shared = (
        read_shared_onedragon_sidecar(backup_dir) if backup_dir is not None else None
    )
    if restored_shared is not None:
        await ctx.script_config.update({"OneDragon": restored_shared})


# ══════════════════ native 池（声明式 + 定制预览/恢复） ══════════════════


async def _native_files(ctx: RestoreContext) -> dict[str, Path] | None:
    """归档内容 = BetterGI 全局主配置（缺失项跳过）。"""

    root_path = _root_path(ctx)
    if root_path is None:
        return None
    return collect_native_files(root_path) or None


async def _native_root(ctx: RestoreContext) -> Path | None:
    root_path = _root_path(ctx)
    if root_path is None:
        return None
    return native_backup_root(root_path)


async def _preview_native(ctx: RestoreContext, ts: str) -> dict:
    root_path = _root_path(ctx)
    if root_path is None:
        return {"sections": []}
    return build_native_preview(root_path, ts)


async def _restore_native(ctx: RestoreContext, ts: str) -> None:
    root_path = _root_path(ctx)
    if root_path is None:
        raise ValueError("请先设置 BetterGI 脚本路径")
    restore_native_backup(root_path, ts)


RESTORE_POOLS = [
    ConfigRestorePool(
        key="mas",
        kind="user",
        mas_base="user_only",
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
