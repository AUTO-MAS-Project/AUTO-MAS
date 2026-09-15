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

"""BAAH 配置恢复服务：MAS 用户字段侧车池 / BAAH 原生配置池（声明式池）。

池声明只提供**专项知识**（归档什么 + 放哪里 + 恢复语义 + 定制预览），
``list`` / ``snapshot`` / ``read_file`` / ``files`` 兜底全部由基座
（``app.utils.config_restore``）从 ``files`` + ``backup_root`` 声明派生。
备份文件级原语见同目录 ``backup_archive``。

- ``mas`` 池（用户级）：MAS 编辑页字段侧车（当前为元字段，预留扩展），
  恢复 = 回填 BAAHUserConfig（来源/快速配置排除）。
- ``native`` 池（脚本级）：按当前用户 ``ConfigName`` 动态解析的用户配置
  JSON + 软件配置，恢复前强制归档当前；恢复写到当前 ConfigName 指向的
  文件（覆盖语义）。未配置 BAAHPath 时 ``backup_root`` / ``files`` 均返回
  ``None``（列表为空、快照报无变化、预览不注入，不抛错——编辑页
  ensure(native) 静默）；``files`` 回调保留守卫（用户不存在/未填配置名时
  抛错，与恢复同口径）。

归档时机：AutoProxy 托管写入前（任务级，核心时机）、编辑界面进入
（native）/ 退出（mas）由前端 ``ensure`` 触发。BAAH 无遮罩会话，不提供
「查看详细配置」。
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
from .config_manager import CONFIG_DIR_NAME

logger = get_logger("BAAH 配置恢复")


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


def _config_dir_or_none(ctx: RestoreContext) -> str | None:
    """BAAH 配置目录（BAAHPath 派生）；未配置脚本路径时返回 ``None``。

    供 ``files`` / ``preview`` 等只读回调静默降级用——与基座
    ``backup_root`` 返回 ``None`` 的 None 防御语义对齐（列表为空、快照报
    无变化、预览不注入、读文件报无可读），用户未配置路径时编辑页不该报错。
    恢复回调仍走 :func:`_config_dir`（恢复是显式用户操作，未配置报错合理）。
    """

    raw = str(ctx.script_config.get("Script", "BAAHPath") or "").strip()
    if not raw:
        return None
    return str(Path(raw).parent / CONFIG_DIR_NAME)


def _config_dir(ctx: RestoreContext) -> str:
    """BAAH 配置目录（BAAHPath 派生；未配置脚本路径时抛错）。"""

    config_dir = _config_dir_or_none(ctx)
    if config_dir is None:
        raise ValueError("请先设置 BAAH 主程序路径")
    return config_dir


async def _mas_files(ctx: RestoreContext) -> dict[str, str] | None:
    """归档内容 = MAS 页面字段侧车（内存 JSON，免临时文件）。"""

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
    if overlay is None:
        return {"sections": []}
    return build_overlay_preview(overlay)


async def _restore_mas(ctx: RestoreContext, ts: str) -> None:
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


async def _native_files(ctx: RestoreContext) -> dict[str, Path] | None:
    """归档内容 = 当前 ConfigName 的用户配置 + 软件配置（缺失项跳过）。

    未配置 BAAHPath 时返回 ``None``（无可归档根，快照报无变化、不抛错——
    编辑页 ensure(native) 静默，与基座 ``backup_root`` 返回 ``None`` 的
    None 防御语义对齐）；用户不存在、未填配置名仍抛 ``ValueError``（与
    恢复同口径，由服务层转 400）。
    """

    _user_guard(ctx)
    config_dir = _config_dir_or_none(ctx)
    if config_dir is None:
        return None
    return collect_native_files(config_dir, _config_name(ctx)) or None


async def _native_root(ctx: RestoreContext) -> Path | None:
    """归档根按 BAAHPath 派生（按配置目录指纹 + 用户分桶）；未配置返回 ``None``。"""

    raw = str(ctx.script_config.get("Script", "BAAHPath") or "").strip()
    if not raw:
        return None
    return native_backup_root(str(Path(raw).parent / CONFIG_DIR_NAME), ctx.user_id)


async def _preview_native(ctx: RestoreContext, ts: str) -> dict:
    """反读备份内用户配置关键字段；未配置 BAAHPath 时返回空载荷（不抛错）。"""

    config_dir = _config_dir_or_none(ctx)
    if config_dir is None:
        return {"sections": []}
    return build_native_preview(config_dir, ctx.user_id, ts)


async def _restore_native(ctx: RestoreContext, ts: str) -> None:
    _user_guard(ctx)
    restore_native_backup(_config_dir(ctx), _config_name(ctx), ctx.user_id, ts)


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
