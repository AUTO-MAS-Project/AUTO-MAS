"""文本处理结果；元数据由调用方提供，不解释业务状态。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TypeAlias

LegacyEntry: TypeAlias = tuple[str, str] | tuple[str, str, float | None]


@dataclass(frozen=True)
class LogEntry:
    """文本处理的只读结果；类型和时间由调用方提供。"""

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
            raise ValueError("条目时间戳必须是有限数值或 None")

    @classmethod
    def from_legacy(cls, entry: LegacyEntry) -> LogEntry:
        if not isinstance(entry, tuple) or len(entry) not in (2, 3):
            raise TypeError("条目必须是二元或三元元组")
        return cls(
            log_type=entry[0],
            text=entry[1],
            timestamp=entry[2] if len(entry) > 2 else None,
        )


Entry: TypeAlias = LogEntry | LegacyEntry
