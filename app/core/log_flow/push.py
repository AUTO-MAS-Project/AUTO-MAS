"""供执行侧使用的会话上报契约，不暴露来源或运行身份。"""

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
