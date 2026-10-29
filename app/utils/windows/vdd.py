"""Parsec 虚拟显示驱动（Parsec VDD）客户端。

所有真实显示输出都断开后，Windows 只保留一块占位的幻影屏，它照旧上报一个看着正常的
分辨率但背后没有输出；冷启动时更会直接起在很小的安全分辨率上，被托管的桌面游戏窗口被
压小、并被游戏写进自己的配置，之后每轮自动运行都不达标。给桌面挂一块真实的虚拟显示器
就从源头断掉这条链子。

**驱动不随 MAS 分发，由用户自行安装**，MAS 只探测并驱动它——姿态与模拟器一致
（只调用用户已装的可执行文件，不释放任何文件）。选 Parsec VDD 是因为它是唯一能被
零附加文件驱动的：一次 `CreateFile` 加四个 IOCTL，纯 ctypes；而且默认模式恰好就是
1920x1080@60，连自定义分辨率都不用配。

**保活不能当作清理机制。** 上游文档称停止心跳约 1 秒后虚拟屏会被自动拔掉，实测**不成立**：
杀掉持有进程后等待 6 秒，屏仍然在，`has_real_display()` 依旧为真，最后是显式发
`VDD_IOCTL_REMOVE` 才拆掉的。所以进程被强杀会留下孤儿屏，必须由下一次启动主动清理。

还有一点实测得来的机制：**心跳是按驱动计的，不是按屏计的**。任何一个进程在 ping，就会把
该驱动下**所有**虚拟屏一起续命，包括别的进程遗留的孤儿。

协议取自 https://github.com/nomi-san/parsec-vdd 。
"""

import ctypes
import threading
import time
from contextlib import suppress
from ctypes import wintypes
from dataclasses import dataclass
from enum import Enum

DIGCF_PRESENT = 0x00000002
DIGCF_DEVICEINTERFACE = 0x00000010
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x00000080
FILE_FLAG_WRITE_THROUGH = 0x80000000
FILE_FLAG_NO_BUFFERING = 0x20000000
FILE_FLAG_OVERLAPPED = 0x40000000
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
ERROR_ACCESS_DENIED = 5
ERROR_IO_PENDING = 997

VDD_IOCTL_ADD = 0x0022E004
VDD_IOCTL_REMOVE = 0x0022A008
VDD_IOCTL_UPDATE = 0x0022A00C
VDD_IOCTL_VERSION = 0x0022E010

# 驱动要求心跳间隔小于 100ms。取一半留足余量。
# 注意：停止心跳**不会**让虚拟屏自己消失（实测杀掉进程 6s 后屏仍在），拆屏必须显式
# 发 VDD_IOCTL_REMOVE；而且心跳是按驱动计的，任何进程在 ping 都会把该驱动下所有屏
# 一起续命，包括别的进程遗留的孤儿。
VDD_PING_INTERVAL = 0.05
VDD_IOCTL_TIMEOUT_MS = 5000
# 插屏后桌面拓扑变更是异步的，给系统一点时间再去重新枚举显示器。
VDD_SETTLE_SECONDS = 1.5

ENUM_CURRENT_SETTINGS = -1
CDS_UPDATEREGISTRY = 0x00000001
CDS_TEST = 0x00000002
DM_PELSWIDTH = 0x00080000
DM_PELSHEIGHT = 0x00100000
DM_DISPLAYFREQUENCY = 0x00400000
DISP_CHANGE_SUCCESSFUL = 0

# 只给 1920x1080，刷新率 30/60 两档。
#
# 分辨率固定的理由：实测只有 1920x1080 及以下几档 Windows 会按 100% 缩放，再高就被
# 自动上缩放（2560x1440 -> 125%，3840x2160 -> 200%），游戏窗口又要面对 DPI 虚拟化——
# 而虚拟屏本来就是为了绕开这类问题。1920x1080 同时也是脚本侧最通用的一档。
#
# 不给高刷的理由：虚拟屏是给无人值守跑脚本用的，高刷只会让 GPU 空转，IDD 屏没有真实
# vsync 源。刷新率必须在驱动 advertise 的模式表里（24/30/60/144/240），写 120 会被
# BADMODE 拒绝。
VDD_MODE_PRESETS: tuple[tuple[int, int, int], ...] = (
    (1920, 1080, 60),
    (1920, 1080, 30),
)
DEFAULT_VDD_MODE = VDD_MODE_PRESETS[0]

_setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_user32 = ctypes.WinDLL("user32", use_last_error=True)


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class _SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("InterfaceClassGuid", _GUID),
        ("Flags", wintypes.DWORD),
        ("Reserved", ctypes.POINTER(ctypes.c_ulonglong)),
    ]


class _OVERLAPPED(ctypes.Structure):
    _fields_ = [
        ("Internal", ctypes.POINTER(ctypes.c_ulonglong)),
        ("InternalHigh", ctypes.POINTER(ctypes.c_ulonglong)),
        ("Offset", wintypes.DWORD),
        ("OffsetHigh", wintypes.DWORD),
        ("hEvent", wintypes.HANDLE),
    ]


class _DEVMODEW(ctypes.Structure):
    """只用到显示相关字段，但整个结构体必须按原样声明，dmSize 才对得上。"""

    _fields_ = [
        ("dmDeviceName", ctypes.c_wchar * 32),
        ("dmSpecVersion", wintypes.WORD),
        ("dmDriverVersion", wintypes.WORD),
        ("dmSize", wintypes.WORD),
        ("dmDriverExtra", wintypes.WORD),
        ("dmFields", wintypes.DWORD),
        ("dmPositionX", ctypes.c_long),
        ("dmPositionY", ctypes.c_long),
        ("dmDisplayOrientation", wintypes.DWORD),
        ("dmDisplayFixedOutput", wintypes.DWORD),
        ("dmColor", ctypes.c_short),
        ("dmDuplex", ctypes.c_short),
        ("dmYResolution", ctypes.c_short),
        ("dmTTOption", ctypes.c_short),
        ("dmCollate", ctypes.c_short),
        ("dmFormName", ctypes.c_wchar * 32),
        ("dmLogPixels", wintypes.WORD),
        ("dmBitsPerPel", wintypes.DWORD),
        ("dmPelsWidth", wintypes.DWORD),
        ("dmPelsHeight", wintypes.DWORD),
        ("dmDisplayFlags", wintypes.DWORD),
        ("dmDisplayFrequency", wintypes.DWORD),
        ("dmICMMethod", wintypes.DWORD),
        ("dmICMIntent", wintypes.DWORD),
        ("dmMediaType", wintypes.DWORD),
        ("dmDitherType", wintypes.DWORD),
        ("dmReserved1", wintypes.DWORD),
        ("dmReserved2", wintypes.DWORD),
        ("dmPanningWidth", wintypes.DWORD),
        ("dmPanningHeight", wintypes.DWORD),
    ]


VDD_ADAPTER_GUID = _GUID(
    0x00B41627,
    0x04C4,
    0x429E,
    (ctypes.c_ubyte * 8)(0xA2, 0x6E, 0x02, 0x65, 0xCF, 0x50, 0xC8, 0xFA),
)


def _declare_prototypes() -> None:
    """显式声明返回类型。

    ctypes 默认 restype=c_int，会把返回句柄的函数截成 32 位。截断之后的失败不像失败：
    `SetupDiGetClassDevsW` 的句柄被截断后，`SetupDiEnumDeviceInterfaces` 立刻
    `ERROR_INVALID_HANDLE`，表现成「一个设备都没枚举到」，与「驱动没装」无法区分。
    """

    _setupapi.SetupDiGetClassDevsW.restype = wintypes.HANDLE
    _setupapi.SetupDiGetClassDevsW.argtypes = [
        ctypes.POINTER(_GUID),
        wintypes.LPCWSTR,
        wintypes.HWND,
        wintypes.DWORD,
    ]
    _setupapi.SetupDiEnumDeviceInterfaces.restype = wintypes.BOOL
    _setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        ctypes.POINTER(_GUID),
        wintypes.DWORD,
        ctypes.POINTER(_SP_DEVICE_INTERFACE_DATA),
    ]
    _setupapi.SetupDiGetDeviceInterfaceDetailW.restype = wintypes.BOOL
    _setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_SP_DEVICE_INTERFACE_DATA),
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p,
    ]
    _setupapi.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL
    _setupapi.SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]

    _kernel32.CreateFileW.restype = wintypes.HANDLE
    _kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    _kernel32.CreateEventW.restype = wintypes.HANDLE
    _kernel32.CreateEventW.argtypes = [
        ctypes.c_void_p,
        wintypes.BOOL,
        wintypes.BOOL,
        wintypes.LPCWSTR,
    ]
    _kernel32.DeviceIoControl.restype = wintypes.BOOL
    _kernel32.DeviceIoControl.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(_OVERLAPPED),
    ]
    _kernel32.GetOverlappedResultEx.restype = wintypes.BOOL
    _kernel32.GetOverlappedResultEx.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_OVERLAPPED),
        ctypes.POINTER(wintypes.DWORD),
        wintypes.DWORD,
        wintypes.BOOL,
    ]
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    _user32.EnumDisplaySettingsExW.restype = wintypes.BOOL
    _user32.ChangeDisplaySettingsExW.restype = ctypes.c_long


_declare_prototypes()


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


def _find_device_path() -> str | None:
    """按 adapter GUID 找设备接口路径。找不到即视为驱动未安装。"""

    dev_info = _setupapi.SetupDiGetClassDevsW(
        ctypes.byref(VDD_ADAPTER_GUID),
        None,
        None,
        DIGCF_PRESENT | DIGCF_DEVICEINTERFACE,
    )
    if dev_info is None or dev_info == INVALID_HANDLE_VALUE:
        return None

    try:
        iface = _SP_DEVICE_INTERFACE_DATA()
        iface.cbSize = ctypes.sizeof(_SP_DEVICE_INTERFACE_DATA)
        index = 0
        while _setupapi.SetupDiEnumDeviceInterfaces(
            dev_info, None, ctypes.byref(VDD_ADAPTER_GUID), index, ctypes.byref(iface)
        ):
            index += 1
            needed = wintypes.DWORD(0)
            _setupapi.SetupDiGetDeviceInterfaceDetailW(
                dev_info, ctypes.byref(iface), None, 0, ctypes.byref(needed), None
            )
            if not needed.value:
                continue
            buf = ctypes.create_string_buffer(needed.value)
            # cbSize 是「固定部分的大小」，x64 上为 8，但 DevicePath 从偏移 4 开始。
            # 这是 SetupAPI 的经典坑，填错会 ERROR_INVALID_USER_BUFFER。
            ctypes.cast(buf, ctypes.POINTER(wintypes.DWORD))[0] = (
                8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
            )
            if _setupapi.SetupDiGetDeviceInterfaceDetailW(
                dev_info,
                ctypes.byref(iface),
                buf,
                needed.value,
                ctypes.byref(needed),
                None,
            ):
                return ctypes.wstring_at(ctypes.addressof(buf) + 4)
    finally:
        _setupapi.SetupDiDestroyDeviceInfoList(dev_info)
    return None


def _open_device(path: str) -> int:
    handle = _kernel32.CreateFileW(
        path,
        GENERIC_READ | GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None,
        OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL
        | FILE_FLAG_NO_BUFFERING
        | FILE_FLAG_OVERLAPPED
        | FILE_FLAG_WRITE_THROUGH,
        None,
    )
    if handle is None or handle == INVALID_HANDLE_VALUE:
        raise ctypes.WinError(ctypes.get_last_error())
    return handle


def _ioctl(handle: int, code: int, data: bytes = b"") -> int:
    """32 字节入、4 字节出、5s 超时的重叠 I/O。参数与驱动约定一致，不能随意改。"""

    in_buf = ctypes.create_string_buffer(32)
    if data:
        ctypes.memmove(in_buf, data, min(len(data), 32))
    out_buf = wintypes.DWORD(0)

    overlapped = _OVERLAPPED()
    overlapped.hEvent = _kernel32.CreateEventW(None, True, False, None)
    if not overlapped.hEvent:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        ok = _kernel32.DeviceIoControl(
            handle,
            code,
            in_buf,
            32,
            ctypes.byref(out_buf),
            ctypes.sizeof(wintypes.DWORD),
            None,
            ctypes.byref(overlapped),
        )
        if not ok:
            # 重叠 I/O 正常会返回 FALSE + ERROR_IO_PENDING，那种情况交给
            # GetOverlappedResultEx 等；其它错误码说明 IRP 根本没发出去，必须当场报错。
            # 不看返回值的话，OVERLAPPED.Internal 仍是 0，GetOverlappedResultEx 会返回
            # 成功、_ioctl 返回 0——VDD_IOCTL_ADD 就会被当成「拿到了 index 0」，
            # 随后 close() 去 REMOVE index 0，可能拆掉别的进程的屏。
            err = ctypes.get_last_error()
            if err != ERROR_IO_PENDING:
                raise ctypes.WinError(err)
        transferred = wintypes.DWORD(0)
        ok = _kernel32.GetOverlappedResultEx(
            handle,
            ctypes.byref(overlapped),
            ctypes.byref(transferred),
            VDD_IOCTL_TIMEOUT_MS,
            False,
        )
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        _kernel32.CloseHandle(overlapped.hEvent)
    return out_buf.value


def probe() -> VddProbeResult:
    """探测驱动是否可用（对应检测流程的前两段）。

    只做「装没装」与「能不能调」，不改变桌面拓扑，因此可以在任务流程里随时调用。
    「有没有效果」由真正插屏时验证，不在这里做。
    """

    try:
        path = _find_device_path()
    except OSError as exc:
        return VddProbeResult(VddStatus.ERROR, detail=str(exc))
    if path is None:
        return VddProbeResult(VddStatus.NOT_INSTALLED)

    try:
        handle = _open_device(path)
    except OSError as exc:
        if exc.winerror == ERROR_ACCESS_DENIED:
            # 与「未安装」是两种完全不同的故障，提示必须分开。
            return VddProbeResult(VddStatus.ACCESS_DENIED, detail=str(exc))
        return VddProbeResult(VddStatus.ERROR, detail=str(exc))

    try:
        version = _ioctl(handle, VDD_IOCTL_VERSION)
    except OSError as exc:
        return VddProbeResult(VddStatus.ERROR, detail=str(exc))
    finally:
        _kernel32.CloseHandle(handle)

    return VddProbeResult(VddStatus.OK, version=version)


def current_mode(device: str) -> tuple[int, int, int] | None:
    """读某块屏当前的 (宽, 高, 刷新率)。"""

    devmode = _DEVMODEW()
    devmode.dmSize = ctypes.sizeof(_DEVMODEW)
    if not _user32.EnumDisplaySettingsExW(
        device, ENUM_CURRENT_SETTINGS, ctypes.byref(devmode), 0
    ):
        return None
    return (
        int(devmode.dmPelsWidth),
        int(devmode.dmPelsHeight),
        int(devmode.dmDisplayFrequency),
    )


def apply_mode(device: str, width: int, height: int, refresh: int) -> bool:
    """把某块屏切到指定模式。

    VDD 的 IOCTL 只管插拔，模式得靠 Windows 的 ChangeDisplaySettingsEx 设。驱动只
    advertise 固定的一批模式，不在表里的会被以 BADMODE 拒绝（实测 120Hz 就不在表里），
    所以先用 CDS_TEST 试一次，不通过就不动现状。
    """

    devmode = _DEVMODEW()
    devmode.dmSize = ctypes.sizeof(_DEVMODEW)
    devmode.dmPelsWidth = width
    devmode.dmPelsHeight = height
    devmode.dmDisplayFrequency = refresh
    devmode.dmFields = DM_PELSWIDTH | DM_PELSHEIGHT | DM_DISPLAYFREQUENCY

    if (
        _user32.ChangeDisplaySettingsExW(
            device, ctypes.byref(devmode), None, CDS_TEST, None
        )
        != DISP_CHANGE_SUCCESSFUL
    ):
        return False
    return (
        _user32.ChangeDisplaySettingsExW(
            device, ctypes.byref(devmode), None, CDS_UPDATEREGISTRY, None
        )
        == DISP_CHANGE_SUCCESSFUL
    )


def remove_display_index(index: int) -> bool:
    """按 index 拆掉一块虚拟屏。用于清理上一次进程留下的孤儿。

    驱动只认 index，不认「谁创建的」，所以调用方必须自己确保这个 index 确实是自己留下的
    ——同一个驱动可能同时被 Parsec 本体或别的程序使用，乱拆会拆掉别人的屏。
    """

    path = _find_device_path()
    if path is None:
        return False
    try:
        handle = _open_device(path)
    except OSError:
        return False
    try:
        _ioctl(handle, VDD_IOCTL_REMOVE, bytes(((index >> 8) & 0xFF, index & 0xFF)))
        _ioctl(handle, VDD_IOCTL_UPDATE)
        return True
    except OSError:
        return False
    finally:
        _kernel32.CloseHandle(handle)


class VirtualDisplay:
    """一块虚拟显示器的生命周期。用作上下文管理器。

    心跳跑在独立的守护线程上，**不能用 asyncio 任务**：事件循环被任何同步操作卡住就会
    停止 ping，而后端里能卡住循环的地方并不少。停 ping 本身不会让屏消失，但驱动会认为
    这块屏已经无人认领，后续行为不可预期。
    """

    def __init__(self, mode: tuple[int, int, int] = DEFAULT_VDD_MODE) -> None:
        self.mode = mode
        self.device: str | None = None
        self.applied_mode: tuple[int, int, int] | None = None
        self._handle: int | None = None
        self._index: int | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def active(self) -> bool:
        return self._index is not None

    @property
    def index(self) -> int | None:
        """驱动内部的屏编号。进程异常退出后要靠它清理孤儿。"""

        return self._index

    def __enter__(self) -> "VirtualDisplay":
        from .display import real_display_devices

        path = _find_device_path()
        if path is None:
            raise VddError("未找到 Parsec 虚拟显示驱动")

        # 先记下现有的**真实输出**，插完靠差集认出哪块是新的——IOCTL 只回一个内部
        # index，不告诉我们 Windows 给它起了什么设备名。
        #
        # 差集必须对「真实输出」做，不能对「所有显示设备」做：无头时桌面上只剩一块系统
        # 占位的幻影屏，挂上虚拟屏之后 Windows 会**复用同一个设备名**，对所有设备做差集
        # 得到空集，认不出新屏，模式也就无从应用。
        before = real_display_devices()

        self._handle = _open_device(path)
        try:
            self._index = self._add_with_retry()
        except OSError:
            self._close_handle()
            raise
        self._thread = threading.Thread(
            target=self._heartbeat, name="vdd-heartbeat", daemon=True
        )
        self._thread.start()

        # 拓扑变更是异步的，等它落定再去认新屏。
        time.sleep(VDD_SETTLE_SECONDS)
        new = sorted(real_display_devices() - before)
        if not new:
            # 认不出新屏就如实抛错。早先这里静默返回、applied_mode 保持 None，上层于是
            # 报「驱动不支持所选的分辨率，请换一档」——换档根本无济于事，误导排查方向。
            raise VddError("虚拟显示器已挂载，但未能在桌面上认出对应的显示设备")
        self.device = new[0]
        if apply_mode(self.device, *self.mode):
            self.applied_mode = current_mode(self.device)
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def _heartbeat(self) -> None:
        while not self._stop.wait(VDD_PING_INTERVAL):
            handle = self._handle
            if handle is None:
                return
            try:
                _ioctl(handle, VDD_IOCTL_UPDATE)
            except OSError:
                # 这里不做重连：句柄已经出问题，上层重新判定比在这里硬撑更安全。
                # 屏不会因为停 ping 自己消失，收尾仍由 close() 的显式 REMOVE 负责。
                return

    def _add_with_retry(self) -> int:
        """插一块屏，失败时隔一个拍子重试一次。

        实测快速反复插拔会让驱动短暂进入坏状态，`VDD_IOCTL_ADD` 报
        `WinError 31`（设备无法正常工作），过几秒自行恢复。正常调度一轮只插一次，
        但「设置页点了检测、紧接着任务开跑」这种连续操作会撞上，重试一次就够。
        """

        assert self._handle is not None
        try:
            index = _ioctl(self._handle, VDD_IOCTL_ADD)
        except OSError:
            time.sleep(VDD_SETTLE_SECONDS * 2)
            index = _ioctl(self._handle, VDD_IOCTL_ADD)
        _ioctl(self._handle, VDD_IOCTL_UPDATE)
        return index

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            # 超时必须大于单次 IOCTL 的超时：心跳若正卡在 GetOverlappedResultEx 里，
            # join 提前返回会导致我们在它仍持有句柄时 CloseHandle。
            self._thread.join(timeout=VDD_IOCTL_TIMEOUT_MS / 1000 + 2)
            self._thread = None
        handle, index = self._handle, self._index
        removed = False
        if handle is not None and index is not None:
            with suppress(OSError):
                # index 是 2 字节大端
                _ioctl(
                    handle, VDD_IOCTL_REMOVE, bytes(((index >> 8) & 0xFF, index & 0xFF))
                )
                _ioctl(handle, VDD_IOCTL_UPDATE)
                removed = True
        self._index = None
        self.device = None
        self.applied_mode = None
        self._close_handle()
        if removed:
            # 等拓扑落定再返回：紧接着又插一块会撞上驱动的坏状态窗口。
            time.sleep(VDD_SETTLE_SECONDS)

    def _close_handle(self) -> None:
        if self._handle is not None:
            with suppress(OSError):
                _kernel32.CloseHandle(self._handle)
            self._handle = None


__all__ = [
    "VDD_MODE_PRESETS",
    "DEFAULT_VDD_MODE",
    "apply_mode",
    "current_mode",
    "VddStatus",
    "VddProbeResult",
    "VddError",
    "VirtualDisplay",
    "probe",
    "remove_display_index",
    "VDD_SETTLE_SECONDS",
]
