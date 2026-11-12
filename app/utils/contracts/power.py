"""电源操作与显示保活的共同契约。"""

from enum import StrEnum
from typing import Protocol


class PowerSignal(StrEnum):
    """电源动作的统一标识；协议与持久化值保持稳定。"""

    NO_ACTION = "NoAction"
    SHUTDOWN = "Shutdown"
    SHUTDOWN_FORCE = "ShutdownForce"
    REBOOT = "Reboot"
    HIBERNATE = "Hibernate"
    SLEEP = "Sleep"
    KILL_SELF = "KillSelf"
    RESTART_SELF = "RestartSelf"
    LOGOFF = "Logoff"


class DisplayHold(Protocol):
    @property
    def active(self) -> bool: ...

    def release(self) -> None: ...


class PowerController(Protocol):
    @property
    def supported(self) -> bool: ...

    @property
    def supported_actions(self) -> frozenset[PowerSignal]: ...

    async def execute(self, action: PowerSignal) -> None: ...

    async def set_sleep_prevention(self, enabled: bool) -> None: ...

    def hold_display(self, owner: str) -> DisplayHold: ...

    def release_display_holds(self) -> None: ...
