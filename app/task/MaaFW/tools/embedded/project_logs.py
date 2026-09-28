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

"""项目自己写进视图的日志：按上限取结尾、按密码打码后另存一份（给问题包用）。

MAS 每次运行另存进 ``history/`` 的只有两份：``.worker.log``（runner 事件、worker 与 agent 的
stdout / stderr）和 ``.maafw.log``（``debug/maafw.log`` 本次运行的部分）。项目 agent 自己写
文件的日志只在视图里：M9A 的 ``debug/custom/*.log``（DEBUG 级，控制台只出 INFO）与
``debug/agent-bootstrap.log``，MaaEnd go-service 的 ``debug/go-service.log``（控制台只出
Error）与 ``debug/go-service.stderr.log``（stderr 被重定向到这里，panic 只在这份里），MaaFgo
的 ``bbcdll/bbc_server.log`` 等。视图里的 ``.log`` 一定是运行期写出来的（投影在任何深度都剔
``.log``，载荷里没有），切换版本时按私有文件原样带过去。

这里只收 ``.log``：单个文件取结尾 :data:`PROJECT_LOG_TAIL_BYTES`，总量
:data:`PROJECT_LOG_TOTAL_BYTES`，``debug/`` 下的优先、同组里新写的优先；``debug/`` 顶层的
``maafw.log`` / ``maafw.bak.*.log`` 不收（history 里的 ``.maafw.log`` 就是它按次切好、打过码
的副本）。打码与 ``.maafw.log`` 同一口径：按字节把密码的各种写法（``secret_log_variants``）
换成「<已隐藏>」。截断处从下一行开始，不留半行（半行里可能是半个密码）。
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.utils import get_logger

from .option_secrets import REDACTED_SECRET_TEXT

logger = get_logger("MFW 项目日志")

PROJECT_LOG_TAIL_BYTES = 2 * 1024 * 1024
PROJECT_LOG_TOTAL_BYTES = 20 * 1024 * 1024
_LOG_SUFFIX = ".log"
# debug/ 顶层的原生日志：history 里的 .maafw.log 是它的按次副本（已打码），不重复收。
_NATIVE_LOG_RE = re.compile(r"^maafw(?:\.bak\..+)?\.log$", re.IGNORECASE)
# 不是项目日志的目录：字节码缓存、MAS 更新器保留目录、切换半成品。
_SKIP_DIR_NAMES = frozenset(
    {"__pycache__", ".pycache", ".mas-update", ".mas-update-cache", ".staging"}
)


@dataclass
class ProjectLogEntry:
    rel: str
    size: int
    written: int
    truncated: bool


@dataclass
class ProjectLogsReport:
    collected: list[ProjectLogEntry] = field(default_factory=list)
    # 超出总量没收的（项目相对路径）。
    skipped: list[str] = field(default_factory=list)
    written_bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "collected": [
                {
                    "path": entry.rel,
                    "size": entry.size,
                    "written": entry.written,
                    "truncated": entry.truncated,
                }
                for entry in self.collected
            ],
            "skipped": list(self.skipped),
            "writtenBytes": self.written_bytes,
        }


def list_project_logs(view: Path) -> list[tuple[str, Path]]:
    """视图里项目自己写的 ``.log``（项目相对 posix 路径, 绝对路径），按收集优先级排好。"""

    view = Path(view)
    found: list[tuple[bool, float, str, Path]] = []

    def _error(exc: OSError) -> None:
        logger.debug(f"读取视图目录失败，跳过: {exc.filename}: {exc}")

    for current, dir_names, file_names in os.walk(view, onerror=_error):
        dir_names[:] = sorted(
            name for name in dir_names if name.casefold() not in _SKIP_DIR_NAMES
        )
        base = Path(current)
        rel_dir = os.path.relpath(current, view).replace(os.sep, "/")
        prefix = "" if rel_dir == "." else f"{rel_dir}/"
        for name in file_names:
            if not name.casefold().endswith(_LOG_SUFFIX):
                continue
            rel = f"{prefix}{name}"
            in_debug = rel.casefold().startswith("debug/")
            if rel_dir.casefold() == "debug" and _NATIVE_LOG_RE.match(name):
                continue
            path = base / name
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            found.append((not in_debug, -mtime, rel, path))
    found.sort()
    return [(rel, path) for _, _, rel, path in found]


def _read_tail(path: Path, limit: int) -> tuple[bytes, int, bool]:
    """``(内容, 文件大小, 是否截断)``：超过 ``limit`` 只取结尾，并从截断处的下一行开始
    （结尾里没有完整的一行时返回空）。"""

    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        if size <= limit:
            handle.seek(0)
            return handle.read(size), size, False
        handle.seek(size - limit)
        data = handle.read(limit)
    newline = data.find(b"\n")
    return (data[newline + 1 :] if newline != -1 else b""), size, True


def _redact(data: bytes, secrets: Sequence[str]) -> bytes:
    placeholder = REDACTED_SECRET_TEXT.encode("utf-8")
    for secret in secrets:
        raw = secret.encode("utf-8")
        if raw and raw in data:
            data = data.replace(raw, placeholder)
    return data


def collect_project_logs(
    view: Path,
    destination: Path,
    *,
    secrets: Sequence[str] = (),
    tail_bytes: int = PROJECT_LOG_TAIL_BYTES,
    total_bytes: int = PROJECT_LOG_TOTAL_BYTES,
) -> ProjectLogsReport:
    """把视图里项目自己写的 ``.log`` 按上限取结尾、打码，照原相对路径写进 ``destination``。

    ``secrets`` 是 ``secret_log_variants`` 给出的密码写法（长的在前）。视图一个字节不动。
    读不了的文件跳过（正被独占写的、刚被轮转掉的）。
    """

    destination = Path(destination)
    report = ProjectLogsReport()
    remaining = max(0, int(total_bytes))
    for rel, path in list_project_logs(view):
        if remaining <= 0:
            report.skipped.append(rel)
            continue
        try:
            data, size, truncated = _read_tail(path, min(tail_bytes, remaining))
        except OSError as exc:
            logger.debug(f"读取项目日志失败，跳过: {rel}: {exc}")
            continue
        if truncated and not data:
            # 取到的结尾里没有一整行（剩下的总量不够，或最后一行本身就超过单文件上限）：
            # 不写半行（半行里可能是半个密码），按没收记下。
            report.skipped.append(rel)
            continue
        data = _redact(data, secrets)
        target = destination / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        remaining -= len(data)
        report.written_bytes += len(data)
        report.collected.append(
            ProjectLogEntry(rel=rel, size=size, written=len(data), truncated=truncated)
        )
    if report.skipped:
        logger.info(
            f"项目日志已收 {len(report.collected)} 个、{report.written_bytes} 字节，"
            f"另有 {len(report.skipped)} 个超出上限没收: {', '.join(report.skipped[:5])}"
        )
    return report


def export_script_project_logs(
    script_id: str, script_config: Any, destination: Path
) -> ProjectLogsReport:
    """按脚本收它视图里的项目日志：密码取该脚本全部用户任务配置里 password 字段的值
    （解不开的跳过），与 ``.worker.log`` / ``.maafw.log`` 同一套打码。视图不在就什么都不收。"""

    from app.task.MaaFW.tools.core.interface.loader import load_interface_model_cached

    from .embedded_project import resolve_maafw_project_root
    from .option_secrets import collect_script_password_values, secret_log_variants

    view = Path(resolve_maafw_project_root(script_id, script_config))
    if not view.is_dir():
        return ProjectLogsReport()
    interface = None
    try:
        interface = load_interface_model_cached(view)
    except Exception as exc:  # noqa: BLE001 - 读不出 interface 时只按密文认密码
        logger.debug(f"收集项目日志时读取 interface 失败，只按已加密的值打码: {exc}")
    secrets = secret_log_variants(
        collect_script_password_values(script_config, interface)
    )
    return collect_project_logs(view, destination, secrets=secrets)


__all__ = [
    "PROJECT_LOG_TAIL_BYTES",
    "PROJECT_LOG_TOTAL_BYTES",
    "ProjectLogEntry",
    "ProjectLogsReport",
    "collect_project_logs",
    "export_script_project_logs",
    "list_project_logs",
]
