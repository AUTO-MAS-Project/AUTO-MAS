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

"""任务报告入口：装配策略、通知状态、投递器和任务页面反馈。"""

import asyncio
from collections.abc import Coroutine
from dataclasses import dataclass, replace
from functools import partial
from typing import Any

from app.config import config_manager
from app.core.config import Config
from app.core.notification_report import (
    NOTIFICATION_FAST_PATH_WAIT_SECONDS,
    TaskReportCoordinator,
    TaskReportDependencies,
)
from app.core.notification_tasks import (
    _PENDING_NOTIFICATIONS,
    consume_notification_result,
    current_notification_task_id,
    drain_notifications,
    publish_notification_failure,
    shutdown_notifications,
    submit_task_notification,
)
from app.core.notify import (
    DispatchResult,
    Notifier,
    NotifyTarget,
    dispatch,
    global_target,
)
from app.models.notification import NotifyPayload
from app.models.notification_community import community_notification_results
from app.models.notification_report import (
    TaskNotificationChange,
    TaskNotificationState,
    TaskReportPolicy,
    TaskReportRequest,
    TaskReportSummary,
    TaskResultHint,
)
from app.models.task import TaskItem
from app.runtime_tasks import RuntimeTasks
from app.services.notification_report import DefaultReportRenderer
from app.utils import get_logger

logger = get_logger("任务报告")

_PENDING_TASK_COMMUNITY_NOTIFICATIONS = _PENDING_NOTIFICATIONS


def read_task_report_policy() -> TaskReportPolicy:
    """每次报告入口读取一次策略；后台补发作为下一次通知重新读取。"""

    return TaskReportPolicy(
        result_time=Config.setting.Notify.SendTaskResultTime,
        community_enabled=Config.ToolsConfig.GameSign.NotifyEnabled,
        wait_seconds=NOTIFICATION_FAST_PATH_WAIT_SECONDS,
    )


def _spawn_community_notification(
    coroutine: Coroutine[Any, Any, None], *, task_id: str | None
) -> asyncio.Task[None] | None:
    task = RuntimeTasks.spawn(coroutine, name=f"task-community-notification:{task_id}")
    if task is not None:
        _PENDING_TASK_COMMUNITY_NOTIFICATIONS.add(task)
        task.add_done_callback(_PENDING_TASK_COMMUNITY_NOTIFICATIONS.discard)
    return task


async def _report_supplement_failure(
    result: DispatchResult, *, results_saved: bool
) -> None:
    from app.core.community_notify import report_community_notification_failure

    await report_community_notification_failure(
        list(result.failed), results_saved=results_saved
    )


def _prepare_community_targets() -> tuple[NotifyTarget, ...]:
    return (global_target(include_system=True),)


def _create_coordinator(
    *,
    state: TaskNotificationState,
    task_id: str | None,
    community_pending: bool = False,
) -> TaskReportCoordinator:
    return TaskReportCoordinator(
        state=state,
        community_pending=community_pending,
        dependencies=TaskReportDependencies(
            dispatch=dispatch,
            renderer=DefaultReportRenderer(),
            read_policy=read_task_report_policy,
            prepare_targets=_prepare_community_targets,
            report_failure=partial(_publish_task_notification_failure, task_id=task_id),
            report_supplement_failure=_report_supplement_failure,
            spawn=partial(_spawn_community_notification, task_id=task_id),
        ),
    )


def create_task_report_coordinator(task_info: TaskItem) -> TaskReportCoordinator:
    """任务启动时绑定独立通知状态，协调器不持有任务执行对象。"""

    return _create_coordinator(
        state=task_info.notification_state,
        task_id=task_info.task_id,
        community_pending=True,
    )


def receive_task_community_results(
    coordinator: TaskReportCoordinator, results: list[dict[str, object]] | None
) -> None:
    """签到业务输出在装配入口转为通知快照，协调器只消费机器状态。"""

    coordinator.receive(
        community_notification_results(results) if results is not None else None
    )


def _notification_state(task_info: object | None) -> TaskNotificationState:
    if task_info is None:
        return TaskNotificationState()
    state = getattr(task_info, "notification_state", None)
    if state is not None:
        return state

    # 旧对象只在边界投影历史字段，不强行添加属性，也不覆盖显式通知状态。
    return TaskNotificationState(
        results=community_notification_results(
            getattr(
                task_info,
                "community_results",
                getattr(task_info, "game_sign_results", ()),
            )
        ),
        summary_consumed=getattr(
            task_info,
            "community_summary_consumed",
            getattr(task_info, "game_sign_summary_consumed", False),
        ),
        delivered=set(getattr(task_info, "game_sign_summary_delivered", ())),
        pending=tuple(getattr(task_info, "game_sign_summary_pending", ())),
    )


def _sync_legacy_state(
    task_info: object, state: TaskNotificationState, change: TaskNotificationChange
) -> None:
    if change == "results":
        setattr(
            task_info,
            "game_sign_results"
            if (
                hasattr(task_info, "game_sign_results")
                and not hasattr(task_info, "community_results")
            )
            else "community_results",
            [item.to_legacy() for item in state.results],
        )
        return
    setattr(task_info, "game_sign_summary_delivered", set(state.delivered))
    setattr(task_info, "game_sign_summary_pending", state.pending)
    setattr(
        task_info,
        (
            "community_summary_consumed"
            if hasattr(task_info, "community_summary_consumed")
            else "game_sign_summary_consumed"
        ),
        state.summary_consumed,
    )


@dataclass(frozen=True)
class PreparedTaskReport:
    """装配边界返回的单次报告上下文，重用同一策略完成判断与发送。"""

    coordinator: TaskReportCoordinator
    policy: TaskReportPolicy
    has_task: bool = False

    def should_send(
        self, *, uncompleted_count: int, embedded_summary: bool = False
    ) -> bool:
        return self.coordinator.should_send_result(
            policy=self.policy,
            uncompleted_count=uncompleted_count,
            embedded_summary=embedded_summary,
        )

    def community_summary(self) -> TaskReportSummary:
        return self.coordinator.community_summary()

    async def dispatch(
        self,
        payload: NotifyPayload,
        targets: list[NotifyTarget],
        *,
        summary_text: str = "",
        attempts: int = 1,
        retry_delay: float = 0,
        notifier: Notifier | None = None,
    ) -> DispatchResult:
        request = TaskReportRequest(
            payload=payload,
            targets=tuple(targets),
            policy=self.policy,
            embedded_summary=summary_text,
            embedded_markdown=(summary_text if not self.has_task else None),
            attempts=attempts,
            retry_delay=retry_delay,
        )
        dispatcher = (
            partial(dispatch, notifier=notifier) if notifier is not None else None
        )

        async def deliver() -> DispatchResult:
            try:
                return await self.coordinator.dispatch_report(
                    request, dispatch=dispatcher
                )
            finally:
                self.coordinator.reports_pending -= 1
                self.coordinator.schedule_supplement()

        # 显式配置事务保持同 Task 执行；常规脚本批次在完整收尾后交给宿主。
        if not config_manager.in_transaction and submit_task_notification(deliver):
            self.coordinator.reports_pending += 1
            return DispatchResult(queued=True)
        return await self.coordinator.dispatch_report(request, dispatch=dispatcher)


def prepare_task_report(task_info: object | None = None) -> PreparedTaskReport:
    state = _notification_state(task_info)
    coordinator = getattr(task_info, "community_sign_notification", None)
    if coordinator is None:
        coordinator = _create_coordinator(
            state=state, task_id=getattr(task_info, "task_id", None)
        )
    if task_info is not None and not hasattr(task_info, "notification_state"):
        # 旧对象通过显式观察端口接收结果与投递状态；后台补发沿用同一适配。
        observer = partial(_sync_legacy_state, task_info)
        coordinator.dependencies = replace(
            coordinator.dependencies, state_changed=observer
        )
        if coordinator.completed.is_set():
            coordinator.notify_state_changed("results")
    return PreparedTaskReport(
        coordinator=coordinator,
        policy=read_task_report_policy(),
        has_task=task_info is not None,
    )


def should_send_result(
    message: TaskResultHint, *, task_info: object | None = None
) -> bool:
    """兼容旧入口；新的报告入口重用 PreparedTaskReport 的策略快照。"""

    return prepare_task_report(task_info).should_send(
        uncompleted_count=message.get("uncompleted_count", 0),
        embedded_summary=bool(message.get("game_sign_summary", False)),
    )


async def dispatch_task_report(
    payload: NotifyPayload,
    targets: list[NotifyTarget],
    task_info: object | None,
    *,
    summary_text: str = "",
    attempts: int = 1,
    retry_delay: float = 0,
    notifier: Notifier | None = None,
) -> DispatchResult:
    """兼容既有任务报告调用；将完整任务对象留在装配边界。"""

    return await prepare_task_report(task_info).dispatch(
        payload,
        targets,
        summary_text=summary_text,
        attempts=attempts,
        retry_delay=retry_delay,
        notifier=notifier,
    )


async def drain_task_community_notifications(timeout: float) -> bool:
    """兼容旧入口；电源动作现在同时等待主报告、统计、补发与失败反馈。"""
    return await drain_notifications(timeout)


async def shutdown_community_notifications() -> None:
    """退出时取消并等待任务报告补发，然后才能释放共享连接。"""

    await shutdown_notifications()


async def _publish_task_notification_failure(
    result: DispatchResult, *, task_id: str | None
) -> None:
    await publish_notification_failure(result, task_id=task_id)


async def dispatch_task_notification(
    payload: NotifyPayload,
    targets: list[NotifyTarget],
    *,
    task_info: object | None = None,
    immediate: bool = False,
) -> DispatchResult:
    """统计与即时提醒共用结果消费；快照先于入队，失败反馈不阻塞业务。"""

    prepared_targets = tuple(targets)
    task_id = getattr(task_info, "task_id", None) or current_notification_task_id()

    async def deliver() -> DispatchResult:
        result = await dispatch(payload, prepared_targets)
        consume_notification_result(result, task_id=task_id)
        return result

    if not config_manager.in_transaction and submit_task_notification(
        deliver, immediate=immediate
    ):
        return DispatchResult(queued=True)
    return await deliver()
