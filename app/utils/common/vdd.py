from enum import Enum

from .errors import UnsupportedPlatformError


def _unsupported(*args, **kwargs):
    raise UnsupportedPlatformError("vdd")


class VddStatus(Enum):
    OK = "ok"
    NOT_INSTALLED = "not_installed"
    ACCESS_DENIED = "access_denied"
    ERROR = "error"


class VddError(RuntimeError):
    pass


VddProbeResult = None
VDD_MODE_PRESETS: tuple[tuple[int, int, int], ...] = (
    (1920, 1080, 60),
    (1920, 1080, 30),
)
DEFAULT_VDD_MODE = VDD_MODE_PRESETS[0]
apply_mode = _unsupported
current_mode = _unsupported
VirtualDisplay = _unsupported
probe = _unsupported
remove_display_index = _unsupported
VDD_SETTLE_SECONDS = 1.5
