"""虚拟显示器公共数据、生命周期与平台能力契约。"""

from dataclasses import dataclass
from enum import Enum
from types import TracebackType
from typing import Protocol


class VddStatus(Enum):
    """探测结果。区分这几档是有意的：给用户的提示完全不同。"""

    OK = "ok"
    NOT_INSTALLED = "not_installed"
    ACCESS_DENIED = "access_denied"
    ERROR = "error"


@dataclass(frozen=True)
class VddProbeResult:
    status: VddStatus
    version: int | None = None
    detail: str = ""


class VddError(RuntimeError):
    """驱动可用但操作失败。"""


Status = VddStatus
ProbeResult = VddProbeResult
Error = VddError
VDD_MODE_PRESETS = ((1920, 1080, 60), (1920, 1080, 30))
DEFAULT_VDD_MODE = VDD_MODE_PRESETS[0]
VDD_SETTLE_SECONDS = 1.5


class VirtualDisplayState(Protocol):
    mode: tuple[int, int, int]
    device: str | None
    applied_mode: tuple[int, int, int] | None

    @property
    def active(self) -> bool: ...

    @property
    def index(self) -> int | None: ...

    def __enter__(self) -> "VirtualDisplayState": ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...
    def close(self) -> None: ...


class VirtualDisplayFactory(Protocol):
    def __call__(
        self, mode: tuple[int, int, int] = DEFAULT_VDD_MODE
    ) -> VirtualDisplayState: ...


class VddAPI(Protocol):
    @property
    def VddStatus(self) -> type[Status]: ...

    @property
    def VddProbeResult(self) -> type[ProbeResult]: ...

    @property
    def VddError(self) -> type[Error]: ...

    @property
    def VirtualDisplay(self) -> VirtualDisplayFactory: ...

    @property
    def VDD_MODE_PRESETS(self) -> tuple[tuple[int, int, int], ...]: ...

    @property
    def DEFAULT_VDD_MODE(self) -> tuple[int, int, int]: ...

    @property
    def VDD_SETTLE_SECONDS(self) -> float: ...

    def probe(self) -> ProbeResult: ...
    def current_mode(self, device: str) -> tuple[int, int, int] | None: ...
    def apply_mode(
        self, device: str, width: int, height: int, refresh: int
    ) -> bool: ...
    def remove_display_index(self, index: int) -> bool: ...
