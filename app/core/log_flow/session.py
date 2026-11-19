"""宿主侧采集会话：持续承接节点、限制容量并监督 worker 退出。"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

from app.models.log_flow import CloseReason, Node, NodeObservation, SessionSummary
from app.utils import process_platform
from app.utils.common.process.runner import close_process_pipes
from app.utils.contracts.process import TaskProcessJob

from .contracts import (
    MAX_FRAME_BYTES,
    MAX_NODE_BYTES,
    MAX_NODE_FRAMES,
    MAX_PENDING_RECORDS,
    WORKER_MESSAGE,
    Closed,
    Failed,
    FinalEntry,
    InputRecord,
    Observed,
    PipelineSpec,
    Ready,
    TextRecord,
)

_SOURCE_ROOT = Path(__file__).resolve().parents[3]
_STOP_GRACE_SECONDS = 1.0


class SessionOpenError(RuntimeError):
    """采集会话未就绪；由执行层与原脚本结果分开处理。"""


class LogFlowSession:
    """每个进程服务一次会话，宿主上报走有界待发队列。"""

    def __init__(
        self,
        process: asyncio.subprocess.Process,
        *,
        job: TaskProcessJob | None,
        accept_push: bool,
        accept_mas: bool,
        observation: NodeObservation,
        requires_final_report: bool,
    ) -> None:
        self._process = process
        self._job = job
        self._accept_push = accept_push
        self._accept_mas = accept_mas
        self._outbox: asyncio.Queue[bytes | None] | None = (
            asyncio.Queue(MAX_PENDING_RECORDS + 1)
            if accept_push or accept_mas
            else None
        )
        self._writer: asyncio.Task[None] | None = None
        self.observation = observation
        self._requires_final_report = requires_final_report
        self._missed_native = False
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
        session: LogFlowSession | None = None
        job: TaskProcessJob | None = None
        try:
            job = process_platform.platform_process.create_task_job(kill_on_close=True)
            if job is not None:
                creation_flags |= job.creation_flags
            async with asyncio.timeout(timeout):
                process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-m",
                    "app.core.log_flow.worker",
                    cwd=_SOURCE_ROOT,
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
                await session.close(timeout=0)
            raise SessionOpenError("LogFlow worker 启动失败或未在期限内就绪") from exc
        except BaseException:
            if session is not None:
                await session.close(timeout=0)
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
        return self._enqueue(record)

    def _enqueue(self, record: InputRecord) -> bool:
        outbox = self._outbox
        if (
            outbox is None
            or self._closing is not None
            or self._receiver.done()
            or self._stopping is not None
        ):
            return False
        if outbox.qsize() >= MAX_PENDING_RECORDS or len(record.text) >= MAX_FRAME_BYTES:
            return False
        frame = record.model_dump_json().encode("utf-8") + b"\n"
        if len(frame) > MAX_FRAME_BYTES:
            return False
        outbox.put_nowait(frame)
        return True

    def native_line_receiver(self) -> Callable[[str], None]:
        """取得宿主监控器的窄输入回调，声明缺失时在绑定阶段发现。"""
        if not self._accept_mas:
            raise ValueError("该会话未启用宿主日志输入")
        return self._accept_native_line

    def _accept_native_line(self, line: str) -> None:
        """由已绑定的 MAS 采集器调用；丢失必须反映在采集摘要。"""
        if not self._enqueue(TextRecord(text=line, source="mas")):
            if self._closing is None and not self._receiver.done():
                self._missed_native = True

    async def _write_records(self, outbox: asyncio.Queue[bytes | None]) -> None:
        assert self._process.stdin is not None
        try:
            while (frame := await outbox.get()) is not None:
                self._process.stdin.write(frame)
                await self._process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            # 接收端以 worker 的终止消息或意外退出记录完整性。
            return
        finally:
            self._process.stdin.close()

    async def close(self, *, timeout: float = 2.0) -> SessionSummary:
        """首位调用者设定唯一收尾预算；取消某个等待者不取消清理。"""
        if self._closing is None:
            self._closing = asyncio.create_task(self._close(timeout))
        return await asyncio.shield(self._closing)

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
            return self.observation.finish(
                "timeout", detail, requires_final_report=self._requires_final_report
            )
        finally:
            if self._writer is not None:
                self._writer.cancel()
                with suppress(asyncio.CancelledError):
                    await self._writer

    async def _stop_worker(self) -> bool:
        if self._stopping is None:
            self._stopping = asyncio.create_task(self._terminate_worker())
        return await asyncio.shield(self._stopping)

    async def _terminate_worker(self) -> bool:
        if self._writer is not None:
            self._writer.cancel()
        with suppress(ProcessLookupError):
            self._process.kill()
        close_process_pipes(self._process)
        # Windows 需要确认 Job 中的实际解释器和启动器都已退出。
        job = self._job
        try:
            if job is not None:
                # Job 自己有退出确认期限；在后台线程等它结束后再关闭句柄，避免争用 Job 锁。
                await asyncio.to_thread(job.kill)
            await asyncio.wait_for(self._process.wait(), _STOP_GRACE_SECONDS)
        except (OSError, TimeoutError, ExceptionGroup):
            return False
        finally:
            self._release_job()
        return True

    def _release_job(self) -> None:
        if self._job is not None:
            job, self._job = self._job, None
            job.close()

    async def _receive(self) -> SessionSummary:
        assert self._process.stdout is not None
        reason: CloseReason = "worker_error"
        detail = "LogFlow worker 意外退出"
        final_entries: list[tuple[str, str, float | None]] = []
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
                elif isinstance(message, FinalEntry) and self._worker_pid is not None:
                    if (
                        len(final_entries) == MAX_NODE_FRAMES
                        or final_bytes + len(frame) > MAX_NODE_BYTES
                    ):
                        reason = "capacity"
                        detail = "最终报告容量已满"
                        break
                    entry = message.entry
                    final_entries.append((entry.node_type, entry.text, entry.timestamp))
                    final_bytes += len(frame)
                elif isinstance(message, Closed) and self._worker_pid is not None:
                    if message.has_final_report != self._requires_final_report:
                        raise ValueError("LogFlow worker 未交付预期的最终报告")
                    if await self._process.wait() == 0:
                        self._release_job()
                        report_entries = (
                            tuple(final_entries) if message.has_final_report else None
                        )
                        if self._missed_native:
                            return self.observation.finish(
                                "capacity",
                                "原生采集记录未能全部交接",
                                report_entries=report_entries,
                                report_bytes=final_bytes,
                                sink_error=message.sink_error,
                            )
                        return self.observation.finish(
                            "complete",
                            report_entries=report_entries,
                            report_bytes=final_bytes,
                            sink_error=message.sink_error,
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
        return self.observation.finish(
            reason, detail, requires_final_report=self._requires_final_report
        )
