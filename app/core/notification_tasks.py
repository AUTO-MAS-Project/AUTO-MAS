"""任务通知的宿主所有权：固定输入后暂存，业务收尾完成后按序投递。"""

import asyncio
from collections.abc import Callable, Coroutine, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from app.models.notification_channel import DispatchResult
from app.runtime_tasks import RuntimeTasks
from app.utils import get_logger

logger = get_logger("任务通知")

type NotificationDelivery = Callable[[], Coroutine[Any, Any, DispatchResult]]

_PENDING_NOTIFICATIONS: set[asyncio.Task[None]] = set()


def spawn_notification(
    coroutine: Coroutine[Any, Any, None], *, task_id: str | None
) -> asyncio.Task[None] | None:
    task = RuntimeTasks.spawn(coroutine, name=f"task-notification:{task_id}")
    if task is not None:
        _PENDING_NOTIFICATIONS.add(task)
        task.add_done_callback(_PENDING_NOTIFICATIONS.discard)
    return task


async def publish_notification_failure(
    result: DispatchResult, *, task_id: str | None, system_notice: bool = False
) -> None:
    """统一消费投递失败；页面反馈故障不向业务传播。"""

    if not result.failed:
        return
    failed_channels = tuple(dict.fromkeys(result.failed))
    logger.warning(f"任务通知未送达: {'、'.join(failed_channels)}")
    title = "部分通知发送失败" if result.succeeded else "通知发送失败"
    try:
        if system_notice:
            # 后台发送可晚于 task.completed；系统常驻订阅不会随任务标签页退订。
            from app.core.config import Config

            await Config.push_system_notice(
                level="warning",
                title=title,
                lines=[f"发送失败的渠道：{'、'.join(failed_channels)}"],
            )
        elif task_id:
            from app.core.ws import Publisher, protocol
            from app.models.schema import WSTaskNoticeData

            await Publisher.send(
                id=str(task_id),
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(
                    level="warning", message=f"{title}：{'、'.join(failed_channels)}"
                ),
            )
    except Exception as exc:
        logger.warning(f"发送通知失败提示到前端时出现异常: {type(exc).__name__}")


def consume_notification_result(result: DispatchResult, *, task_id: str | None) -> None:
    if result.failed:
        spawn_notification(
            publish_notification_failure(result, task_id=task_id, system_notice=True),
            task_id=task_id,
        )


@dataclass
class TaskNotificationBatch:
    task_id: str | None
    deliveries: list[NotificationDelivery] = field(default_factory=list)
    closed: bool = False

    async def deliver(self) -> None:
        # 暂存的最终报告保持准备顺序；一个通知异常不丢掉后续通知。
        for delivery in self.deliveries:
            try:
                await delivery()
            except Exception as exc:
                logger.warning(f"任务通知执行失败: {type(exc).__name__}")
                consume_notification_result(
                    DispatchResult(failed=("任务通知",)), task_id=self.task_id
                )
        self.deliveries.clear()


_CURRENT_BATCH: ContextVar[TaskNotificationBatch | None] = ContextVar(
    "task_notification_batch", default=None
)


@contextmanager
def task_notification_batch(*, task_id: str | None) -> Iterator[None]:
    """覆盖整个脚本执行及收尾；子账号沿用同一批次，退出后才注册投递。"""

    batch = TaskNotificationBatch(task_id=task_id)
    token = _CURRENT_BATCH.set(batch)
    try:
        yield
    finally:
        _CURRENT_BATCH.reset(token)
        batch.closed = True
        if batch.deliveries:
            spawn_notification(batch.deliver(), task_id=batch.task_id)


def current_notification_task_id() -> str | None:
    batch = _CURRENT_BATCH.get()
    return batch.task_id if batch is not None else None


def submit_task_notification(
    delivery: NotificationDelivery, *, immediate: bool = False
) -> bool:
    """接管已固定的请求；即时提醒立即注册，其余在脚本完整收尾后注册。"""

    batch = _CURRENT_BATCH.get()
    if batch is None or batch.closed:
        return False
    if immediate:
        spawn_notification(
            TaskNotificationBatch(
                task_id=batch.task_id, deliveries=[delivery], closed=True
            ).deliver(),
            task_id=batch.task_id,
        )
    else:
        batch.deliveries.append(delivery)
    return True


async def drain_notifications(timeout: float) -> bool:
    """电源动作前有限等待全部任务通知与反馈；超时不取消投递。"""

    deadline = asyncio.get_running_loop().time() + timeout
    while tasks := {task for task in _PENDING_NOTIFICATIONS if not task.done()}:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            return False
        _, pending = await asyncio.wait(tasks, timeout=remaining)
        if pending:
            return False
    return True


async def shutdown_notifications() -> None:
    tasks = [task for task in _PENDING_NOTIFICATIONS if not task.done()]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
