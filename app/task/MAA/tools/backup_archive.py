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

"""MAA 配置备份归档：MAS 用户配置 / 脚本原生配置，两类独立快照。

备份时机（MAS「动手前」，此时 MAA 配置尚未被触碰）：

- 任务 / 配置会话启动（manager ``prepare``）：``native`` 归档 MAA 安装
  目录 ``config/`` 当前状态（整目录）——安装配置物理上跨用户共享，只在
  任务级归档一次；下发处按用户归档会把上一轮下发的 MAS 配置误当原生
  内容挤进保留池；
- 运行 / 配置会话下发前（AutoProxy / ScriptConfig 的 ``set_maa``）：
  ``mas`` 归档本轮下发源（脚本态共享 Default 目录、用户态当前用户目录，
  按 owner 各归各的；运行回写与会话保存会覆盖它）；
- 编辑界面进入 / 退出（前端 ensure）：进入时归档 ``native``（MAS 触碰前
  原始态）、退出时归档 ``mas``（编辑会话包络的 MAS 侧终态）。

mas 池的备份对象是「运行下发源」：MAA 的 AutoProxy 按用户 ``Info.Mode``
两态（脚本=Default 共享目录、用户=独立目录）把 MAS 配置 copytree 进安装
目录，并把运行期写盘变更回写该目录。池恒按用户分桶（``mas/{user_id}``），
多用户共享同一份 Default 目录时各自持有快照、互不混淆（教训见
config-restore.md §1.1.1）。时间戳快照、指纹去重、保留清理与整目录恢复的
通用逻辑由公共模块 ``app.utils.config_archive`` 提供（默认每池保留 10 份），
本模块只保留 MAA 特有的目录布局、恢复语义（恢复前强制归档当前）与归档
目录布局。
"""

import json
from pathlib import Path

from app.utils import get_logger
from app.utils.config_archive import (
    archive_dir,
    config_root_key,
    dir_files,
    get_backup_dir,
    list_times,
    restore_dir,
)

logger = get_logger("MAA 配置备份")

_MAA_CONFIG_FILES = ("gui.json", "gui.new.json")
"""MAA 原生配置核心文件（预览白名单；恢复仍整目录写回）"""


def backup_root(script_id: str) -> Path:
    """某脚本的备份归档根目录（MAS 用户池用）：``data/{script_id}/MaaBackups``。"""

    return Path.cwd() / "data" / script_id / "MaaBackups"


def project_backup_root() -> Path:
    """MAA 备份的项目级根目录：``data/MaaBackups``。

    native（脚本原生配置）池挂在这里而不是脚本目录下——同一份物理安装
    可被多个脚本实例引用，原生备份按物理配置根指纹分桶、跨脚本共享、
    不随脚本删除（mas 用户池仍按脚本，见 :func:`mas_backup_root`）。
    """

    return Path.cwd() / "data" / "MaaBackups"


def mas_backup_root(script_id: str, user_id: str) -> Path:
    """MAS 池归档根：``data/{script_id}/MaaBackups/mas/{user_id}``。

    **恒按用户分桶**——脚本态多用户共享 Default 下发源，但每个用户要
    看到、恢复自己的备份；池与恢复目标解耦（目标路径见
    :func:`mas_config_dir`，由 Info.Mode 决定 Default 或用户目录）。
    """

    return backup_root(script_id) / "mas" / user_id


def native_backup_root(config_path: str | Path) -> Path:
    """MAA 原生配置的项目级归档目录：``data/MaaBackups/native/{key}``。

    ``key`` 是物理配置根的指纹（:func:`config_root_key`）——同一份物理
    配置无论被哪个脚本引用都归同一个池；跨脚本共享、不随脚本删除。
    """

    return project_backup_root() / "native" / config_root_key(config_path)


def mas_config_dir(script_id: str, owner: str) -> Path:
    """MAS 配置目录：``data/{script_id}/{owner}/ConfigFile``。"""

    return Path.cwd() / "data" / script_id / owner / "ConfigFile"


# ══════════════════ MAS 配置（池按用户，目标路径按 owner） ══════════════════


def archive_mas_backup(
    script_id: str,
    user_id: str,
    mas_dir: Path,
    force: bool = False,
) -> Path | None:
    """归档 MAS 配置整份到用户池（指纹去重，无变化跳过）。

    ``user_id`` 是池归属（恒按用户分桶，见 :func:`mas_backup_root`）；
    ``mas_dir`` 是归档/恢复目标路径，由调用方按两态 owner 解析（脚本态
    共享 Default 目录、用户态独立目录）——池与目标解耦。
    目录不存在或为空时无可恢复内容，返回 ``None``；``force=True`` 强制
    归档（恢复前存底——让「恢复前的配置」在列表里有明确的时间戳条目）。
    """

    mas_dir = Path(mas_dir)
    if not mas_dir.is_dir() or not any(mas_dir.iterdir()):
        return None
    dest = archive_dir(mas_dir, mas_backup_root(script_id, user_id), force=force)
    if dest is None:
        logger.info("MAS 配置无变化，跳过归档")
        return None
    logger.info(f"用户 {user_id} 的 MAS 配置已归档: {dest.name}")
    return dest


def list_mas_backups(script_id: str, user_id: str) -> list[str]:
    """用户池的全部归档时间戳（倒序，最新在前）。"""

    return list_times(mas_backup_root(script_id, user_id))


def get_mas_backup_dir(script_id: str, user_id: str, ts: str) -> Path | None:
    """取用户池指定时间戳的归档目录；不存在返回 None。"""

    return get_backup_dir(mas_backup_root(script_id, user_id), ts)


def restore_mas_backup(
    script_id: str,
    user_id: str,
    ts: str,
    mas_dir: Path,
) -> None:
    """把用户池归档恢复到 MAS 配置目录（恢复前自动归档当前，误恢复可找回）。

    ``user_id`` 是池归属（与归档一致按用户分桶）；``mas_dir`` 是恢复目标
    路径，由调用方按两态 owner 解析（脚本态共享 Default 目录、用户态独立
    目录）。
    """

    backup_dir = get_mas_backup_dir(script_id, user_id, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    mas_dir = Path(mas_dir)
    if mas_dir.is_dir() and any(mas_dir.iterdir()):
        archive_mas_backup(script_id, user_id, mas_dir, force=True)
    restore_dir(mas_backup_root(script_id, user_id), ts, mas_dir)
    logger.info(f"用户 {user_id} 的 MAS 配置已恢复备份 {ts}")


def archive_mas_runtime_backup(script_id: str, user_id: str, mas_dir: Path) -> None:
    """运行 / 配置会话下发前归档 MAS 配置（下发源）到用户池。

    运行回写与会话保存会覆盖它，下发前存底；指纹去重，失败只记日志，
    绝不中止随后的运行或会话（归档是现场保护，不是前置条件）。
    ``user_id`` 是池归属；``mas_dir`` 是下发源目录，由调用方按当前用户
    两态解析（脚本态=Default 共享目录、用户态=独立目录）。native 池与
    此处无关：原生配置跨用户共享，由 manager ``prepare`` 在任务级一次性
    归档（见 :func:`archive_native_backup`）。
    """

    archive_mas_backup(script_id, user_id, mas_dir)


# ══════════════════ 脚本原生配置（安装目录 config/ 整目录） ══════════════════


def archive_native_backup(config_path: Path, force: bool = False) -> Path | None:
    """归档 MAA 安装目录 config/ 当前状态（整目录）。

    归档落到该项目级池（按物理配置根指纹分桶），与脚本实例解耦。
    目录不存在或为空时无可归档内容，返回 ``None``。
    """

    config_path = Path(config_path)
    if not config_path.is_dir() or not any(config_path.iterdir()):
        return None
    dest = archive_dir(config_path, native_backup_root(config_path), force=force)
    if dest is None:
        logger.info("MAA 原生配置无变化，跳过归档")
        return None
    logger.info(f"MAA 原生配置已归档: {dest.name}")
    return dest


def list_native_backups(config_path: str | Path) -> list[str]:
    """MAA 原生配置全部归档时间戳（倒序，最新在前）。"""

    return list_times(native_backup_root(config_path))


def get_native_backup_dir(config_path: str | Path, ts: str) -> Path | None:
    """取指定时间戳的原生配置归档目录；不存在返回 None。"""

    return get_backup_dir(native_backup_root(config_path), ts)


def restore_native_backup(config_path: Path, ts: str) -> None:
    """把归档恢复到 MAA 安装目录 config/（恢复前自动归档当前，误恢复可找回）。

    整目录替换（MAA 原生配置恒为目录，无 Folder/File 双模式）。
    """

    backup_dir = get_native_backup_dir(config_path, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    config_path = Path(config_path)
    # 恢复前强制归档当前——「恢复前的配置」在列表里有明确的时间戳条目
    archive_native_backup(config_path, force=True)
    restore_dir(native_backup_root(config_path), ts, config_path)
    logger.info(f"MAA 原生配置已恢复备份 {ts}")


# ══════════════════ 备份预览摘要 ══════════════════

_SUMMARY_ROW_LIMIT = 6
"""单文件摘要展示的最大字段行数"""

_SUMMARY_VALUE_LIMIT = 50
"""摘要字段值的最大字符数（超出截断）"""

CONFIG_DISPLAY_NAMES = {
    "gui.json": "MAA 设置",
    "gui.new.json": "MAA 设置（新版）",
}
"""MAA 已知配置文件的展示名（未知文件回退文件名）"""


def _summary_value(value) -> str:
    """摘要标量值转展示文本（布尔转是否、超长截断）。"""

    if isinstance(value, bool):
        return "是" if value else "否"
    text = str(value)
    if len(text) > _SUMMARY_VALUE_LIMIT:
        return text[: _SUMMARY_VALUE_LIMIT - 1] + "…"
    return text


def _gui_summary_rows(data: dict) -> list[dict]:
    """gui.json 的稳定字段摘要（抗 MAA 版本漂移，只取结构稳定项）。

    预览的语义是「这份备份的 MAA 设置是什么样」：展示当前方案与方案数，
    其余配置项随 MAA 版本变化大，不进预览（经「查看详细配置」恢复后在
    MAA GUI 里查看）。
    """

    rows: list[dict] = []
    current = data.get("Current")
    if current is not None:
        rows.append({"key": "当前方案", "value": _summary_value(current)})
    configurations = data.get("Configurations")
    if isinstance(configurations, dict) and len(configurations) > 1:
        rows.append(
            {"key": "方案数", "value": str(len(configurations))}
        )
    return rows[: _SUMMARY_ROW_LIMIT]


def build_backup_file_summary(backup_dir: Path) -> list[dict]:
    """备份目录内 MAA 配置文件的摘要列表（预览用，纯读）。

    每个文件一条 ``{name, label, summary}``：label 用 MAA 配置展示名
    （未知文件回退文件名），summary 只取稳定字段。只保留预览白名单内的
    文件，非 JSON / 坏 JSON / 无可展示字段的文件跳过（恢复时仍会随备份
    完整写回）。
    """

    files: list[dict] = []
    for rel in sorted(dir_files(backup_dir)):
        if "/" in rel or rel not in _MAA_CONFIG_FILES:
            continue
        try:
            data = json.loads((backup_dir / rel).read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        rows = _gui_summary_rows(data)
        if not rows:  # 无可展示字段的文件不进预览
            continue
        files.append(
            {
                "name": rel,
                "label": CONFIG_DISPLAY_NAMES.get(rel, rel),
                "summary": rows,
            }
        )
    return files
