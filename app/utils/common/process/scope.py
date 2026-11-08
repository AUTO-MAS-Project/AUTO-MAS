"""任务所属进程及停止检查；确认结束后统一强制清理。"""

from __future__ import annotations

import asyncio
import subprocess
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager, suppress
from contextvars import Context, ContextVar, copy_context
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
        self._breakaway_flags = process_platform.platform_process.breakaway_flags
        self.checks: list[StopCheck] = []
        self.requested = False
        self.closed = False
        self.cleanup_failed = False
        self.pending_creations: set[asyncio.Task] = set()
        self.retained_workers: set[asyncio.Task] = set()
        self._finalizers: dict[asyncio.Task, float] = {}
        self.finished = asyncio.Event()
        self._updates: dict[asyncio.Task, int] = {}
        self._update_stoppers: dict[asyncio.Task, Callable[[], None]] = {}
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

    def retain_worker(self, task: asyncio.Task) -> None:
        """保留反映底层真实完成的句柄，不让统一取消制造假完成。"""
        self.retained_workers.add(task)
        task.add_done_callback(self.retained_workers.discard)

    def watch_finalizer(self, task: asyncio.Task, *, timeout: float) -> None:
        self._finalizers[task] = timeout
        task.add_done_callback(lambda done: self._finalizers.pop(done, None))
        if self.closed:
            # 强杀后新开始的本地收尾也只能有限等待，不能再次卡住任务结束。
            timer = asyncio.get_running_loop().call_later(timeout, task.cancel)
            task.add_done_callback(lambda done: timer.cancel())

    @contextmanager
    def updating(self, *, cancel: Callable[[], None] | None = None) -> Iterator[None]:
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("更新必须在异步任务中执行")
        if self.closed or (self.requested and task not in self._updates):
            raise asyncio.CancelledError
        token = current_update_scope.set(self)
        self._updates[task] = self._updates.get(task, 0) + 1
        previous_stop = self._update_stoppers.get(task)
        if cancel is not None:
            self._update_stoppers[task] = cancel
            self.retain_worker(task)
        self._updates_idle.clear()
        try:
            yield
        except Exception as error:
            if self.requested:
                self._update_stop_error = error
            raise
        finally:
            current_update_scope.reset(token)
            if cancel is not None:
                if previous_stop is None:
                    self._update_stoppers.pop(task, None)
                else:
                    self._update_stoppers[task] = previous_stop
            count = self._updates[task] - 1
            if count:
                self._updates[task] = count
            else:
                del self._updates[task]
            if not self._updates:
                self._updates_idle.set()

    async def stop_updates(self) -> None:
        for task in tuple(self._updates):
            stop = self._update_stoppers.get(task)
            if stop is None:
                task.cancel()
            else:
                stop()
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
        self,
        operation: Callable[[], T],
        *,
        cancel: Callable[[], None],
        release_cancelled: Callable[[T], Any] | None = None,
    ) -> T:
        """线程结束前更新确认保持未完成；取消后的成功资源交给 release_cancelled。"""
        with self.updating():
            worker = asyncio.create_task(asyncio.to_thread(operation))
            self.retain_worker(worker)
            owner = asyncio.current_task()
            if owner is not None:
                self.retain_worker(owner)
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
                if (
                    release_cancelled is not None
                    and not worker.cancelled()
                    and worker.exception() is None
                ):
                    # 取消仍向上传播，但迟到的成功资源必须交回既有释放入口。
                    cleanup = asyncio.create_task(
                        asyncio.to_thread(release_cancelled, worker.result())
                    )
                    self.retain_worker(cleanup)
                    cleanup.add_done_callback(_consume_result)
                else:
                    _consume_result(worker)
                raise

    async def run_checks(self) -> None:
        self.requested = True
        # 只确认停止时已经开始的收尾；每项独立限时，到期后仍执行强制清理。
        for finalizer, timeout in tuple(self._finalizers.items()):
            if finalizer.done():
                continue

            async def finish(task=finalizer) -> None:
                await asyncio.shield(task)

            self.add_check(f"finalize:{finalizer.get_name()}", finish, timeout=timeout)

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
        self,
        handle: Any,
        *,
        suspended: bool = False,
        writer: bool = False,
        breakaway: bool = False,
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
            self._job.assign(pid, suspended=suspended, breakaway=breakaway)
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
        try:
            process = subprocess.Popen(*args, **kwargs)
        except OSError as error:
            if (
                not kwargs["creationflags"] & self._breakaway_flags
                or getattr(error, "winerror", None) != 5
            ):
                raise
            kwargs["creationflags"] &= ~self._breakaway_flags
            process = subprocess.Popen(*args, **kwargs)
        try:
            if self.closed:
                process.kill()
                raise asyncio.CancelledError
            self.track(
                process,
                suspended=bool(self.creation_flags),
                writer=True,
                breakaway=bool(kwargs["creationflags"] & self._breakaway_flags),
            )
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
        except BaseException:
            self.cleanup_failed = True
            raise
        finally:
            for handle, _ in owned:
                transport = getattr(handle, "_transport", None)
                if transport is not None:
                    for fd in (0, 1, 2):
                        pipe = transport.get_pipe_transport(fd)
                        if pipe is not None:
                            pipe.close()
            # 同步 Popen 的管道由正在 communicate() 的安装线程自行关闭。
            # 从事件循环线程抢先 close 会使该线程的 select/read 触发 EBADF。
            self._processes.clear()
            self._writers.clear()
            self._external_processes.clear()
            if self._job is not None:
                self._job.close()


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


def detached_process_context() -> Context:
    """应用级后台任务不继承调用方的任务停止/进程归属，保留其余上下文。"""
    context = copy_context()
    for variable in (current_process_scope, current_update_scope, current_stop_check):
        context.run(variable.set, None)
    return context
