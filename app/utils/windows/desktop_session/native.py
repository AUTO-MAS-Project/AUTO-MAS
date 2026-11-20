"""桌面分身的 Win32 绑定。"""

import ctypes as C
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


def token_sid(token) -> str:
    import win32security

    sid, _ = win32security.GetTokenInformation(token, win32security.TokenUser)
    return win32security.ConvertSidToStringSid(sid)


def current_identity() -> tuple[str, str]:
    import win32api
    import win32con
    import win32security

    with handle_scope(
        win32security.OpenProcessToken(
            win32api.GetCurrentProcess(), win32con.TOKEN_QUERY
        )
    ) as token:
        sid = token_sid(token)
    return win32api.GetUserNameEx(2), sid
