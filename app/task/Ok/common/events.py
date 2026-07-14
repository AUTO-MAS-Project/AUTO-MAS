#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright 2025-2026 AUTO-MAS Team
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
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""ok-script 与 MAS 间的结构化运行事件协议。

外部 ok-script 项目可在 `working/logs/mas-events.jsonl` 逐行写入 UTF-8 JSON。
协议仅作为比传统文本日志更可靠的运行结果通道；未输出该文件的旧版本继续使用
`ok-script.log` 判态。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


OK_SCRIPT_EVENT_PROTOCOL_VERSION = 1
OK_SCRIPT_PLUGIN_EVENT = "ok_script.event"
OK_SCRIPT_PLUGIN_EVENT_SOURCE = "core.ok_script"

_SUPPORTED_EVENT_NAMES = frozenset(
    {
        "run_started",
        "step",
        "task_failed",
        "task_completed",
        "run_failed",
        "run_completed",
        "summary",
    }
)


@dataclass(frozen=True)
class OkScriptRunFailure:
    """ok-script 汇总事件中的单项任务失败。"""

    task: str
    message: str


@dataclass(frozen=True)
class OkScriptRunEvent:
    """单行 JSONL 解析得到的 ok-script 运行事件。"""

    event: str
    message: str
    task: str
    success: bool | None
    failures: tuple[OkScriptRunFailure, ...]

    @property
    def is_terminal(self) -> bool:
        return self.event in {"run_failed", "run_completed"}


def _parse_failures(raw_failures: object) -> tuple[OkScriptRunFailure, ...]:
    if not isinstance(raw_failures, list):
        return ()

    failures: list[OkScriptRunFailure] = []
    for raw_failure in raw_failures:
        if not isinstance(raw_failure, dict):
            continue
        task = str(
            raw_failure.get("task") or raw_failure.get("name") or ""
        ).strip()
        message = str(
            raw_failure.get("message") or raw_failure.get("reason") or ""
        ).strip()
        if task or message:
            failures.append(
                OkScriptRunFailure(
                    task=task or "未命名任务",
                    message=message or "未提供失败原因",
                )
            )
    return tuple(failures)


def parse_ok_script_run_event(raw_line: str) -> OkScriptRunEvent | None:
    """解析单行结构化事件；无效或未知协议行返回 None。"""

    try:
        payload = json.loads(raw_line)
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, dict):
        return None
    if payload.get("version") != OK_SCRIPT_EVENT_PROTOCOL_VERSION:
        return None

    event = str(payload.get("event") or "").strip()
    if event not in _SUPPORTED_EVENT_NAMES:
        return None

    success = payload.get("success")
    if success is not None and not isinstance(success, bool):
        return None

    return OkScriptRunEvent(
        event=event,
        message=str(payload.get("message") or "").strip(),
        task=str(payload.get("task") or "").strip(),
        success=success,
        failures=_parse_failures(payload.get("failures")),
    )


def read_ok_script_run_events(
    event_log_path: Path,
    offset: int,
) -> tuple[list[OkScriptRunEvent], int]:
    """从 JSONL 文件读取新增的完整事件行，保留未写完的末行等待下次读取。"""

    try:
        with event_log_path.open("rb") as fp:
            file_size = event_log_path.stat().st_size
            start_offset = 0 if file_size < offset else offset
            fp.seek(start_offset)
            content = fp.read()
    except FileNotFoundError:
        return [], offset

    newline_index = content.rfind(b"\n")
    if newline_index < 0:
        completed_content = b""
        pending_content = content
        next_offset = start_offset
    else:
        completed_content = content[: newline_index + 1]
        pending_content = content[newline_index + 1 :]
        next_offset = start_offset + len(completed_content)

    events: list[OkScriptRunEvent] = []
    for raw_line in completed_content.decode("utf-8", errors="replace").splitlines():
        event = parse_ok_script_run_event(raw_line)
        if event is not None:
            events.append(event)

    if pending_content:
        pending_line = pending_content.decode("utf-8", errors="replace")
        pending_event = parse_ok_script_run_event(pending_line)
        if pending_event is not None:
            events.append(pending_event)
            next_offset = start_offset + len(content)

    return events, next_offset


def format_partial_success_status(
    failures: tuple[OkScriptRunFailure, ...],
) -> str:
    """将已完成但包含子任务失败的汇总转成 MAS 状态文本。"""

    lines = ["Success! 但部分任务失败："]
    lines.extend(f"  - {failure.task} : {failure.message}" for failure in failures)
    return "\n".join(lines)
