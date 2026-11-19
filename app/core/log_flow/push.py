"""供执行侧使用的会话上报契约，不暴露来源或运行身份。"""

from collections.abc import Callable
from enum import StrEnum
from typing import Protocol


class SubmitResult(StrEnum):
    ACCEPTED = "accepted"
    BACKPRESSURE = "backpressure"
    TOO_LARGE = "too_large"
    CLOSED = "closed"
    INVALID = "invalid"


class PushReporter(Protocol):
    """在 MAS 事件循环内非阻塞上报；接受仅表示宿主入队。"""

    def text(self, text: str, *, timestamp: float | None = None) -> SubmitResult: ...

    def node(
        self, node_type: str, text: str, *, timestamp: float | None = None
    ) -> SubmitResult: ...


class GuardedReporter:
    """会话能力随插件实例准入撤销，已接收记录仍由会话排空。"""

    def __init__(self, reporter: PushReporter, accepting: Callable[[], bool]) -> None:
        self._reporter = reporter
        self._accepting = accepting

    def text(self, text: str, *, timestamp: float | None = None) -> SubmitResult:
        if not self._accepting():
            return SubmitResult.CLOSED
        return self._reporter.text(text, timestamp=timestamp)

    def node(
        self, node_type: str, text: str, *, timestamp: float | None = None
    ) -> SubmitResult:
        if not self._accepting():
            return SubmitResult.CLOSED
        return self._reporter.node(node_type, text, timestamp=timestamp)
