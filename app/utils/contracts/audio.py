"""AudioAPI 的平台无关调用契约。"""

from collections.abc import Iterable
from typing import Protocol


class AudioAPI(Protocol):
    async def mute_once(self, pids: Iterable[int]) -> dict[int, bool]: ...

    async def restore_processes(self, states: dict[int, bool]) -> dict[int, bool]: ...
