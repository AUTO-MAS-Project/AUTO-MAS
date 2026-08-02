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
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""MAS 生产路径唯一的 ok-script 进程与结果控制器。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from app.services import System
from app.utils import decode_bytes, get_logger
from app.utils.LogMonitor import LogMonitor
from app.utils.ProcessManager import ProcessInfo, ProcessManager

from ..common.events import (
    OkScriptRunEvent,
    OkScriptRunFailure,
    append_ok_script_run_event,
    read_ok_script_run_events,
)
from ..shell.descriptor import PROTOCOL_LEGACY_EXE
from .execution import (
    ExecutionPlan,
    ResultObserver,
    RunObservation,
)


logger = get_logger("ok-script 运行控制")


class _ProcessManager(Protocol):
    process: Any

    async def open_process(
        self,
        program: Path | str,
        *args: str,
        **kwargs: object,
    ) -> None: ...

    async def is_running(self) -> bool: ...

    async def kill(self) -> None: ...


class _LogMonitor(Protocol):
    async def start_monitor_file(
        self,
        log_file_path: Path,
        start_time: datetime,
        bak_log_path: Path | None = None,
    ) -> None: ...

    async def stop(self) -> None: ...


@dataclass(frozen=True, slots=True)
class AttemptPreparation:
    """delegate 完成一次运行前置工作后的结果。"""

    started_at: datetime
    failure_status: str = ""


@dataclass(frozen=True, slots=True)
class RunControllerUpdate:
    """控制器向 MAS 适配边界发送的一项统一进度更新。"""

    kind: str
    message: str = ""
    source: str = ""
    lines: tuple[str, ...] = ()
    event: OkScriptRunEvent | None = None
    observation: RunObservation | None = None
    failures: tuple[OkScriptRunFailure, ...] = ()


@dataclass(frozen=True, slots=True)
class RunControllerResult:
    """执行计划完成后的整轮结果。"""

    observation: RunObservation
    attempts: int

    @property
    def successful(self) -> bool:
        return self.observation.successful


class RunControllerDelegate(Protocol):
    """RunController 与 AutoProxy 业务状态之间的窄边界。"""

    async def prepare_attempt(
        self,
        attempt: int,
        total_attempts: int,
    ) -> AttemptPreparation: ...

    async def complete_attempt(self, result: RunControllerResult) -> None: ...

    async def fail_attempt(
        self,
        result: RunControllerResult,
        *,
        will_retry: bool,
    ) -> None: ...

    async def cancel_run(self) -> None: ...

    def should_kill_game(self) -> bool: ...

    async def kill_game(self) -> None: ...

    async def on_run_update(self, update: RunControllerUpdate) -> None: ...


class RunController:
    """执行不可变计划，并统一进程、observer、取消和整轮重试。"""

    def __init__(
        self,
        plan: ExecutionPlan,
        *,
        process_manager_factory: Callable[[], _ProcessManager] = ProcessManager,
        log_monitor_factory: Callable[..., _LogMonitor] = LogMonitor,
        event_reader: Callable[
            [Path, int], tuple[list[OkScriptRunEvent], int]
        ] = read_ok_script_run_events,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        kill_process: Callable[[Path], Awaitable[None]] = System.kill_process,
        process_poll_interval_seconds: float = 1.0,
        event_poll_interval_seconds: float = 1.0,
        exit_event_grace_seconds: float = 1.0,
        exit_check_timeout_seconds: float = 2.0,
        exit_kill_timeout_seconds: float = 5.0,
    ) -> None:
        self.plan = plan
        self.process_manager = process_manager_factory()
        self.log_monitor_factory = log_monitor_factory
        self.event_reader = event_reader
        self.sleep = sleep
        self.kill_process = kill_process
        self.process_poll_interval_seconds = process_poll_interval_seconds
        self.event_poll_interval_seconds = event_poll_interval_seconds
        self.exit_event_grace_seconds = exit_event_grace_seconds
        self.exit_check_timeout_seconds = exit_check_timeout_seconds
        self.exit_kill_timeout_seconds = exit_kill_timeout_seconds

        self.observer: ResultObserver | None = None
        self.wait_event = asyncio.Event()
        self.log_monitor: _LogMonitor | None = None
        self.event_monitor_task: asyncio.Task[None] | None = None
        self.stream_reader_tasks: list[asyncio.Task[None]] = []
        self.event_log_offset = 0
        self.decision: RunObservation | None = None
        self.running = False

    async def run(self, delegate: RunControllerDelegate) -> RunControllerResult:
        """按 whole-run 策略执行并重试一份计划。"""

        if self.running:
            raise RuntimeError("ok-script 执行计划已在运行")
        self.running = True
        last_result: RunControllerResult | None = None
        try:
            for attempt in range(1, self.plan.attempt_limit + 1):
                self._reset_attempt()
                preparation = await delegate.prepare_attempt(
                    attempt,
                    self.plan.attempt_limit,
                )
                if preparation.failure_status:
                    observation = self._require_observer().set_failure(
                        preparation.failure_status,
                        source="prepare",
                    )
                    await self._publish_observation(delegate, observation)
                else:
                    observation = await self._run_process_attempt(
                        delegate,
                        preparation.started_at,
                    )

                result = RunControllerResult(
                    observation=observation,
                    attempts=attempt,
                )
                last_result = result
                if result.successful:
                    try:
                        await self._wait_script_exit(delegate)
                    finally:
                        await self._stop_process_stream_readers()
                    await delegate.complete_attempt(result)
                    return result

                await self._kill_script_process()
                if delegate.should_kill_game():
                    await delegate.kill_game()
                will_retry = attempt < self.plan.attempt_limit
                await delegate.fail_attempt(result, will_retry=will_retry)
                if will_retry:
                    await self._send_update(
                        delegate,
                        RunControllerUpdate(
                            kind="dispatch",
                            message=(
                                f"将在 {self.plan.retry_delay_seconds:g} 秒后开始"
                                f"第 {attempt + 1}/{self.plan.attempt_limit} 次重试"
                            ),
                        ),
                    )
                    await self.sleep(self.plan.retry_delay_seconds)

            if last_result is None:
                raise RuntimeError("ok-script 执行计划没有产生任何尝试")
            return last_result
        except asyncio.CancelledError:
            await asyncio.shield(self._cancel(delegate))
            raise
        finally:
            self.running = False

    async def close(self) -> None:
        """幂等停止观察任务并终止脚本进程。"""

        await self._stop_log_monitor()
        await self._stop_event_monitor()
        await self._kill_script_process()

    def _reset_attempt(self) -> None:
        self.observer = ResultObserver(self.plan.observation)
        self.wait_event = asyncio.Event()
        self.log_monitor = None
        self.event_monitor_task = None
        self.stream_reader_tasks = []
        self.decision = None
        try:
            self.event_log_offset = self.plan.event_path.stat().st_size
        except FileNotFoundError:
            self.event_log_offset = 0

    async def _run_process_attempt(
        self,
        delegate: RunControllerDelegate,
        started_at: datetime,
    ) -> RunObservation:
        await self._kill_script_process()
        invocation = self.plan.invocation
        await self._send_update(
            delegate,
            RunControllerUpdate(
                kind="dispatch",
                message=(
                    f"启动 {self.plan.observation.display_name}："
                    f"{' '.join(invocation.command[1:])}"
                ),
            ),
        )

        target_process = None
        if invocation.target_process is not None:
            target_process = ProcessInfo(
                name=invocation.target_process.name or None,
                exe=invocation.target_process.executable or None,
            )
        try:
            await self.process_manager.open_process(
                invocation.command[0],
                *invocation.command[1:],
                cwd=invocation.cwd,
                env=invocation.environment_dict(),
                target_process=target_process,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._start_process_stream_readers(delegate)
        except Exception as exc:
            logger.exception(
                f"启动 {self.plan.observation.display_name} 失败: {exc}"
            )
            observation = self._require_observer().set_failure(
                f"{self.plan.observation.display_name} 启动失败: {exc}",
                source="process-start",
            )
            await self._publish_observation(delegate, observation)
            with suppress(Exception):
                await self._kill_script_process()
            return observation

        try:
            await self._start_event_monitor(delegate)
            try:
                await asyncio.to_thread(
                    append_ok_script_run_event,
                    self.plan.event_path,
                    "run_started",
                    task=str(invocation.task_index),
                    message="MAS 已启动项目进程，正在等待日志判态",
                    protocol=invocation.protocol,
                    command=list(invocation.command),
                )
            except OSError as exc:
                logger.warning(f"写入 ok-script 启动事件失败，继续文本判态: {exc}")
                await self._send_update(
                    delegate,
                    RunControllerUpdate(
                        kind="dispatch",
                        message=f"结构化启动事件写入失败，已回退文本日志：{exc}",
                    ),
                )

            loop = asyncio.get_running_loop()
            log_deadline = loop.time() + self.plan.log_start_timeout_seconds
            while (
                not self.plan.log_path.exists()
                and not self.wait_event.is_set()
                and loop.time() < log_deadline
            ):
                if not await self.process_manager.is_running():
                    return await self._resolve_process_exit(
                        delegate,
                        missing_log=True,
                    )
                await self.sleep(self.process_poll_interval_seconds)

            if self.wait_event.is_set():
                return self._require_decision()

            if self.plan.log_path.exists():
                await self._send_update(
                    delegate,
                    RunControllerUpdate(
                        kind="dispatch",
                        message=f"已开始监察文本日志：{self.plan.log_path}",
                    ),
                )
                self.log_monitor = self.log_monitor_factory(
                    self.plan.observation.log_time_range,
                    self.plan.observation.log_time_format,
                    lambda lines, latest: self._observe_legacy_log(
                        delegate,
                        lines,
                        latest,
                    ),
                )
                await self.log_monitor.start_monitor_file(
                    self.plan.log_path,
                    started_at,
                )
            else:
                await self._send_update(
                    delegate,
                    RunControllerUpdate(
                        kind="dispatch",
                        message=(
                            "未发现传统文本日志，继续等待结构化事件："
                            f"{self.plan.event_path}"
                        ),
                    ),
                )

            run_deadline = loop.time() + self.plan.run_timeout_seconds
            while not self.wait_event.is_set():
                if not await self.process_manager.is_running():
                    return await self._resolve_process_exit(
                        delegate,
                        missing_log=not self.plan.log_path.exists(),
                    )
                if not self.plan.log_path.exists() and loop.time() > run_deadline:
                    observation = self._require_observer().set_failure(
                        (
                            f"{self.plan.observation.display_name} "
                            "未输出日志或结构化事件"
                        ),
                        source="timeout",
                    )
                    await self._publish_observation(delegate, observation)
                    return observation
                await self.sleep(self.process_poll_interval_seconds)

            return self._require_decision()
        finally:
            await self._stop_log_monitor()
            await self._stop_event_monitor()
            if self.decision is None or not self.decision.successful:
                await self._stop_process_stream_readers()

    async def _resolve_process_exit(
        self,
        delegate: RunControllerDelegate,
        *,
        missing_log: bool,
    ) -> RunObservation:
        await self.sleep(self.exit_event_grace_seconds)
        if self.wait_event.is_set():
            return self._require_decision()

        process = self.process_manager.process
        return_code = getattr(process, "returncode", None)
        observation = self._require_observer().observe_process_exit(
            return_code=return_code,
            protocol=self.plan.invocation.protocol,
        )
        if observation is None:
            suffix = "在生成日志前退出" if missing_log else "在完成任务前退出"
            observation = self._require_observer().set_failure(
                f"{self.plan.observation.display_name} {suffix}",
                source="process-exit",
            )
        await self._publish_observation(delegate, observation)
        return observation

    def _start_process_stream_readers(
        self,
        delegate: RunControllerDelegate,
    ) -> None:
        process = self.process_manager.process
        if process is None:
            return
        self.stream_reader_tasks = [
            asyncio.create_task(
                self._read_process_stream(delegate, process.stdout, "stdout")
            ),
            asyncio.create_task(
                self._read_process_stream(delegate, process.stderr, "stderr")
            ),
        ]

    async def _read_process_stream(
        self,
        delegate: RunControllerDelegate,
        stream: asyncio.StreamReader | None,
        source: str,
    ) -> None:
        if stream is None:
            return
        try:
            while True:
                raw_line = await stream.readline()
                if not raw_line:
                    return
                line = decode_bytes(raw_line).rstrip("\r\n")
                if not line:
                    continue
                await self._send_update(
                    delegate,
                    RunControllerUpdate(
                        kind="stream",
                        message=line,
                        source=source,
                    ),
                )
                observation = self._require_observer().observe_text(
                    line,
                    source=source,
                )
                if observation is not None:
                    await self._publish_observation(delegate, observation)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                f"读取 ok-script {source} 失败: {type(exc).__name__}: {exc}"
            )

    async def _stop_process_stream_readers(self) -> None:
        stream_tasks = list(self.stream_reader_tasks)
        for task in stream_tasks:
            if not task.done():
                task.cancel()
        for task in stream_tasks:
            with suppress(asyncio.CancelledError, Exception):
                await task
        self.stream_reader_tasks = []

    async def _observe_legacy_log(
        self,
        delegate: RunControllerDelegate,
        log_content: list[str],
        latest_time: datetime,
    ) -> None:
        await self._send_update(
            delegate,
            RunControllerUpdate(
                kind="legacy",
                lines=tuple(log_content),
            ),
        )
        process_running = await self.process_manager.is_running()
        observation = self._require_observer().observe_legacy_log(
            log_content,
            process_running=process_running,
            latest_time=latest_time,
            now=datetime.now(),
            run_timeout_seconds=self.plan.run_timeout_seconds,
        )
        if observation is not None:
            await self._publish_observation(delegate, observation)

    async def _start_event_monitor(
        self,
        delegate: RunControllerDelegate,
    ) -> None:
        if self.event_monitor_task is not None and not self.event_monitor_task.done():
            return
        await self._send_update(
            delegate,
            RunControllerUpdate(
                kind="dispatch",
                message=f"已开启 MAS 结构化事件监听：{self.plan.event_path}",
            ),
        )
        self.event_monitor_task = asyncio.create_task(
            self._monitor_event_log(delegate)
        )

    async def _monitor_event_log(
        self,
        delegate: RunControllerDelegate,
    ) -> None:
        observer = self._require_observer()
        while not self.wait_event.is_set():
            try:
                events, self.event_log_offset = await asyncio.to_thread(
                    self.event_reader,
                    self.plan.event_path,
                    self.event_log_offset,
                )
                for event in events:
                    was_active = observer.event_protocol_active
                    observation = observer.observe_event(event)
                    if not was_active and observer.event_protocol_active:
                        await self._send_update(
                            delegate,
                            RunControllerUpdate(
                                kind="dispatch",
                                message=(
                                    "检测到 ok-script 结构化事件，"
                                    "切换为 MAS 事件判态"
                                ),
                            ),
                        )
                    if event.event in {
                        "step",
                        "task_completed",
                        "task_failed",
                        "summary",
                    }:
                        await self._send_update(
                            delegate,
                            RunControllerUpdate(
                                kind="dispatch",
                                message=(
                                    f"事件 {event.event}: "
                                    f"{event.message or event.task or event.event}"
                                ),
                            ),
                        )
                    await self._send_update(
                        delegate,
                        RunControllerUpdate(
                            kind="event",
                            event=event,
                            observation=observation,
                            failures=tuple(observer.failures),
                        ),
                    )
                    if observation is not None:
                        await self._publish_observation(delegate, observation)
                        break
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception(f"监听 ok-script 结构化事件失败: {exc}")
                await self._send_update(
                    delegate,
                    RunControllerUpdate(
                        kind="dispatch",
                        message=f"结构化事件监听异常，已回退文本日志：{exc}",
                    ),
                )
                return
            await self.sleep(self.event_poll_interval_seconds)

    async def _stop_event_monitor(self) -> None:
        task = self.event_monitor_task
        if task is None:
            return
        self.event_monitor_task = None
        if task.done():
            with suppress(asyncio.CancelledError, Exception):
                task.result()
            return
        task.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await task

    async def _stop_log_monitor(self) -> None:
        monitor = self.log_monitor
        self.log_monitor = None
        if monitor is not None:
            with suppress(Exception):
                await monitor.stop()

    async def _publish_observation(
        self,
        delegate: RunControllerDelegate,
        observation: RunObservation,
    ) -> None:
        if self.decision is not None:
            return
        self.decision = observation
        self.wait_event.set()
        await self._send_update(
            delegate,
            RunControllerUpdate(
                kind="observation",
                observation=observation,
                failures=observation.failures,
            ),
        )

    async def _wait_script_exit(
        self,
        delegate: RunControllerDelegate,
    ) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.plan.exit_wait_timeout_seconds
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            try:
                process_running = await asyncio.wait_for(
                    self.process_manager.is_running(),
                    timeout=min(self.exit_check_timeout_seconds, remaining),
                )
            except asyncio.TimeoutError:
                await self._send_update(
                    delegate,
                    RunControllerUpdate(
                        kind="dispatch",
                        message="确认脚本退出状态超时，开始受控收尾",
                    ),
                )
                break
            if not process_running:
                logger.info(
                    f"{self.plan.observation.display_name} 已自行退出"
                )
                return
            await self.sleep(min(1.0, remaining))

        logger.warning(
            f"{self.plan.observation.display_name} 未在 "
            f"{self.plan.exit_wait_timeout_seconds:g}s 内自行退出，兜底强杀"
        )
        await self._send_update(
            delegate,
            RunControllerUpdate(
                kind="dispatch",
                message=(
                    "脚本未在 "
                    f"{self.plan.exit_wait_timeout_seconds:g}s 内退出，"
                    "正在执行受控收尾"
                ),
            ),
        )
        try:
            await asyncio.wait_for(
                self._kill_script_process(),
                timeout=self.exit_kill_timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.error(
                f"{self.plan.observation.display_name} 受控收尾超时，继续结束调度任务"
            )
            await self._send_update(
                delegate,
                RunControllerUpdate(
                    kind="dispatch",
                    message="脚本受控收尾超时，继续结束调度任务",
                ),
            )

    async def _kill_script_process(self) -> None:
        await self._stop_process_stream_readers()
        try:
            await self.process_manager.kill()
        except Exception as exc:
            logger.exception(
                "通过进程管理器中止 "
                f"{self.plan.observation.display_name} 进程失败: {exc}"
            )

        invocation = self.plan.invocation
        executable = Path(invocation.command[0])
        if invocation.protocol == PROTOCOL_LEGACY_EXE and executable.is_file():
            try:
                await self.kill_process(executable)
            except Exception as exc:
                logger.exception(
                    f"中止 {self.plan.observation.display_name} 主进程失败: {exc}"
                )

        target = invocation.target_process
        if target is not None and target.executable:
            target_executable = Path(target.executable)
            if target_executable.is_file():
                try:
                    await self.kill_process(target_executable)
                except Exception as exc:
                    logger.exception(
                        f"中止 {self.plan.observation.display_name} 追踪进程失败: {exc}"
                    )

    async def _cancel(self, delegate: RunControllerDelegate) -> None:
        await self._stop_log_monitor()
        await self._stop_event_monitor()
        await self._kill_script_process()
        await delegate.cancel_run()

    async def _send_update(
        self,
        delegate: RunControllerDelegate,
        update: RunControllerUpdate,
    ) -> None:
        await delegate.on_run_update(update)

    def _require_observer(self) -> ResultObserver:
        if self.observer is None:
            raise RuntimeError("ok-script ResultObserver 尚未初始化")
        return self.observer

    def _require_decision(self) -> RunObservation:
        if self.decision is None:
            raise RuntimeError("ok-script 控制器已结束等待但没有终态")
        return self.decision
