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

"""OK-NTE 配置备份归档：MAS 用户配置 / 脚本原生配置，两类独立快照。

备份时机（MAS「动手前」，此时 ok-nte 尚未被触碰）：

- 任务 / 配置会话启动（manager ``prepare``）：``native`` 归档脚本原生配置
  当前状态（Folder 整目录 / File 单文件）——原生配置物理上跨用户共享，
  只在任务级归档一次；``set_oknte`` 里按用户/重试归档会把上一轮下发的
  MAS 配置误当原生内容挤进保留池；
- 运行 / 配置会话下发前（AutoProxy / ScriptConfig 的 ``set_oknte``）：
  ``mas`` 归档 MAS 用户 ConfigFile（下发源，运行回写与会话保存会覆盖它，
  按用户各归各的）；
- 编辑界面进入 / 退出（前端 ensure）：进入时归档 ``native``（MAS 触碰前
  原始态）、退出时归档 ``mas``（编辑会话包络的 MAS 侧终态）。

时间戳快照、指纹去重、保留清理与整目录恢复的通用逻辑由公共模块
``app.utils.config_archive`` 提供（默认每池保留 10 份），本模块只保留
ok-nte 特有的文件集收集（Folder/File 双模式）、恢复语义（恢复前强制
归档当前）与归档目录布局。
"""

import json
import shutil
from contextlib import suppress
from pathlib import Path

from app.utils import get_logger
from app.utils.config_archive import (
    archive_dir,
    archive_files,
    config_root_key,
    dir_files,
    get_backup_dir,
    list_times,
    restore_dir,
)

from ..config_schema import (
    _FALLBACK_LABELS,
    CONFIG_DISPLAY_NAMES,
    DAILY_ROUTINE_CONFIGS_FILE,
    DAILY_ROUTINE_ITEMS,
    DAILY_ROUTINE_TASK_FILE,
)

logger = get_logger("OK-NTE 配置备份")

_SUMMARY_ROW_LIMIT = 8
"""单文件摘要展示的最大字段行数"""

_SUMMARY_VALUE_LIMIT = 50
"""摘要字段值的最大字符数（超出截断）"""


def backup_root(script_id: str) -> Path:
    """某脚本的备份归档根目录（MAS 用户池用）：``data/{script_id}/OkNteBackups``。"""

    return Path.cwd() / "data" / script_id / "OkNteBackups"


def project_backup_root() -> Path:
    """ok-nte 备份的项目级根目录：``data/OkNteBackups``。

    native（脚本原生配置）池挂在这里而不是脚本目录下——物理配置跨脚本共享、
    不随脚本删除（mas 用户池仍按脚本，见 :func:`mas_backup_root`）。
    """

    return Path.cwd() / "data" / "OkNteBackups"


def mas_backup_root(script_id: str, user_id: str) -> Path:
    """MAS 用户配置的归档目录：``data/{script_id}/OkNteBackups/mas/{user_id}``。"""

    return backup_root(script_id) / "mas" / user_id


def native_backup_root(config_path: str | Path) -> Path:
    """ok-nte 原生配置的项目级归档目录：``data/OkNteBackups/native/{key}``。

    ``key`` 是物理配置根的指纹（:func:`config_root_key`）——同一份物理配置
    无论被哪个脚本引用都归同一个池；跨脚本共享、不随脚本删除。
    """

    return project_backup_root() / "native" / config_root_key(config_path)


def mas_config_dir(script_id: str, user_id: str) -> Path:
    """MAS 用户配置目录：``data/{script_id}/{user_id}/ConfigFile``。"""

    return Path.cwd() / "data" / script_id / user_id / "ConfigFile"


def collect_config_files(config_path: Path, mode: str) -> dict[str, Path] | None:
    """收集当前原生配置文件集；配置不存在（或目录为空）返回 ``None``。

    ``mode`` 为 ``Folder`` 时整目录收集，``File`` 时单文件（相对键为文件名），
    与 ``Script.ConfigPathMode`` 的两种取值对应。
    """

    config_path = Path(config_path)
    if not config_path.name:  # 空配置路径解析为 '.'，绝不整树归档当前目录
        return None
    if mode == "File":
        if not config_path.is_file():
            return None
        return {config_path.name: config_path}
    if not config_path.is_dir() or not any(config_path.iterdir()):
        return None
    return dir_files(config_path)


# ══════════════════ MAS 用户配置 ══════════════════


def archive_mas_backup(
    script_id: str,
    user_id: str,
    mas_dir: Path,
    force: bool = False,
) -> Path | None:
    """归档 MAS 用户 ConfigFile 整份（指纹去重，无变化跳过）。

    目录不存在或为空时无可恢复内容，返回 ``None``；``force=True`` 强制
    归档（恢复前存底——让「恢复前的配置」在列表里有明确的时间戳条目）。
    """

    mas_dir = Path(mas_dir)
    if not mas_dir.is_dir() or not any(mas_dir.iterdir()):
        return None
    dest = archive_dir(mas_dir, mas_backup_root(script_id, user_id), force=force)
    if dest is None:
        logger.info("用户 MAS 配置无变化，跳过归档")
        return None
    logger.info(f"用户 {user_id} 的 MAS 配置已归档: {dest.name}")
    return dest


def list_mas_backups(script_id: str, user_id: str) -> list[str]:
    """MAS 用户配置全部归档时间戳（倒序，最新在前）。"""

    return list_times(mas_backup_root(script_id, user_id))


def get_mas_backup_dir(script_id: str, user_id: str, ts: str) -> Path | None:
    """取指定时间戳的 MAS 用户归档目录；不存在返回 None。"""

    return get_backup_dir(mas_backup_root(script_id, user_id), ts)


def restore_mas_backup(script_id: str, user_id: str, ts: str, mas_dir: Path) -> None:
    """把归档恢复到 MAS 用户 ConfigFile（恢复前自动归档当前，误恢复可找回）。"""

    mas_dir = Path(mas_dir)
    if mas_dir.is_dir() and any(mas_dir.iterdir()):
        archive_mas_backup(script_id, user_id, mas_dir, force=True)
    restore_dir(mas_backup_root(script_id, user_id), ts, mas_dir)
    logger.info(f"用户 {user_id} 的 MAS 配置已恢复备份 {ts}")


# ══════════════════ 脚本原生配置 ══════════════════


def archive_native_backup(
    config_path: Path,
    mode: str,
    force: bool = False,
) -> Path | None:
    """归档 ok-nte 原生配置当前状态（Folder 整目录 / File 单文件）。

    归档落到该项目级池（按物理配置根指纹分桶），与脚本实例解耦。
    """

    files = collect_config_files(config_path, mode)
    if not files:
        return None
    dest = archive_files(files, native_backup_root(config_path), force=force)
    if dest is None:
        logger.info("ok-nte 原生配置无变化，跳过归档")
        return None
    logger.info(f"ok-nte 原生配置已归档: {dest.name} ({len(files)} 个文件)")
    return dest


def list_native_backups(config_path: str | Path) -> list[str]:
    """ok-nte 原生配置全部归档时间戳（倒序，最新在前）。"""

    return list_times(native_backup_root(config_path))


def get_native_backup_dir(config_path: str | Path, ts: str) -> Path | None:
    """取指定时间戳的原生配置归档目录；不存在返回 None。"""

    return get_backup_dir(native_backup_root(config_path), ts)


def restore_native_backup(config_path: Path, ts: str, mode: str) -> None:
    """把归档恢复到 ok-nte 原生配置位置（恢复前自动归档当前，误恢复可找回）。

    Folder 模式整目录替换；File 模式把备份内文件写回原文件名。
    """

    backup_dir = get_native_backup_dir(config_path, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    config_path = Path(config_path)
    # 恢复前强制归档当前——「恢复前的配置」在列表里有明确的时间戳条目
    archive_native_backup(config_path, mode, force=True)
    if mode == "File":
        files = dir_files(backup_dir)
        if not files:
            raise ValueError(f"备份内容为空: {ts}")
        src = files.get(config_path.name) or next(iter(files.values()))
        config_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, config_path)
        logger.info(f"ok-nte 原生配置文件已恢复备份 {ts}")
        return
    restore_dir(native_backup_root(config_path), ts, config_path)
    logger.info(f"ok-nte 原生配置已恢复备份 {ts}")


def archive_mas_runtime_backup(script_id: str, user_id: str) -> None:
    """运行 / 配置会话下发前归档 MAS 用户 ConfigFile（下发源）。

    运行回写与会话保存会覆盖它，下发前存底；指纹去重，失败只记日志，
    绝不中止随后的运行或会话（归档是现场保护，不是前置条件）。
    native 池与此处无关：原生配置跨用户共享，由 manager ``prepare`` 在
    任务级一次性归档（见 :func:`archive_native_backup`）。
    """

    with suppress(Exception):
        archive_mas_backup(script_id, user_id, mas_config_dir(script_id, user_id))


# ══════════════════ 备份预览摘要 ══════════════════


def _translate_key(key: str, labels: dict[str, str]) -> str:
    """字段键翻译：ok-nte 安装目录翻译 > 兜底标签 > 原始键。"""

    return labels.get(key) or _FALLBACK_LABELS.get(key, key)


def _summary_value(value) -> str:
    """摘要标量值转展示文本（布尔转是否、超长截断）。"""

    if isinstance(value, bool):
        return "是" if value else "否"
    text = str(value)
    if len(text) > _SUMMARY_VALUE_LIMIT:
        return text[: _SUMMARY_VALUE_LIMIT - 1] + "…"
    return text


def _file_summary_rows(name: str, data: dict, labels: dict[str, str]) -> list[dict]:
    """单个 JSON 配置文件的摘要行（顶层标量字段，Routine Items 特殊展开）。"""

    rows: list[dict] = []

    if name == DAILY_ROUTINE_CONFIGS_FILE:
        # 子任务配置顶层是「任务 id → 子对象」结构，无顶层标量——按任务
        # 展开一层，行键带任务名前缀（如「异象界域·目标消耗体力」）
        label_by_id = {item["id"]: item["label"] for item in DAILY_ROUTINE_ITEMS}
        for task_id, sub in data.items():
            if task_id.startswith("_") or not isinstance(sub, dict):
                continue
            prefix = label_by_id.get(task_id, task_id)
            for key, value in sub.items():
                if key.startswith("_") or isinstance(value, (dict, list)):
                    continue
                rows.append(
                    {
                        "key": f"{prefix}·{_translate_key(key, labels)}",
                        "value": _summary_value(value),
                    }
                )
                if len(rows) >= _SUMMARY_ROW_LIMIT:
                    return rows
        return rows

    for key, value in data.items():
        if key.startswith("_"):  # ok-nte 框架内部字段（_enabled 等）
            continue
        if name == DAILY_ROUTINE_TASK_FILE and key == "Routine Items":
            enabled_ids = {
                item.get("id")
                for item in (value or [])
                if isinstance(item, dict) and item.get("enabled")
            }
            enabled_names = [
                item["label"]
                for item in DAILY_ROUTINE_ITEMS
                if item["id"] in enabled_ids
            ]
            rows.append(
                {"key": "已启用任务", "value": "、".join(enabled_names) or "无"}
            )
            continue
        if isinstance(value, (dict, list)):
            continue  # 子对象/列表不展开，预览保持轻量
        rows.append(
            {"key": _translate_key(key, labels), "value": _summary_value(value)}
        )
        if len(rows) >= _SUMMARY_ROW_LIMIT:
            break
    return rows


def build_backup_file_summary(
    backup_dir: Path,
    option_labels: dict[str, str],
) -> list[dict]:
    """备份目录内 JSON 配置文件的摘要列表（预览用，纯读）。

    每个文件一条 ``{name, label, summary}``：label 用 ok-nte 配置显示名
    （未知文件回退文件名），summary 取顶层标量字段。非 JSON 文件不展示
    （恢复时仍会随备份完整写回）。
    """

    files: list[dict] = []
    for rel in sorted(dir_files(backup_dir)):
        if "/" in rel or not rel.lower().endswith(".json"):
            continue
        try:
            data = json.loads((backup_dir / rel).read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        rows = _file_summary_rows(rel, data, option_labels)
        if not rows:  # 无可展示字段（如纯嵌套结构）的文件不进预览
            continue
        files.append(
            {
                "name": rel,
                "label": CONFIG_DISPLAY_NAMES.get(rel, rel),
                "summary": rows,
            }
        )
    return files
