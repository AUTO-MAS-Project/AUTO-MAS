from app.utils.platform.common.errors import UnsupportedPlatformError


class CommonStartupManager:
    async def set_enabled(self, enabled: bool) -> None:
        raise UnsupportedPlatformError("startup")

    async def is_enabled(self) -> bool:
        raise UnsupportedPlatformError("startup")
