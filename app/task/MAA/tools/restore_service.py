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
from app.utils.config_restore import ConfigRestorePool

from .backup_archive import (
    archive_mas_backup,
    archive_native_backup,
    build_backup_file_summary,
    build_overlay_summary,
    get_mas_backup_dir,
    get_native_backup_dir,
    group_overlay,
    list_mas_backups,
    list_native_backups,
    mas_config_dir,
    read_overlay_sidecar,
    read_overlay_values,
    restore_mas_backup,
    restore_native_backup,
)

logger = get_logger("MAA 配置恢复")

RESTORE_SCRIPT_NAME = "maa"
"""专项统一名（文案参数化用）"""


def _user_guard(ctx) -> None:
    """恢复守卫：目标用户必须存在，避免把配置恢复进孤儿目录。"""

    if uuid.UUID(ctx.user_id) not in ctx.script_config.UserData:
        raise ValueError("MAA 用户不存在，请刷新后重试")


def _mas_owner(ctx) -> str | None:
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


def _native_config_path(ctx) -> Path | None:
    """MAA 安装目录 config/；未配置脚本路径返回 ``None``。"""

    raw = str(ctx.script_config.get("Info", "Path") or "").strip()
    return Path(raw) / "config" if raw else None


def _mas_dir_for_owner(ctx, owner: str) -> Path:
    """按两态 owner 求 MAS 配置目录（归档/恢复目标路径）。"""

    return mas_config_dir(ctx.script_id, owner)


def _seed_mas_dir(ctx, mas_dir: Path) -> None:
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


def _preview_payload(ctx, ts: str, backup: Path | None) -> dict:
    """预览载荷：MAA 配置文件摘要（与 MAS 侧同口径的稳定字段），其余经
    「查看详细配置」恢复后在 MAA GUI 里查看。

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


def _overlay_preview_payload(backup: Path | None, ts: str) -> dict:
    """mas 池预览载荷：侧车字段分区预览（MAS 独有配置 + MAA 对应配置）。

    ConfigFile 里的 gui.json 是 MAA GUI 结构，MAS 页面配置（Info/Task 段）
    运行时才注入、不落盘其中——展示它只会误导（与页面对不上）；这里只
    展示与页面同源的侧车字段，且按「MAS 独有（查看详细配置看不到）/
    MAA 对应（可在 MAA GUI 对照）」分区。旧版备份无侧车，无可展示内容。
    """

    if backup is None:
        raise ValueError(f"备份不存在: {ts}")
    overlay = read_overlay_sidecar(backup)
    if overlay is None:
        return {"files": []}
    return {"files": build_overlay_summary(overlay)}


async def _preview_mas(ctx, ts: str) -> dict:
    return _overlay_preview_payload(
        get_mas_backup_dir(ctx.script_id, ctx.user_id, ts), ts
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


async def _restore_native(ctx, ts: str) -> object:
    config_path = _native_config_path(ctx)
    if config_path is None:
        raise ValueError("请先设置 MAA 脚本路径")
    restore_native_backup(config_path, ts)


async def _snapshot_mas(ctx) -> dict:
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
