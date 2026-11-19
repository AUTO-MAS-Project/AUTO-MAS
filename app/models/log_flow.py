"""任务运行树内的日志节点状态；独立于任务执行成败。"""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

type NodeSource = Literal["file", "push", "mas"]
type CloseReason = Literal["complete", "timeout", "worker_error", "capacity"]

_PAGE_BYTES = 256 * 1024


class Node(BaseModel, frozen=True):
    sequence: int = Field(gt=0)
    node_type: str
    text: str
    source: NodeSource
    timestamp: float | None = Field(default=None, allow_inf_nan=False)


@dataclass(frozen=True)
class SessionSummary:
    reason: CloseReason
    nodes: tuple[Node, ...]
    detail: str = ""
    report_entries: tuple[tuple[str, str, float | None], ...] | None = None
    requires_final_report: bool = False

    @property
    def complete(self) -> bool:
        return self.reason == "complete"


class InvalidObservationCursor(ValueError):
    """游标不属于当前会话或超出宿主已接收的节点。"""


@dataclass(frozen=True)
class ObservationCursor:
    session_id: UUID
    sequence: int


@dataclass(frozen=True)
class ObservationPage:
    nodes: tuple[Node, ...]
    cursor: ObservationCursor
    has_more: bool
    close_reason: CloseReason | None


class NodeObservation:
    """同一宿主事件循环内持有节点及观察终态；初版仅追加。"""

    def __init__(self) -> None:
        self.session_id = uuid4()
        self._nodes: list[Node] = []
        self._node_sizes: list[int] = []
        self.size_bytes = 0
        self._report_bytes = 0
        self._summary: SessionSummary | None = None

    def append(self, node: Node, *, frame_bytes: int) -> None:
        if self._summary is not None or node.sequence != len(self._nodes) + 1:
            raise ValueError("节点不属于当前观察进度")
        self._nodes.append(node)
        self._node_sizes.append(frame_bytes)
        self.size_bytes += frame_bytes

    @property
    def retained_bytes(self) -> int:
        return self.size_bytes + self._report_bytes

    def __len__(self) -> int:
        return len(self._nodes)

    def snapshot(self) -> tuple[Node, ...]:
        return self._summary.nodes if self._summary is not None else tuple(self._nodes)

    def finish(
        self,
        reason: CloseReason,
        detail: str = "",
        *,
        report_entries: tuple[tuple[str, str, float | None], ...] | None = None,
        report_bytes: int = 0,
        requires_final_report: bool = False,
    ) -> SessionSummary:
        if self._summary is None:
            self._report_bytes = report_bytes
            self._summary = SessionSummary(
                reason=reason,
                nodes=self.snapshot(),
                detail=detail,
                report_entries=report_entries,
                requires_final_report=requires_final_report,
            )
        return self._summary

    def read(
        self, *, after: ObservationCursor | None = None, limit: int = 50
    ) -> ObservationPage:
        """读取当前会话有界的一页，含补读游标和独立的采集终态。"""
        start = 0
        if after is not None:
            if after.session_id != self.session_id or not 0 <= after.sequence <= len(
                self
            ):
                raise InvalidObservationCursor("观察游标已失效，请从头读取")
            start = after.sequence
        if not 1 <= limit <= 100:
            raise ValueError("观察分页大小必须在 1 到 100 之间")
        stop = start
        size = 0
        for node_size in self._node_sizes[start : start + limit]:
            if stop > start and size + node_size > _PAGE_BYTES:
                break
            stop += 1
            size += node_size
        return ObservationPage(
            nodes=tuple(self._nodes[start:stop]),
            cursor=ObservationCursor(self.session_id, stop),
            has_more=stop < len(self),
            close_reason=self._summary.reason if self._summary is not None else None,
        )
