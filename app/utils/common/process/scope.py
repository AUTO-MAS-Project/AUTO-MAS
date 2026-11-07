"""任务所属进程及停止检查；确认结束后统一强制清理。"""

from __future__ import annotations

import asyncio
import subprocess
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Literal

import psutil


@dataclass
class StopCheck:
    name: str
    run: Callable[[], Awaitable[None]]
    timeout: float
    status: Literal["pending", "passed", "timed_out", "failed"] = "pending"


class TaskProcessScope:
    def __init__(self) -> None:
        from app.utils import process_platform

        self._job = process_platform.platform_process.create_task_job()
        self._base_flags = process_platform.platform_process.creation_flags
        self.checks: list[StopCheck] = []
        self.requested = False
        self.closed = False
        self.finished = asyncio.Event()
        self._updates: dict[asyncio.Task, int] = {}
        self._updates_idle = asyncio.Event()
        self._updates_idle.set()
        self._update_stop_error: Exception | None = None
        self._processes: dict[int, tuple[Any, psutil.Process | None]] = {}
        self._writers: dict[int, Any] = {}
        self._external_processes: dict[int, tuple[Any, psutil.Process | None]] = {}

    def add_check(
        self, name: str, run: Callable[[], Awaitable[None]], *, timeout: float
    ) -> None:
        if timeout <= 0:
            raise ValueError("停止检查超时必须大于 0")
        self.checks.append(StopCheck(name, run, timeout))

    @contextmanager
    def updating(self) -> Iterator[None]:
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("更新必须在异步任务中执行")
        if self.closed or (self.requested and task not in self._updates):
            raise asyncio.CancelledError
        token = current_update_scope.set(self)
        self._updates[task] = self._updates.get(task, 0) + 1
        self._updates_idle.clear()
        try:
            yield
        except Exception as error:
            if self.requested:
                self._update_stop_error = error
            raise
        finally:
            current_update_scope.reset(token)
            count = self._updates[task] - 1
            if count:
                self._updates[task] = count
            else:
                del self._updates[task]
            if not self._updates:
                self._updates_idle.set()

    async def stop_updates(self) -> None:
        for task in tuple(self._updates):
            task.cancel()
        await self._updates_idle.wait()
        # 协程结束不等于安装子进程退出；仍在运行的写入者必须等到退出或检查超时。
        while any(
            (
                handle.poll() is None
                if isinstance(handle, subprocess.Popen)
                else handle.returncode is None
            )
            for handle in tuple(self._writers.values())
        ):
            await asyncio.sleep(0.01)
        if self._update_stop_error is not None:
            raise RuntimeError(
                "更新停止未正常确认，转入强制清理"
            ) from self._update_stop_error

    async def run_update_worker[T](
        self, operation: Callable[[], T], *, cancel: Callable[[], None]
    ) -> T:
        """安装线程先收到停止令牌；线程结束前更新确认保持未完成。"""
        with self.updating():
            worker = asyncio.create_task(asyncio.to_thread(operation))
            try:
                return await asyncio.shield(worker)
            except asyncio.CancelledError:
                cancel()
                while not worker.done():
                    try:
                        await asyncio.shield(worker)
                    except (asyncio.CancelledError, Exception):
                        if worker.done():
                            break
                _consume_result(worker)
                raise

    async def run_checks(self) -> None:
        self.requested = True

        async def run(check: StopCheck) -> None:
            scope_token = current_process_scope.set(self)
            check_token = current_stop_check.set(self)
            try:
                task = asyncio.ensure_future(check.run())
            except (asyncio.CancelledError, Exception):
                check.status = "failed"
                return
            finally:
                current_stop_check.reset(check_token)
                current_process_scope.reset(scope_token)
            done, _ = await asyncio.wait({task}, timeout=check.timeout)
            if not done:
                check.status = "timed_out"
                task.cancel()
                # 不 await 可能屏蔽取消的检查；超时就是转入强制清理。
                task.add_done_callback(_consume_result)
            else:
                try:
                    task.result()
                    check.status = "passed"
                except (asyncio.CancelledError, Exception):
                    check.status = "failed"

        await asyncio.gather(*(run(check) for check in self.checks))

    def ensure_can_start(self) -> None:
        if self.closed or (
            self.requested
            and current_update_scope.get() is not self
            and current_stop_check.get() is not self
        ):
            raise asyncio.CancelledError

    @property
    def creation_flags(self) -> int:
        return self._job.creation_flags if self._job is not None else 0

    def track(
        self, handle: Any, *, suspended: bool = False, writer: bool = False
    ) -> None:
        if self.closed:
            raise asyncio.CancelledError
        pid = handle.pid
        if pid is None:
            return
        try:
            process = (
                handle if isinstance(handle, psutil.Process) else psutil.Process(pid)
            )
            process.create_time()  # 缓存身份，避免命令退出后把复用 PID 当成本任务。
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            process = None
        self._processes[id(handle)] = (handle, process)
        if writer:
            self._writers[id(handle)] = handle
        if self._job is not None and suspended:
            self._job.assign(pid, suspended=suspended)
        else:
            # 已存在的跟踪目标只登记归属，不改它原有的系统进程组。
            self._external_processes[id(handle)] = (handle, process)

    def forget(self, handle: Any) -> None:
        self._processes.pop(id(handle), None)
        self._writers.pop(id(handle), None)
        self._external_processes.pop(id(handle), None)

    def popen(self, *args: Any, **kwargs: Any) -> subprocess.Popen:
        """供安装线程使用的进程工厂，同样登记到任务进程组。"""
        if self.closed:
            raise asyncio.CancelledError
        kwargs["creationflags"] = (
            kwargs.get("creationflags", 0) | self._base_flags | self.creation_flags
        )
        process = subprocess.Popen(*args, **kwargs)
        try:
            if self.closed:
                process.kill()
                raise asyncio.CancelledError
            self.track(process, suspended=bool(self.creation_flags), writer=True)
        except BaseException:
            with suppress(ProcessLookupError):
                process.kill()
            raise
        return process

    async def force_close(self) -> None:
        """只强杀本任务记录的进程树，并直接关闭其管道。"""
        self.closed = True
        owned = tuple(self._processes.values())

        def kill(handle: Any, process: psutil.Process | None) -> None:
            if process is None:
                if getattr(handle, "returncode", None) is None:
                    with suppress(ProcessLookupError, psutil.NoSuchProcess):
                        handle.kill()
                return
            # children() 使用父进程的缓存身份，并一次获取进程树；Windows 上
            # 包装命令已退出时，仍能找到继承了管道的后代，PID 复用会被拒绝。
            try:
                children = process.children(recursive=True)
            except psutil.NoSuchProcess:
                children = []
            for target in [*reversed(children), process]:
                with suppress(psutil.NoSuchProcess):
                    if target.is_running():
                        target.kill()

        try:
            if self._job is not None:
                self._job.kill()
                targets = tuple(self._external_processes.values())
            else:
                targets = owned
            results = await asyncio.gather(
                *(
                    asyncio.to_thread(kill, handle, process)
                    for handle, process in targets
                ),
                return_exceptions=True,
            )
            errors = [result for result in results if isinstance(result, BaseException)]
            if errors:
                raise RuntimeError("部分任务进程未能强制终止") from errors[0]
        finally:
            file_closers = []
            for handle, _ in owned:
                transport = getattr(handle, "_transport", None)
                if transport is not None:
                    for fd in (0, 1, 2):
                        pipe = transport.get_pipe_transport(fd)
                        if pipe is not None:
                            pipe.close()
                elif isinstance(handle, subprocess.Popen):
                    for name in ("stdin", "stdout", "stderr"):
                        stream = getattr(handle, name, None)
                        if stream is not None:
                            file_closers.append(
                                asyncio.create_task(asyncio.to_thread(stream.close))
                            )
            self._processes.clear()
            self._writers.clear()
            self._external_processes.clear()
            if self._job is not None:
                self._job.close()
            if file_closers:
                done, pending = await asyncio.wait(file_closers, timeout=1)
                for task in done:
                    _consume_result(task)
                for task in pending:
                    task.cancel()


def _consume_result(task: asyncio.Future) -> None:
    if not task.cancelled():
        task.exception()


current_process_scope: ContextVar[TaskProcessScope | None] = ContextVar(
    "current_process_scope", default=None
)
current_update_scope: ContextVar[TaskProcessScope | None] = ContextVar(
    "current_update_scope", default=None
)
current_stop_check: ContextVar[TaskProcessScope | None] = ContextVar(
    "current_stop_check", default=None
)
