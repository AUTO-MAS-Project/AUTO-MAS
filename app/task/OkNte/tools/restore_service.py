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

"""OK-NTE 配置恢复服务：MAS 用户配置池 / ok-nte 原生配置池（声明式池）。

池声明只提供**专项知识**（归档什么 + 放哪里 + 恢复语义 + 定制预览），
``list`` / ``snapshot`` / ``read_file`` / ``files`` 兜底预览全部由基座
（``app.utils.config_restore``）从 ``files`` + ``backup_root`` 声明派生。
备份文件级原语见同目录 ``backup_archive``。

mas 池 = MAS 用户 ConfigFile 目录副本（恒按用户分桶）。native 池 =
ok-nte 原生配置（Folder 整目录 / File 单文件，随 ``Script.ConfigPathMode``
两种取值），按物理配置根指纹分桶。
"""

import uuid
from pathlib import Path

from app.task.OkNte.config_schema import (
    DAILY_ROUTINE_CONFIGS_FILE,
    DAILY_ROUTINE_TASK_FILE,
    load_oknte_option_labels,
)
from app.utils.config_restore import ConfigRestorePool, RestoreContext

from .backup_archive import (
    build_backup_file_summary,
    collect_config_files,
    collect_mas_files,
    get_mas_backup_dir,
    get_native_backup_dir,
    mas_backup_root,
    mas_config_dir,
    native_backup_root,
    restore_mas_backup,
    restore_native_backup,
)

RESTORE_SCRIPT_NAME = "ok-nte"
"""专项统一名（文案参数化用）"""


def _user_guard(ctx: RestoreContext) -> None:
    """恢复守卫：目标用户必须存在，避免把配置恢复进孤儿目录。"""

    if uuid.UUID(ctx.user_id) not in ctx.script_config.UserData:
        raise ValueError("OK-NTE 用户不存在，请刷新后重试")


def _native_config_path(ctx: RestoreContext) -> tuple[Path | None, str]:
    """原生配置路径与模式（Folder/File）；未配置路径返回 None。"""

    raw = str(ctx.script_config.get("Script", "ConfigPath") or "").strip()
    mode = str(ctx.script_config.get("Script", "ConfigPathMode") or "Folder")
    return (Path(raw) if raw else None, mode)


# ══════════════════ mas 池（声明式 + 定制预览/恢复） ══════════════════


async def _mas_files(ctx: RestoreContext) -> dict[str, Path] | None:
    """归档内容 = MAS 用户 ConfigFile 副本（缺失/为空返回 ``None``）。"""

    return collect_mas_files(mas_config_dir(ctx.script_id, ctx.user_id)) or None


async def _mas_root(ctx: RestoreContext) -> Path:
    return mas_backup_root(ctx.script_id, ctx.user_id)


def _preview_payload(ctx: RestoreContext, ts: str, backup: Path | None) -> dict:
    """两个目标池内容同构（ok-nte JSON 配置文件集）：预览只给任务配置两件套
    （日常任务流程 + 日常子任务配置，即 MAS 编辑页「任务配置」组，对齐一条龙
    的「编排清单」预览），其余文件经「查看详细配置」恢复后在 ok-nte GUI 里
    查看。

    载荷必须是 dict（通用预览响应模型的 ``data`` 字段）；摘要卡挂
    ``fileCards`` 键（专项自定义结构，与基座标准 ``files`` 归档清单分离），
    前端 ``#preview`` 插槽按 ``raw.fileCards`` 消费。
    """

    if backup is None:
        raise ValueError(f"备份不存在: {ts}")
    root_path = str(ctx.script_config.get("Info", "RootPath") or "")
    labels = load_oknte_option_labels(root_path) if root_path else {}
    keep = (DAILY_ROUTINE_TASK_FILE, DAILY_ROUTINE_CONFIGS_FILE)
    files = [f for f in build_backup_file_summary(backup, labels) if f["name"] in keep]
    return {"fileCards": files}


async def _preview_mas(ctx: RestoreContext, ts: str) -> dict:
    return _preview_payload(ctx, ts, get_mas_backup_dir(ctx.script_id, ctx.user_id, ts))


async def _restore_mas(ctx: RestoreContext, ts: str) -> object:
    _user_guard(ctx)
    restore_mas_backup(
        ctx.script_id, ctx.user_id, ts, mas_config_dir(ctx.script_id, ctx.user_id)
    )


# ══════════════════ native 池（声明式 + 定制预览/恢复） ══════════════════


async def _native_files(ctx: RestoreContext) -> dict[str, Path] | None:
    """归档内容 = ok-nte 原生配置文件集（Folder/File 双模式；缺失返回 ``None``）。"""

    config_path, mode = _native_config_path(ctx)
    if config_path is None:
        return None
    return collect_config_files(config_path, mode) or None


async def _native_root(ctx: RestoreContext) -> Path | None:
    config_path, _ = _native_config_path(ctx)
    if config_path is None:
        return None
    return native_backup_root(config_path)


async def _preview_native(ctx: RestoreContext, ts: str) -> dict:
    config_path, _ = _native_config_path(ctx)
    if config_path is None:
        return {"fileCards": []}
    return _preview_payload(ctx, ts, get_native_backup_dir(config_path, ts))


async def _restore_native(ctx: RestoreContext, ts: str) -> object:
    config_path, mode = _native_config_path(ctx)
    if config_path is None:
        raise ValueError("请先设置 OK-NTE 配置路径")
    restore_native_backup(config_path, ts, mode)


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
