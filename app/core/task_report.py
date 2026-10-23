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

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import partial

from app.config import config_manager
from app.core.config import Config
from app.core.notification_report import (
    NOTIFICATION_FAST_PATH_WAIT_SECONDS,
    TaskReportCoordinator,
    TaskReportDependencies,
)
from app.core.notification_tasks import (
    consume_notification_result,
    current_notification_task_id,
    drain_notifications,
    publish_notification_failure,
    shutdown_notifications,
    spawn_notification,
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
    TaskNotificationState,
    TaskReportPolicy,
    TaskReportRequest,
    TaskReportSummary,
)
from app.models.task import TaskItem
from app.services.notification_report import DefaultReportRenderer
from app.utils import get_logger

logger = get_logger("任务报告")


def read_task_report_policy() -> TaskReportPolicy:
    """每次报告入口读取一次策略；后台补发作为下一次通知重新读取。"""

    return TaskReportPolicy(
        result_time=Config.setting.Notify.SendTaskResultTime,
        community_enabled=Config.ToolsConfig.GameSign.NotifyEnabled,
        wait_seconds=NOTIFICATION_FAST_PATH_WAIT_SECONDS,
    )


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
    report_failure: Callable[[DispatchResult], Awaitable[None]] | None = None,
) -> TaskReportCoordinator:
    return TaskReportCoordinator(
        state=state,
        community_pending=community_pending,
        dependencies=TaskReportDependencies(
            dispatch=dispatch,
            renderer=DefaultReportRenderer(),
            read_policy=read_task_report_policy,
            prepare_targets=_prepare_community_targets,
            report_failure=report_failure
            if report_failure is not None
            else partial(publish_notification_failure, task_id=task_id),
            report_supplement_failure=_report_supplement_failure,
            spawn=partial(
                spawn_notification,
                task_id=task_id,
                name="task-community-notification",
            ),
        ),
    )


def create_task_report_coordinator(task_info: TaskItem) -> TaskReportCoordinator:
    """任务启动时绑定独立通知状态，协调器不持有任务执行对象。"""

    return _create_coordinator(
        state=task_info.notification_state,
        task_id=task_info.task_id,
        community_pending=True,
        report_failure=partial(
            publish_notification_failure,
            task_id=task_info.task_id,
            system_notice=True,
        ),
    )


def receive_task_community_results(
    coordinator: TaskReportCoordinator, results: list[dict[str, object]] | None
) -> None:
    """签到业务输出在装配入口转为通知快照，协调器只消费机器状态。"""

    coordinator.receive(
        community_notification_results(results) if results is not None else None
    )


@dataclass(frozen=True)
class PreparedTaskReport:
    """装配边界返回的单次报告上下文，重用同一策略完成判断与发送。"""

    coordinator: TaskReportCoordinator
    policy: TaskReportPolicy

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


def prepare_task_report(task_info: TaskItem | None = None) -> PreparedTaskReport:
    coordinator = getattr(task_info, "community_sign_notification", None)
    if coordinator is None:
        batch_task_id = current_notification_task_id()
        task_id = (
            task_info.task_id if task_info is not None else None
        ) or batch_task_id
        coordinator = _create_coordinator(
            state=(
                task_info.notification_state
                if task_info is not None
                else TaskNotificationState()
            ),
            task_id=task_id,
            report_failure=(
                partial(
                    publish_notification_failure,
                    task_id=task_id,
                    system_notice=True,
                )
                if task_info is not None or batch_task_id
                else None
            ),
        )
    return PreparedTaskReport(
        coordinator=coordinator,
        policy=read_task_report_policy(),
    )


async def drain_task_community_notifications(timeout: float) -> bool:
    """兼容旧入口；电源动作现在同时等待主报告、统计、补发与失败反馈。"""
    return await drain_notifications(timeout)


async def shutdown_community_notifications() -> None:
    """退出时取消并等待任务报告补发，然后才能释放共享连接。"""

    await shutdown_notifications()


async def dispatch_task_notification(
    payload: NotifyPayload,
    targets: list[NotifyTarget],
    *,
    task_info: object | None = None,
    immediate: bool = True,
) -> DispatchResult:
    """统计与即时提醒准备后立即托管；失败反馈不阻塞业务，最终报告另行暂存。"""

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
