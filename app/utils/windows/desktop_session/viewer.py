"""在父会话中承载 Windows RDP ActiveX。"""

from __future__ import annotations

import ctypes as C
import os
import queue
import time
from collections.abc import Callable
from ctypes import wintypes as W
from pathlib import Path

from .credentials import Credential
from .native import (
    SYSTEM32,
    bind,
    checked,
    child_session,
    kernel32,
    process_session,
    session_state,
    user32,
)

CLSID = "{A0C63C30-F08D-4AB4-907C-34905D770C7D}"
WINDOW_CLASS = "AutoMasDesktopSession"
WM_SIZE, WM_CLOSE, WM_SETFOCUS = 5, 0x10, 7
WM_DISPLAYCHANGE, WM_TIMER, WM_RDP_EVENT = 0x7E, 0x113, 0x8002
SW_SHOW_NOACTIVATE, SW_RESTORE = 4, 9
SWP_NOSIZE, SWP_NOZORDER, SWP_NOACTIVATE = 1, 4, 16
WS_POPUP, WS_CLIPCHILDREN, WS_CHILD, WS_VISIBLE = (
    0x80000000,
    0x02000000,
    0x40000000,
    0x10000000,
)
WS_CLIPSIBLINGS = 0x04000000
WNDPROC = C.WINFUNCTYPE(C.c_ssize_t, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
MONITORENUMPROC = C.WINFUNCTYPE(W.BOOL, W.HANDLE, W.HDC, C.POINTER(W.RECT), W.LPARAM)


class WNDCLASS(C.Structure):
    _fields_ = [
        ("style", W.UINT),
        ("proc", WNDPROC),
        ("cls_extra", C.c_int),
        ("wnd_extra", C.c_int),
        ("instance", W.HINSTANCE),
        ("icon", W.HICON),
        ("cursor", W.HANDLE),
        ("background", W.HBRUSH),
        ("menu", W.LPCWSTR),
        ("name", W.LPCWSTR),
    ]


class RdpEvents:
    def __init__(self, viewer: RdpViewer) -> None:
        self.viewer = viewer

    def OnLoginComplete(self):
        self.viewer.queue_event("login_complete")

    def OnDisconnected(self, reason):
        self.viewer.queue_event("disconnected", reason)

    def OnFatalError(self, error):
        self.viewer.queue_event("fatal_error", error)

    def OnLogonError(self, error):
        self.viewer.queue_event("logon_error", error)

    def OnRemoteDesktopSizeChange(self, width, height):
        self.viewer.queue_event("remote_size", width, height)

    def OnRequestContainerMinimize(self):
        self.viewer.queue_event("minimize_requested")

    def OnConfirmClose(self):
        return False


class RdpViewer:
    def __init__(
        self,
        *,
        mode: str,
        port: int,
        size: tuple[int, int],
        owner: int,
        bounds: tuple[int, int, int, int],
        report: Callable[..., None],
        tick: Callable[[], None],
        on_connected: Callable[[], None],
        adopt_session_id: int | None = None,
    ) -> None:
        self.mode = mode
        self.port = port
        self.size = size
        self.owner = owner
        self.bounds = bounds
        self.report = report
        self.tick = tick
        self.on_connected = on_connected
        self.adopt_session_id = adopt_session_id
        self.parent_session = process_session(os.getpid())
        self.preview = self.host = None
        self.rdp = self.events = self.active_object = None
        self.login_complete = False
        self.logon_error: int | None = None
        self.session_id: int | None = None
        self.remote_size: tuple[int, int] | None = None
        self.started = time.monotonic()
        self.closing = False
        self.window_state = "visible"
        self.phase = "connecting"
        self.event_queue: queue.SimpleQueue[tuple[str, tuple[int, ...]]] = (
            queue.SimpleQueue()
        )
        self.window_proc = WNDPROC(self.on_message)
        self.instance = bind(kernel32, "GetModuleHandleW", W.HMODULE, W.LPCWSTR)(None)
        self.show = bind(user32, "ShowWindow", W.BOOL, W.HWND, C.c_int)
        self.move = bind(
            user32,
            "SetWindowPos",
            W.BOOL,
            W.HWND,
            W.HWND,
            C.c_int,
            C.c_int,
            C.c_int,
            C.c_int,
            W.UINT,
        )
        self.iconic = bind(user32, "IsIconic", W.BOOL, W.HWND)
        self.visible = bind(user32, "IsWindowVisible", W.BOOL, W.HWND)
        self.embedded = True

    def _embed(self, embedded: bool) -> None:
        if self.embedded == embedded:
            return
        set_parent = bind(user32, "SetParent", W.HWND, W.HWND, W.HWND)
        set_style = bind(user32, "SetWindowLongW", W.LONG, W.HWND, C.c_int, W.LONG)

        def change_parent(parent: int | None) -> None:
            C.set_last_error(0)
            if not set_parent(self.preview, parent) and C.get_last_error():
                checked(False, "SetParent")

        def change_style(style: int) -> None:
            C.set_last_error(0)
            if not set_style(
                self.preview,
                -16,
                style | WS_VISIBLE | WS_CLIPCHILDREN | WS_CLIPSIBLINGS,
            ):
                if C.get_last_error():
                    checked(False, "SetWindowLongW(GWL_STYLE)")

        if embedded:
            change_style(WS_CHILD)
            try:
                change_parent(self.owner)
            except OSError:
                change_style(WS_POPUP)
                raise
        else:
            change_parent(None)
            change_style(WS_POPUP)
        self.embedded = embedded

    def open(self, credential: Credential) -> None:
        name = WINDOW_CLASS
        cursor = bind(user32, "LoadCursorW", W.HANDLE, W.HINSTANCE, C.c_void_p)
        cls = WNDCLASS(
            0,
            self.window_proc,
            0,
            0,
            self.instance,
            None,
            cursor(None, 32512),
            W.HBRUSH(5),
            None,
            name,
        )
        register = bind(user32, "RegisterClassW", W.ATOM, C.POINTER(WNDCLASS))
        checked(register(C.byref(cls)), "RegisterClassW")
        create = bind(
            user32,
            "CreateWindowExW",
            W.HWND,
            W.DWORD,
            W.LPCWSTR,
            W.LPCWSTR,
            W.DWORD,
            C.c_int,
            C.c_int,
            C.c_int,
            C.c_int,
            W.HWND,
            W.HMENU,
            W.HINSTANCE,
            W.LPVOID,
        )
        self.preview = checked(
            create(
                0x80,
                name,
                "AUTO-MAS",
                WS_CHILD | WS_CLIPCHILDREN | WS_CLIPSIBLINGS,
                *self.bounds,
                self.owner,
                None,
                self.instance,
                None,
            ),
            "CreateWindowExW(preview)",
        )
        self.host = checked(
            create(
                0,
                "STATIC",
                "",
                WS_CHILD | WS_VISIBLE,
                0,
                0,
                *self.bounds[2:],
                self.preview,
                None,
                self.instance,
                None,
            ),
            "CreateWindowExW(ATL host)",
        )
        self.position(self.bounds)
        self.show(self.preview, SW_SHOW_NOACTIVATE)
        self.connect(credential)
        timer = bind(
            user32, "SetTimer", C.c_size_t, W.HWND, C.c_size_t, W.UINT, C.c_void_p
        )
        checked(timer(self.preview, 1, 100, None), "SetTimer")

    def position(self, bounds: tuple[int, int, int, int]) -> None:
        self.bounds = bounds
        if self.window_state == "visible":
            checked(
                # HWND_TOP 只调整同一父窗内的顺序，避免 Chromium 渲染子窗遮住画面。
                self.move(self.preview, None, *bounds, SWP_NOACTIVATE),
                "Position preview",
            )

    def _park(self) -> None:
        # 后台模式临时把 ActiveX 停到屏幕外，恢复时装回 Electron 客户区。
        self._embed(False)
        if self.iconic(self.preview):
            self.show(self.preview, SW_RESTORE)
        edges: list[int] = []

        @MONITORENUMPROC
        def remember(_monitor, _dc, rect, _data):
            edges.append(rect.contents.right)
            return True

        enumerate_monitors = bind(
            user32,
            "EnumDisplayMonitors",
            W.BOOL,
            W.HDC,
            C.POINTER(W.RECT),
            MONITORENUMPROC,
            W.LPARAM,
        )
        checked(enumerate_monitors(None, None, remember, 0), "EnumDisplayMonitors")
        checked(
            self.move(
                self.preview,
                None,
                max(edges) + 64,
                0,
                0,
                0,
                SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE,
            ),
            "Park preview",
        )
        self.show(self.preview, SW_SHOW_NOACTIVATE)
        monitor = bind(user32, "MonitorFromWindow", W.HANDLE, W.HWND, W.DWORD)
        if (
            monitor(self.preview, 0)
            or self.iconic(self.preview)
            or not self.visible(self.host)
        ):
            raise RuntimeError("proxy_parking_failed")

    def set_window_state(self, state: str) -> None:
        if state == self.window_state:
            return
        previous = self.window_state
        self.window_state = state
        try:
            if state == "visible":
                if self.iconic(self.preview):
                    self.show(self.preview, SW_RESTORE)
                self._embed(True)
                self.position(self.bounds)
                self.show(self.preview, SW_SHOW_NOACTIVATE)
            elif self.mode == "native" and state == "minimized":
                self._embed(True)
            else:
                self._park()
        except (OSError, RuntimeError):
            self.window_state = previous
            if previous == "visible":
                self._embed(True)
                self.position(self.bounds)
            raise
        self.report("window", state=state, mode=self.mode, bounds=self.bounds)

    def queue_event(self, name: str, *args: int) -> None:
        if not self.closing:
            self.event_queue.put((name, args))
            post = bind(
                user32, "PostMessageW", W.BOOL, W.HWND, W.UINT, W.WPARAM, W.LPARAM
            )
            if self.preview:
                post(self.preview, WM_RDP_EVENT, 0, 0)

    def handle_events(self) -> None:
        while not self.event_queue.empty():
            name, args = self.event_queue.get_nowait()
            self.report("rdp_event", name=name, nativeCodes=args)
            if name == "login_complete":
                self.login_complete = True
                self.logon_error = None
            elif name == "logon_error":
                if args[0] in {
                    0,
                    1,
                    -1,
                    -1073741715,
                    -1073741714,
                    -1073741276,
                    -1073741260,
                }:
                    self.logon_error = args[0]
            elif name == "disconnected":
                if self.phase == "disconnected":
                    continue
                self.login_complete = False
                self.phase = "disconnected"
                self.report(
                    "state",
                    state=self.phase,
                    code="rdp_disconnected",
                    nativeCodes=(*args, int(self.rdp.ExtendedDisconnectReason)),
                    logonError=self.logon_error,
                    sessionId=self.session_id,
                )
            elif name == "fatal_error":
                self.login_complete = False
                self.phase = "disconnected"
                self.report(
                    "state",
                    state=self.phase,
                    code="rdp_fatal",
                    logonError=self.logon_error,
                    sessionId=self.session_id,
                )
            elif name == "remote_size":
                self.remote_size = (args[0], args[1])
                self.report("desktop_size", size=self.remote_size, expected=self.size)
                if self.remote_size != self.size:
                    self.phase = "disconnected"
                    self.report(
                        "state",
                        state=self.phase,
                        code="desktop_size_changed",
                        sessionId=self.session_id,
                    )
            elif name == "minimize_requested":
                self.report("minimize_requested")

    def sample(self) -> None:
        if self.phase == "disconnected":
            return
        if self.login_complete and int(self.rdp.Connected) == 1:
            try:
                session = child_session()
                active = (
                    session not in (None, 0, self.parent_session)
                    and session_state(session) == 0
                )
            except OSError:
                if self.session_id is None:
                    return
                session, active = None, False
            if self.session_id is None and active:
                if (
                    self.adopt_session_id is not None
                    and session != self.adopt_session_id
                ):
                    self.phase = "disconnected"
                    self.report("state", state=self.phase, code="session_changed")
                    return
                self.session_id = session
                if self.remote_size is None:
                    self.remote_size = (
                        int(self.rdp.DesktopWidth),
                        int(self.rdp.DesktopHeight),
                    )
                self.on_connected()
                self.phase = "connected"
                self.report(
                    "state",
                    state=self.phase,
                    sessionId=session,
                    size=self.remote_size,
                    adopted=self.adopt_session_id is not None,
                )
            elif self.session_id is not None and (
                session != self.session_id or not active
            ):
                self.phase = "disconnected"
                self.report(
                    "state",
                    state=self.phase,
                    code="session_changed",
                    sessionId=self.session_id,
                    observed=session,
                )
        if self.phase == "connecting" and time.monotonic() - self.started >= 90:
            self.phase = "disconnected"
            self.report(
                "state",
                state=self.phase,
                code="connect_timeout",
                logonError=self.logon_error,
                sessionId=self.session_id,
            )

    def on_message(self, hwnd, message, wparam, lparam):
        default = bind(
            user32, "DefWindowProcW", C.c_ssize_t, W.HWND, W.UINT, W.WPARAM, W.LPARAM
        )
        if self.closing or hwnd != self.preview:
            return default(hwnd, message, wparam, lparam)
        try:
            if message == WM_CLOSE:
                self.report("close_requested")
                return 0
            if message == WM_SIZE and wparam != 1 and self.host:
                rect = W.RECT()
                get_rect = bind(
                    user32, "GetClientRect", W.BOOL, W.HWND, C.POINTER(W.RECT)
                )
                checked(get_rect(self.preview, C.byref(rect)), "GetClientRect")
                checked(
                    self.move(
                        self.host,
                        None,
                        0,
                        0,
                        rect.right,
                        rect.bottom,
                        SWP_NOZORDER | SWP_NOACTIVATE,
                    ),
                    "Resize ATL host",
                )
            elif (
                message == WM_SETFOCUS and self.host and self.window_state == "visible"
            ):
                bind(user32, "SetFocus", W.HWND, W.HWND)(self.host)
            elif message == WM_DISPLAYCHANGE and (
                self.window_state == "hidden"
                or self.window_state == "minimized"
                and self.mode == "proxy"
            ):
                self._park()
            elif message == WM_RDP_EVENT:
                self.handle_events()
                return 0
            elif message == WM_TIMER:
                self.tick()
                return 0
        except Exception as exc:
            self.report(
                "viewer_error",
                code=type(exc).__name__,
                nativeCode=getattr(exc, "winerror", None),
            )
            self.phase = "disconnected"
            self.report(
                "state",
                state=self.phase,
                code="viewer_failed",
                sessionId=self.session_id,
            )
        return default(hwnd, message, wparam, lparam)

    def connect(self, credential: Credential) -> None:
        from comtypes import GUID, STDMETHOD, COMError, IUnknown
        from comtypes.automation import VARIANT
        from comtypes.client import GetEvents, GetModule
        from comtypes.typeinfo import LoadTypeLibEx

        class IOleInPlaceActiveObject(IUnknown):
            _iid_ = GUID("{00000117-0000-0000-C000-000000000046}")
            _methods_ = [
                STDMETHOD(C.HRESULT, "GetWindow", [C.POINTER(W.HWND)]),
                STDMETHOD(C.HRESULT, "ContextSensitiveHelp", [W.BOOL]),
                STDMETHOD(C.HRESULT, "TranslateAccelerator", [C.POINTER(W.MSG)]),
            ]

        mstscax = GetModule(
            LoadTypeLibEx(str(Path(os.environ["SystemRoot"]) / "System32/mstscax.dll"))
        )
        atl = C.WinDLL("atl", use_last_error=True, winmode=SYSTEM32)
        pointer = C.POINTER(IUnknown)
        create = bind(
            atl,
            "AtlAxCreateControlEx",
            C.HRESULT,
            W.LPCWSTR,
            W.HWND,
            C.c_void_p,
            C.POINTER(pointer),
            C.POINTER(pointer),
            C.POINTER(GUID),
            pointer,
        )
        control = pointer()
        create(CLSID, self.host, None, None, C.byref(control), C.byref(GUID()), None)
        if not control:
            raise RuntimeError("activex_missing")
        self.rdp = control.QueryInterface(mstscax.IMsRdpClient10)
        try:
            self.active_object = control.QueryInterface(IOleInPlaceActiveObject)
        except COMError as exc:
            if exc.hresult != -2147467262:  # E_NOINTERFACE
                raise
        self.events = GetEvents(
            control, RdpEvents(self), interface=mstscax.IMsTscAxEvents
        )
        rdp = self.rdp
        rdp.Server = "localhost"
        rdp.DesktopWidth, rdp.DesktopHeight = self.size
        rdp.ColorDepth = 32
        rdp.SecuredSettings2.AudioRedirectionMode = 0
        settings = rdp.AdvancedSettings7
        settings.RDPPort = self.port
        settings.EnableCredSspSupport = True
        settings.SmartSizing = True
        settings.EnableAutoReconnect = False
        nonscriptable = control.QueryInterface(mstscax.IMsRdpClientNonScriptable5)
        nonscriptable.UseMultimon = False
        nonscriptable.AllowCredentialSaving = False
        nonscriptable.AllowPromptingForCredentials = False
        extended = control.QueryInterface(mstscax.IMsRdpExtendedSettings)
        extended.Property["ConnectToChildSession"] = C.byref(VARIANT(True))
        rdp.Domain, rdp.UserName = credential.rdp_identity
        nonscriptable.ClearTextPassword = credential.password
        current = child_session()
        if current != self.adopt_session_id:
            # 验证凭据和初始化 ActiveX 期间也可能出现别的子会话。
            self.phase = "disconnected"
            self.report(
                "state",
                state="idle",
                code="existing_child_session"
                if self.adopt_session_id is None
                else "session_changed",
                existingSessionId=current,
            )
            return
        self.started = time.monotonic()
        rdp.Connect()

    def pump_until(self, finished: Callable[[], bool]) -> None:
        from comtypes import COMError

        get = bind(
            user32, "GetMessageW", C.c_int, C.POINTER(W.MSG), W.HWND, W.UINT, W.UINT
        )
        translate = bind(user32, "TranslateMessage", W.BOOL, C.POINTER(W.MSG))
        dispatch = bind(user32, "DispatchMessageW", C.c_ssize_t, C.POINTER(W.MSG))
        is_child = bind(user32, "IsChild", W.BOOL, W.HWND, W.HWND)
        message = W.MSG()
        while not finished() and (result := get(C.byref(message), None, 0, 0)) != 0:
            if result == -1:
                checked(False, "GetMessageW")
            if (
                self.active_object
                and 0x100 <= message.message <= 0x109
                and (message.hWnd == self.host or is_child(self.host, message.hWnd))
            ):
                try:
                    if self.active_object.TranslateAccelerator(C.byref(message)) == 0:
                        continue
                except COMError:
                    # ActiveX 可拒绝此条快捷键，继续按普通消息分发。
                    pass
            translate(C.byref(message))
            dispatch(C.byref(message))

    def close(self) -> None:
        self.closing = True
        try:
            if self.rdp is not None and self.rdp.Connected:
                self.rdp.Disconnect()
        finally:
            try:
                if self.events is not None:
                    self.events.disconnect()
            finally:
                self.events = self.active_object = self.rdp = None
                if self.preview:
                    destroy = bind(user32, "DestroyWindow", W.BOOL, W.HWND)
                    destroy(self.preview)
                    self.preview = self.host = None
                unregister = bind(
                    user32, "UnregisterClassW", W.BOOL, W.LPCWSTR, W.HINSTANCE
                )
                unregister(WINDOW_CLASS, self.instance)
