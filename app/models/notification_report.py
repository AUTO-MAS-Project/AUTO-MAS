"""任务通知的策略、请求和独立运行状态；不依赖任务执行对象。"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal, NotRequired, Protocol, TypedDict

from app.models.notification import DeferredContent, NotifyPayload
from app.models.notification_channel import DispatchResult, NotifyTarget
from app.models.notification_community import CommunityNotificationResult


class ReportScreenshot(TypedDict):
    image_ref: str
    label: str


class TaskResultData(TypedDict):
    """专项边界现有报告字典的公共字段，额外展示字段仍由专项拥有。"""

    start_time: str
    end_time: str
    completed_count: int
    uncompleted_count: int
    result: str
    title: NotRequired[str]
    script_name: NotRequired[str]
    summary_title: NotRequired[str]
    screenshots: NotRequired[list[ReportScreenshot]]
    push_log: NotRequired[str]


@dataclass(frozen=True)
class TaskResultReport:
    """共享报告只读取明确字段，专项的模板扩展不参与投递决策。"""

    start_time: str
    end_time: str
    completed_count: int
    uncompleted_count: int
    result: str
    summary_title: str | None = None
    template_fields: Mapping[str, object] = field(default_factory=dict, repr=False)

    @classmethod
    def from_message(cls, message: TaskResultData) -> "TaskResultReport":
        return cls(
            start_time=message["start_time"],
            end_time=message["end_time"],
            completed_count=message["completed_count"],
            uncompleted_count=message["uncompleted_count"],
            result=message["result"],
            summary_title=message.get("summary_title"),
            template_fields=MappingProxyType(
                {
                    key: value
                    for key, value in message.items()
                    if key
                    not in {
                        "start_time",
                        "end_time",
                        "completed_count",
                        "uncompleted_count",
                        "result",
                    }
                }
            ),
        )

    def template_context(self) -> dict[str, object]:
        return {
            **self.template_fields,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "completed_count": self.completed_count,
            "uncompleted_count": self.uncompleted_count,
            "result": self.result,
        }


@dataclass
class TaskNotificationState:
    results: tuple[CommunityNotificationResult, ...] = field(default=(), repr=False)
    summary_consumed: bool = False
    delivered: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class TaskReportPolicy:
    result_time: Literal["不推送", "任何时刻", "仅失败时"]
    community_enabled: bool
    wait_seconds: float


@dataclass(frozen=True)
class TaskReportSummary:
    text: str = ""
    markdown: str | DeferredContent[str] = ""


class ReportRenderer(Protocol):
    """编排只消费内容端口，模板、字体和图片由实现管理。"""

    def community_summary(
        self, results: tuple[CommunityNotificationResult, ...]
    ) -> TaskReportSummary: ...

    def community_payload(
        self, results: tuple[CommunityNotificationResult, ...]
    ) -> NotifyPayload: ...

    def append_summary(
        self, payload: NotifyPayload, summary: TaskReportSummary
    ) -> NotifyPayload: ...


@dataclass(frozen=True)
class TaskReportRequest:
    payload: NotifyPayload
    targets: tuple[NotifyTarget, ...]
    policy: TaskReportPolicy
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
