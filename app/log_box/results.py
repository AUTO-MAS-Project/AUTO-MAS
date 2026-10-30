"""节点交付契约；保留存量文本，结构化状态不再由各个渲染器重复识别。"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Literal, TypeAlias

LegacyEntry: TypeAlias = tuple[str, str] | tuple[str, str, float | None]
NodeStatus: TypeAlias = Literal["success", "skipped", "failed", "warning"]

STATUS_MARKS: dict[NodeStatus, str] = {
    "success": "✅ 成功",
    "skipped": "⏭ 跳过",
    "failed": "❌ 失败",
    "warning": "⚠ 异常",
}
_MARK_STATUSES = {mark: status for status, mark in STATUS_MARKS.items()}
# 与旧报告的识别范围一致：不把未知状态、全角冒号或普通文本猜成节点。
_STATUS_RE = re.compile(
    r"^(?:【(?P<acc>[^】]+)】)?(✅ 成功|⏭ 跳过|❌ 失败|⚠ 异常): (.*)$"
)


@dataclass(frozen=True)
class Node:
    """一条已确认的节点状态；日志类型仍独立表达报告筛选策略。"""

    status: NodeStatus
    name: str
    account: str | None = None

    def __post_init__(self) -> None:
        if self.status not in STATUS_MARKS:
            raise ValueError("未知节点状态")
        if not isinstance(self.name, str):
            raise TypeError("节点名称必须是字符串")
        if self.account is not None and not isinstance(self.account, str):
            raise TypeError("节点账号必须是字符串或 None")

    @property
    def text(self) -> str:
        prefix = f"【{self.account}】" if self.account else ""
        return f"{prefix}{STATUS_MARKS[self.status]}: {self.name}"

    @classmethod
    def from_text(cls, text: str) -> Node | None:
        match = _STATUS_RE.match(text)
        if match is None:
            return None
        return cls(
            status=_MARK_STATUSES[match.group(2)],
            name=match.group(3),
            account=match.group("acc"),
        )


@dataclass(frozen=True)
class LogEntry:
    """采集或结构化来源的交付项；文本原样保留，时间为真实发生或采集时间。"""

    log_type: str
    text: str
    timestamp: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.log_type, str) or not isinstance(self.text, str):
            raise TypeError("日志类型与文本必须是字符串")
        if self.timestamp is not None and (
            isinstance(self.timestamp, bool)
            or not isinstance(self.timestamp, (int, float))
            or not math.isfinite(self.timestamp)
        ):
            raise ValueError("节点时间戳必须是有限数值或 None")

    @classmethod
    def from_legacy(cls, entry: LegacyEntry) -> LogEntry:
        return cls(
            log_type=entry[0],
            text=entry[1],
            timestamp=entry[2] if len(entry) > 2 else None,
        )

    @property
    def node(self) -> Node | None:
        return Node.from_text(self.text)


Entry: TypeAlias = LogEntry | LegacyEntry
