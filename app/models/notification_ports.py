"""业务与插件消费的通知能力；实现和生命周期由宿主负责。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from app.models.notification import (
    NotificationImage,
    NotifyPayload,
    WebhookTargetSnapshot,
)
from app.models.notification_channel import (
    DispatchResult,
    EmptyPolicy,
    NotificationSourceConfig,
    UserNotificationConfig,
)
from app.models.notification_community import CommunityNotificationResult
from app.models.notification_report import TaskResultReport

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
        logger: Any | None = None,
        skip_debug_message: str | None = None,
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
