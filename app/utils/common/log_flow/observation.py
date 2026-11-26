"""任务运行树内的日志节点状态；独立于任务执行成败。"""

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import AfterValidator, BaseModel, Field, StrictBool, StrictInt

from app.utils.common.security import is_sensitive_log_key, sanitize_log_message

type NodeSource = Literal["file", "push", "mas", "custom"]
type CloseReason = Literal["complete", "timeout", "worker_error", "capacity"]
type ReportedNodeKey = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:-]{1,96}$")]
type NodeDisplayStatus = Literal[
    "success", "skipped", "failed", "exception", "running", "warning", "info"
]
type ReportOrder = Literal["first_seen", "last_updated"]

MAX_NODE_ATTRIBUTE_TEXT = 256
_PAGE_BYTES = 256 * 1024


class NodeAttribute(BaseModel, frozen=True):
    key: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_.-]{0,47}$")
    value: (
        StrictBool
        | StrictInt
        | Annotated[float, Field(strict=True, allow_inf_nan=False)]
        | Annotated[str, Field(strict=True, max_length=MAX_NODE_ATTRIBUTE_TEXT)]
        | None
    )


type NodeAttributes = Annotated[tuple[NodeAttribute, ...], Field(max_length=16)]


class Node(BaseModel, frozen=True):
    sequence: int = Field(gt=0)
    node_type: str
    text: str
    source: NodeSource
    timestamp: float | None = Field(default=None, allow_inf_nan=False)
    node_id: str | None = None
    revision: int = Field(default=1, ge=1)
    withdrawn: bool = False
    status: NodeDisplayStatus = "info"
    attributes: NodeAttributes = ()


def public_log_node(node: Node) -> Node:
    """过滤对外节点的凭据及敏感字段。"""
    attributes = []
    for attribute in node.attributes:
        if is_sensitive_log_key(attribute.key):
            continue
        value = attribute.value
        if isinstance(value, str):
            attribute = attribute.model_copy(
                update={"value": sanitize_log_message(value)[:MAX_NODE_ATTRIBUTE_TEXT]}
            )
        attributes.append(attribute)
    return node.model_copy(
        update={
            "text": sanitize_log_message(node.text),
            "attributes": tuple(attributes),
        }
    )


def _validate_timestamp(timestamp: float) -> float:
    try:
        datetime.fromtimestamp(timestamp)
    except (OSError, OverflowError, ValueError) as exc:
        raise ValueError("日志时间戳应为可转换为本地时间的 Unix 秒数") from exc
    return timestamp


type LogTimestamp = Annotated[
    float, Field(allow_inf_nan=False), AfterValidator(_validate_timestamp)
]


class ReportEntry(BaseModel, frozen=True):
    """LogFlow 收尾使用的结构化条目，由归并器保留或重新声明状态。"""

    node_type: str
    text: str
    timestamp: LogTimestamp | None = None
    status: NodeDisplayStatus = "info"

    @classmethod
    def from_node(cls, node: Node) -> "ReportEntry":
        return cls(
            node_type=node.node_type,
            text=node.text,
            timestamp=node.timestamp,
            status=node.status,
        )


@dataclass(frozen=True)
class SessionSummary:
    reason: CloseReason
    nodes: tuple[Node, ...]
    detail: str = ""
    report_entries: tuple[ReportEntry, ...] | None = None
    requires_final_report: bool = False
    sink_error: str = ""
    report_order: ReportOrder = "first_seen"

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


@dataclass(frozen=True)
class ObservationSnapshot:
    nodes: tuple[Node, ...]
    cursor: ObservationCursor
    close_reason: CloseReason | None


class NodeObservation:
    """保留变更游标，并投影每个逻辑节点的最新状态。"""

    def __init__(self) -> None:
        self.session_id = uuid4()
        self._nodes: list[Node] = []
        self._current: dict[str | int, Node] = {}
        self._node_sizes: list[int] = []
        self.size_bytes = 0
        self._report_bytes = 0
        self._summary: SessionSummary | None = None

    def append(self, node: Node, *, frame_bytes: int) -> None:
        if self._summary is not None or node.sequence != len(self._nodes) + 1:
            raise ValueError("节点不属于当前观察进度")
        self._nodes.append(node)
        key = node.node_id if node.node_id is not None else node.sequence
        if node.withdrawn:
            self._current.pop(key, None)
        else:
            self._current[key] = node
        self._node_sizes.append(frame_bytes)
        self.size_bytes += frame_bytes

    @property
    def retained_bytes(self) -> int:
        return self.size_bytes + self._report_bytes

    def __len__(self) -> int:
        return len(self._nodes)

    @property
    def summary(self) -> SessionSummary | None:
        return self._summary

    def snapshot(self) -> tuple[Node, ...]:
        return (
            self._summary.nodes
            if self._summary is not None
            else tuple(self._current.values())
        )

    def capture(self) -> ObservationSnapshot:
        """在同一事件循环轮次获取当前节点与下一次补读起点。"""
        return ObservationSnapshot(
            nodes=self.snapshot(),
            cursor=ObservationCursor(self.session_id, len(self)),
            close_reason=self._summary.reason if self._summary is not None else None,
        )

    def finish(
        self,
        reason: CloseReason,
        detail: str = "",
        *,
        report_entries: tuple[ReportEntry, ...] | None = None,
        report_bytes: int = 0,
        requires_final_report: bool = False,
        sink_error: str = "",
        report_order: ReportOrder = "first_seen",
    ) -> SessionSummary:
        if self._summary is None:
            self._report_bytes = report_bytes
            self._summary = SessionSummary(
                reason=reason,
                nodes=self.snapshot(),
                detail=detail,
                report_entries=report_entries,
                requires_final_report=requires_final_report,
                sink_error=sink_error,
                report_order=report_order,
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
