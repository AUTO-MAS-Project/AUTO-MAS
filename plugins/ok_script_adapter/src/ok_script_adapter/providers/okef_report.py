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
import tempfile
import time
from contextlib import suppress
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from app.core import Config
from app.services import Notify
from ..common.report import OkScriptReportHandler
from app.utils import get_logger

if TYPE_CHECKING:
    from ..adapter.autoproxy import OkScriptAutoProxyTask


logger = get_logger("OK-EF 日常汇报")

_OKEF_DAILY_SUMMARY_RE = re.compile(
    r"日常执行情况汇总已创建(?P<open_state>并打开|（未打开）):"
    r"\s*(?P<path>[^\r\n]+?\.txt)"
)
_DAILY_SUMMARY_NOTEPAD_CLOSE_ATTEMPTS = 20
_DAILY_SUMMARY_NOTEPAD_CLOSE_INTERVAL = 0.25
_DAILY_SUMMARY_WATCH_INTERVAL = 0.2
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


def _extract_daily_summary_reference(log: str) -> tuple[Path, bool] | None:
    matches = list(_OKEF_DAILY_SUMMARY_RE.finditer(log))
    if not matches:
        return None
    match = matches[-1]
    return (
        Path(match.group("path").strip()),
        match.group("open_state") == "并打开",
    )


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


def _close_daily_summary_windows(path: Path) -> int:
    closed_count = 0
    if not hasattr(ctypes, "windll"):
        return closed_count

    user32 = ctypes.windll.user32
    for hwnd, _pid, title in _iter_window_titles():
        if not _window_title_matches_daily_summary(title, path):
            continue

        if user32.PostMessageW(hwnd, _WM_CLOSE, 0, 0):
            closed_count += 1

    return closed_count


def _close_daily_summary_notepad(path: Path) -> int:
    """关闭标题精确匹配日报 TXT 的窗口，不终止共享记事本进程。"""

    return _close_daily_summary_windows(path.resolve())


def _recent_daily_summary_paths(run_started_at: float) -> tuple[Path, ...]:
    """返回本轮运行后写入的 OK-EF 日报，避免碰触历史 TXT。"""

    summary_dir = Path(tempfile.gettempdir()) / "日常执行情况" / "ok-ef"
    candidates: list[tuple[float, Path]] = []
    try:
        for path in summary_dir.glob("*.txt"):
            if not path.is_file():
                continue
            modified_at = path.stat().st_mtime
            if modified_at >= run_started_at:
                candidates.append((modified_at, path))
    except OSError:
        return ()

    return tuple(path for _, path in sorted(candidates))


class OkefDailySummaryReportHandler(OkScriptReportHandler):
    """接管 OK-EF 完成后自动打开的日常汇报 TXT。"""

    def __init__(self) -> None:
        self.summary_path: Path | None = None
        self.summary: OkefDailySummary | None = None
        self.notepad_closed = False
        self.run_started_at = 0.0
        self.window_watch_task: asyncio.Task[None] | None = None

    async def start(self, runtime: "OkScriptAutoProxyTask") -> None:
        self.run_started_at = time.time()
        if self.window_watch_task is None or self.window_watch_task.done():
            self.window_watch_task = asyncio.create_task(
                self._watch_daily_summary_windows(runtime)
            )

    async def stop(self, runtime: "OkScriptAutoProxyTask") -> None:
        if self.window_watch_task is None:
            return
        if not self.window_watch_task.done():
            self.window_watch_task.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await self.window_watch_task
        self.window_watch_task = None

    async def _watch_daily_summary_windows(
        self,
        runtime: "OkScriptAutoProxyTask",
    ) -> None:
        """在日志到达前也按当前运行生成的 TXT 关闭旧版弹窗。"""

        try:
            while True:
                paths = await asyncio.to_thread(
                    _recent_daily_summary_paths,
                    self.run_started_at,
                )
                for summary_path in paths:
                    await self._capture_summary(
                        summary_path,
                        was_opened=True,
                        retry_notepad_close=False,
                    )
                await asyncio.sleep(_DAILY_SUMMARY_WATCH_INTERVAL)
        except asyncio.CancelledError:
            raise

    async def _capture_summary(
        self,
        summary_path: Path,
        *,
        was_opened: bool,
        retry_notepad_close: bool,
    ) -> None:
        if self.summary_path != summary_path:
            self.summary_path = summary_path
            self.summary = None
            self.notepad_closed = not was_opened

        if was_opened and not self.notepad_closed:
            attempts = (
                _DAILY_SUMMARY_NOTEPAD_CLOSE_ATTEMPTS
                if retry_notepad_close
                else 1
            )
            for _ in range(attempts):
                closed_count = await asyncio.to_thread(
                    _close_daily_summary_notepad,
                    summary_path,
                )
                if closed_count > 0:
                    logger.info(
                        f"已关闭 OK-EF 日常汇报记事本窗口: {summary_path} ({closed_count})"
                    )
                    self.notepad_closed = True
                    break
                if retry_notepad_close:
                    await asyncio.sleep(_DAILY_SUMMARY_NOTEPAD_CLOSE_INTERVAL)

        if self.summary is not None:
            return

        read_attempts = 10 if retry_notepad_close else 1
        for _ in range(read_attempts):
            summary = await asyncio.to_thread(_read_daily_summary, summary_path)
            if summary is not None:
                self.summary = summary
                logger.info(f"已接管 OK-EF 日常汇报: {summary_path}")
                return
            if retry_notepad_close:
                await asyncio.sleep(0.2)

    async def capture(
        self,
        runtime: "OkScriptAutoProxyTask",
        log: str,
    ) -> None:
        summary_reference = _extract_daily_summary_reference(log)
        if summary_reference is None:
            return
        summary_path, was_opened = summary_reference

        if not was_opened:
            self.notepad_closed = True
        await self._capture_summary(
            summary_path,
            was_opened=was_opened,
            retry_notepad_close=was_opened,
        )

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
