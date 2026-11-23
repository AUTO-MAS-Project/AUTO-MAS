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

from .credentials import current_identity
from .native import SYSTEM32, bind, child_sessions_enabled, process_session, user32

TERM_SERVER = r"SYSTEM\CurrentControlSet\Control\Terminal Server"
TERM_POLICY = r"SOFTWARE\Policies\Microsoft\Windows NT\Terminal Services"
TERM_SERVICE = r"SYSTEM\CurrentControlSet\Services\TermService\Parameters"
WINDOWS_VERSION = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
HELLO = WINDOWS_VERSION + r"\PasswordLess\Device"
RDP_DENY = "fDenyTSConnections"
POWERSHELL = (
    Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
)

REPAIRABLE = frozenset(
    {
        "child_enabled",
        "rdp_local_disabled",
        "term_service_disabled",
        "term_service_stopped",
    }
)


def is_home_edition(edition: object) -> bool:
    return isinstance(edition, str) and edition.startswith("Core")


def repair_plan(checks: list[dict[str, object]]) -> frozenset[str]:
    failures = {row["code"] for row in checks if not row["ok"] and row["required"]}
    changes = REPAIRABLE.intersection(failures)
    if changes and not failures.difference(REPAIRABLE | {"rdp_listener"}):
        return changes
    return frozenset()


def account_details() -> tuple[str, str]:
    from pywintypes import error

    try:
        _, sid = current_identity()
        output = subprocess.run(
            [
                str(POWERSHELL),
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                f"$u=Get-LocalUser -SID '{sid}' -ErrorAction SilentlyContinue;"
                f"if (!$u) {{ $u=Get-CimInstance Win32_UserAccount -Filter \"SID = '{sid}'\" }};"
                "if ($u.PrincipalSource -eq 'MicrosoftAccount') {"
                "'microsoft'; try {"
                "$n=New-Object -ComObject NetworkListManager -ErrorAction Stop;"
                "if ($n.IsConnectedToInternet) { 'online' } else { 'offline' }"
                "} catch { 'unknown' }"
                "} elseif ($u.PrincipalSource -eq 'Local') { 'local' }"
                "elseif ($u.PrincipalSource -eq 'ActiveDirectory') { 'active_directory' }"
                "elseif ($u.PrincipalSource -in 'AzureAD','AzureActiveDirectory') { 'entra' }"
                "elseif ($u.PrincipalSource -or ($u -and !$u.LocalAccount)) { 'other' }",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        ).stdout.split()
    except (OSError, subprocess.SubprocessError, error):
        return "unknown", "unknown"
    if not output or output[0] not in {
        "local",
        "microsoft",
        "active_directory",
        "entra",
        "other",
    }:
        return "unknown", "unknown"
    network = output[1] if output[1:] in (["online"], ["offline"]) else "unknown"
    return output[0], network


def registry_value(key: str, name: str):
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, key, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY
        ) as handle:
            return winreg.QueryValueEx(handle, name)[0]
    except FileNotFoundError:
        return None


def version_details() -> dict[str, str | int | None]:
    """读取可用于本地诊断的系统版本字段。"""

    def read(name: str):
        try:
            return registry_value(WINDOWS_VERSION, name)
        except OSError:
            return None

    edition = read("EditionID")
    release = read("DisplayVersion") or read("ReleaseId")
    revision = read("UBR")
    return {
        "windowsEdition": edition if isinstance(edition, str) else None,
        "windowsDisplayVersion": release if isinstance(release, str) else None,
        "windowsBuildRevision": revision if type(revision) is int else None,
    }


def windows_signature() -> bool:
    # Get-AuthenticodeSignature 也验证 Windows 目录签名。
    result = subprocess.run(
        [
            str(POWERSHELL),
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "$ErrorActionPreference='Stop';"
            "Import-Module (Join-Path $PSHOME 'Modules/Microsoft.PowerShell.Security');"
            "$s=Get-AuthenticodeSignature -LiteralPath "
            "(Join-Path $env:SystemRoot 'System32/termsrv.dll');"
            "if ($s.Status -ne 'Valid' -or "
            "$s.SignerCertificate.Subject -notmatch '(^|, )O=Microsoft Corporation(,|$)') { exit 2 };"
            "exit 0",
        ],
        env={
            key: value
            for key, value in os.environ.items()
            if key.upper() != "PSMODULEPATH"
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=15,
        creationflags=subprocess.CREATE_NO_WINDOW,
        check=False,
    )
    if result.returncode == 2:
        return False
    result.check_returncode()
    return True


def probe(*, include_account: bool = True) -> tuple[list[dict[str, object]], int]:
    """返回逐项检查结果和 RDP 连接端口，不改变系统配置。"""
    import win32service
    from pywintypes import error as Win32Error

    result: list[dict[str, object]] = []

    def check(code, operation, *, required=True, error_code=None) -> dict[str, object]:
        try:
            ok, value = operation()
        except (
            OSError,
            AttributeError,
            RuntimeError,
            subprocess.SubprocessError,
            Win32Error,
        ) as exc:
            code = error_code or code
            ok, value = False, getattr(exc, "winerror", None)
        row = {"code": code, "ok": bool(ok), "required": required, "value": value}
        result.append(row)
        return row

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
        edition = registry_value(WINDOWS_VERSION, "EditionID")
        if not isinstance(edition, str) or not edition:
            return True, "unknown"
        return True, edition

    edition = check("home_edition", home_edition, required=False)

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

    service_dll = check("service_dll", native_service)
    if service_dll["value"] == "missing":
        service_dll["code"] = "service_dll_config_missing"
    if service_dll["ok"]:
        service_dll_missing = check(
            "service_dll_missing", lambda: ((system / "termsrv.dll").is_file(), None)
        )
        if service_dll_missing["ok"]:
            check(
                "service_signature",
                lambda: (windows_signature(), None),
                error_code="service_signature_check_failed",
            )

    def service_state(name):
        scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT)
        try:
            service = win32service.OpenService(
                scm, name, win32service.SERVICE_QUERY_STATUS
            )
            try:
                state = win32service.QueryServiceStatus(service)[1]
                if name == "TermService" or state == win32service.SERVICE_STOPPED:
                    config_handle = win32service.OpenService(
                        scm, name, win32service.SERVICE_QUERY_CONFIG
                    )
                    try:
                        start_type = win32service.QueryServiceConfig(config_handle)[1]
                    finally:
                        win32service.CloseServiceHandle(config_handle)
                    if start_type == win32service.SERVICE_DISABLED:
                        return False, "disabled"
                if state == win32service.SERVICE_RUNNING:
                    return True, None
                if state == win32service.SERVICE_STOPPED:
                    return False, "stopped"
                return False, "not_running"
            finally:
                win32service.CloseServiceHandle(service)
        finally:
            win32service.CloseServiceHandle(scm)

    for code, name in (("term_service", "TermService"), ("task_scheduler", "Schedule")):
        row = check(code, lambda: service_state(name))
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

    child_enabled = check("child_enabled", child_state)
    if not child_enabled["ok"] and child_enabled["value"] is not False:
        child_enabled["code"] = "child_query_failed"

    def host_policy():
        policy = registry_value(TERM_POLICY, RDP_DENY)
        local = registry_value(TERM_SERVER, RDP_DENY) if policy is None else None
        return (
            local if policy is None else policy
        ) != 1, "local" if policy is None else "policy"

    rdp_policy = check("rdp_policy", host_policy)
    if not rdp_policy["ok"] and rdp_policy["value"] in ("local", "policy"):
        rdp_policy["code"] = f"rdp_{rdp_policy['value']}_disabled"
    if include_account:
        account, internet = account_details()
        check(f"account_source_{account}", lambda: (True, None), required=False)
        if account == "microsoft":
            if internet != "online":
                check(
                    f"microsoft_internet_{internet}",
                    lambda: (False, None),
                    required=False,
                )
            try:
                hello_setting = registry_value(HELLO, "DevicePasswordLessBuildVersion")
            except OSError:
                hello_setting = None
            if hello_setting == 2:
                check("hello_only", lambda: (False, None), required=False)
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

    # 家庭版缺少常规 RDP 监听时，仍可尝试 ActiveX 的原生子会话连接。
    rdp_listener = check(
        "rdp_listener", listener, required=not is_home_edition(edition["value"])
    )
    if rdp_listener["value"] == "invalid_port":
        rdp_listener["code"] = "rdp_port_invalid"
        rdp_listener["required"] = True
    elif not rdp_listener["ok"] and not rdp_listener["required"]:
        rdp_listener["code"] = "rdp_home_listener"
    return result, port
