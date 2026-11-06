from app.utils import UnsupportedPlatformError


class CommonDisplayHold:
    """不支持的平台上什么都不做，只记着撤没撤过。"""

    def __init__(self, owner: str) -> None:
        self.owner = owner
        self.active = True

    def release(self) -> None:
        self.active = False


class CommonPowerController:
    supported = False
    supported_actions = frozenset()

    async def execute(self, action: str) -> None:
        raise UnsupportedPlatformError("power")

    async def set_sleep_prevention(self, enabled: bool) -> None:
        raise UnsupportedPlatformError("prevent_sleep")

    def hold_display(self, owner: str) -> CommonDisplayHold:
        return CommonDisplayHold(owner)

    def release_display_holds(self) -> None:
        pass


power = CommonPowerController()
