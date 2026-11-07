"""应用级背景任务组：持有执行、限额及限时保留的一次性结果。"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, cast
from uuid import UUID, uuid4

from app.utils import get_logger

logger = get_logger("背景任务")


class BackgroundTaskState(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


@dataclass(frozen=True)
class TaskOutcome[T]:
    state: BackgroundTaskState
    value: T | None = None
    error: BaseException | None = None

    def unwrap(self) -> T:
        """取成功值（包括 None），否则重新抛出原异常或取消原因。"""
        if self.error is not None:
            raise self.error
        return cast(T, self.value)


@dataclass(frozen=True)
class TaskPending:
    """尚未完成，与成功返回 None 明确区分。"""


PENDING = TaskPending()


@dataclass(frozen=True)
class BackgroundTaskInfo:
    uid: UUID
    state: BackgroundTaskState
    retain_result: bool


class BackgroundTaskHandle[T]:
    """不暴露 asyncio.Task；等待方取消不会取消背景执行。"""

    def __init__(self, group: BackgroundTaskGroup, uid: UUID) -> None:
        self.group = group
        self.uid = uid
        self._completed = asyncio.Event()

    def done(self) -> bool:
        return self._completed.is_set()

    def cancel(self) -> None:
        self.group._cancel(self.uid)

    async def wait_done(self, timeout: float | None = None) -> bool:
        """只等待执行退出，不提取结果；超时返回 False。"""
        try:
            async with asyncio.timeout(timeout):
                await self._completed.wait()
        except TimeoutError:
            return False
        return True

    async def wait_take(self, timeout: float | None = None) -> TaskOutcome[T]:
        return await self.group.wait_take(self, timeout=timeout)


@dataclass
class _TaskRecord:
    handle: BackgroundTaskHandle[Any]
    retain_result: bool
    outcome: TaskOutcome[Any] | None = None
    deadline: asyncio.TimerHandle | None = None
    expires: asyncio.TimerHandle | None = None
    timed_out: bool = False


class BackgroundTaskGroup:
    """单事件循环所有权；并发执行和结果记录分别限额，不提供排队。"""

    def __init__(
        self,
        owner: BackgroundTaskRegistry,
        name: str,
        *,
        max_running: int,
        max_retained: int,
        execution_timeout: float | None,
        result_ttl: float,
    ) -> None:
        if max_running < 1 or max_retained < max_running:
            raise ValueError("任务组容量必须为正数，记录容量不能小于并发容量")
        if result_ttl <= 0 or (
            execution_timeout is not None and execution_timeout <= 0
        ):
            raise ValueError("任务执行期限与结果保留期限必须为正数")
        self.name = name
        self.max_running = max_running
        self.max_retained = max_retained
        self.execution_timeout = execution_timeout
        self.result_ttl = result_ttl
        self.closing = False
        self._owner = owner
        self._loop: asyncio.AbstractEventLoop | None = None
        self._records: dict[UUID, _TaskRecord] = {}
        self._running: dict[UUID, asyncio.Task[Any]] = {}

    def spawn[T](
        self,
        factory: Callable[[], Coroutine[Any, Any, T]],
        *,
        retain_result: bool = True,
    ) -> BackgroundTaskHandle[T] | None:
        """准入后才调用工厂；关闭或容量不足时拒绝，不创建协程。"""
        loop = asyncio.get_running_loop()
        if self._loop is not None and self._loop is not loop:
            raise RuntimeError("背景任务组不能跨事件循环使用")
        if (
            self.closing
            or len(self._running) >= self.max_running
            or len(self._records) >= self.max_retained
        ):
            logger.warning(f"背景任务组 {self.name} 拒绝任务：已关闭或容量已满")
            return None
        self._loop = loop
        handle = BackgroundTaskHandle[T](self, uuid4())
        record = _TaskRecord(handle, retain_result)

        async def run() -> T:
            return await factory()

        task = loop.create_task(run(), name=self.name)
        self._records[handle.uid] = record
        self._running[handle.uid] = task
        task.add_done_callback(lambda done: self._finish(record, done))
        if self.execution_timeout is not None:
            record.deadline = loop.call_later(
                self.execution_timeout, self._timeout, handle.uid
            )
        return handle

    def query[T](self, handle: BackgroundTaskHandle[T]) -> BackgroundTaskInfo | None:
        """查询不提取、不延长结果期限；已提取或已丢弃返回 None。"""
        self._check_owner(handle)
        record = self._records.get(handle.uid)
        if record is None:
            return None
        return BackgroundTaskInfo(
            handle.uid,
            record.outcome.state if record.outcome else BackgroundTaskState.RUNNING,
            record.retain_result,
        )

    def try_take[T](
        self, handle: BackgroundTaskHandle[T]
    ) -> TaskOutcome[T] | TaskPending:
        """原子提取并删除一项结果；不存在或未保留的结果抛出 KeyError。"""
        self._check_owner(handle)
        record = self._records[handle.uid]
        if not record.retain_result:
            raise KeyError("该任务未申请保留结果")
        if record.outcome is None:
            return PENDING
        outcome = cast(TaskOutcome[T], record.outcome)
        self._discard(handle.uid, log_error=False)
        return outcome

    async def wait_take[T](
        self, handle: BackgroundTaskHandle[T], *, timeout: float | None = None
    ) -> TaskOutcome[T]:
        """等待并提取；等待超时或调用方取消不影响任务及结果所有权。"""
        self._check_owner(handle)
        if not self._records[handle.uid].retain_result:
            raise KeyError("该任务未申请保留结果")
        if not await handle.wait_done(timeout):
            raise TimeoutError("等待背景任务结果超时")
        result = self.try_take(handle)
        assert isinstance(result, TaskOutcome)
        return result

    async def drain(self, timeout: float | None = None) -> bool:
        """等待当前及等待期间新接纳的执行退出，不提取结果、不取消任务。"""
        loop = asyncio.get_running_loop()
        deadline = None if timeout is None else loop.time() + timeout
        while self._running:
            remaining = None if deadline is None else max(0, deadline - loop.time())
            _, pending = await asyncio.wait(
                tuple(self._running.values()), timeout=remaining
            )
            if pending:
                return False
            # done 回调可能尚未轮到；下一轮需要看到已更新的运行集合。
            await asyncio.sleep(0)
        return True

    def _check_owner[T](self, handle: BackgroundTaskHandle[T]) -> None:
        if handle.group is not self:
            raise ValueError("任务不属于此任务组")

    def _cancel(self, uid: UUID) -> None:
        task = self._running.get(uid)
        if task is not None and not task.done() and not task.cancelling():
            task.cancel()

    def _timeout(self, uid: UUID) -> None:
        task = self._running.get(uid)
        if task is not None and not task.done():
            self._records[uid].timed_out = True
            self._cancel(uid)

    def _finish(self, record: _TaskRecord, task: asyncio.Task[Any]) -> None:
        uid = record.handle.uid
        self._running.pop(uid)
        if record.deadline is not None:
            record.deadline.cancel()
        outcome: TaskOutcome[Any]
        if task.cancelled():
            outcome = TaskOutcome(
                BackgroundTaskState.CANCELLED, error=asyncio.CancelledError()
            )
        elif (error := task.exception()) is not None:
            outcome = TaskOutcome(BackgroundTaskState.FAILED, error=error)
        else:
            outcome = TaskOutcome(BackgroundTaskState.SUCCEEDED, value=task.result())
        if record.timed_out:
            outcome = TaskOutcome(
                BackgroundTaskState.TIMED_OUT, error=TimeoutError("背景任务执行超时")
            )
        record.outcome = outcome
        record.handle._completed.set()
        if self.closing or not record.retain_result:
            self._discard(uid)
        else:
            assert self._loop is not None
            record.expires = self._loop.call_later(self.result_ttl, self._discard, uid)
        if self.closing and not self._running:
            self._owner._remove(self)

    def _discard(self, uid: UUID, *, log_error: bool = True) -> None:
        record = self._records.pop(uid, None)
        if record is None:
            return
        if record.expires is not None:
            record.expires.cancel()
        if (
            log_error
            and record.outcome is not None
            and record.outcome.state
            in {BackgroundTaskState.FAILED, BackgroundTaskState.TIMED_OUT}
        ):
            logger.warning(
                f"背景任务组 {self.name} 未提取的任务异常：{record.outcome.error}"
            )

    def _close(self) -> None:
        self.closing = True
        for uid in tuple(self._running):
            self._cancel(uid)
        for uid in tuple(self._records):
            if uid not in self._running:
                self._discard(uid)
        if not self._running:
            self._owner._remove(self)


class BackgroundTaskRegistry:
    """应用级任务组申请与注销；注销超时仍持有尚未退出的任务组。"""

    def __init__(self) -> None:
        self._groups: dict[str, BackgroundTaskGroup] = {}
        self._closing = False

    def register_group(
        self,
        name: str,
        *,
        max_running: int,
        max_retained: int,
        execution_timeout: float | None = None,
        result_ttl: float = 300,
    ) -> BackgroundTaskGroup:
        """名称在当前管理器内唯一；关闭开始后拒绝申请。"""
        if self._closing:
            raise RuntimeError("背景任务管理器已关闭")
        if name in self._groups:
            raise ValueError(f"背景任务组已存在：{name}")
        group = BackgroundTaskGroup(
            self,
            name,
            max_running=max_running,
            max_retained=max_retained,
            execution_timeout=execution_timeout,
            result_ttl=result_ttl,
        )
        self._groups[name] = group
        return group

    def get_group(self, name: str) -> BackgroundTaskGroup | None:
        return self._groups.get(name)

    async def unregister_group(
        self, group: BackgroundTaskGroup, *, timeout: float | None = None
    ) -> bool:
        """停止接纳、取消并等待；False 表示仍有执行在清理，引用不会提前释放。"""
        if group._owner is not self:
            raise ValueError("任务组不属于此管理器")
        group._close()
        return await group.drain(timeout)

    async def shutdown(self, *, timeout: float | None = None) -> bool:
        """关闭全部组；统一等待期限，超时或调用方取消都不会丢失在途引用。"""
        self._closing = True
        groups = tuple(self._groups.values())
        for group in groups:
            group._close()
        loop = asyncio.get_running_loop()
        deadline = None if timeout is None else loop.time() + timeout
        completed = True
        for group in groups:
            remaining = None if deadline is None else max(0, deadline - loop.time())
            if not await group.drain(remaining):
                completed = False
        return completed

    def _remove(self, group: BackgroundTaskGroup) -> None:
        if self._groups.get(group.name) is group:
            del self._groups[group.name]


BackgroundTaskManager = BackgroundTaskRegistry()
