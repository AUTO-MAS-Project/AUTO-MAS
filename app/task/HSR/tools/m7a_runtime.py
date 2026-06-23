#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
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


import asyncio
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from inspect import isawaitable
from pathlib import Path
from typing import Awaitable, Callable

from app.utils import ProcessManager, decode_bytes, get_logger

from .log_detect import (
    M7A_COMPLETION_MARKERS,
    can_read_stream_live,
    emit_process_output,
    has_failure_output,
)


logger = get_logger("HSR M7A 运行器")


@dataclass
class M7ACommandResult:
    task_name: str
    exe_path: str
    success: bool = False
    output: str = ""
    error: str = ""
    returncode: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None


class M7ARunner:
    """March7th Assistant 命令执行器。"""

    def __init__(
        self,
        m7a_dir: Path,
        log_callback: Callable[[str], None] | None = None,
        output_line_callback: Callable[[str], Awaitable[None] | None] | None = None,
        completion_grace_timeout: float = 5.0,
    ):
        self._m7a_dir = Path(m7a_dir)
        self._m7a_exe = self._m7a_dir / "March7th Assistant.exe"
        self._commands: list[str] = []
        self._process_manager = ProcessManager()
        self._log_callback = log_callback
        self._output_line_callback = output_line_callback
        self._completion_grace_timeout = completion_grace_timeout

    @property
    def exe_path(self) -> Path:
        return self._m7a_exe

    @property
    def root_path(self) -> Path:
        return self._m7a_dir

    @property
    def command_log(self) -> list[str]:
        return list(self._commands)

    async def terminate_current_process(self) -> bool:
        """终止当前 M7A 子进程。"""

        if not await self._process_manager.is_running():
            return False

        logger.warning("正在终止 M7A 当前子进程")
        await self._process_manager.kill()
        return True

    def _emit_process_output(self, title: str, text: str) -> None:
        emit_process_output(self._log_callback, title, text)

    async def _read_stream_live(
        self,
        stream,
        title: str,
        lines: list[str],
        completion_event: asyncio.Event | None = None,
    ) -> None:
        """逐行读取子进程输出并立即转发到日志。"""

        while True:
            raw = await stream.readline()
            if not raw:
                break
            if isinstance(raw, str):
                text = raw
            else:
                text = decode_bytes(bytes(raw))
            for line in text.rstrip("\r\n").splitlines():
                line = line.strip()
                if not line:
                    continue
                lines.append(line)
                self._emit_process_output(title, line)
                if self._output_line_callback is not None:
                    result = self._output_line_callback(line)
                    if isawaitable(result):
                        await result
                if completion_event is not None and self._is_completion_line(line):
                    completion_event.set()

    @staticmethod
    def _is_completion_line(line: str) -> bool:
        return any(marker in line for marker in M7A_COMPLETION_MARKERS)

    @classmethod
    def _has_completion_marker(cls, text: str) -> bool:
        return any(cls._is_completion_line(line) for line in text.splitlines())

    async def _send_enter_to_process(self, proc: asyncio.subprocess.Process) -> bool:
        """向已完成但等待交互关闭的 M7A 进程发送回车。"""

        stdin = getattr(proc, "stdin", None)
        if stdin is None:
            return False

        try:
            stdin.write(b"\n")
            await stdin.drain()
        except (BrokenPipeError, ConnectionResetError, RuntimeError, OSError) as e:
            logger.debug(f"M7A 子进程 stdin 已不可写，跳过发送回车：{e}")
            return False
        return True

    async def _communicate_with_live_output(
        self,
        proc: asyncio.subprocess.Process,
        timeout: int,
    ) -> tuple[str, str, bool]:
        """读取 M7A 输出并检测完成/失败标记。"""

        stdout_stream = getattr(proc, "stdout", None)
        stderr_stream = getattr(proc, "stderr", None)
        if not (
            can_read_stream_live(stdout_stream)
            or can_read_stream_live(stderr_stream)
        ):
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            stdout = decode_bytes(stdout_bytes).strip()
            stderr = decode_bytes(stderr_bytes).strip()
            self._emit_process_output("M7A", stdout)
            self._emit_process_output("M7A stderr", stderr)
            if self._output_line_callback is not None:
                for text in (stdout, stderr):
                    for line in text.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        result = self._output_line_callback(line)
                        if isawaitable(result):
                            await result
            completed = (
                self._has_completion_marker(stdout)
                or self._has_completion_marker(stderr)
            )
            return stdout, stderr, completed

        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        read_tasks: list[asyncio.Task] = []
        completion_event = asyncio.Event()
        if can_read_stream_live(stdout_stream):
            read_tasks.append(
                asyncio.create_task(
                    self._read_stream_live(
                        stdout_stream,
                        "M7A",
                        stdout_lines,
                        completion_event,
                    )
                )
            )
        if can_read_stream_live(stderr_stream):
            read_tasks.append(
                asyncio.create_task(
                    self._read_stream_live(
                        stderr_stream,
                        "M7A stderr",
                        stderr_lines,
                        completion_event,
                    )
                )
            )

        wait_group = asyncio.gather(proc.wait(), *read_tasks)
        completion_wait = asyncio.create_task(completion_event.wait())
        completed_by_marker = False
        wait_group_cancelled = False
        try:
            done, _ = await asyncio.wait(
                {wait_group, completion_wait},
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if not done:
                raise asyncio.TimeoutError

            completed_by_marker = completion_event.is_set()
            if completed_by_marker and not wait_group.done():
                if await self._send_enter_to_process(proc):
                    logger.info("M7A 已输出停止运行标记，已发送回车并等待进程自然退出")
                else:
                    logger.info("M7A 已输出停止运行标记，等待进程自然退出")
                try:
                    await asyncio.wait_for(
                        asyncio.shield(wait_group),
                        timeout=self._completion_grace_timeout,
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "M7A 命令已完成但进程未退出，终止子进程以继续后续任务"
                    )
                    await self.terminate_current_process()
                    try:
                        await asyncio.wait_for(wait_group, timeout=2.0)
                    except asyncio.TimeoutError:
                        wait_group.cancel()
                        wait_group_cancelled = True
                        with suppress(BaseException):
                            await asyncio.gather(wait_group, return_exceptions=True)

            if wait_group.done() and not wait_group_cancelled:
                await wait_group
        except Exception:
            wait_group.cancel()
            completion_wait.cancel()
            for task in read_tasks:
                task.cancel()
            with suppress(BaseException):
                await asyncio.gather(
                    wait_group,
                    completion_wait,
                    return_exceptions=True,
                )
            raise
        finally:
            completion_wait.cancel()
            with suppress(BaseException):
                await asyncio.gather(
                    completion_wait,
                    return_exceptions=True,
                )

        return (
            "\n".join(stdout_lines).strip(),
            "\n".join(stderr_lines).strip(),
            completed_by_marker,
        )

    async def run_task(self, task_name: str, timeout: int = 600) -> M7ACommandResult:
        """执行一条 M7A 命令。"""

        started_at = datetime.now(timezone.utc)
        self._commands.append(task_name)

        if not self._m7a_exe.exists():
            msg = f"March7th Assistant.exe does not exist: {self._m7a_exe}"
            logger.error(msg)
            return M7ACommandResult(
                task_name=task_name,
                exe_path=str(self._m7a_exe),
                success=False,
                error=msg,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
            )

        try:
            await self._process_manager.open_process(
                str(self._m7a_exe),
                task_name,
                cwd=self._m7a_dir,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            proc = self._process_manager.main_process
            if not isinstance(proc, asyncio.subprocess.Process):
                raise RuntimeError("M7A 子进程启动后未能被 ProcessManager 跟踪")
            stdout, stderr, completed_by_marker = (
                await self._communicate_with_live_output(proc, timeout)
            )
            success = (
                (completed_by_marker or proc.returncode == 0)
                and not has_failure_output(stdout, stderr)
            )

            logger.info(
                f"M7A {task_name} → {'success' if success else 'failed'}"
                f" (rc={proc.returncode})"
            )
            return M7ACommandResult(
                task_name=task_name,
                exe_path=str(self._m7a_exe),
                success=success,
                output=stdout,
                error=stderr,
                returncode=proc.returncode or 0,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
            )

        except asyncio.TimeoutError:
            logger.error(f"M7A {task_name} timed out after {timeout}s")
            await self.terminate_current_process()
            return M7ACommandResult(
                task_name=task_name,
                exe_path=str(self._m7a_exe),
                success=False,
                error=f"command timed out after {timeout}s",
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
            )

        except asyncio.CancelledError:
            logger.warning(f"M7A {task_name} 收到取消请求，准备终止子进程")
            await self.terminate_current_process()
            raise

        except Exception as e:
            logger.exception(f"M7A {task_name} error: {e}")
            return M7ACommandResult(
                task_name=task_name,
                exe_path=str(self._m7a_exe),
                success=False,
                error=str(e),
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
            )
        finally:
            await self._process_manager.clear()
