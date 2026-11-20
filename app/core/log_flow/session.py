"""宿主侧采集会话：持续承接节点、限制容量并监督 worker 退出。"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import ClassVar

from pydantic import ValidationError

from app.models.log_flow import (
    CloseReason,
    Node,
    NodeAttributes,
    NodeDisplayStatus,
    NodeObservation,
    ReportEntry,
    ReportOrder,
    SessionSummary,
)
from app.utils import process_platform
from app.utils.common.process.runner import close_process_pipes
from app.utils.contracts.process import TaskProcessJob

from .contracts import (
    MAX_FRAME_BYTES,
    MAX_HOST_PENDING_BYTES,
    MAX_NATIVE_PENDING_RECORDS,
    MAX_NODE_BYTES,
    MAX_NODE_FRAMES,
    MAX_PENDING_RECORDS,
    WORKER_MESSAGE,
    Closed,
    Failed,
    FinalEntry,
    FinalReportReady,
    InputRecord,
    Observed,
    PipelineSpec,
    Ready,
    ReportedRecord,
    TextRecord,
    WithdrawnRecord,
)
from .push import PushReporter, SubmitResult

_SOURCE_ROOT = Path(__file__).resolve().parents[3]
_STOP_GRACE_SECONDS = 1.0


class SessionOpenError(RuntimeError):
    """采集会话未就绪；由执行层与原脚本结果分开处理。"""


class _SessionReporter:
    def __init__(self, enqueue: Callable[[InputRecord], SubmitResult]) -> None:
        self._enqueue = enqueue

    def text(self, text: str, *, timestamp: float | None = None) -> SubmitResult:
        try:
            record = TextRecord(text=text, timestamp=timestamp)
        except ValidationError:
            return SubmitResult.INVALID
        return self._enqueue(record)

    def node(
        self,
        node_type: str,
        text: str,
        *,
        timestamp: float | None = None,
        node_id: str | None = None,
        status: NodeDisplayStatus | None = None,
        attributes: NodeAttributes = (),
    ) -> SubmitResult:
        try:
            record = ReportedRecord(
                node_type=node_type,
                text=text,
                timestamp=timestamp,
                node_id=node_id,
                status=status,
                attributes=attributes,
            )
        except ValidationError:
            return SubmitResult.INVALID
        return self._enqueue(record)

    def withdraw(self, node_id: str) -> SubmitResult:
        try:
            record = WithdrawnRecord(node_id=node_id)
        except ValidationError:
            return SubmitResult.INVALID
        return self._enqueue(record)


class LogFlowSession:
    """每个进程服务一次会话，宿主上报走有界待发队列。"""

    _unconfirmed_workers: ClassVar[set[LogFlowSession]] = set()

    def __init__(
        self,
        process: asyncio.subprocess.Process,
        *,
        job: TaskProcessJob | None,
        accept_push: bool,
        accept_mas: bool,
        observation: NodeObservation,
        requires_final_report: bool,
        report_order: ReportOrder,
    ) -> None:
        self._process = process
        self._job = job
        self._accept_push = accept_push
        self._accept_mas = accept_mas
        self._outbox: asyncio.Queue[bytes | None] | None = (
            asyncio.Queue(
                (MAX_NATIVE_PENDING_RECORDS if accept_mas else MAX_PENDING_RECORDS) + 1
            )
            if accept_push or accept_mas
            else None
        )
        self._queued_bytes = 0
        self._writer: asyncio.Task[None] | None = None
        self.observation = observation
        self._requires_final_report = requires_final_report
        self._report_order = report_order
        self._final_report: tuple[ReportEntry, ...] | None = None
        self._final_report_bytes = 0
        self._missed_native = False
        self._native_incomplete_detail = ""
        self._ready = asyncio.Event()
        self._worker_pid: int | None = None
        self._closing: asyncio.Task[SessionSummary] | None = None
        self._stopping: asyncio.Task[bool] | None = None
        self._receiver = asyncio.create_task(self._receive())

    @classmethod
    async def open(
        cls,
        config: PipelineSpec,
        *,
        timeout: float = 5.0,
        observation: NodeObservation | None = None,
    ) -> LogFlowSession:
        """启动子进程；只有规则编译完并记录文件偏移后才返回。"""
        payload = config.model_dump_json().encode("utf-8") + b"\n"
        if len(payload) > MAX_FRAME_BYTES:
            raise SessionOpenError("采集会话配置超过启动消息容量")
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        python_path = os.environ.get("PYTHONPATH")
        worker_env = {
            **os.environ,
            "AUTO_MAS_LOGFLOW_WORKER": "1",
            "PYTHONPATH": os.pathsep.join(
                (str(_SOURCE_ROOT), python_path)
                if python_path
                else (str(_SOURCE_ROOT),)
            ),
        }
        session: LogFlowSession | None = None
        job: TaskProcessJob | None = None
        try:
            job = process_platform.platform_process.create_task_job(kill_on_close=True)
            if job is not None:
                creation_flags |= job.creation_flags
            async with asyncio.timeout(timeout):
                process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-P",
                    "-m",
                    "app.core.log_flow.worker",
                    env=worker_env,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                    creationflags=creation_flags,
                    limit=MAX_FRAME_BYTES,
                )
                session = cls(
                    process,
                    job=job,
                    accept_push=config.accept_push,
                    accept_mas=config.accept_mas,
                    requires_final_report=config.postprocess is not None,
                    report_order=config.report_order,
                    observation=observation
                    if observation is not None
                    else NodeObservation(),
                )
                if job is not None:
                    # 先加入 Job 再恢复；Windows venv 启动器派生的解释器也由 Job 持有。
                    job.assign(process.pid, suspended=True, breakaway=False)
                assert process.stdin is not None
                process.stdin.write(payload)
                await process.stdin.drain()
                await session._ready.wait()
                if session._worker_pid is None:
                    summary = await asyncio.shield(session._receiver)
                    raise SessionOpenError(summary.detail)
        except (TimeoutError, OSError) as exc:
            if session is not None:
                await session.close_on_exit(timeout=0)
            raise SessionOpenError("LogFlow worker 启动失败或未在期限内就绪") from exc
        except BaseException:
            if session is not None:
                await session.close_on_exit(timeout=0)
            raise
        finally:
            if session is None and job is not None:
                job.close()
        if session._outbox is not None:
            session._writer = asyncio.create_task(
                session._write_records(session._outbox)
            )
        return session

    @property
    def pid(self) -> int:
        assert self._worker_pid is not None
        return self._worker_pid

    def snapshot(self) -> tuple[Node, ...]:
        """读取宿主已承接的节点；关闭超时后保持最后一份快照。"""
        return self.observation.snapshot()

    def submit(self, record: InputRecord) -> bool:
        """接受到当前会话的宿主队列；不承诺处理完成，不等待堵塞的 worker。"""
        if (
            not self._accept_push
            or isinstance(record, TextRecord)
            and record.source == "mas"
        ):
            return False
        return self._enqueue(record) == SubmitResult.ACCEPTED

    def _enqueue(self, record: InputRecord) -> SubmitResult:
        outbox = self._outbox
        if (
            outbox is None
            or self._closing is not None
            or self._receiver.done()
            or self._stopping is not None
        ):
            return SubmitResult.CLOSED
        if (
            not isinstance(record, WithdrawnRecord)
            and len(record.text) >= MAX_FRAME_BYTES
        ) or (
            isinstance(record, ReportedRecord)
            and len(record.node_type) >= MAX_FRAME_BYTES
        ):
            return SubmitResult.TOO_LARGE
        limit = (
            MAX_NATIVE_PENDING_RECORDS
            if isinstance(record, TextRecord) and record.source == "mas"
            else MAX_PENDING_RECORDS
        )
        if outbox.qsize() >= limit:
            return SubmitResult.BACKPRESSURE
        frame = record.model_dump_json().encode("utf-8") + b"\n"
        if len(frame) > MAX_FRAME_BYTES:
            return SubmitResult.TOO_LARGE
        if self._queued_bytes + len(frame) > MAX_HOST_PENDING_BYTES:
            return SubmitResult.BACKPRESSURE
        outbox.put_nowait(frame)
        self._queued_bytes += len(frame)
        return SubmitResult.ACCEPTED

    def native_line_receiver(self) -> Callable[[str], None]:
        """取得宿主监控器的窄输入回调，声明缺失时在绑定阶段发现。"""
        if not self._accept_mas:
            raise ValueError("该会话未启用宿主日志输入")
        return self._accept_native_line

    def _accept_native_line(self, line: str) -> None:
        """由已绑定的 MAS 采集器调用；丢失必须反映在采集摘要。"""
        if self._enqueue(TextRecord(text=line, source="mas")) != SubmitResult.ACCEPTED:
            if self._closing is None and not self._receiver.done():
                self._missed_native = True

    def mark_native_incomplete(self, detail: str) -> None:
        """保留原生采集器报告的第一处输入缺口。"""
        if not self._native_incomplete_detail:
            self._native_incomplete_detail = detail

    def push_reporter(self) -> PushReporter:
        """只为明确启用主动上报的当前会话签发能力。"""
        if not self._accept_push:
            raise ValueError("该会话未启用主动上报")
        return _SessionReporter(self._enqueue)

    async def _write_records(self, outbox: asyncio.Queue[bytes | None]) -> None:
        assert self._process.stdin is not None
        try:
            while (frame := await outbox.get()) is not None:
                self._queued_bytes -= len(frame)
                self._process.stdin.write(frame)
                await self._process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            # 接收端以 worker 的终止消息或意外退出记录完整性。
            return
        finally:
            self._process.stdin.close()

    async def close(self, *, timeout: float = 2.0) -> SessionSummary:
        """首位调用者设定唯一收尾预算；取消某个等待者不取消清理。"""
        return await asyncio.shield(self._start_close(timeout))

    def _start_close(self, timeout: float) -> asyncio.Task[SessionSummary]:
        if self._closing is None:
            self._closing = asyncio.create_task(self._close(timeout))
        return self._closing

    async def close_on_exit(self, *, timeout: float = 2.0) -> None:
        """生命周期所有者先等待有界收尾，再传播取消。"""
        closing = self._start_close(timeout)
        cancelled: asyncio.CancelledError | None = None
        while not closing.done():
            try:
                await asyncio.shield(closing)
            except asyncio.CancelledError as exc:
                cancelled = exc
        closing.result()
        if cancelled is not None:
            raise cancelled

    async def _close(self, timeout: float) -> SessionSummary:
        assert self._process.stdin is not None
        if self._writer is None:
            self._process.stdin.close()
        else:
            assert self._outbox is not None
            # 为关闭哨兵预留一格；此前所有已接受消息排在它前面。
            self._outbox.put_nowait(None)
        try:
            return await asyncio.wait_for(asyncio.shield(self._receiver), timeout)
        except TimeoutError:
            # 到期立即停止承接；后续清理期间的缓冲节点不再修改冻结快照。
            self._receiver.cancel()
            stopped = await self._stop_worker()
            with suppress(asyncio.CancelledError):
                await self._receiver
            detail = "采集收尾超时，报告不完整"
            if not stopped:
                detail += "；worker 退出未确认"
            return self._finish_observation("timeout", detail)
        finally:
            if self._writer is not None:
                self._writer.cancel()
                with suppress(asyncio.CancelledError):
                    await self._writer

    @classmethod
    def has_unconfirmed_workers(cls) -> bool:
        """退出待确认的 worker 仍可能读取共享插件环境。"""
        return bool(cls._unconfirmed_workers)

    @classmethod
    async def retry_unconfirmed_workers(cls) -> None:
        """环境变更前并行复查一次，保留仍无法确认的进程。"""
        await asyncio.gather(
            *(
                session._stop_worker(retry=True)
                for session in tuple(cls._unconfirmed_workers)
            )
        )

    async def _stop_worker(self, *, retry: bool = False) -> bool:
        if self._stopping is None or (retry and self._stopping.done()):
            self._stopping = asyncio.create_task(self._terminate_worker())
        return await asyncio.shield(self._stopping)

    async def _terminate_worker(self) -> bool:
        if self._writer is not None:
            self._writer.cancel()
        # Windows 需要确认 Job 中的实际解释器和启动器都已退出。
        job = self._job
        try:
            try:
                self._process.kill()
            except ProcessLookupError:
                pass
            except PermissionError:
                if job is None:
                    raise
                # 启动器句柄拒绝终止时，仍使用已有 Job 回收进程组。
            finally:
                close_process_pipes(self._process)
            if job is not None:
                # Job 自己有退出确认期限；在后台线程等它结束后再关闭句柄，避免争用 Job 锁。
                await asyncio.to_thread(job.kill)
            await asyncio.wait_for(self._process.wait(), _STOP_GRACE_SECONDS)
        except (OSError, TimeoutError, ExceptionGroup):
            self._unconfirmed_workers.add(self)
            return False
        self._release_job()
        self._unconfirmed_workers.discard(self)
        return True

    def _release_job(self) -> None:
        if self._job is not None:
            job, self._job = self._job, None
            job.close()

    def _finish_observation(
        self, reason: CloseReason, detail: str = "", *, sink_error: str = ""
    ) -> SessionSummary:
        return self.observation.finish(
            reason,
            detail,
            report_entries=self._final_report,
            report_bytes=self._final_report_bytes,
            requires_final_report=self._requires_final_report,
            sink_error=sink_error,
            report_order=self._report_order,
        )

    async def _receive(self) -> SessionSummary:
        assert self._process.stdout is not None
        reason: CloseReason = "worker_error"
        detail = "LogFlow worker 意外退出"
        final_entries: list[ReportEntry] = []
        final_bytes = 0
        try:
            while frame := await self._process.stdout.readline():
                message = WORKER_MESSAGE.validate_json(frame)
                if isinstance(message, Ready) and self._worker_pid is None:
                    self._worker_pid = message.pid
                    self._ready.set()
                elif isinstance(message, Observed) and self._worker_pid is not None:
                    if (
                        len(self.observation) == MAX_NODE_FRAMES
                        or self.observation.size_bytes + len(frame) > MAX_NODE_BYTES
                    ):
                        reason = "capacity"
                        detail = "宿主节点容量已满"
                        break
                    self.observation.append(message.node, frame_bytes=len(frame))
                elif (
                    isinstance(message, FinalEntry)
                    and self._worker_pid is not None
                    and self._requires_final_report
                    and self._final_report is None
                ):
                    if (
                        len(final_entries) == MAX_NODE_FRAMES
                        or final_bytes + len(frame) > MAX_NODE_BYTES
                    ):
                        reason = "capacity"
                        detail = "最终报告容量已满"
                        break
                    final_entries.append(message.entry)
                    final_bytes += len(frame)
                elif (
                    isinstance(message, FinalReportReady)
                    and self._worker_pid is not None
                    and self._requires_final_report
                    and self._final_report is None
                ):
                    self._final_report = tuple(final_entries)
                    self._final_report_bytes = final_bytes
                    final_entries.clear()
                elif isinstance(message, Closed) and self._worker_pid is not None:
                    if (self._final_report is not None) != self._requires_final_report:
                        raise ValueError("LogFlow worker 未交付预期的最终报告")
                    if await self._process.wait() == 0:
                        self._release_job()
                        if message.capacity_error:
                            return self._finish_observation(
                                "capacity",
                                message.capacity_error,
                                sink_error=message.sink_error,
                            )
                        if self._missed_native:
                            return self._finish_observation(
                                "capacity",
                                "原生采集记录未能全部交接",
                                sink_error=message.sink_error,
                            )
                        if gap := message.file_error or self._native_incomplete_detail:
                            return self._finish_observation(
                                "worker_error",
                                gap,
                                sink_error=message.sink_error,
                            )
                        return self._finish_observation(
                            "complete", sink_error=message.sink_error
                        )
                    break
                elif isinstance(message, Failed):
                    reason = message.reason
                    detail = message.detail
                    break
                else:
                    raise ValueError("LogFlow worker 消息顺序无效")
        except (OSError, ValueError, ExceptionGroup) as exc:
            detail = str(exc)
        if not await self._stop_worker():
            detail += "；worker 退出未确认"
        self._ready.set()
        return self._finish_observation(reason, detail)
