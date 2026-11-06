from pathlib import Path

from app.utils import UnsupportedPlatformError


class CommonStartupManager:
    supported = False

    async def set_enabled(self, enabled: bool) -> None:
        raise UnsupportedPlatformError("startup")

    async def is_enabled(self) -> bool:
        raise UnsupportedPlatformError("startup")

    async def sync_wakeup(
        self, *, executable: Path, times: tuple[tuple[int, int, int], ...]
    ) -> None:
        raise UnsupportedPlatformError("startup")


startup = CommonStartupManager()
