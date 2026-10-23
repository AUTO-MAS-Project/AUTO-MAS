"""业务与插件消费的通知能力；实现和生命周期由宿主负责。"""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from app.models.notification import (
    NotificationImage,
    NotifyPayload,
    WebhookTargetSnapshot,
)
from app.models.notification_channel import (
    DispatchResult,
    EmptyPolicy,
    NotificationSourceConfig,
    NotifyTarget,
    RecruitmentNotificationConfig,
    UserNotificationConfig,
)
from app.models.notification_community import CommunityNotificationResult
from app.models.notification_report import TaskReportSummary, TaskResultReport

if TYPE_CHECKING:
    from app.models.task import TaskItem


class NotificationService(Protocol):
    """宿主提供的业务发送能力；不暴露渠道资源的启停和登记。"""

    async def send_global(
        self,
        payload: NotifyPayload,
        *,
        include_system: bool = False,
        empty_policy: EmptyPolicy = "send",
        system_timeout_seconds: int | None = None,
        attempts: int = 1,
        retry_delay: float = 0,
    ) -> DispatchResult: ...

    async def send_user(
        self,
        payload: NotifyPayload,
        user_config: NotificationSourceConfig,
        *,
        attempts: int = 1,
        retry_delay: float = 0,
    ) -> DispatchResult: ...

    async def send_statistics(
        self,
        payload: NotifyPayload,
        user_config: UserNotificationConfig | None,
        *,
        global_empty_policy: EmptyPolicy = "send",
        compact_summary: bool = False,
        attempts: int = 1,
        retry_delay: float = 0,
    ) -> DispatchResult: ...

    async def push_proxy_result(
        self,
        *,
        title: str,
        report: TaskResultReport,
        task_info: TaskItem | None = None,
        result_template: str = "general_result.html",
        signature_sep: str = "\n\n",
        images: Sequence[NotificationImage] = (),
        include_system: bool = True,
    ) -> DispatchResult: ...


@dataclass(frozen=True)
class LocalNotice:
    title: str
    message: str
    ticker: str
    duration_seconds: int


class LocalNotifier(Protocol):
    async def send_notice(self, notice: LocalNotice) -> None: ...


class PreparedReport(Protocol):
    def should_send(
        self, *, uncompleted_count: int, embedded_summary: bool = False
    ) -> bool: ...

    def community_summary(self) -> TaskReportSummary: ...

    async def dispatch(
        self,
        payload: NotifyPayload,
        targets: list[NotifyTarget],
        *,
        summary_text: str = "",
        attempts: int = 1,
        retry_delay: float = 0,
    ) -> DispatchResult: ...


class TaskNotifications(NotificationService, LocalNotifier, Protocol):
    """现役任务消费的目标选择和报告能力；批次仍由任务生命周期界定。"""

    def global_target(
        self,
        *,
        include_system: bool = False,
        empty_policy: EmptyPolicy = "send",
        system_timeout_seconds: int | None = None,
    ) -> NotifyTarget: ...

    def statistic_targets(
        self,
        user_config: UserNotificationConfig | None,
        *,
        global_empty_policy: EmptyPolicy = "send",
        compact_summary: bool = False,
    ) -> list[NotifyTarget]: ...

    def user_statistic_targets(
        self, user_config: UserNotificationConfig | None
    ) -> list[NotifyTarget]: ...

    def recruitment_targets(
        self, user_config: RecruitmentNotificationConfig | None
    ) -> list[NotifyTarget]: ...

    def failure_targets(self) -> list[NotifyTarget]: ...

    def prepare_task_report(
        self, task_info: TaskItem | None = None
    ) -> PreparedReport: ...

    async def push_statistics_report(
        self,
        *,
        payload: NotifyPayload,
        user_config: UserNotificationConfig | None,
        task_info: TaskItem,
        compact_summary: bool = False,
    ) -> DispatchResult: ...

    async def dispatch_task_notification(
        self,
        payload: NotifyPayload,
        targets: list[NotifyTarget],
        *,
        task_info: TaskItem | None = None,
        immediate: bool = True,
    ) -> DispatchResult: ...

    def task_notification_batch(
        self, *, task_id: str | None
    ) -> AbstractContextManager[None]: ...


class WebhookTester(Protocol):
    async def test_webhook(
        self, payload: NotifyPayload, webhook: WebhookTargetSnapshot
    ) -> None: ...


class CommunityNotifier(Protocol):
    async def send(
        self, results: tuple[CommunityNotificationResult, ...]
    ) -> list[str]: ...

    async def submit(
        self, results: tuple[CommunityNotificationResult, ...]
    ) -> list[str] | None: ...

    async def drain(self, timeout: float) -> bool: ...
