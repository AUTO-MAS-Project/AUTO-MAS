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

"""MAA 配置恢复服务：MAS 用户配置池 / MAA 原生配置池（声明式池）。

池声明只提供**专项知识**（归档什么 + 放哪里 + 恢复语义 + 定制预览），
``list`` / ``snapshot`` / ``read_file`` / ``files`` 兜底预览全部由基座
（``app.utils.config_restore``）从 ``files`` + ``backup_root`` 声明派生。
备份文件级原语见同目录 ``backup_archive``。

mas 池 = 「MAS 为该用户维护的全部配置」：ConfigFile 目录副本 + 页面核心
字段侧车（Info/Task 两段，覆盖 MAS 编辑页全部可配置核心内容）。这些字段
运行时注入 gui.json、不落盘在 ConfigFile——备份/恢复两端都带上侧车（恢复
后按段分组回填表单，对齐 ZzzOd / ok-ww 字段回填模式），预览与页面认知才
一致。池恒按用户分桶（侧车是用户级的，脚本态多用户共享 Default 目录时
各自快照仍需隔离）；两态 owner（脚本=Default 共享目录、用户=独立目录）
只决定归档/恢复目标路径，与运行下发（AutoProxy ``set_maa``）同一套来源
规则。
"""

import shutil
import uuid
from pathlib import Path

from app.utils import get_logger
from app.utils.config_restore import ConfigRestorePool, RestoreContext

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

logger = get_logger("MAA 配置恢复")

RESTORE_SCRIPT_NAME = "maa"
"""专项统一名（文案参数化用）"""


def _user_guard(ctx: RestoreContext) -> None:
    """恢复守卫：目标用户必须存在，避免把配置恢复进孤儿目录。"""

    if uuid.UUID(ctx.user_id) not in ctx.script_config.UserData:
        raise ValueError("MAA 用户不存在，请刷新后重试")


def _mas_owner(ctx: RestoreContext) -> str | None:
    """当前用户的 MAS 配置目录 owner；直控/无法解析时返回 ``None``。

    脚本态共享 ``Default``、用户态用当前用户目录，与 AutoProxy ``set_maa``
    的下发源同一套来源规则；直控用户没有 MAS 托管配置目录（对齐 MaaEnd
    的「直控无 mas 池」），mas 池列表/预览为空；用户不存在时无法判态，
    同样返回 ``None``（恢复/归档另有用户守卫）。
    """

    try:
        uid = uuid.UUID(ctx.user_id)
        mode = str(ctx.script_config.UserData[uid].get("Info", "Mode") or "").strip()
    except (ValueError, KeyError, TypeError):
        return None
    if mode == "直控":
        return None
    return ctx.user_id if mode == "用户" else "Default"


def _native_config_path(ctx: RestoreContext) -> Path | None:
    """MAA 安装目录 config/；未配置脚本路径返回 ``None``。"""

    raw = str(ctx.script_config.get("Info", "Path") or "").strip()
    return Path(raw) / "config" if raw else None


def _mas_dir_for_owner(ctx: RestoreContext, owner: str) -> Path:
    """按两态 owner 求 MAS 配置目录（归档/恢复目标路径）。"""

    return mas_config_dir(ctx.script_id, owner)


def _seed_mas_dir(ctx: RestoreContext, mas_dir: Path) -> None:
    """MAS 配置目录缺失时从 MAA 安装目录 config/ 播种。

    对齐 ok-ww 的 owner 目录初始化（add_user 时播种）：MAA 的配置目录历史
    上只在老版本迁移或一次完成的配置会话后才存在，缺失时退出归档会静默
    跳过（mas 池永远为空，「改了配置也不生产备份」）。播种让「进入编辑页
    → 退出」的包络自第一次退出起就有现场可归档。不在 add_user 时播种：
    MAA 路径可以晚于用户配置，播种失败不该挡建用户。
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
    logger.info(f"已从 MAA 本体播种 MAS 配置目录: {mas_dir}")


# ══════════════════ mas 池（声明式 + 定制预览/恢复） ══════════════════


async def _mas_files(ctx: RestoreContext) -> dict[str, "Path | str"] | None:
    """归档内容 = owner 目录 ConfigFile 副本 + 页面核心字段侧车（内存 JSON）。

    归档前播种 owner 目录（缺失时从 MAA 本体 config/ 回灌）；直控/无法
    判态（owner 为 ``None``）或目录仍缺失/为空时返回 ``None``（无可归档
    内容）。
    """

    _user_guard(ctx)
    owner = _mas_owner(ctx)
    if owner is None:
        return None
    mas_dir = _mas_dir_for_owner(ctx, owner)
    _seed_mas_dir(ctx, mas_dir)
    return (
        collect_mas_files(
            mas_dir,
            read_overlay_values(ctx.script_config.UserData[uuid.UUID(ctx.user_id)]),
        )
        or None
    )


async def _mas_root(ctx: RestoreContext) -> Path:
    return mas_backup_root(ctx.script_id, ctx.user_id)


def _overlay_preview_payload(backup: Path | None, ts: str) -> dict:
    """mas 池预览载荷：侧车字段分区 + ConfigFile 副本摘要（与 native 同口径）。

    侧车字段按「MAS 独有（查看详细配置看不到）/ MAA 对应（可在 MAA GUI
    对照）」分区展示页面字段。ConfigFile 副本里的 gui.json 等配置文件与
    native 池共用同一摘要口径（:func:`build_backup_file_summary`）——副本
    恢复时会完整写回，预览范围必须与恢复范围一致（两池同等存在的文件共用
    渲染）；MAS 页面配置运行时注入、不落盘其中，生效值以侧车分区为准。
    旧版备份无侧车，只剩文件摘要。
    """

    if backup is None:
        raise ValueError(f"备份不存在: {ts}")
    file_cards = build_backup_file_summary(backup)
    overlay = read_overlay_sidecar(backup)
    if overlay is None:
        return {"fileCards": file_cards}
    return {"fileCards": build_overlay_summary(overlay) + file_cards}


async def _preview_mas(ctx: RestoreContext, ts: str) -> dict:
    return _overlay_preview_payload(
        get_mas_backup_dir(ctx.script_id, ctx.user_id, ts), ts
    )


async def _restore_mas(ctx: RestoreContext, ts: str) -> object:
    _user_guard(ctx)
    owner = _mas_owner(ctx)
    if owner is None:
        raise ValueError("无法确定该用户的 MAS 配置目录，请刷新后重试")
    user = ctx.script_config.UserData[uuid.UUID(ctx.user_id)]
    restored_overlay = restore_mas_backup(
        ctx.script_id,
        ctx.user_id,
        ts,
        _mas_dir_for_owner(ctx, owner),
        overlay=read_overlay_values(user),
    )
    if restored_overlay:
        # 侧车字段回填（对齐 ZzzOd / ok-ww 字段回填模式）：按配置段分组写回
        # （Info/Task），页面配置随文件一起回到备份时点，否则旧表单值下次
        # 保存会静默覆盖回滚结果
        await user.update(group_overlay(restored_overlay))


# ══════════════════ native 池（声明式 + 定制预览/恢复） ══════════════════


async def _native_files(ctx: RestoreContext) -> dict[str, Path] | None:
    """归档内容 = MAA 安装目录 config/ 整目录（缺失/为空返回 ``None``）。"""

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
    """预览载荷：MAA 配置文件摘要（与 MAS 侧同口径的稳定字段），其余经
    「查看详细配置」恢复后在 MAA GUI 里查看。

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


async def _restore_native(ctx: RestoreContext, ts: str) -> object:
    config_path = _native_config_path(ctx)
    if config_path is None:
        raise ValueError("请先设置 MAA 脚本路径")
    restore_native_backup(config_path, ts)


RESTORE_POOLS = [
    ConfigRestorePool(
        key="mas",
        kind="user",
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
