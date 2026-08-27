from app.utils.platform.common.errors import UnsupportedPlatformError


class CommonPowerController:
    supported_actions = frozenset()

    async def execute(self, action: str) -> None:
        raise UnsupportedPlatformError("power")

    async def set_sleep_prevention(self, enabled: bool) -> None:
        raise UnsupportedPlatformError("prevent_sleep")
