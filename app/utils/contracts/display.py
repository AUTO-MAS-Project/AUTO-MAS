"""显示器公共数据与几何/显示能力契约。"""

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

DEFAULT_DPI = 96


@dataclass(frozen=True)
class MonitorInfo:
    """一块显示器的几何信息，坐标均为物理像素。"""

    device: str
    handle: int
    bounds: tuple[int, int, int, int]
    work: tuple[int, int, int, int]
    dpi: int
    primary: bool

    @property
    def size(self) -> tuple[int, int]:
        left, top, right, bottom = self.bounds
        return right - left, bottom - top

    @property
    def work_size(self) -> tuple[int, int]:
        """去掉任务栏之后的可用区域。窗口能不能放下要看它，不是看整块屏。"""

        left, top, right, bottom = self.work
        return right - left, bottom - top

    @property
    def scaling(self) -> float:
        return self.dpi / DEFAULT_DPI

    def describe(self) -> str:
        width, height = self.size
        work_width, work_height = self.work_size
        return (
            f"{self.device} {width}x{height}"
            f"(可用 {work_width}x{work_height})"
            f" DPI={self.dpi}({self.scaling:.2f}x)"
            f"{' 主显示器' if self.primary else ''}"
        )


Monitor = MonitorInfo


class DisplayAPI(Protocol):
    @property
    def MonitorInfo(self) -> type[Monitor]: ...

    def per_monitor_dpi(self) -> AbstractContextManager[None]: ...
    def list_monitors(self) -> list[Monitor]: ...
    def frame_size_for_client(
        self,
        client_width: int,
        client_height: int,
        dpi: int = 96,
        style: int = 13565952,
        ex_style: int = 0,
    ) -> tuple[int, int]: ...
    def can_host_client(
        self, monitor: Monitor, client_width: int, client_height: int
    ) -> bool: ...
    def find_host_monitor(
        self, client_width: int, client_height: int
    ) -> Monitor | None: ...
    def has_real_display(self) -> bool: ...
    def real_display_devices(self) -> set[str]: ...
    def describe_monitors(self) -> str: ...
