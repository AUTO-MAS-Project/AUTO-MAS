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
    machine = platform.machine().upper()
    check(
        "x64",
        lambda: (
            machine == "AMD64" and C.sizeof(C.c_void_p) == 8,
            machine if machine in {"AMD64", "ARM64", "X86"} else "unknown",
        ),
    )

    def home_edition():
        edition = registry_value(
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion", "EditionID"
        )
        if not isinstance(edition, str) or not edition:
            return True, "unknown"
        is_home = edition.startswith("Core")
        return not is_home, "home" if is_home else "other"

    check("home_edition", home_edition, required=False)

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

    def component(name, *exports):
        library = C.WinDLL(name, winmode=SYSTEM32)
        return all(getattr(library, export) for export in exports), None

    check("component_atl", lambda: component("atl", "AtlAxCreateControlEx"))
    check("component_rdp", lambda: component("mstscax", "DllGetClassObject"))
    check(
        "component_credentials",
        lambda: component("ncrypt", "NCryptProtectSecret", "NCryptUnprotectSecret"),
    )

    def native_service():
        service = registry_value(TERM_SERVICE, "ServiceDll")
        expected = str(system / "termsrv.dll")
        native = isinstance(service, str) and os.path.normcase(
            os.path.normpath(os.path.expandvars(service))
        ) == os.path.normcase(expected)
        return native, "missing" if service is None else None

    check("service_dll", native_service)
    if result[-1]["value"] == "missing":
        result[-1]["code"] = "service_dll_config_missing"
    if result[-1]["ok"]:
        check("service_dll_missing", lambda: ((system / "termsrv.dll").is_file(), None))
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
                if state == win32service.SERVICE_RUNNING:
                    return True, None
                if state == win32service.SERVICE_STOPPED:
                    config_handle = win32service.OpenService(
                        scm, name, win32service.SERVICE_QUERY_CONFIG
                    )
                    try:
                        start_type = win32service.QueryServiceConfig(config_handle)[1]
                    finally:
                        win32service.CloseServiceHandle(config_handle)
                    return False, (
                        "disabled"
                        if start_type == win32service.SERVICE_DISABLED
                        else "stopped"
                    )
                return False, "not_running"
            finally:
                win32service.CloseServiceHandle(service)
        finally:
            win32service.CloseServiceHandle(scm)

    for code, name in (("term_service", "TermService"), ("task_scheduler", "Schedule")):
        check(code, lambda: service_state(name))
        row = result[-1]
        if not row["ok"]:
            reason = row["value"]
            if reason == 1060:  # ERROR_SERVICE_DOES_NOT_EXIST
                reason = "missing"
            if not isinstance(reason, str):
                reason = "query_failed"
            row["code"] = f"{code}_{reason}"

    def child_state():
        enabled = child_sessions_enabled()
        return enabled, enabled

    check("child_enabled", child_state)
    # 已确认关闭时允许用户启动，由宿主尝试启用。读取失败仍阻止启动。
    if result[-1]["value"] is False:
        result[-1]["required"] = False
    elif not result[-1]["ok"]:
        result[-1]["code"] = "child_query_failed"

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
    if not result[-1]["ok"] and result[-1]["value"] in ("local", "policy"):
        result[-1]["code"] = f"rdp_{result[-1]['value']}_disabled"
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
            return False, "invalid_port"
        with socket.create_connection(("localhost", port), timeout=1):
            return True, port

    check("rdp_listener", listener)
    if result[-1]["value"] == "invalid_port":
        result[-1]["code"] = "rdp_port_invalid"
    return result, port
