"""任务通知的策略、请求和独立运行状态；不依赖任务执行对象。"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal, Protocol

from app.models.notification import NotifyPayload
from app.models.notification_channel import DispatchResult, NotifyTarget

TaskNotificationChange = Literal["results", "delivery"]


@dataclass
class TaskNotificationState:
    results: list[dict[str, object]] = field(default_factory=list, repr=False)
    summary_consumed: bool = False
    delivered: set[str] = field(default_factory=set)
    pending: tuple[str, ...] = ()


@dataclass(frozen=True)
class TaskReportPolicy:
    result_time: Literal["不推送", "任何时刻", "仅失败时"]
    community_enabled: bool
    wait_seconds: float


@dataclass(frozen=True)
class TaskReportSummary:
    text: str = ""
    markdown: str = ""


@dataclass(frozen=True)
class TaskReportRequest:
    payload: NotifyPayload
    targets: tuple[NotifyTarget, ...]
    policy: TaskReportPolicy
    embedded_summary: str = ""
    embedded_markdown: str | None = None
    attempts: int = 1
    retry_delay: float = 0


class NotificationDispatcher(Protocol):
    async def __call__(
        self,
        payload: NotifyPayload,
        targets: Iterable[NotifyTarget],
        *,
        attempts: int = 1,
        retry_delay: float = 0,
        skip_channel_ids: Iterable[str] = (),
    ) -> DispatchResult: ...
