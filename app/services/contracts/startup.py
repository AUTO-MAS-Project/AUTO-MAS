"""开机自启能力契约。"""

from typing import Protocol


class StartupManager(Protocol):
    @property
    def supported(self) -> bool: ...

    async def set_enabled(self, enabled: bool) -> None: ...

    async def is_enabled(self) -> bool: ...
