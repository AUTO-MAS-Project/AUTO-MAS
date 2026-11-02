"""任务通知的宿主所有权：固定输入后暂存，业务收尾完成后按序投递。"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from app.core import RuntimeTasks
from app.models.notification.channel import DispatchResult
from app.utils import get_logger

logger = get_logger("任务通知")
type NotificationDelivery = Callable[[], Coroutine[Any, Any, DispatchResult]]


@dataclass
class TaskNotificationBatch:
    owner: NotificationTasks
    task_id: str | None
    deliveries: list[NotificationDelivery] = field(default_factory=list)
    closed: bool = False

    async def deliver(self) -> None:
        # 暂存的最终报告保持准备顺序；一个通知异常不丢掉后续通知。
        for delivery in self.deliveries:
            await self.owner._deliver_notification(delivery, task_id=self.task_id)
        self.deliveries.clear()


class NotificationTasks:
    """每个通知服务独立记录 drain 范围；后台任务的关闭仍由宿主统一拥有。"""

    def __init__(self) -> None:
        self._pending: set[asyncio.Task[None]] = set()
        self._current_batch: ContextVar[TaskNotificationBatch | None] = ContextVar(
            "task_notification_batch", default=None
        )

    def spawn_notification(
        self,
        coroutine: Coroutine[Any, Any, None],
        *,
        task_id: str | None,
        name: str = "task-notification",
    ) -> asyncio.Task[None] | None:
        task = RuntimeTasks.spawn(coroutine, name=f"{name}:{task_id}")
        if task is not None:
            self._pending.add(task)
            task.add_done_callback(self._pending.discard)
        return task

    async def publish_notification_failure(
        self, result: DispatchResult, *, system_notice: bool = False
    ) -> None:
        """统一消费投递失败；页面反馈故障不向业务传播。"""

        if not result.failed:
            return
        failed_channels = tuple(dict.fromkeys(result.failed))
        logger.warning(f"任务通知未送达: {'、'.join(failed_channels)}")
        title = "部分通知发送失败" if result.succeeded else "通知发送失败"
        try:
            if system_notice:
                from app.core import Notify

                # 后台发送可晚于 task.completed；系统常驻订阅不会随任务标签页退订。
                await Notify.push_system_notice(
                    level="warning",
                    title=title,
                    lines=[f"发送失败的渠道：{'、'.join(failed_channels)}"],
                )
        except Exception as exc:
            logger.warning(f"发送通知失败提示到前端时出现异常: {type(exc).__name__}")

    def consume_notification_result(
        self, result: DispatchResult, *, task_id: str | None
    ) -> None:
        if result.failed:
            self.spawn_notification(
                self.publish_notification_failure(result, system_notice=True),
                task_id=task_id,
            )

    async def _deliver_notification(
        self, delivery: NotificationDelivery, *, task_id: str | None
    ) -> None:
        try:
            await delivery()
        except Exception as exc:
            logger.warning(f"任务通知执行失败: {type(exc).__name__}")
            self.consume_notification_result(
                DispatchResult(failed=("任务通知",)), task_id=task_id
            )

    @contextmanager
    def task_notification_batch(self, *, task_id: str | None) -> Iterator[None]:
        """覆盖整个脚本执行及收尾；子账号沿用同一批次，退出后才注册投递。"""

        batch = TaskNotificationBatch(owner=self, task_id=task_id)
        token = self._current_batch.set(batch)
        try:
            yield
        finally:
            self._current_batch.reset(token)
            batch.closed = True
            if batch.deliveries:
                self.spawn_notification(batch.deliver(), task_id=batch.task_id)

    def current_notification_task_id(
        self,
    ) -> str | None:
        batch = self._current_batch.get()
        return batch.task_id if batch is not None else None

    def submit_task_notification(
        self, delivery: NotificationDelivery, *, immediate: bool = False
    ) -> bool:
        """接管已固定的请求；即时提醒立即注册，其余在脚本完整收尾后注册。"""

        batch = self._current_batch.get()
        if batch is None or batch.closed:
            return False
        if immediate:
            self.spawn_notification(
                self._deliver_notification(delivery, task_id=batch.task_id),
                task_id=batch.task_id,
            )
        else:
            batch.deliveries.append(delivery)
        return True

    async def drain_notifications(self, timeout: float) -> bool:
        """电源动作前有限等待全部任务通知与反馈；超时不取消投递。"""

        deadline = asyncio.get_running_loop().time() + timeout
        while tasks := {task for task in self._pending if not task.done()}:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return False
            _, pending = await asyncio.wait(tasks, timeout=remaining)
            if pending:
                return False
        return True
