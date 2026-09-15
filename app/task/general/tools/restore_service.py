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

"""通用脚本配置恢复服务：MAS 用户配置副本池 / 脚本原生配置池（声明式池）。

池声明只提供**专项知识**（归档什么 + 放哪里 + 恢复语义 + 定制预览），
``list`` / ``snapshot`` / ``read_file`` / ``files`` 兜底全部由基座
（``app.utils.config_restore``）从 ``files`` + ``backup_root`` 声明派生。
备份文件级原语见同目录 ``backup_archive``。

- ``mas`` 池（用户级）：该用户的 ``ConfigFile`` 目录副本（General 恒按
  用户隔离，无 MAA 式 owner 解耦），恢复 = 整目录回写；MAS 编辑页字段
  不注入原生配置，无侧车、无字段回填。
- ``native`` 池（脚本级）：用户自填的 ``Script.ConfigPath``（Folder 整
  目录 / File 单文件两态），按物理配置根指纹分桶，恢复前强制存底当前。

两池均无定制 preview：通用脚本配置格式任意（透传），MAS 不解析内容，
预览直接吃基座标准 ``files`` 注入（归档内文件清单，前端「备份文件」
兜底节渲染），详细内容经「查看详细配置」（viewOnly 会话）在脚本 GUI
里查看。General 是声明式接入的零定制样板。

归档时机：manager ``prepare``（任务级 native 一次）、运行/会话下发前
（AutoProxy / ScriptConfig）、编辑界面进入（native）/ 退出（mas）由前端
``ensure`` 触发。
"""

import uuid
from pathlib import Path

from app.utils import get_logger
from app.utils.config_restore import ConfigRestorePool, RestoreContext

from .backup_archive import (
    collect_mas_files,
    collect_native_files,
    mas_backup_root,
    mas_config_dir,
    native_backup_root,
    restore_mas_backup,
    restore_native_backup,
)

logger = get_logger("通用脚本配置恢复")

RESTORE_SCRIPT_NAME = "general"
"""专项统一名（文案参数化用）"""


def _user_guard(ctx: RestoreContext) -> None:
    """恢复守卫：目标用户必须存在，避免把配置恢复进孤儿目录。"""

    if uuid.UUID(ctx.user_id) not in ctx.script_config.UserData:
        raise ValueError("通用脚本用户不存在，请刷新后重试")


def _native_config_path(ctx: RestoreContext) -> Path | None:
    """脚本原生配置路径（``Script.ConfigPath``）；未配置返回 ``None``。"""

    raw = str(ctx.script_config.get("Script", "ConfigPath") or "").strip()
    return Path(raw) if raw else None


def _native_config_mode(ctx: RestoreContext) -> str:
    """配置路径模式（``Script.ConfigPathMode``：Folder / File）。"""

    return str(ctx.script_config.get("Script", "ConfigPathMode") or "Folder")


async def _mas_files(ctx: RestoreContext) -> dict[str, Path] | None:
    """归档内容 = 用户 ConfigFile 目录（恒按用户，无侧车；空目录返回 ``None``）。"""

    _user_guard(ctx)
    return collect_mas_files(mas_config_dir(ctx.script_id, ctx.user_id)) or None


async def _mas_root(ctx: RestoreContext) -> Path:
    return mas_backup_root(ctx.script_id, ctx.user_id)


async def _restore_mas(ctx: RestoreContext, ts: str) -> object:
    _user_guard(ctx)
    restore_mas_backup(
        ctx.script_id, ctx.user_id, ts, mas_config_dir(ctx.script_id, ctx.user_id)
    )


async def _native_files(ctx: RestoreContext) -> dict[str, Path] | None:
    """归档内容 = ConfigPath 当前状态（Folder 整目录 / File 单文件；缺失返回 ``None``）。"""

    config_path = _native_config_path(ctx)
    if config_path is None:
        return None
    return collect_native_files(config_path, _native_config_mode(ctx)) or None


async def _native_root(ctx: RestoreContext) -> Path | None:
    config_path = _native_config_path(ctx)
    if config_path is None:
        return None
    return native_backup_root(ctx.script_id, config_path)


async def _restore_native(ctx: RestoreContext, ts: str) -> object:
    config_path = _native_config_path(ctx)
    if config_path is None:
        raise ValueError("请先设置脚本配置路径")
    restore_native_backup(ctx.script_id, config_path, _native_config_mode(ctx), ts)


RESTORE_POOLS = [
    ConfigRestorePool(
        key="mas",
        kind="user",
        mas_mode="user_only",
        files=_mas_files,
        backup_root=_mas_root,
        restore=_restore_mas,
    ),
    ConfigRestorePool(
        key="native",
        kind="script",
        files=_native_files,
        backup_root=_native_root,
        restore=_restore_native,
    ),
]
