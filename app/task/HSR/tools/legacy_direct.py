#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""旧版 HSR 直控快照（``Direct.*``）停用前的留档，在 ``ScriptConfig.connect()`` 之前读原始 JSON。

v5.5.0 及更早的 HSR 用户配置带一组 ``Direct``：``SRAConfig`` / ``M7AConfig`` 是导入进来的
原生配置快照（DPAPI 密文），直控时跑它而不是脚本当前的活配置。三态收敛删掉了这组字段，
而 ``ConfigBase.load`` 只认类里声明的条目，按新类加载的那一刻快照就被丢掉并写回盘；字段
侧车备份从不收快照内容，丢了就找不回来。

所以启动时在连接之前扫一遍：HSR 脚本下快照非空的用户，把整组 ``Direct`` 原样（密文不解）
另存为 ``data/<脚本 uid>/HSRBackups/direct/<用户 uid>-<时间>.json``，结果交给启动流程发一条
系统通知。某个用户另存失败时退一步，把整份 ``ScriptConfig.json`` 复制成同目录下的
``ScriptConfig.json.hsr-direct-<时间>.bak``：它和随后要写回的文件在同一目录，连它都写不进去
时写回大概率也会失败，快照就还留在盘上，下次启动再试。

幂等：快照被上一次加载删掉后就扫不到了；留档目录里已有 ``Direct`` 完全相同的文件（另存成功、
写回失败的情形）也不再另存、不再通知。非 HSR 脚本不读不写。
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from app.utils import get_logger

logger = get_logger("HSR 直控快照留档")

HSR_SCRIPT_TYPE = "HSRConfig"
LEGACY_GROUP = "Direct"
_SNAPSHOT_KEYS = ("SRAConfig", "M7AConfig")
FALLBACK_SUFFIX = ".hsr-direct-"
FALLBACK_KEEP = 3
_ARCHIVE_NOTE = (
    "AUTO-MAS 已停用 HSR 直控快照，这是停用前的原样留档，AUTO-MAS 不会再读取本文件。"
    "SRAConfig / M7AConfig 是本机当前 Windows 账户加密的原生配置内容。"
)


def direct_snapshot_root(script_id: str) -> Path:
    """旧直控快照的留档目录：``data/{script_id}/HSRBackups/direct``（与 ``mas`` 池同级）。"""

    return Path.cwd() / "data" / script_id / "HSRBackups" / "direct"


@dataclass
class LegacyDirectSnapshot:
    """一个用户的旧直控快照（原始 ``Direct`` 组）与它的留档结果。"""

    script_id: str
    script_name: str
    user_id: str
    user_name: str
    direct: dict[str, Any]
    archive_path: Path | None = None
    error: str = ""

    @property
    def label(self) -> str:
        return f"脚本「{self.script_name}」用户「{self.user_name}」"


@dataclass
class LegacyDirectReport:
    """一趟留档的结果，给启动通知与日志用。"""

    archived: list[LegacyDirectSnapshot] = field(default_factory=list)
    failed: list[LegacyDirectSnapshot] = field(default_factory=list)
    fallback_path: Path | None = None
    fallback_error: str = ""

    @property
    def needs_notice(self) -> bool:
        return bool(self.archived or self.failed)

    def notice(self) -> dict[str, Any]:
        lines: list[str] = []
        if self.archived:
            lines.append(
                "以下用户的旧直控快照已停用，原内容已另存（本机加密，仅作留档）："
            )
            lines.extend(f"{item.label}：{item.archive_path}" for item in self.archived)
        for item in self.failed:
            lines.append(f"{item.label}的旧直控快照另存失败：{item.error}")
        if self.failed:
            if self.fallback_path is not None:
                lines.append(f"已把整份脚本配置备份为 {self.fallback_path}")
            else:
                lines.append(
                    f"整份脚本配置也没能备份（{self.fallback_error}），"
                    "这些快照可能已丢失"
                )
        lines.append(
            "直控现在直接运行 SRA / 三月七当前的配置，"
            "同一脚本下的多个直控用户会运行同一份配置"
        )
        lines.append("如需恢复原来的设置，请在 SRA / 三月七中重新设置一次")
        return {"level": "warning", "title": "HSR 直控快照已停用", "lines": lines}


def _display_name(payload: Any, fallback: str) -> str:
    info = payload.get("Info") if isinstance(payload, dict) else None
    name = str(info.get("Name") or "").strip() if isinstance(info, dict) else ""
    return name or fallback[:8]


def find_legacy_direct_snapshots(data: dict[str, Any]) -> list[LegacyDirectSnapshot]:
    """从整份 ``ScriptConfig.json`` 字典里找出 HSR 脚本下快照非空的用户。纯逻辑。"""

    instances = data.get("instances")
    if not isinstance(instances, list):
        return []
    found: list[LegacyDirectSnapshot] = []
    for instance in instances:
        if not isinstance(instance, dict) or instance.get("type") != HSR_SCRIPT_TYPE:
            continue
        script_id = str(instance.get("uid") or "")
        payload = data.get(script_id)
        if not script_id or not isinstance(payload, dict):
            continue
        sub_configs = payload.get("SubConfigsInfo")
        user_data = (
            sub_configs.get("UserData") if isinstance(sub_configs, dict) else None
        )
        if not isinstance(user_data, dict):
            continue
        for user_instance in user_data.get("instances") or []:
            if not isinstance(user_instance, dict):
                continue
            user_id = str(user_instance.get("uid") or "")
            user = user_data.get(user_id)
            direct = user.get(LEGACY_GROUP) if isinstance(user, dict) else None
            if not isinstance(direct, dict):
                continue
            if not any(
                isinstance(direct.get(key), str) and direct[key].strip()
                for key in _SNAPSHOT_KEYS
            ):
                continue
            found.append(
                LegacyDirectSnapshot(
                    script_id=script_id,
                    script_name=_display_name(payload, script_id),
                    user_id=user_id,
                    user_name=_display_name(user, user_id),
                    direct=direct,
                )
            )
    return found


def _existing_archive(item: LegacyDirectSnapshot) -> Path | None:
    """留档目录里 ``Direct`` 与这份快照完全相同的文件；没有返回 None。"""

    root = direct_snapshot_root(item.script_id)
    if not root.is_dir():
        return None
    for path in sorted(root.glob(f"{item.user_id}-*.json")):
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(saved, dict) and saved.get(LEGACY_GROUP) == item.direct:
            return path
    return None


def _write_archive(item: LegacyDirectSnapshot, moment: datetime) -> Path:
    """把一份快照原样写进留档目录，读回核对一致才算成功。"""

    root = direct_snapshot_root(item.script_id)
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{item.user_id}-{moment.strftime('%Y%m%d%H%M%S')}.json"
    payload = {
        "note": _ARCHIVE_NOTE,
        "script_id": item.script_id,
        "script_name": item.script_name,
        "user_id": item.user_id,
        "user_name": item.user_name,
        "archived_at": moment.isoformat(timespec="seconds"),
        LEGACY_GROUP: item.direct,
    }
    tmp = target.with_name(f"{target.name}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, target)
    saved = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(saved, dict) or saved.get(LEGACY_GROUP) != item.direct:
        raise OSError(f"留档读回与原快照不一致：{target}")
    return target


def _backup_whole_file(path: Path, moment: datetime) -> Path:
    """另存失败时的退路：整份 ``ScriptConfig.json`` 复制到同目录，只留最近几份。"""

    backup = path.with_name(
        f"{path.name}{FALLBACK_SUFFIX}{moment.strftime('%Y%m%d%H%M%S')}.bak"
    )
    shutil.copyfile(path, backup)
    stale = sorted(path.parent.glob(f"{path.name}{FALLBACK_SUFFIX}*.bak"))
    for old in stale[:-FALLBACK_KEEP]:
        try:
            old.unlink()
        except OSError:
            pass
    return backup


def archive_legacy_direct_snapshots(
    script_config_path: Path, *, now: datetime | None = None
) -> LegacyDirectReport:
    """启动期入口：读原始 JSON、逐个另存快照、失败时整份备份。任何异常都不阻断启动。

    不改 ``ScriptConfig.json`` 本身：快照随后由 ``ScriptConfig.connect()`` 按新模型丢弃。
    """

    report = LegacyDirectReport()
    path = Path(script_config_path)
    if not path.is_file():
        return report
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text) if text.strip() else {}
    except (OSError, ValueError) as exc:
        logger.warning(f"跳过 HSR 旧直控快照留档：ScriptConfig.json 读取失败：{exc}")
        return report
    if not isinstance(data, dict):
        return report

    moment = now or datetime.now()
    for item in find_legacy_direct_snapshots(data):
        try:
            existing = _existing_archive(item)
            if existing is not None:
                logger.info(f"{item.label}的旧直控快照已有留档，跳过：{existing}")
                continue
            item.archive_path = _write_archive(item, moment)
        except Exception as exc:  # noqa: BLE001 - 留档失败不该挡住启动
            item.error = str(exc) or type(exc).__name__
            report.failed.append(item)
            logger.opt(exception=True).warning(
                f"{item.label}的旧直控快照另存失败：{item.error}"
            )
            continue
        report.archived.append(item)
        logger.info(f"{item.label}的旧直控快照已停用并另存：{item.archive_path}")

    if report.failed:
        try:
            report.fallback_path = _backup_whole_file(path, moment)
            logger.warning(f"已把整份脚本配置备份为 {report.fallback_path}")
        except Exception as exc:  # noqa: BLE001 - 同上
            report.fallback_error = str(exc) or type(exc).__name__
            logger.opt(exception=True).warning(
                f"整份脚本配置备份失败，旧直控快照可能丢失：{report.fallback_error}"
            )
    return report


__all__ = [
    "LegacyDirectReport",
    "LegacyDirectSnapshot",
    "archive_legacy_direct_snapshots",
    "direct_snapshot_root",
    "find_legacy_direct_snapshots",
]
