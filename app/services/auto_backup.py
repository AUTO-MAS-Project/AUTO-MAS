#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


"""版本升级时的自动备份（#949）。

版本号变化后的首次启动，把 data/config/history 打包成一份 zip 放进用户指定的目录，
并按「主.次」滚动保留：当前段 + 上一段，且最新两份永远保留。

清理只作用于本工具按 AUTO-MAS-auto-<旧版本号>-<时间戳>.zip 生成的文件，目录里的其它
文件一律不动；打包/移动失败时不删任何文件、也不推进已记录的版本号，下次启动重试这一版。
"""

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from packaging.version import InvalidVersion
from packaging.version import parse as parse_version

from app.services.data_backup import create_data_backup
from app.utils import get_logger
from app.utils.io import read_file, write_file

logger = get_logger("升级自动备份")

_BACKUP_FILE_PATTERN = re.compile(r"^AUTO-MAS-auto-v?(.+)-(\d{8}-\d{6})\.zip$")


def _segment(version: str) -> tuple[int, int] | None:
    """版本号 -> (主, 次)；认不出的返回 None（beta 与正式版同段）。"""

    try:
        parsed = parse_version(str(version))
    except InvalidVersion:
        return None
    return (parsed.major, parsed.minor)


def plan_retention(names: list[str], current_version: str) -> list[str]:
    """返回应当删除的备份文件名（只考虑本工具生成的文件）。

    - 当前段 = 本次启动版本的 (主, 次)
    - 上一段 = 现存备份里比当前段小的最大那一段，不拿次版本号减一
      （升到 6.0 时上一段是 5.x 的最后一段，跨版本直升时上一段就是原段）
    - 最新两份按文件名尾部时间戳排序，永远保留，即使落在更老的段里
    """

    current = _segment(current_version)
    if current is None:
        return []

    parsed: dict[str, tuple[tuple[int, int], str]] = {}
    for name in names:
        matched = _BACKUP_FILE_PATTERN.match(name)
        if matched is None:
            continue
        segment = _segment(matched.group(1))
        if segment is None:
            continue
        parsed[name] = (segment, matched.group(2))

    newest = {
        name
        for name, _ in sorted(
            parsed.items(), key=lambda item: item[1][1], reverse=True
        )[:2]
    }
    older = [segment for segment, _ in parsed.values() if segment < current]
    keep = {current} | ({max(older)} if older else set())

    return sorted(
        name
        for name, (segment, _) in parsed.items()
        if name not in newest and segment not in keep
    )


def _remember(
    config_file: Path, raw: dict[str, Any], section: dict[str, Any], version: str
) -> None:
    """把「上次运行的版本号」写回 Config.json（原子写）。"""

    updated = dict(raw)
    updated["Backup"] = {**section, "LastVersion": version}
    write_file(config_file, updated)


def _remove_stale(backup_dir: Path, current_version: str) -> list[str]:
    """清理滚动保留之外的旧备份，返回实际删掉的文件名。"""

    names = [path.name for path in backup_dir.iterdir() if path.is_file()]
    removed: list[str] = []
    for name in plan_retention(names, current_version):
        try:
            (backup_dir / name).unlink()
            removed.append(name)
        except OSError as exc:
            logger.warning(f"清理旧备份 {name} 失败：{exc}")
    return removed


def run_upgrade_backup(
    root: Path, config_path: Path, current_version: str
) -> dict[str, Any] | None:
    """版本号变化后的首次启动做一次自动备份；无需备份时返回 None。

    返回 {"created": 新备份文件名或 None, "removed": 被清理的文件名, "error": 失败原因或 None}。
    """

    config_file = Path(config_path) / "Config.json"
    try:
        raw = read_file(config_file)
    except Exception as exc:  # noqa: BLE001 - 读不到配置不阻断启动
        logger.opt(exception=True).warning(
            f"读取 Config.json 失败，跳过自动备份：{exc}"
        )
        return None
    if not isinstance(raw, dict):
        logger.warning("Config.json 内容不是对象，跳过自动备份")
        return None

    section = raw.get("Backup")
    section = dict(section) if isinstance(section, dict) else {}
    previous = str(section.get("LastVersion") or "").strip()
    if not previous:
        # 新装或功能落地后的首次记录：只记下当前版本，不凭空产生一份备份
        _remember(config_file, raw, section, current_version)
        return None
    if previous == current_version:
        return None

    if _segment(previous) is None or _segment(current_version) is None:
        logger.warning(
            f"版本号无法识别（{previous!r} -> {current_version!r}），跳过自动备份"
        )
        return None

    if not bool(section.get("IfAutoBackup")):
        _remember(config_file, raw, section, current_version)
        return None

    target = str(section.get("BackupDir") or "").strip()
    if not target:
        _remember(config_file, raw, section, current_version)
        return None

    backup_dir = Path(target)
    if not backup_dir.is_absolute() or len(backup_dir.resolve().parts) < 2:
        message = f"自动备份目录不合法（{target}），本次不备份"
        logger.warning(message)
        return {"created": None, "removed": [], "error": message}

    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        temporary = create_data_backup(root)
        try:
            destination = backup_dir / (
                f"AUTO-MAS-auto-{previous}-{datetime.now():%Y%m%d-%H%M%S}.zip"
            )
            shutil.move(str(temporary), str(destination))
        except Exception:
            Path(temporary).unlink(missing_ok=True)
            raise
    except Exception as exc:  # noqa: BLE001 - 打包失败不删任何文件、不改版本号
        logger.opt(exception=True).warning(f"升级自动备份失败：{exc}")
        return {"created": None, "removed": [], "error": str(exc)}

    removed = _remove_stale(backup_dir, current_version)
    try:
        _remember(config_file, raw, section, current_version)
    except Exception as exc:  # noqa: BLE001 - 备份已落盘，写不回版本号只影响下次是否重试
        logger.opt(exception=True).warning(f"写回 LastVersion 失败：{exc}")
        return {"created": destination.name, "removed": removed, "error": str(exc)}

    return {"created": destination.name, "removed": removed, "error": None}
