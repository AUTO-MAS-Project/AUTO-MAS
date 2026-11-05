"""开机自启能力契约。"""

from pathlib import Path
from typing import Protocol


class StartupManager(Protocol):
    @property
    def supported(self) -> bool: ...

    async def set_enabled(self, enabled: bool) -> None: ...

    async def is_enabled(self) -> bool: ...

    async def sync_wakeup(
        self, *, executable: Path, times: tuple[tuple[int, int, int], ...]
    ) -> None: ...
