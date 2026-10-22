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


def filter_community_notification_results(
    results: list[dict[str, object]],
) -> list[dict[str, object]]:
    """占位结果不参与摘要和独立通知。"""

    return [item for item in results if not item.get("_notification_only")]


class ReportRenderer(Protocol):
    """编排只消费内容端口，模板、字体和图片由实现管理。"""

    def community_summary(
        self, results: list[dict[str, object]]
    ) -> TaskReportSummary: ...

    def community_payload(self, results: list[dict[str, object]]) -> NotifyPayload: ...

    def append_summary(
        self, payload: NotifyPayload, summary: TaskReportSummary
    ) -> NotifyPayload: ...

    def prepare_payloads(
        self,
        payload: NotifyPayload,
        *,
        summary: TaskReportSummary,
        embedded_summary: str = "",
    ) -> tuple[NotifyPayload, NotifyPayload]: ...


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
