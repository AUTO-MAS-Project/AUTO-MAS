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

from app.core.config import Config
from app.core.notification_report import (
    NOTIFICATION_FAST_PATH_WAIT_SECONDS,
    TaskReportCoordinator,
    TaskReportDependencies,
)
from app.core.notify import (
    DispatchResult,
    Notifier,
    NotifyTarget,
    dispatch,
    global_target,
)
from app.models.notification import NotifyPayload
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

_PENDING_TASK_COMMUNITY_NOTIFICATIONS: set[asyncio.Task[None]] = set()


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


def _notification_state(task_info: object | None) -> TaskNotificationState:
    if task_info is None:
        return TaskNotificationState()
    state = getattr(task_info, "notification_state", None)
    if state is not None:
        return state

    # 旧对象只在边界投影历史字段，不强行添加属性，也不覆盖显式通知状态。
    return TaskNotificationState(
        results=list(
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
            state.results,
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
        return await self.coordinator.dispatch_report(
            TaskReportRequest(
                payload=payload,
                targets=tuple(targets),
                policy=self.policy,
                embedded_summary=summary_text,
                embedded_markdown=(summary_text if not self.has_task else None),
                attempts=attempts,
                retry_delay=retry_delay,
            ),
            dispatch=partial(dispatch, notifier=notifier),
        )


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
            observer(coordinator.state, "results")
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
    """电源动作前有限等待签到补发，超时只停止等待，不取消投递。"""

    deadline = asyncio.get_running_loop().time() + timeout
    while tasks := {
        task for task in _PENDING_TASK_COMMUNITY_NOTIFICATIONS if not task.done()
    }:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            return False
        _, pending = await asyncio.wait(tasks, timeout=remaining)
        if pending:
            return False
    return True


async def shutdown_community_notifications() -> None:
    """退出时取消并等待任务报告补发，然后才能释放共享连接。"""

    tasks = [task for task in _PENDING_TASK_COMMUNITY_NOTIFICATIONS if not task.done()]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def _publish_task_notification_failure(
    result: DispatchResult, *, task_id: str | None
) -> None:
    """任务页面反馈在入口装配，不进入报告协调器。"""

    if not result.failed or not task_id:
        return

    from app.core.ws import Publisher, protocol
    from app.models.schema import WSTaskNoticeData

    failed_channels = tuple(dict.fromkeys(result.failed))
    title = "部分通知发送失败" if result.succeeded else "通知发送失败"
    message = f"{title}：{'、'.join(failed_channels)}"
    try:
        await Publisher.send(
            id=str(task_id),
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level="warning", message=message),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"发送通知失败提示到前端时出现异常: {exc}")
