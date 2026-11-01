"""尚无实现的平台虚拟显示器操作。"""

from ..common.errors import UnsupportedPlatformError
from ..contracts.vdd import (
    DEFAULT_VDD_MODE as DEFAULT_VDD_MODE,
)
from ..contracts.vdd import (
    VDD_MODE_PRESETS as VDD_MODE_PRESETS,
)
from ..contracts.vdd import (
    VDD_SETTLE_SECONDS as VDD_SETTLE_SECONDS,
)
from ..contracts.vdd import (
    VddError as VddError,
)
from ..contracts.vdd import (
    VddProbeResult as VddProbeResult,
)
from ..contracts.vdd import (
    VddStatus as VddStatus,
)
from ..contracts.vdd import (
    VirtualDisplayState,
)


def probe() -> VddProbeResult:
    raise UnsupportedPlatformError("vdd")


def current_mode(device: str) -> tuple[int, int, int] | None:
    raise UnsupportedPlatformError("vdd")


def apply_mode(device: str, width: int, height: int, refresh: int) -> bool:
    raise UnsupportedPlatformError("vdd")


def remove_display_index(index: int) -> bool:
    raise UnsupportedPlatformError("vdd")


def VirtualDisplay(
    mode: tuple[int, int, int] = DEFAULT_VDD_MODE,
) -> VirtualDisplayState:
    raise UnsupportedPlatformError("vdd")
