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

"""M9A 配置恢复服务：MAS 用户字段池 / M9A 本体原生配置池（声明式池）。

池声明只提供**专项知识**（归档什么 + 放哪里 + 恢复语义 + 定制预览），
``list`` / ``snapshot`` / ``read_file`` / ``files`` 兜底全部由基座
（``app.utils.config_restore``）从 ``files`` + ``backup_root`` 声明派生。
备份文件级原语见同目录 ``backup_archive``。

- ``mas`` 池（用户级）：M9A 没有 per-user ConfigFile 目录，池内容是
  **纯字段侧车**（Info 核心 + Task.Queue 原始值 + Display 展示快照）；
  恢复 = 读取侧车并回填 M9AUserConfig（配置来源等危险字段排除，见
  :func:`group_overlay`），回填后表单即时刷新。池分桶恒按用户（共享
  ScriptConfig.json 里的字段是用户级数据），与三态 owner 无关——直控
  用户同样有面板字段（直控+快速配置运行前会写入原生实例配置）。
- ``native`` 池（脚本级）：M9A 安装目录 ``config/`` 整目录，按物理配置根
  指纹分桶；恢复前强制归档当前（误恢复可找回）。

归档时机：manager ``prepare``（任务级 native 一次）、编辑界面进入
（native）/ 退出（mas）由前端 ``ensure`` 触发。M9A 为 MFAA 线，无
ScriptConfig 遮罩会话，不提供「查看详细配置」入口。
"""

import json
import uuid
from pathlib import Path

from app.utils import get_logger
from app.utils.config_restore import ConfigRestorePool, RestoreContext

from .backup_archive import (
    OVERLAY_SIDECAR_NAME,
    archive_mas_backup,
    build_display_overlay,
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

logger = get_logger("M9A 配置恢复")

RESTORE_SCRIPT_NAME = "m9a"
"""专项统一名（文案参数化用）"""


def _user_guard(ctx: RestoreContext) -> None:
    """恢复守卫：目标用户必须存在，避免把字段回填进孤儿目录。"""

    if uuid.UUID(ctx.user_id) not in ctx.script_config.UserData:
        raise ValueError("M9A 用户不存在，请刷新后重试")


def _task_loader(ctx: RestoreContext):
    """按脚本路径取任务加载器（展示快照翻译用）；不可用返回 ``None``。"""

    try:
        raw = str(ctx.script_config.get("Info", "Path") or "").strip()
        if not raw:
            return None
        from app.task.M9A.task_loader import M9ATaskLoader

        return M9ATaskLoader.get_cached(Path(raw))
    except Exception:  # noqa: BLE001 - 任务定义不可用时展示降级，不阻断归档
        return None


def _native_config_path(ctx: RestoreContext) -> Path | None:
    """M9A 安装目录 config/；未配置脚本路径返回 ``None``。"""

    raw = str(ctx.script_config.get("Info", "Path") or "").strip()
    return Path(raw) / "config" if raw else None


async def _mas_files(ctx: RestoreContext) -> dict[str, str]:
    """归档内容 = 页面核心字段侧车（含展示快照，内存 JSON 免临时文件）。

    守卫沿用原快照语义：用户不存在时抛 ``ValueError``。
    """

    _user_guard(ctx)
    user = ctx.script_config.UserData[uuid.UUID(ctx.user_id)]
    overlay = build_display_overlay(read_overlay_values(user), _task_loader(ctx))
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


async def _restore_mas(ctx: RestoreContext, ts: str) -> object:
    _user_guard(ctx)
    user = ctx.script_config.UserData[uuid.UUID(ctx.user_id)]
    # 恢复前把当前字段终态存底（force），误恢复可找回
    current = read_overlay_values(user)
    archive_mas_backup(
        ctx.script_id,
        ctx.user_id,
        build_display_overlay(current, _task_loader(ctx)),
        force=True,
    )
    restored = restore_mas_backup(ctx.script_id, ctx.user_id, ts)
    if restored:
        # 侧车字段回填（Mode/Display 排除）：回填后前端重拉表单，否则旧
        # 表单值下次保存会静默覆盖恢复结果
        await user.update(group_overlay(restored))
        logger.info("用户 %s 的 MAS 字段已恢复备份 %s", ctx.user_id, ts)


async def _native_files(ctx: RestoreContext) -> dict[str, Path] | None:
    """归档内容 = M9A 安装目录 config/ 整目录（缺失或为空返回 ``None``）。"""

    config_path = _native_config_path(ctx)
    if config_path is None:
        return None
    return collect_native_files(config_path) or None


async def _native_root(ctx: RestoreContext) -> Path | None:
    config_path = _native_config_path(ctx)
    return native_backup_root(config_path) if config_path is not None else None


async def _preview_native(ctx: RestoreContext, ts: str) -> dict:
    config_path = _native_config_path(ctx)
    if config_path is None:
        return {"instances": []}
    return build_native_preview(config_path, ts, _task_loader(ctx))


async def _restore_native(ctx: RestoreContext, ts: str) -> object:
    config_path = _native_config_path(ctx)
    if config_path is None:
        raise ValueError("请先设置 M9A 脚本路径")
    restore_native_backup(config_path, ts)


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
