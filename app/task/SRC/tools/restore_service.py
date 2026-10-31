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

"""SRC 配置恢复服务：MAS 用户配置池 / SRC 原生配置池（声明式池）。

池声明只提供**专项知识**（归档什么 + 放哪里 + 恢复语义 + 定制预览），
``list`` / ``snapshot`` / ``read_file`` / ``files`` 兜底全部由基座
（``app.utils.common.config.restore``）从 ``files`` + ``backup_root`` 声明派生。
备份文件级原语见同目录 ``backup_archive``。

mas 池 = 「MAS 为该用户维护的全部配置」：ConfigFile 整目录 + 页面核心
字段侧车（Stage 段 + Info 的 Server/Base，运行时才注入 src.json）。池恒
按用户分桶（侧车是用户级的）；owner（shared=Default 共享目录、independent=独立
目录）只决定归档/恢复目标路径，与运行下发（AutoProxy ``set_src``）和
会话（ScriptConfigTask）同一套来源规则；native 来源用户无 MAS 配置目录，mas 池
对其为空（``files`` 回调返回 ``None``，快照报无变化）。
"""

import json
import shutil
import uuid
from pathlib import Path

from app.task.proxy_helpers import (
    CONFIG_BASE_INDEPENDENT,
    CONFIG_BASE_NATIVE,
    CONFIG_BASE_SHARED,
    read_config_base,
)
from app.utils import get_logger
from app.utils.common.config import restore as _utils_config_restore

from .backup_archive import (
    OVERLAY_SIDECAR_NAME,
    build_native_preview,
    build_overlay_preview,
    collect_mas_files,
    collect_native_files,
    get_mas_backup_dir,
    group_overlay,
    mas_backup_root,
    mas_config_dir,
    native_backup_root,
    read_overlay_sidecar,
    read_overlay_values,
    restore_mas_backup,
    restore_native_backup,
)

logger = get_logger("SRC 配置恢复")


def _user_guard(ctx: _utils_config_restore.RestoreContext) -> None:
    """恢复守卫：目标用户必须存在，避免把配置恢复进孤儿目录。"""

    if uuid.UUID(ctx.user_id) not in ctx.script_config.UserData:
        raise ValueError("SRC 用户不存在，请刷新后重试")


async def _set_base(ctx: _utils_config_restore.RestoreContext, base: str) -> None:
    """跨来源恢复确认后把 ``Info.Base`` 写回备份时点（tri_state 必须）。

    基座校验到备份 Base ≠ 当前 Base 时回调；写回后 restore 按当前 Base
    解析 owner，恢复目标自然就是备份 Base 的目录（跨来源恢复 = 目录
    重定向 + 状态切回）。
    """

    user = ctx.script_config.UserData[uuid.UUID(ctx.user_id)]
    await user.update(type(user).model_validate({"Info": {"Base": base}}))


def _mas_owner(ctx: _utils_config_restore.RestoreContext) -> str | None:
    """当前用户的 MAS 配置目录 owner；原生来源/无法解析时返回 ``None``。

    与运行下发（AutoProxy ``set_src``）和会话（ScriptConfigTask）同一套
    来源规则：shared 来源共享 ``Default``、independent 来源用当前用户目录；用户不存在时
    无法判态，返回 ``None`` 让列表/预览为空（恢复/归档另有用户守卫）。
    """

    try:
        uid = uuid.UUID(ctx.user_id)
        base = read_config_base(ctx.script_config.UserData[uid], CONFIG_BASE_SHARED)
    except (ValueError, KeyError, TypeError):
        return None
    if base == CONFIG_BASE_NATIVE:
        return None
    return ctx.user_id if base == CONFIG_BASE_INDEPENDENT else "Default"


def _native_config_path(ctx: _utils_config_restore.RestoreContext) -> Path | None:
    """SRC 安装目录 config/；未配置脚本路径返回 ``None``。"""

    raw = str(ctx.script_config.Info.Path or "").strip()
    return Path(raw) / "config" if raw else None


def _mas_dir_for_owner(ctx: _utils_config_restore.RestoreContext, owner: str) -> Path:
    """按 owner 求 MAS 配置目录（归档/恢复目标路径）。"""

    return mas_config_dir(ctx.script_id, owner)


def _seed_mas_dir(ctx: _utils_config_restore.RestoreContext, mas_dir: Path) -> None:
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


async def _mas_files(
    ctx: _utils_config_restore.RestoreContext,
) -> dict[str, Path | str] | None:
    """归档内容 = ConfigFile 整目录 + 页面核心字段侧车（内存 JSON）。

    守卫与 owner 解析沿用原快照语义：用户不存在时抛 ``ValueError``；
    原生来源用户无 MAS 配置目录，返回 ``None``（快照报无变化）；目录缺失时
    从 SRC 安装目录 config/ 播种。
    """

    _user_guard(ctx)
    owner = _mas_owner(ctx)
    if owner is None:
        return None
    mas_dir = _mas_dir_for_owner(ctx, owner)
    _seed_mas_dir(ctx, mas_dir)
    files: dict[str, Path | str] = dict(collect_mas_files(mas_dir))
    overlay = read_overlay_values(ctx.script_config.UserData[uuid.UUID(ctx.user_id)])
    if overlay:
        files[OVERLAY_SIDECAR_NAME] = json.dumps(overlay, ensure_ascii=False, indent=2)
    return files or None


async def _mas_root(ctx: _utils_config_restore.RestoreContext) -> Path:
    return mas_backup_root(ctx.script_id, ctx.user_id)


async def _preview_mas(ctx: _utils_config_restore.RestoreContext, ts: str) -> dict:
    backup_dir = get_mas_backup_dir(ctx.script_id, ctx.user_id, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    overlay = read_overlay_sidecar(backup_dir)
    if overlay is None:
        return {"sections": []}
    return build_overlay_preview(overlay)


async def _restore_mas(ctx: _utils_config_restore.RestoreContext, ts: str) -> None:
    _user_guard(ctx)
    owner = _mas_owner(ctx)
    if owner is None:
        raise ValueError("原生来源用户不使用 MAS 独立配置，无可恢复内容")
    user = ctx.script_config.UserData[uuid.UUID(ctx.user_id)]
    restored_overlay = restore_mas_backup(
        ctx.script_id,
        ctx.user_id,
        ts,
        _mas_dir_for_owner(ctx, owner),
        overlay=read_overlay_values(user),
        base=str(user.Info.Base or "").strip() or None,
    )
    if restored_overlay:
        # 页面核心字段回填（对齐 ok-ww 模式）：文件回滚的同时把页面关卡
        # 配置回到备份时点，否则旧表单值下次保存会静默覆盖回滚结果
        await user.update(type(user).model_validate(group_overlay(restored_overlay)))


async def _native_files(
    ctx: _utils_config_restore.RestoreContext,
) -> dict[str, Path] | None:
    """归档内容 = SRC 安装目录 config/ 整目录（缺失或入口不可解析返回 ``None``）。"""

    config_path = _native_config_path(ctx)
    if config_path is None:
        return None
    return collect_native_files(config_path) or None


async def _native_root(ctx: _utils_config_restore.RestoreContext) -> Path | None:
    config_path = _native_config_path(ctx)
    return native_backup_root(config_path) if config_path is not None else None


async def _preview_native(ctx: _utils_config_restore.RestoreContext, ts: str) -> dict:
    config_path = _native_config_path(ctx)
    if config_path is None:
        return {"sections": []}
    return build_native_preview(config_path, ts)


async def _restore_native(ctx: _utils_config_restore.RestoreContext, ts: str) -> None:
    config_path = _native_config_path(ctx)
    if config_path is None:
        raise ValueError("请先设置 SRC 脚本路径")
    restore_native_backup(config_path, ts, ctx.script_id)


RESTORE_POOLS = [
    _utils_config_restore.ConfigRestorePool(
        key="mas",
        kind="user",
        mas_base="tri_state",
        set_base=_set_base,
        files=_mas_files,
        backup_root=_mas_root,
        preview=_preview_mas,
        restore=_restore_mas,
    ),
    _utils_config_restore.ConfigRestorePool(
        key="native",
        kind="script",
        files=_native_files,
        backup_root=_native_root,
        preview=_preview_native,
        restore=_restore_native,
    ),
]
