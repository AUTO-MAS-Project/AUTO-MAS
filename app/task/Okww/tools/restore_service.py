#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 or (at your option)
#   any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public
#   License along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""OK-WW 配置恢复服务：MAS 用户配置池 / ok-ww 原生配置池（声明式池）。

池声明只提供**专项知识**（归档什么 + 放哪里 + 恢复语义 + 定制预览），
``list`` / ``snapshot`` / ``read_file`` / ``files`` 兜底预览全部由基座
（``app.utils.config_restore``）从 ``files`` + ``backup_root`` 声明派生。
备份文件级原语见同目录 ``backup_archive``。

mas 池 = 「MAS 为该用户维护的全部配置」：ConfigFile 目录副本 + 侧车
（Info.Id 账号 + 快速配置覆盖层字段）。页面任务配置卡片的字段存在 MAS
用户配置里、运行时才覆盖进 DailyTask.json——备份/恢复两端都带上侧车字段
（恢复后按段回填表单，对齐 ZzzOd / MAA 字段回填模式），预览与页面认知
才一致。**池恒按用户分桶**（侧车是用户级的，脚本态多用户若共享一个
Default 池会互相污染）；三态 owner（脚本=Default 共享目录、用户=独立
目录、直控=无）只决定归档/恢复目标路径，与运行下发
（``_okww_mas_config_dir``）同一套来源规则。
"""

import uuid
from pathlib import Path

from app.utils.config_restore import ConfigRestorePool, RestoreContext

from ..AutoProxy import _OKWW_REL_CONFIG_DIR, _okww_config_mode
from .backup_archive import (
    build_backup_file_summary,
    build_overlay_summary,
    collect_mas_files,
    collect_native_files,
    get_mas_backup_dir,
    get_native_backup_dir,
    group_overlay,
    mas_backup_root,
    mas_config_dir,
    native_backup_root,
    read_overlay_sidecar,
    read_overlay_values,
    restore_mas_backup,
    restore_native_backup,
)


def _user_guard(ctx: RestoreContext) -> None:
    """恢复守卫：目标用户必须存在，避免把配置恢复进孤儿目录。"""

    if uuid.UUID(ctx.user_id) not in ctx.script_config.UserData:
        raise ValueError("OK-WW 用户不存在，请刷新后重试")


async def _set_mode(ctx: RestoreContext, mode: str) -> None:
    """跨来源恢复确认后把 ``Info.Mode`` 写回备份时点（tri_state 必须）。

    基座校验到备份 Mode ≠ 当前 Mode 时回调；写回后 restore 按当前 Mode
    解析 owner，恢复目标自然就是备份 Mode 的目录（跨来源恢复 = 目录
    重定向 + 状态切回）。
    """

    user = ctx.script_config.UserData[uuid.UUID(ctx.user_id)]
    await user.update({"Info": {"Mode": mode}})


def _mas_owner(ctx: RestoreContext) -> str | None:
    """当前用户的 MAS 配置目录 owner；直控/无法解析时返回 ``None``。

    脚本态共享 ``Default``、用户态用当前用户目录，与
    ``_okww_mas_config_dir``（运行下发）同一套来源规则；用户不存在时
    无法判态，返回 ``None`` 让列表/预览为空（恢复/归档另有用户守卫）。

    注意：owner 只决定**归档/恢复目标路径**（脚本态=Default 共享目录、
    用户态=独立目录）；mas 池本身恒按 ``ctx.user_id`` 分桶——侧车字段是
    用户级的，脚本态多用户若共享同一个 Default 池会把各自的覆盖层字段
    混在一起、互相污染，见 :func:`~app.task.Okww.tools.backup_archive.mas_backup_root`。
    """

    try:
        uid = uuid.UUID(ctx.user_id)
        mode = _okww_config_mode(ctx.script_config.UserData[uid].get("Info", "Mode"))
    except (ValueError, KeyError, TypeError):
        return None
    if mode == "直控":
        return None
    return ctx.user_id if mode == "用户" else "Default"


def _native_config_path(ctx: RestoreContext) -> Path | None:
    """ok-ww 原生 working 配置目录；未配置脚本路径返回 ``None``。"""

    raw = str(ctx.script_config.get("Info", "RootPath") or "").strip()
    return Path(raw) / _OKWW_REL_CONFIG_DIR if raw else None


def _mas_dir_for_owner(ctx: RestoreContext, owner: str) -> Path:
    """按三态 owner 求 MAS 配置目录（归档/恢复目标路径）。"""

    return mas_config_dir(ctx.script_id, owner)


# ══════════════════ mas 池（声明式 + 定制预览/恢复） ══════════════════


async def _mas_files(ctx: RestoreContext) -> dict[str, "Path | str"] | None:
    """归档内容 = owner 目录 ConfigFile 副本 + 覆盖层字段侧车（内存 JSON）。

    直控/无法判态（owner 为 ``None``）或目录缺失/为空时返回 ``None``
    （无可归档内容）。
    """

    _user_guard(ctx)
    owner = _mas_owner(ctx)
    if owner is None:
        return None
    return (
        collect_mas_files(
            _mas_dir_for_owner(ctx, owner),
            read_overlay_values(ctx.script_config.UserData[uuid.UUID(ctx.user_id)]),
        )
        or None
    )


async def _mas_root(ctx: RestoreContext) -> Path:
    return mas_backup_root(ctx.script_id, ctx.user_id)


def _overlay_preview_payload(backup: Path | None, ts: str) -> dict:
    """mas 池预览载荷：覆盖层字段侧车卡 + ConfigFile 副本摘要（与 native 同口径）。

    ConfigFile 副本（含 DailyTask.json）恢复时会完整写回，预览范围必须与
    恢复范围一致——两池同等存在的文件共用渲染
    （:func:`build_backup_file_summary`）。覆盖层字段（快速配置）展示的是
    备份时点的 MAS 页面表单值，运行时才覆盖进 DailyTask.json；来源配置本体
    经「查看详细配置」在 ok-ww GUI 查看。旧版备份无侧车，只剩文件摘要。
    """

    if backup is None:
        raise ValueError(f"备份不存在: {ts}")
    file_cards = build_backup_file_summary(backup)
    overlay = read_overlay_sidecar(backup)
    if overlay is None:
        return {"fileCards": file_cards}
    return {
        "fileCards": [
            {
                "name": "overlay",
                "label": "任务配置",
                "summary": build_overlay_summary(overlay),
            },
            *file_cards,
        ]
    }


async def _preview_mas(ctx: RestoreContext, ts: str) -> dict:
    return _overlay_preview_payload(
        get_mas_backup_dir(ctx.script_id, ctx.user_id, ts), ts
    )


async def _restore_mas(ctx: RestoreContext, ts: str) -> None:
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
        # force 存底标注恢复时点来源（跨来源时 set_mode 已切回备份来源）
        mode=str(user.get("Info", "Mode") or "").strip() or None,
    )
    if restored_overlay:
        # 侧车字段按段分组回填（Info 账号 / Task 覆盖层，对齐 MAA 分组回填）：
        # 文件回滚的同时把表单字段回到备份时点，否则旧表单值下次保存会静默
        # 覆盖回滚结果
        await user.update(group_overlay(restored_overlay))


# ══════════════════ native 池（声明式 + 定制预览/恢复） ══════════════════


async def _native_files(ctx: RestoreContext) -> dict[str, Path] | None:
    """归档内容 = ok-ww 原生 working 配置整目录（缺失/为空返回 ``None``）。"""

    config_path = _native_config_path(ctx)
    if config_path is None:
        return None
    return collect_native_files(config_path) or None


async def _native_root(ctx: RestoreContext) -> Path | None:
    config_path = _native_config_path(ctx)
    if config_path is None:
        return None
    return native_backup_root(config_path)


def _preview_payload(ctx: RestoreContext, ts: str, backup: Path | None) -> dict:
    """native 池预览载荷：MAS 任务配置文件（日常任务，ok-ww 直接消费、
    文件值即生效值），其余文件经「查看详细配置」恢复后在 ok-ww GUI 查看。

    载荷必须是 dict（通用预览响应模型的 ``data`` 字段）；摘要卡挂
    ``fileCards`` 键（专项自定义结构，与基座标准 ``files`` 归档清单分离），
    前端 ``#preview`` 插槽按 ``raw.fileCards`` 消费。
    """

    if backup is None:
        raise ValueError(f"备份不存在: {ts}")
    return {"fileCards": build_backup_file_summary(backup)}


async def _preview_native(ctx: RestoreContext, ts: str) -> dict:
    config_path = _native_config_path(ctx)
    if config_path is None:
        return {"fileCards": []}
    return _preview_payload(ctx, ts, get_native_backup_dir(config_path, ts))


async def _restore_native(ctx: RestoreContext, ts: str) -> None:
    config_path = _native_config_path(ctx)
    if config_path is None:
        raise ValueError("请先设置 ok-ww 脚本路径")
    restore_native_backup(config_path, ts)


RESTORE_POOLS = [
    ConfigRestorePool(
        key="mas",
        kind="user",
        mas_mode="tri_state",
        set_mode=_set_mode,
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
