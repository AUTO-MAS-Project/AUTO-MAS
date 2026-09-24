"""显示器几何查询。

无人值守跑 Win32 桌面游戏时需要知道「桌面上还有没有真实的显示输出」：所有输出都断开
后 Windows 并不会让桌面消失，而是保留一块占位的幻影屏——它照旧上报一个看着正常的分辨率
（实测甚至会继承上一块屏的模式），但背后没有任何输出。冷启动时更会直接起在很小的安全
分辨率上，游戏窗口被压小并被游戏自己记住。

本模块只查询，不改动任何显示设置。DPI 感知用 `SetThreadDpiAwarenessContext` 按调用
临时切换，不去动进程级的 DPI 感知——那会影响到同进程里其它按逻辑像素工作的代码。
"""

import ctypes
from contextlib import contextmanager, suppress
from ctypes import wintypes
from dataclasses import dataclass

DEFAULT_DPI = 96
MONITORINFOF_PRIMARY = 0x00000001
QDC_ONLY_ACTIVE_PATHS = 0x00000002
# 「系统强行让这个输出可用」——Windows 在没有任何真实输出时保留的占位屏会带上它。
# 实测：物理显示器关闭后活动路径 flags=0x11(IN_USE|FORCED_SYSTEM)，挂上真实的虚拟屏
# 之后变成 0x01(IN_USE)，拆掉又回到 0x11。
DISPLAYCONFIG_TARGET_FORCED_AVAILABILITY_SYSTEM = 0x00000010
DISPLAY_DEVICE_ATTACHED_TO_DESKTOP = 0x00000001
MDT_EFFECTIVE_DPI = 0
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
# 普通可调整大小的窗口。用它换算「客户区 -> 窗口外框」的非客户区开销。
WS_OVERLAPPEDWINDOW = 0x00CF0000


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class _MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", _RECT),
        ("rcWork", _RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", ctypes.c_wchar * 32),
    ]


class _DISPLAY_DEVICEW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("DeviceName", ctypes.c_wchar * 32),
        ("DeviceString", ctypes.c_wchar * 128),
        ("StateFlags", wintypes.DWORD),
        ("DeviceID", ctypes.c_wchar * 128),
        ("DeviceKey", ctypes.c_wchar * 128),
    ]


class _LUID(ctypes.Structure):
    _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", ctypes.c_long)]


class _PATH_SOURCE_INFO(ctypes.Structure):
    _fields_ = [
        ("adapterId", _LUID),
        ("id", wintypes.UINT),
        ("modeInfoIdx", wintypes.UINT),
        ("statusFlags", wintypes.UINT),
    ]


class _PATH_TARGET_INFO(ctypes.Structure):
    _fields_ = [
        ("adapterId", _LUID),
        ("id", wintypes.UINT),
        ("modeInfoIdx", wintypes.UINT),
        ("outputTechnology", wintypes.UINT),
        ("rotation", wintypes.UINT),
        ("scaling", wintypes.UINT),
        ("refreshNumerator", wintypes.UINT),
        ("refreshDenominator", wintypes.UINT),
        ("scanLineOrdering", wintypes.UINT),
        ("targetAvailable", wintypes.BOOL),
        ("statusFlags", wintypes.UINT),
    ]


class _PATH_INFO(ctypes.Structure):
    _fields_ = [
        ("sourceInfo", _PATH_SOURCE_INFO),
        ("targetInfo", _PATH_TARGET_INFO),
        ("flags", wintypes.UINT),
    ]


_MONITORENUMPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL,
    wintypes.HMONITOR,
    wintypes.HDC,
    ctypes.POINTER(_RECT),
    wintypes.LPARAM,
)


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


# 用私有的 WinDLL 实例，不是 `_user32`：后者是进程级共享缓存，在它上面
# 声明 restype 会波及仓库里其它同样用它的模块（如 OkNte 的 launcher_start）。
_user32 = ctypes.WinDLL("user32", use_last_error=True)
_shcore = ctypes.WinDLL("shcore", use_last_error=True)


def _declare_prototypes() -> None:
    """显式声明返回类型。

    ctypes 默认 restype=c_int，会把返回句柄的函数截成 32 位。截断后的失败往往不像
    失败——比如设备枚举会表现成「一个都没有」，和「真的没有」无法区分。
    老系统上缺失的函数用 AttributeError 跳过即可。
    """

    for dll, name, restype, argtypes in (
        (_user32, "SetThreadDpiAwarenessContext", ctypes.c_void_p, [ctypes.c_void_p]),
        (
            _user32,
            "MonitorFromWindow",
            wintypes.HMONITOR,
            [wintypes.HWND, wintypes.DWORD],
        ),
        (_user32, "GetMonitorInfoW", wintypes.BOOL, None),
        (_user32, "EnumDisplayDevicesW", wintypes.BOOL, None),
        (_user32, "GetDisplayConfigBufferSizes", ctypes.c_long, None),
        (_user32, "QueryDisplayConfig", ctypes.c_long, None),
        (_user32, "EnumDisplayMonitors", wintypes.BOOL, None),
        (_user32, "AdjustWindowRectExForDpi", wintypes.BOOL, None),
        (_user32, "AdjustWindowRectEx", wintypes.BOOL, None),
        (_shcore, "GetDpiForMonitor", ctypes.c_long, None),
    ):
        with suppress(AttributeError, OSError):
            func = getattr(dll, name)
            func.restype = restype
            if argtypes is not None:
                func.argtypes = argtypes


_declare_prototypes()


@contextmanager
def per_monitor_dpi():
    """临时切到 per-monitor DPI 感知，保证拿到的是物理像素。

    不用进程级的 `SetProcessDpiAwareness`：那是一次性且不可逆的全局副作用，
    会影响同进程里其它按逻辑像素工作的代码。
    """

    user32 = _user32
    previous = None
    with suppress(AttributeError, OSError):
        # Windows 10 1703 以下没有这个函数，拿不到就按当前感知级别继续。
        previous = user32.SetThreadDpiAwarenessContext(
            ctypes.c_void_p(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
        )
    try:
        yield
    finally:
        if previous:
            with suppress(OSError):
                user32.SetThreadDpiAwarenessContext(previous)


def _monitor_dpi(handle: int) -> int:
    dpi_x = wintypes.UINT()
    dpi_y = wintypes.UINT()
    try:
        result = _shcore.GetDpiForMonitor(
            wintypes.HMONITOR(handle),
            MDT_EFFECTIVE_DPI,
            ctypes.byref(dpi_x),
            ctypes.byref(dpi_y),
        )
    except (AttributeError, OSError):
        return DEFAULT_DPI
    if result != 0 or not dpi_x.value:
        return DEFAULT_DPI
    return int(dpi_x.value)


def _read_monitor(handle: int) -> MonitorInfo | None:
    info = _MONITORINFOEXW()
    info.cbSize = ctypes.sizeof(_MONITORINFOEXW)
    if not _user32.GetMonitorInfoW(wintypes.HMONITOR(handle), ctypes.byref(info)):
        return None
    return MonitorInfo(
        device=info.szDevice,
        handle=int(handle),
        bounds=(
            info.rcMonitor.left,
            info.rcMonitor.top,
            info.rcMonitor.right,
            info.rcMonitor.bottom,
        ),
        work=(
            info.rcWork.left,
            info.rcWork.top,
            info.rcWork.right,
            info.rcWork.bottom,
        ),
        dpi=_monitor_dpi(handle),
        primary=bool(info.dwFlags & MONITORINFOF_PRIMARY),
    )


def list_monitors() -> list[MonitorInfo]:
    """枚举当前所有显示器。失败返回空列表，由调用方决定要不要当成致命。"""

    monitors: list[MonitorInfo] = []

    def callback(handle, _hdc, _rect, _param) -> bool:
        monitor = _read_monitor(handle)
        if monitor is not None:
            monitors.append(monitor)
        return True

    with per_monitor_dpi():
        try:
            _user32.EnumDisplayMonitors(None, None, _MONITORENUMPROC(callback), 0)
        except OSError:
            return []
    return monitors


def frame_size_for_client(
    client_width: int,
    client_height: int,
    dpi: int = DEFAULT_DPI,
    style: int = WS_OVERLAPPEDWINDOW,
    ex_style: int = 0,
) -> tuple[int, int]:
    """把目标客户区换算成所需的窗口外框尺寸。

    非客户区（标题栏、边框）的高度随 DPI 变——150% 下标题栏约 48px、100% 下约
    31px，写死余量在高 DPI 显示器上必然误判，所以走系统的换算函数。
    """

    rect = _RECT(0, 0, int(client_width), int(client_height))
    user32 = _user32
    adjusted = False
    with suppress(AttributeError, OSError):
        # Windows 10 1607+ 才有带 DPI 的版本。
        adjusted = bool(
            user32.AdjustWindowRectExForDpi(
                ctypes.byref(rect),
                wintypes.DWORD(style),
                wintypes.BOOL(False),
                wintypes.DWORD(ex_style),
                wintypes.UINT(int(dpi)),
            )
        )
    if not adjusted:
        with suppress(AttributeError, OSError):
            user32.AdjustWindowRectEx(
                ctypes.byref(rect),
                wintypes.DWORD(style),
                wintypes.BOOL(False),
                wintypes.DWORD(ex_style),
            )
    return rect.right - rect.left, rect.bottom - rect.top


def can_host_client(
    monitor: MonitorInfo, client_width: int, client_height: int
) -> bool:
    """这块屏的可用区域放不放得下目标客户区（含标题栏与边框）。"""

    frame_width, frame_height = frame_size_for_client(
        client_width, client_height, monitor.dpi
    )
    work_width, work_height = monitor.work_size
    return work_width >= frame_width and work_height >= frame_height


def find_host_monitor(client_width: int, client_height: int) -> MonitorInfo | None:
    """挑一块放得下目标客户区的屏；主显示器优先，其次可用面积最大的。"""

    candidates = [
        monitor
        for monitor in list_monitors()
        if can_host_client(monitor, client_width, client_height)
    ]
    if not candidates:
        return None
    for monitor in candidates:
        if monitor.primary:
            return monitor
    return max(candidates, key=lambda item: item.work_size[0] * item.work_size[1])


def has_real_display() -> bool:
    """桌面上是不是至少有一块**真实输出**（物理显示器或虚拟显示器）。

    这是虚拟屏的触发判据，比「有没有一块屏够大」可靠：所有真实输出都没有时，Windows
    并不会让桌面消失，而是保留一块占位的「幻影屏」——它**照旧上报原来的分辨率**，
    `EnumDisplayMonitors` 看起来一切正常，但那块屏背后没有任何输出，游戏渲染与截图链路
    是否可靠没有保证（DXGI 桌面复制在这种屏上尤其容易出问题）。

    实测有两个完全一致的判据，这里用其一、另一个兜底：

    - `QueryDisplayConfig` 的活动路径带 `FORCED_AVAILABILITY_SYSTEM`（系统强行让它可用）
    - 该适配器下没有 monitor 子设备

    取不到信息时返回 True（按「有真实输出」处理）：这一层是尽力而为的改善项，
    宁可不插屏，也不要因为查询失败去改用户的桌面拓扑。
    """

    forced = _paths_are_all_forced()
    if forced is not None:
        return not forced
    children = _adapters_have_monitor_child()
    if children is not None:
        return children
    return True


def _paths_are_all_forced() -> bool | None:
    """活动显示路径是否**全部**是系统强行造出来的。查询失败返回 None。"""

    path_count = wintypes.UINT()
    mode_count = wintypes.UINT()
    try:
        if _user32.GetDisplayConfigBufferSizes(
            QDC_ONLY_ACTIVE_PATHS, ctypes.byref(path_count), ctypes.byref(mode_count)
        ):
            return None
        if not path_count.value:
            return True
        paths = (_PATH_INFO * path_count.value)()
        modes = (ctypes.c_byte * (mode_count.value * 64))()
        if _user32.QueryDisplayConfig(
            QDC_ONLY_ACTIVE_PATHS,
            ctypes.byref(path_count),
            paths,
            ctypes.byref(mode_count),
            modes,
            None,
        ):
            return None
    except (AttributeError, OSError):
        return None

    return all(
        paths[i].targetInfo.statusFlags
        & DISPLAYCONFIG_TARGET_FORCED_AVAILABILITY_SYSTEM
        for i in range(path_count.value)
    )


def _adapters_have_monitor_child() -> bool | None:
    """挂在桌面上的适配器下有没有 monitor 子设备。查询失败返回 None。

    幻影屏没有子设备；真实输出（含 IDD 虚拟屏）会有一个 `Generic PnP Monitor`。
    """

    try:
        index = 0
        seen_adapter = False
        while True:
            adapter = _DISPLAY_DEVICEW()
            adapter.cb = ctypes.sizeof(_DISPLAY_DEVICEW)
            if not _user32.EnumDisplayDevicesW(None, index, ctypes.byref(adapter), 0):
                break
            index += 1
            if not adapter.StateFlags & DISPLAY_DEVICE_ATTACHED_TO_DESKTOP:
                continue
            seen_adapter = True
            child = _DISPLAY_DEVICEW()
            child.cb = ctypes.sizeof(_DISPLAY_DEVICEW)
            if _user32.EnumDisplayDevicesW(
                adapter.DeviceName, 0, ctypes.byref(child), 0
            ):
                return True
    except (AttributeError, OSError):
        return None
    return False if seen_adapter else None


def real_display_devices() -> set[str]:
    r"""当前**有真实输出**的显示设备名集合（`\\.\DISPLAYn`）。

    幻影屏不算：它同样挂在桌面上、同样有设备名，但没有 monitor 子设备。这个区别很重要
    ——无头时挂上虚拟屏，Windows 会**复用同一个设备名**（幻影屏是被替换而不是并存），
    对「所有显示设备」做差集会得到空集，认不出新挂的那块屏。对「真实输出」做差集才行。
    """

    devices: set[str] = set()
    try:
        index = 0
        while True:
            adapter = _DISPLAY_DEVICEW()
            adapter.cb = ctypes.sizeof(_DISPLAY_DEVICEW)
            if not _user32.EnumDisplayDevicesW(None, index, ctypes.byref(adapter), 0):
                break
            index += 1
            if not adapter.StateFlags & DISPLAY_DEVICE_ATTACHED_TO_DESKTOP:
                continue
            child = _DISPLAY_DEVICEW()
            child.cb = ctypes.sizeof(_DISPLAY_DEVICEW)
            if _user32.EnumDisplayDevicesW(
                adapter.DeviceName, 0, ctypes.byref(child), 0
            ):
                devices.add(adapter.DeviceName)
    except (AttributeError, OSError):
        return devices
    return devices


def describe_monitors() -> str:
    """一行式的显示器概况，供诊断日志使用。"""

    monitors = list_monitors()
    if not monitors:
        return "未能枚举到显示器"
    return "; ".join(monitor.describe() for monitor in monitors)


# 显式声明公开面：`platform/display.py` 用星号导入本模块，不声明的话 ctypes、wintypes
# 这些实现细节会一起泄漏进 `app.utils.platform.display` 命名空间。
__all__ = [
    "MonitorInfo",
    "per_monitor_dpi",
    "list_monitors",
    "frame_size_for_client",
    "can_host_client",
    "find_host_monitor",
    "has_real_display",
    "real_display_devices",
    "describe_monitors",
]
