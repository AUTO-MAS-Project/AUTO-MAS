"""供执行侧使用的会话上报契约，不暴露来源或运行身份。"""

from collections.abc import Callable
from enum import StrEnum
from typing import Protocol

from app.models.log_flow import NodeAttributes, NodeDisplayStatus


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
        self,
        node_type: str,
        text: str,
        *,
        timestamp: float | None = None,
        node_id: str | None = None,
        status: NodeDisplayStatus | None = None,
        attributes: NodeAttributes = (),
    ) -> SubmitResult: ...

    def withdraw(self, node_id: str) -> SubmitResult: ...


class GuardedReporter:
    """没有可用会话或插件实例已撤销时返回已关闭。"""

    def __init__(
        self, reporter: PushReporter | None, accepting: Callable[[], bool]
    ) -> None:
        self._reporter = reporter
        self._accepting = accepting

    def text(self, text: str, *, timestamp: float | None = None) -> SubmitResult:
        if self._reporter is None or not self._accepting():
            return SubmitResult.CLOSED
        return self._reporter.text(text, timestamp=timestamp)

    def node(
        self,
        node_type: str,
        text: str,
        *,
        timestamp: float | None = None,
        node_id: str | None = None,
        status: NodeDisplayStatus | None = None,
        attributes: NodeAttributes = (),
    ) -> SubmitResult:
        if self._reporter is None or not self._accepting():
            return SubmitResult.CLOSED
        return self._reporter.node(
            node_type,
            text,
            timestamp=timestamp,
            node_id=node_id,
            status=status,
            attributes=attributes,
        )

    def withdraw(self, node_id: str) -> SubmitResult:
        if self._reporter is None or not self._accepting():
            return SubmitResult.CLOSED
        return self._reporter.withdraw(node_id)
