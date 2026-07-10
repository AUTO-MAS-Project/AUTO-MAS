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
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

from __future__ import annotations

import asyncio
import ctypes
import re
from contextlib import suppress
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import psutil

from app.core import Config
from app.services import Notify
from app.task.Ok.common.report import OkScriptReportHandler
from app.utils import get_logger

if TYPE_CHECKING:
    from app.task.Ok.runtime import OkScriptAutoProxyTask


logger = get_logger("OK-EF 日常汇报")

_OKEF_DAILY_SUMMARY_RE = re.compile(
    r"日常执行情况汇总已创建并打开:\s*(?P<path>[^\r\n]+?\.txt)"
)
_DAILY_SUMMARY_NOTEPAD_CLOSE_ATTEMPTS = 20
_DAILY_SUMMARY_NOTEPAD_CLOSE_INTERVAL = 0.25
_WM_CLOSE = 0x0010


@dataclass(frozen=True)
class OkefDailyFailure:
    task_name: str
    message: str


@dataclass(frozen=True)
class OkefDailySummary:
    path: Path
    status: str
    failures: tuple[OkefDailyFailure, ...]
    content: tuple[str, ...]

    def partial_status(self) -> str:
        lines = ["Success! 但部分任务失败:"]
        lines.extend(
            f"  - {failure.task_name} : {failure.message}"
            for failure in self.failures
        )
        return "\n".join(lines)


def _extract_daily_summary_path(log: str) -> Path | None:
    matches = list(_OKEF_DAILY_SUMMARY_RE.finditer(log))
    if not matches:
        return None
    return Path(matches[-1].group("path").strip())


def _parse_daily_summary_failures(lines: list[str]) -> tuple[OkefDailyFailure, ...]:
    failures: list[OkefDailyFailure] = []
    in_failure_messages = False

    for raw_line in lines:
        line = raw_line.strip()
        if line == "失败消息:":
            in_failure_messages = True
            continue
        if in_failure_messages and line.startswith("--- "):
            break
        if not in_failure_messages or not line.startswith("- "):
            continue

        payload = line[2:].strip()
        if not payload or payload == "无":
            continue
        if " : " in payload:
            task_name, message = payload.split(" : ", 1)
        elif ":" in payload:
            task_name, message = payload.split(":", 1)
        else:
            task_name, message = payload, "未提供失败原因"
        failures.append(
            OkefDailyFailure(
                task_name=task_name.strip(),
                message=message.strip() or "未提供失败原因",
            )
        )

    if failures:
        return tuple(failures)

    in_round = False
    capture_failed_list = False
    for raw_line in lines:
        line = raw_line.strip()
        if line.startswith("--- 第 "):
            in_round = True
            capture_failed_list = False
            continue
        if in_round and line == "失败任务:":
            capture_failed_list = True
            continue
        if not capture_failed_list:
            continue
        if not line:
            continue
        if line != "无":
            for task_name in line.split(","):
                task_name = task_name.strip()
                if task_name:
                    failures.append(
                        OkefDailyFailure(
                            task_name=task_name,
                            message="未提供失败原因",
                        )
                    )
        break

    return tuple(failures)


def _read_daily_summary(path: Path) -> OkefDailySummary | None:
    if not path.is_file():
        return None

    lines = path.read_text(encoding="utf-8-sig").splitlines()
    status = ""
    for line in lines:
        if line.startswith("执行状态:"):
            status = line.split(":", 1)[1].strip()
            break

    return OkefDailySummary(
        path=path,
        status=status,
        failures=_parse_daily_summary_failures(lines),
        content=tuple(lines),
    )


def _window_title_matches_daily_summary(title: str, path: Path) -> bool:
    title_text = title.casefold()
    return path.name.casefold() in title_text or str(path).casefold() in title_text


def _iter_window_titles() -> list[tuple[int, int, str]]:
    if not hasattr(ctypes, "windll"):
        return []

    user32 = ctypes.windll.user32
    titles: list[tuple[int, int, str]] = []

    def callback(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True

        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True

        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value.strip()
        if not title:
            return True

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        titles.append((int(hwnd), int(pid.value), title))
        return True

    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(
        callback
    )
    user32.EnumWindows(enum_proc, 0)
    return titles


def _close_daily_summary_windows(path: Path) -> tuple[int, set[int]]:
    closed_count = 0
    matched_pids: set[int] = set()
    if not hasattr(ctypes, "windll"):
        return closed_count, matched_pids

    user32 = ctypes.windll.user32
    for hwnd, pid, title in _iter_window_titles():
        if not _window_title_matches_daily_summary(title, path):
            continue

        matched_pids.add(pid)
        if user32.PostMessageW(hwnd, _WM_CLOSE, 0, 0):
            closed_count += 1

    return closed_count, matched_pids


def _cmdline_matches_daily_summary(cmdline: list[str], path: Path) -> bool:
    cmdline_text = " ".join(str(item) for item in cmdline).casefold()
    return path.name.casefold() in cmdline_text or str(path).casefold() in cmdline_text


def _close_daily_summary_notepad(path: Path) -> int:
    target_path = path.resolve()
    closed_count, matched_pids = _close_daily_summary_windows(target_path)

    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = str(proc.info.get("name") or "").casefold()
            if name != "notepad.exe":
                continue

            cmdline = proc.info.get("cmdline") or []
            if proc.pid not in matched_pids and not _cmdline_matches_daily_summary(
                cmdline,
                target_path,
            ):
                continue

            proc.terminate()
            try:
                proc.wait(timeout=0.3)
            except psutil.TimeoutExpired:
                proc.kill()
            closed_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    return closed_count


class OkefDailySummaryReportHandler(OkScriptReportHandler):
    """接管 OK-EF 完成后自动打开的日常汇报 TXT。"""

    def __init__(self) -> None:
        self.summary_path: Path | None = None
        self.summary: OkefDailySummary | None = None
        self.notepad_closed = False

    async def capture(
        self,
        runtime: "OkScriptAutoProxyTask",
        log: str,
    ) -> None:
        summary_path = _extract_daily_summary_path(log)
        if summary_path is None:
            return

        if self.summary_path != summary_path:
            self.summary_path = summary_path
            self.summary = None
            self.notepad_closed = False

        if not self.notepad_closed:
            closed_count = 0
            for _ in range(_DAILY_SUMMARY_NOTEPAD_CLOSE_ATTEMPTS):
                closed_count += await asyncio.to_thread(
                    _close_daily_summary_notepad,
                    summary_path,
                )
                if closed_count > 0:
                    break
                await asyncio.sleep(_DAILY_SUMMARY_NOTEPAD_CLOSE_INTERVAL)

            if closed_count > 0:
                logger.info(
                    f"已关闭 OK-EF 日常汇报记事本窗口: {summary_path} ({closed_count})"
                )
                self.notepad_closed = True
            else:
                logger.warning(f"未发现可关闭的 OK-EF 日常汇报窗口: {summary_path}")

        if self.summary is not None:
            return

        for _ in range(10):
            summary = await asyncio.to_thread(_read_daily_summary, summary_path)
            if summary is not None:
                self.summary = summary
                logger.info(f"已接管 OK-EF 日常汇报: {summary_path}")
                return
            await asyncio.sleep(0.2)

        logger.warning(f"未能读取 OK-EF 日常汇报: {summary_path}")

    async def apply(self, runtime: "OkScriptAutoProxyTask") -> None:
        if self.summary is None and runtime.cur_user_log is not None:
            await self.capture(runtime, "".join(runtime.cur_user_log.content))

        if (
            self.summary is None
            or not self.summary.failures
            or runtime.cur_user_log is None
        ):
            return

        status = self.summary.partial_status()
        runtime.cur_user_log.status = status
        runtime.script_info.log = status
        message = (
            f"用户 {runtime.cur_user_item.name} OK-EF 整轮完成，但存在子任务失败：\n"
            f"{status}"
        )

        with suppress(Exception):
            await Config.send_websocket_message(
                id=runtime.task_info.task_id,
                type="Info",
                data={"Warning": message},
            )

        with suppress(Exception):
            await Notify.push_plyer(
                "OK-EF 部分任务失败",
                message,
                f"{runtime.cur_user_item.name} OK-EF 部分任务失败",
                8,
            )
