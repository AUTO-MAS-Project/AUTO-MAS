"""桌面分身的只读 Windows 环境检查。"""

import ctypes as C
import os
import platform
import socket
import subprocess
import sys
import winreg
from ctypes import wintypes as W
from pathlib import Path

from .native import SYSTEM32, bind, child_sessions_enabled, process_session, user32

TERM_SERVER = r"SYSTEM\CurrentControlSet\Control\Terminal Server"
TERM_POLICY = r"SOFTWARE\Policies\Microsoft\Windows NT\Terminal Services"
TERM_SERVICE = r"SYSTEM\CurrentControlSet\Services\TermService\Parameters"
HELLO = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\PasswordLess\Device"


def registry_value(key: str, name: str):
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, key, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY
        ) as handle:
            return winreg.QueryValueEx(handle, name)[0]
    except FileNotFoundError:
        return None


def windows_signature(system: Path) -> bool:
    # Get-AuthenticodeSignature 也验证 Windows 目录签名。
    result = subprocess.run(
        [
            str(system / "WindowsPowerShell" / "v1.0" / "powershell.exe"),
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "$s=Get-AuthenticodeSignature (Join-Path $env:SystemRoot 'System32/termsrv.dll');"
            "if ($s.Status -ne 'Valid' -or "
            "$s.SignerCertificate.Subject -notmatch '(^|, )O=Microsoft Corporation(,|$)') { exit 1 }",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=15,
        creationflags=subprocess.CREATE_NO_WINDOW,
        check=False,
    )
    return result.returncode == 0


def probe() -> tuple[list[dict[str, object]], int]:
    """返回逐项检查结果和 RDP 连接端口，不改变系统配置。"""
    import win32service
    from pywintypes import error as Win32Error

    result: list[dict[str, object]] = []

    def check(code, operation, *, required=True):
        try:
            ok, value = operation()
        except (
            OSError,
            AttributeError,
            RuntimeError,
            subprocess.SubprocessError,
            Win32Error,
        ) as exc:
            ok, value = False, getattr(exc, "winerror", None)
        result.append(
            {"code": code, "ok": bool(ok), "required": required, "value": value}
        )

    version = sys.getwindowsversion()
    check(
        "windows",
        lambda: (
            version.major == 10
            and version.build >= 17763
            and version.product_type == 1,
            version.build,
        ),
    )
    check(
        "x64",
        lambda: (
            platform.machine().upper() == "AMD64" and C.sizeof(C.c_void_p) == 8,
            platform.machine(),
        ),
    )
    check(
        "edition",
        lambda: (
            True,
            registry_value(
                r"SOFTWARE\Microsoft\Windows NT\CurrentVersion", "EditionID"
            ),
        ),
        required=False,
    )

    def interactive():
        session = process_session(os.getpid())
        desktop = bind(user32, "OpenInputDesktop", W.HANDLE, W.DWORD, W.BOOL, W.DWORD)(
            0, False, 1
        )
        if desktop:
            bind(user32, "CloseDesktop", W.BOOL, W.HANDLE)(desktop)
        return session > 0 and bool(desktop), session

    check("interactive", interactive)
    system = Path(os.environ["SystemRoot"]) / "System32"

    def components():
        atl = C.WinDLL("atl", winmode=SYSTEM32)
        mstsc = C.WinDLL("mstscax", winmode=SYSTEM32)
        ncrypt = C.WinDLL("ncrypt", winmode=SYSTEM32)
        return all(
            (
                atl.AtlAxCreateControlEx,
                mstsc.DllGetClassObject,
                ncrypt.NCryptProtectSecret,
                ncrypt.NCryptUnprotectSecret,
            )
        ), None

    check("components", components)

    def native_service():
        service = registry_value(TERM_SERVICE, "ServiceDll")
        expected = str(system / "termsrv.dll")
        native = isinstance(service, str) and os.path.normcase(
            os.path.normpath(os.path.expandvars(service))
        ) == os.path.normcase(expected)
        return native, "native" if native else "non_native"

    check("service_dll", native_service)
    if result[-1]["ok"]:
        check("service_signature", lambda: (windows_signature(system), None))

    def service_state(name):
        scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT)
        try:
            service = win32service.OpenService(
                scm, name, win32service.SERVICE_QUERY_STATUS
            )
            try:
                state = win32service.QueryServiceStatus(service)[1]
                return state == win32service.SERVICE_RUNNING, state
            finally:
                win32service.CloseServiceHandle(service)
        finally:
            win32service.CloseServiceHandle(scm)

    check("term_service", lambda: service_state("TermService"))
    check("task_scheduler", lambda: service_state("Schedule"))
    check("child_enabled", lambda: (child_sessions_enabled(), None))

    def host_policy():
        policy = registry_value(TERM_POLICY, "fDenyTSConnections")
        local = (
            registry_value(TERM_SERVER, "fDenyTSConnections")
            if policy is None
            else None
        )
        return (
            local if policy is None else policy
        ) != 1, "local" if policy is None else "policy"

    check("rdp_policy", host_policy)
    check(
        "hello_only",
        lambda: (registry_value(HELLO, "DevicePasswordLessBuildVersion") != 2, None),
        required=False,
    )
    port = 0

    def listener():
        nonlocal port
        value = registry_value(TERM_SERVER + r"\WinStations\RDP-Tcp", "PortNumber")
        port = 3389 if value is None else value
        if type(port) is not int or not 1 <= port <= 65535:
            port = 0
            return False, None
        with socket.create_connection(("localhost", port), timeout=1):
            return True, port

    check("rdp_listener", listener)
    return result, port
