"""配置只声明命令，执行所有权由宿主注入。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol
from uuid import UUID

if TYPE_CHECKING:
    from .core.entry import ConfigEntry


class TriggerDispatcher(Protocol):
    def submit(
        self, entry: ConfigEntry, *, group: str, field: str, value: object
    ) -> UUID: ...
