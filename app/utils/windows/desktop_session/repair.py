"""管理员权限下的桌面分身配置事务。"""

import os
import subprocess
import sys
import winreg
from contextlib import ExitStack
from uuid import uuid4

import pywintypes
import win32api
import win32con
import win32event
import win32process
import win32security
import win32service
from win32com.shell import shell, shellcon

from app.utils.windows.host import IS_ELEVATED

from .credentials import current_identity
from .environment import RDP_DENY, TERM_SERVER, probe, repair_plan
from .native import child_sessions_enabled, handle_scope, set_child_sessions_enabled

READY_TIMEOUT_MS = 45_000
DECISION_TIMEOUT_MS = 45_000
ROLLBACK_FAILED = 2
ROLLED_BACK = 3
NO_CHANGES = 4


class RepairError(RuntimeError):
    pass


class EnvironmentRepair:
    """让提权进程持有原设置，连接成功后才确认更改。"""

    def __init__(self) -> None:
        self._handles = ExitStack()

    def start(self, changes: frozenset[str]) -> None:
        try:
            self._start(changes)
        except pywintypes.error as exc:
            self._handles.close()
            code = (
                "environment_repair_cancelled"
                if exc.winerror == 1223
                else "environment_repair_failed"
            )
            raise RepairError(code) from exc
        except BaseException:
            self._handles.close()
            raise

    def _start(self, changes: frozenset[str]) -> None:
        _, sid = current_identity()
        security = pywintypes.SECURITY_ATTRIBUTES()
        security.SECURITY_DESCRIPTOR = (
            win32security.ConvertStringSecurityDescriptorToSecurityDescriptor(
                f"D:P(A;;GA;;;BA)(A;;GA;;;{sid})", 1
            )
        )
        name = rf"Local\AUTO-MAS-desktop-repair-{uuid4().hex}"
        ready, self._commit, self._cancel = (
            self._handles.enter_context(
                handle_scope(
                    win32event.CreateEvent(security, True, False, name + suffix)
                )
            )
            for suffix in ("-ready", "-commit", "-cancel")
        )
        args = [
            "-E",
            "-s",
            "-m",
            "app.utils.windows.desktop_session.repair",
            str(os.getpid()),
            name,
            *sorted(changes),
        ]
        launched = shell.ShellExecuteEx(
            fMask=shellcon.SEE_MASK_NOCLOSEPROCESS | shellcon.SEE_MASK_FLAG_DDEWAIT,
            lpVerb="open" if IS_ELEVATED else "runas",
            lpFile=sys.executable,
            lpParameters=subprocess.list2cmdline(args),
            lpDirectory=os.getcwd(),
            nShow=win32con.SW_HIDE,
        )
        self._process = self._handles.enter_context(handle_scope(launched["hProcess"]))
        try:
            wait = win32event.WaitForMultipleObjects(
                (self._process, ready), False, READY_TIMEOUT_MS
            )
        except BaseException:
            self.finish(commit=False)
            raise
        if wait != win32event.WAIT_OBJECT_0 + 1:
            self.finish(commit=False)
            raise RepairError("environment_repair_failed")

    def finish(self, *, commit: bool) -> None:
        try:
            self._finish(commit=commit)
        except pywintypes.error as exc:
            raise RepairError("environment_restore_failed") from exc

    def _finish(self, *, commit: bool) -> None:
        with self._handles:
            if (
                win32event.WaitForSingleObject(self._process, 0)
                == win32event.WAIT_TIMEOUT
            ):
                win32event.SetEvent(self._commit if commit else self._cancel)
            if (
                win32event.WaitForSingleObject(self._process, 15_000)
                == win32event.WAIT_TIMEOUT
            ):
                raise RepairError("environment_restore_failed")
            status = win32process.GetExitCodeProcess(self._process)
            if commit and status == 0:
                return
            if status not in {ROLLED_BACK, NO_CHANGES}:
                raise RepairError("environment_restore_failed")
            if commit:
                raise RepairError("environment_repair_failed")


def _set_start_type(service, start_type: int) -> None:
    no_change = win32service.SERVICE_NO_CHANGE
    win32service.ChangeServiceConfig(
        service,
        no_change,
        start_type,
        no_change,
        None,
        None,
        0,
        None,
        None,
        None,
        None,
    )


def _apply(changes: frozenset[str], handles: ExitStack, rollback: ExitStack) -> None:
    rdp = None
    service = None
    if "rdp_local_disabled" in changes:
        rdp = handles.enter_context(
            winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                TERM_SERVER,
                0,
                winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY,
            )
        )
        original = winreg.QueryValueEx(rdp, RDP_DENY)
        if original != (1, winreg.REG_DWORD):
            raise RepairError("RDP configuration changed")
    service_disabled = "term_service_disabled" in changes
    if service_disabled or "term_service_stopped" in changes:
        scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT)
        handles.callback(win32service.CloseServiceHandle, scm)
        access = (
            win32service.SERVICE_QUERY_CONFIG
            | win32service.SERVICE_QUERY_STATUS
            | win32service.SERVICE_START
        )
        if service_disabled:
            access |= win32service.SERVICE_CHANGE_CONFIG
        service = win32service.OpenService(
            scm,
            "TermService",
            access,
        )
        handles.callback(win32service.CloseServiceHandle, service)
        start_type = win32service.QueryServiceConfig(service)[1]
        if service_disabled != (start_type == win32service.SERVICE_DISABLED):
            raise RepairError("TermService configuration changed")
    child_off = "child_enabled" in changes
    if child_off and child_sessions_enabled():
        raise RepairError("Child Session configuration changed")

    if service is not None:
        if service_disabled:
            rollback.callback(_set_start_type, service, start_type)
            _set_start_type(service, win32service.SERVICE_DEMAND_START)
        if win32service.QueryServiceStatus(service)[1] == win32service.SERVICE_STOPPED:
            try:
                win32service.StartService(service, None)
            except pywintypes.error as exc:
                if exc.winerror != 1056:  # ERROR_SERVICE_ALREADY_RUNNING
                    raise
    if rdp is not None:
        rollback.callback(winreg.SetValueEx, rdp, RDP_DENY, 0, original[1], original[0])
        winreg.SetValueEx(rdp, RDP_DENY, 0, winreg.REG_DWORD, 0)
    if child_off:
        rollback.callback(set_child_sessions_enabled, enabled=False)
        set_child_sessions_enabled(enabled=True)


def _run(parent_pid: int, name: str, changes: frozenset[str]) -> int:
    if not IS_ELEVATED:
        return NO_CHANGES
    with ExitStack() as handles:
        mutex = handles.enter_context(
            handle_scope(
                win32event.CreateMutex(None, False, r"Global\AUTO-MAS-desktop-repair")
            )
        )
        acquired = win32event.WaitForSingleObject(mutex, 0)
        if acquired not in (win32event.WAIT_OBJECT_0, win32event.WAIT_ABANDONED_0):
            return NO_CHANGES
        handles.callback(win32event.ReleaseMutex, mutex)
        parent = handles.enter_context(
            handle_scope(win32api.OpenProcess(win32con.SYNCHRONIZE, False, parent_pid))
        )
        ready, commit, cancel = (
            handles.enter_context(
                handle_scope(
                    win32event.OpenEvent(
                        win32con.SYNCHRONIZE | win32event.EVENT_MODIFY_STATE,
                        False,
                        name + suffix,
                    )
                )
            )
            for suffix in ("-ready", "-commit", "-cancel")
        )
        checks, _ = probe(include_account=False)
        if not changes or repair_plan(checks) != changes:
            return NO_CHANGES
        if (
            win32event.WaitForMultipleObjects((parent, cancel), False, 0)
            != win32event.WAIT_TIMEOUT
        ):
            return NO_CHANGES
        rollback = ExitStack()
        try:
            _apply(changes, handles, rollback)
            for _ in range(20):
                if _remote_desktop_service_running():
                    break
                if (
                    win32event.WaitForMultipleObjects((parent, cancel), False, 250)
                    != win32event.WAIT_TIMEOUT
                ):
                    return ROLLED_BACK
            win32event.SetEvent(ready)
            action = win32event.WaitForMultipleObjects(
                (cancel, commit, parent), False, DECISION_TIMEOUT_MS
            )
            if action == win32event.WAIT_OBJECT_0 + 1:
                rollback.pop_all()
                return 0
            return ROLLED_BACK
        except (OSError, pywintypes.error, RepairError):
            return ROLLED_BACK
        finally:
            try:
                rollback.close()
            except (OSError, pywintypes.error) as exc:
                raise RepairError("environment_restore_failed") from exc


def _remote_desktop_service_running() -> bool:
    with ExitStack() as handles:
        scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT)
        handles.callback(win32service.CloseServiceHandle, scm)
        service = win32service.OpenService(
            scm, "TermService", win32service.SERVICE_QUERY_STATUS
        )
        handles.callback(win32service.CloseServiceHandle, service)
        return (
            win32service.QueryServiceStatus(service)[1] == win32service.SERVICE_RUNNING
        )


if __name__ == "__main__":
    try:
        sys.exit(_run(int(sys.argv[1]), sys.argv[2], frozenset(sys.argv[3:])))
    except RepairError as exc:
        sys.exit(ROLLBACK_FAILED if str(exc) == "environment_restore_failed" else 1)
    except (OSError, pywintypes.error):
        sys.exit(1)
