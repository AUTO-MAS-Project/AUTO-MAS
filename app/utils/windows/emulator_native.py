"""模拟器的 Windows 宿主能力。"""

import ctypes
from pathlib import Path

from ..contracts.emulator_native import WindowVisibility

_EMULATOR_WINDOW_PREFIX = "Android Emulator - "
_EMULATOR_TOOLBAR_TITLE = "Emulator"


def shm_exists(port: int) -> bool:
    """截图共享内存 ``SHM_videmulator<控制台端口>`` 在不在（MaaFW AVDExtras 读它）。"""
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except (AttributeError, OSError):
        return False
    open_mapping = kernel32.OpenFileMappingW
    open_mapping.restype = ctypes.c_void_p
    open_mapping.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p)
    handle = open_mapping(0x0004, 0, f"SHM_videmulator{port}")  # FILE_MAP_READ
    if not handle:
        return False
    kernel32.CloseHandle(ctypes.c_void_p(handle))
    return True


def prepare_window_visibility() -> WindowVisibility:
    """在事件循环线程解析桌面依赖，返回同步窗口操作。"""
    from ctypes import wintypes

    import win32con
    import win32gui
    import win32process

    def set_emulator_windows_visible(pid: int, name_port: str, visible: bool) -> int:
        """对 qemu 进程 ``pid`` 的主窗口与侧边工具栏发 ``SW_SHOW`` / ``SW_HIDE``，返回处理的窗口数。

        只认 Qt 窗口（类名以 ``Qt`` 开头）里标题是 ``Android Emulator - <avd>:<端口>`` 的主窗口和标题为
        ``Emulator`` 的工具栏；同一进程里一大堆 OpenGL / 输入法隐藏窗口不碰。无头开机的进程没有这两个
        窗口，返回 0。用 ``ShowWindowAsync`` 只投递消息，不等模拟器界面线程。"""
        targets: list[int] = []

        def collect(hwnd: int, _: object) -> bool:
            try:
                _, owner = win32process.GetWindowThreadProcessId(hwnd)
                if owner != pid or not win32gui.GetClassName(hwnd).startswith("Qt"):
                    return True
                title = win32gui.GetWindowText(hwnd)
            except Exception:  # noqa: BLE001 - 枚举途中窗口被销毁
                return True
            if (
                title == f"{_EMULATOR_WINDOW_PREFIX}{name_port}"
                or title == _EMULATOR_TOOLBAR_TITLE
            ):
                targets.append(hwnd)
            return True

        win32gui.EnumWindows(collect, None)

        # 私有一份 user32 声明原型，不影响进程里其它走 ctypes.windll.user32 的代码
        show = ctypes.WinDLL("user32").ShowWindowAsync
        show.argtypes = [wintypes.HWND, ctypes.c_int]
        show.restype = wintypes.BOOL
        for hwnd in targets:
            show(hwnd, win32con.SW_SHOW if visible else win32con.SW_HIDE)
        return len(targets)

    return set_emulator_windows_visible


def cpu_cache_topology() -> bytes:
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except (AttributeError, OSError):
        return b""
    get_info = kernel32.GetLogicalProcessorInformationEx
    get_info.restype = ctypes.c_int
    get_info.argtypes = (ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32))
    relation_cache = 2
    length = ctypes.c_uint32(0)
    get_info(relation_cache, None, ctypes.byref(length))
    if not length.value:
        return b""
    buffer = ctypes.create_string_buffer(length.value)
    if not get_info(relation_cache, buffer, ctypes.byref(length)):
        return b""
    return buffer.raw[: length.value]


def vulkan_probe_path() -> Path | None:
    from pathlib import Path

    return Path(__file__).with_name("vulkan_probe.py")
