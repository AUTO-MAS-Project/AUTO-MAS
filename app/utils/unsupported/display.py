"""尚无实现的平台显示器操作。"""

from contextlib import AbstractContextManager

from ..common.errors import UnsupportedPlatformError
from ..contracts.display import MonitorInfo as MonitorInfo


def per_monitor_dpi() -> AbstractContextManager[None]:
    raise UnsupportedPlatformError("display")


def list_monitors() -> list[MonitorInfo]:
    raise UnsupportedPlatformError("display")


def frame_size_for_client(
    client_width: int,
    client_height: int,
    dpi: int = 96,
    style: int = 13565952,
    ex_style: int = 0,
) -> tuple[int, int]:
    raise UnsupportedPlatformError("display")


def can_host_client(
    monitor: MonitorInfo, client_width: int, client_height: int
) -> bool:
    raise UnsupportedPlatformError("display")


def find_host_monitor(client_width: int, client_height: int) -> MonitorInfo | None:
    raise UnsupportedPlatformError("display")


def has_real_display() -> bool:
    raise UnsupportedPlatformError("display")


def real_display_devices() -> set[str]:
    raise UnsupportedPlatformError("display")


def describe_monitors() -> str:
    raise UnsupportedPlatformError("display")
