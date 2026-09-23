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

"""运行收尾的视图巡检：写穿检测（§2.2 第 4 层）与原生日志轮转备份清理。

写穿：视图里 ≥ 64 KB 的出厂文件是载荷 / 共用库的硬链接，没有写时复制；有项目 agent
对它 ``open("w")`` 就等于改了所有同谱系视图与载荷。尺寸、排除表、「运行期新建即新
inode」挡住了已知项目的全部写入，这里是对未知项目的兜底：只 stat 视图里 nlink > 1 的
文件，修改时间晚于视图物化时刻的才算嫌疑（硬链接共享 inode 也共享 mtime），再拿单个
文件的 sha256 与载荷清单比对确认。确认写穿：告警、把共用库里那份隔离（改名
``.corrupt-*``，新项目不再沾它）、把路径记进谱系的 ``privatePaths``（下次物化按拷贝）、
把载荷标 ``damaged``。修改时间变了但内容没变的（解包时间戳、touch）不误报。
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from app.task.MaaFW.tools.core.automas_maafw_project_update import payloads
from app.task.MaaFW.tools.core.automas_maafw_project_update.blob_store import (
    RuntimeBlobStore,
    sha256_file,
)
from app.task.MaaFW.tools.embedded.embedded_project import (
    VIEW_MARKER_NAME,
    payloads_root,
    read_view_marker,
)
from app.utils import get_logger

logger = get_logger("MFW 写穿巡检")

NATIVE_LOG_BACKUP_GLOB = "maafw.bak.*.log"


@dataclass
class AuditReport:
    suspects: int = 0
    written_through: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)


def _materialized_at(marker: dict) -> float | None:
    text = str(marker.get("materializedAt") or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def audit_view(view: Path, base: Path | None = None) -> AuditReport:
    """巡检一个视图；只 stat，嫌疑文件才读。"""

    report = AuditReport()
    marker = read_view_marker(view)
    if marker is None:
        return report
    since = _materialized_at(marker)
    lineage = str(marker["lineage"])
    payload_id = str(marker["payload"])
    root = payloads_root(base)
    try:
        manifest = payloads.read_manifest(root, lineage, payload_id)
    except payloads.PayloadError:
        manifest = None
    if manifest is None or since is None:
        return report
    files = payloads.manifest_files(manifest)
    blob_store = RuntimeBlobStore.default(base)
    for current, _dirs, names in os.walk(view):
        current_path = Path(current)
        for name in names:
            path = current_path / name
            try:
                info = path.stat()
            except OSError:
                continue
            if info.st_nlink <= 1 or info.st_mtime <= since + 1:
                continue
            rel = path.relative_to(view).as_posix()
            if rel == VIEW_MARKER_NAME or rel not in files:
                continue
            report.suspects += 1
            expected = files[rel]["sha256"]
            try:
                actual = sha256_file(path)
            except OSError:
                continue
            if actual == expected:
                continue
            report.written_through.append(rel)
            _quarantine(blob_store, expected)
            try:
                payloads.add_private_path(root, lineage, rel)
                payloads.mark_damaged(root, lineage, payload_id)
            except payloads.PayloadError as exc:
                logger.warning(f"记录写穿失败：{rel} - {exc}")
            message = (
                f"检测到项目运行时改写了共用文件 {rel}（与同项目其它脚本共享同一份），"
                "已隔离共用库里的那份并记为私有文件；下次更新会整版重建"
            )
            logger.warning(f"[{view.name}] {message}")
            report.messages.append(message)
    return report


def _quarantine(blob_store: RuntimeBlobStore, digest: str) -> None:
    blob = blob_store.blob_path(digest)
    if not blob.is_file():
        return
    try:
        blob.rename(blob.with_name(f"{blob.name}.corrupt-{uuid.uuid4().hex[:8]}"))
    except OSError as exc:
        logger.warning(f"隔离被写穿的共用文件失败：{blob} - {exc}")


def clean_native_log_backups(view: Path, before: float) -> int:
    """删 ``debug/maafw.bak.*.log`` 里修改时间早于本轮开始的（history 里已有原样副本）。

    MaaFramework 自己从不回收轮转备份，``HistoryRetentionTime`` 默认 0 = 永久，靠它永远清不掉。
    本轮新轮转出来的留着：它们这一轮的片段刚抄进 history，稳妥起见留到下一轮再删。
    """

    debug = Path(view) / "debug"
    if not debug.is_dir():
        return 0
    removed = 0
    for path in debug.glob(NATIVE_LOG_BACKUP_GLOB):
        try:
            if path.is_file() and path.stat().st_mtime < before:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed


__all__ = ["AuditReport", "audit_view", "clean_native_log_backups"]
