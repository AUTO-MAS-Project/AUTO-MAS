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

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import partial

from app.config import config_manager
from app.core import Notify
from app.core.notify import report as _notification_report
from app.core.notify.coordinator import TaskReportCoordinator, TaskReportDependencies
from app.models.notification import NotifyPayload
from app.models.notification.channel import DispatchResult, NotifyTarget
from app.models.notification.community import community_notification_results
from app.models.notification.report import (
    TaskNotificationState,
    TaskReportPolicy,
    TaskReportRequest,
)
from app.models.task import TaskItem


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
            dispatch=Notify.dispatch,
            renderer=_notification_report.DefaultReportRenderer(),
            read_policy=Notify.read_task_report_policy,
            prepare_targets=lambda: (Notify.global_target(include_system=True),),
            report_failure=report_failure
            if report_failure is not None
            else Notify.tasks.publish_notification_failure,
            report_supplement_failure=Notify.report_community_failure,
            spawn=partial(
                Notify.tasks.spawn_notification,
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
            Notify.tasks.publish_notification_failure,
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

    def should_send(self, *, uncompleted_count: int) -> bool:
        return self.coordinator.should_send_result(
            policy=self.policy,
            uncompleted_count=uncompleted_count,
        )

    async def dispatch(
        self,
        payload: NotifyPayload,
        targets: list[NotifyTarget],
    ) -> DispatchResult:
        request = TaskReportRequest(
            payload=payload,
            targets=tuple(targets),
            policy=self.policy,
        )

        async def deliver() -> DispatchResult:
            try:
                return await self.coordinator.dispatch_report(request)
            finally:
                self.coordinator.reports_pending -= 1
                self.coordinator.schedule_supplement()

        # 显式配置事务保持同 Task 执行；常规脚本批次在完整收尾后交给宿主。
        if not config_manager.in_transaction and Notify.tasks.submit_task_notification(
            deliver
        ):
            self.coordinator.reports_pending += 1
            return DispatchResult(queued=True)
        return await self.coordinator.dispatch_report(request)


def prepare_task_report(task_info: TaskItem | None = None) -> PreparedTaskReport:
    coordinator = getattr(task_info, "community_sign_notification", None)
    if coordinator is None:
        batch_task_id = Notify.tasks.current_notification_task_id()
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
                    Notify.tasks.publish_notification_failure,
                    system_notice=True,
                )
                if task_info is not None or batch_task_id
                else None
            ),
        )
    return PreparedTaskReport(
        coordinator=coordinator,
        policy=Notify.read_task_report_policy(),
    )


async def dispatch_task_notification(
    payload: NotifyPayload,
    targets: list[NotifyTarget],
    *,
    task_info: TaskItem | None = None,
) -> DispatchResult:
    """统计与即时提醒准备后立即托管；失败反馈不阻塞业务，最终报告另行暂存。"""

    prepared_targets = tuple(targets)
    task_id = (
        task_info.task_id if task_info is not None else None
    ) or Notify.tasks.current_notification_task_id()

    async def deliver() -> DispatchResult:
        result = await Notify.dispatch(payload, prepared_targets)
        Notify.tasks.consume_notification_result(result, task_id=task_id)
        return result

    if not config_manager.in_transaction and Notify.tasks.submit_task_notification(
        deliver, immediate=True
    ):
        return DispatchResult(queued=True)
    return await deliver()
