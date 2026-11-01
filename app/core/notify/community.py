"""社区通知编排；内容、开关、投递与后台任务所有权均通过端口提供。"""

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from app.core.notify.coordinator import (
    NOTIFICATION_RETRY_DELAY_SECONDS,
    NOTIFICATION_SEND_ATTEMPTS,
    CommunityFailureReporter,
    schedule_notification_feedback,
)
from app.models.notification import NotifyPayload
from app.models.notification.channel import DispatchResult, NotifyTarget
from app.models.notification.community import CommunityNotificationResult
from app.models.notification.report import NotificationDispatcher
from app.utils import get_logger

logger = get_logger("社区通知")


@dataclass(frozen=True)
class CommunityNotificationDependencies:
    dispatch: NotificationDispatcher
    prepare_targets: Callable[[], tuple[NotifyTarget, ...]]
    render: Callable[[tuple[CommunityNotificationResult, ...]], NotifyPayload]
    enabled: Callable[[], bool]
    report_failure: CommunityFailureReporter
    spawn: Callable[[Coroutine[Any, Any, list[str]]], asyncio.Task[list[str]] | None]
    fast_path_seconds: float


class CommunityNotificationCoordinator:
    def __init__(self, dependencies: CommunityNotificationDependencies) -> None:
        self.dependencies = dependencies
        self._pending: set[asyncio.Task[list[str]]] = set()

    async def _send(
        self, results: tuple[CommunityNotificationResult, ...]
    ) -> list[str]:
        if not results:
            return []
        result = await self.dependencies.dispatch(
            self.dependencies.render(results),
            self.dependencies.prepare_targets(),
            attempts=NOTIFICATION_SEND_ATTEMPTS,
            retry_delay=NOTIFICATION_RETRY_DELAY_SECONDS,
        )
        if result.failed:
            self._schedule_feedback(result)
        return list(result.failed)

    def _schedule_feedback(self, result: DispatchResult) -> None:
        task = schedule_notification_feedback(
            lambda: self.dependencies.report_failure(result, results_saved=True),
            spawn=self.dependencies.spawn,
            result=[],
            logger=logger,
            label="社区通知",
        )
        if task is not None:
            self._pending.add(task)
            task.add_done_callback(self._completed)

    async def send(self, results: tuple[CommunityNotificationResult, ...]) -> list[str]:
        if not self.dependencies.enabled():
            return []
        return await self._send(results)

    def _completed(self, task: asyncio.Task[list[str]]) -> None:
        self._pending.discard(task)
        if task.cancelled():
            return
        try:
            failed = task.result()
        except Exception as exc:
            logger.warning(f"后台社区通知发送失败: {type(exc).__name__}")
        else:
            if failed:
                logger.warning(f"后台社区通知部分失败: {'、'.join(failed)}")

    async def submit(
        self, results: tuple[CommunityNotificationResult, ...]
    ) -> list[str] | None:
        """短暂等待渠道结果；超时和请求取消均保留已注册的后台通知。"""

        if not self.dependencies.enabled():
            return []
        task = self.dependencies.spawn(self._send(results))
        if task is None:
            return ["通知服务"]
        self._pending.add(task)
        task.add_done_callback(self._completed)
        try:
            return await asyncio.wait_for(
                asyncio.shield(task), timeout=self.dependencies.fast_path_seconds
            )
        except asyncio.TimeoutError:
            logger.info("等待窗口内未返回，通知渠道仍在后台发送")
            return None
        except Exception as exc:
            logger.warning(f"社区通知服务异常: {type(exc).__name__}")
            return ["通知服务"]

    async def drain(self, timeout: float) -> bool:
        deadline = asyncio.get_running_loop().time() + timeout
        while pending := {task for task in self._pending if not task.done()}:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return False
            _, waiting = await asyncio.wait(pending, timeout=remaining)
            if waiting:
                return False
        return True
