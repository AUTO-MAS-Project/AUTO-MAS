"""桌面分身的 Win32 绑定。"""

import ctypes as C
import os
from contextlib import contextmanager
from ctypes import wintypes as W

SYSTEM32 = 0x00000800  # LOAD_LIBRARY_SEARCH_SYSTEM32
user32 = C.WinDLL("user32", use_last_error=True, winmode=SYSTEM32)
kernel32 = C.WinDLL("kernel32", use_last_error=True, winmode=SYSTEM32)
wtsapi32 = C.WinDLL("wtsapi32", use_last_error=True, winmode=SYSTEM32)


@contextmanager
def handle_scope(handle):
    try:
        yield handle
    finally:
        handle.Close()


def bind(dll, name, result, *args):
    fn = getattr(dll, name)
    fn.argtypes = args
    fn.restype = result
    return fn


def checked(result, name):
    if not result:
        code = C.get_last_error()
        raise OSError(0, name, None, code)
    return result


def set_dpi_awareness():
    set_context = bind(user32, "SetProcessDpiAwarenessContext", W.BOOL, W.HANDLE)
    checked(set_context(-4), "SetProcessDpiAwarenessContext(PER_MONITOR_AWARE_V2)")


def process_session(pid):
    fn = bind(kernel32, "ProcessIdToSessionId", W.BOOL, W.DWORD, C.POINTER(W.DWORD))
    session = W.DWORD()
    checked(fn(pid, C.byref(session)), "ProcessIdToSessionId")
    return session.value


def child_session():
    fn = bind(wtsapi32, "WTSGetChildSessionId", W.BOOL, C.POINTER(W.ULONG))
    session = W.ULONG()
    if not fn(C.byref(session)):
        if C.get_last_error() == 1168:  # ERROR_NOT_FOUND
            return None
        checked(False, "WTSGetChildSessionId")
    return None if session.value == 0xFFFFFFFF else session.value


def child_sessions_enabled():
    fn = bind(wtsapi32, "WTSIsChildSessionsEnabled", W.BOOL, C.POINTER(W.BOOL))
    enabled = W.BOOL()
    checked(fn(C.byref(enabled)), "WTSIsChildSessionsEnabled")
    return bool(enabled.value)


def logoff_child(expected: int) -> None:
    current = child_session()
    if current is None:
        return
    if current != expected or current in (0, process_session(os.getpid())):
        raise RuntimeError("session_changed")
    logoff = bind(wtsapi32, "WTSLogoffSession", W.BOOL, W.HANDLE, W.DWORD, W.BOOL)
    checked(logoff(None, current, True), "WTSLogoffSession")


def session_state(session_id: int) -> int:
    query = bind(
        wtsapi32,
        "WTSQuerySessionInformationW",
        W.BOOL,
        W.HANDLE,
        W.DWORD,
        C.c_int,
        C.POINTER(C.c_void_p),
        C.POINTER(W.DWORD),
    )
    data = C.c_void_p()
    length = W.DWORD()
    checked(
        query(None, session_id, 8, C.byref(data), C.byref(length)), "WTSConnectState"
    )
    try:
        if not data or length.value != C.sizeof(C.c_int):
            raise RuntimeError("invalid_wts_state")
        return C.cast(data, C.POINTER(C.c_int)).contents.value
    finally:
        bind(wtsapi32, "WTSFreeMemory", None, C.c_void_p)(data)


def primary_size() -> tuple[int, int]:
    metric = bind(user32, "GetSystemMetrics", C.c_int, C.c_int)
    return metric(0), metric(1)
