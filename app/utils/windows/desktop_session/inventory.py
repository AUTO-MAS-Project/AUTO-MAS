"""检查分身会话中注销会影响的外部进程。"""

import os
from pathlib import Path

import psutil
import win32security
import win32ts
from pywintypes import error as Win32Error

from app.utils.windows.process import desktop_task_processes

from .native import process_session
from .process_runner import supervised_processes

_WINDOWS_SESSION_PROCESSES = frozenset(
    {
        "applicationframehost.exe",
        "backgroundtaskhost.exe",
        "conhost.exe",
        "csrss.exe",
        "ctfmon.exe",
        "dllhost.exe",
        "dwm.exe",
        "explorer.exe",
        "fontdrvhost.exe",
        "rdpclip.exe",
        "runtimebroker.exe",
        "securityhealthsystray.exe",
        "sihost.exe",
        "smartscreen.exe",
        "svchost.exe",
        "taskhostw.exe",
        "userinit.exe",
        "winlogon.exe",
    }
)
_WINDOWS_SHELL_APPS = frozenset(
    {
        "lockapp.exe",
        "searchhost.exe",
        "shellexperiencehost.exe",
        "shellhost.exe",
        "startmenuexperiencehost.exe",
        "textinputhost.exe",
    }
)
_SYSTEM_IDENTITIES = frozenset({"S-1-5-18", "S-1-5-19", "S-1-5-20"})


def _windows_shell(pid: int, name: str, token) -> bool:
    if name not in _WINDOWS_SESSION_PROCESSES and name not in _WINDOWS_SHELL_APPS:
        return False
    if token is not None:
        sid = win32security.ConvertSidToStringSid(token)
        if name in _WINDOWS_SESSION_PROCESSES and (
            sid in _SYSTEM_IDENTITIES or sid.startswith(("S-1-5-90-", "S-1-5-96-"))
        ):
            return True
    process = psutil.Process(pid)
    executable = Path(process.exe())
    windows = Path(os.environ["SystemRoot"])
    if not process.is_running():
        raise psutil.NoSuchProcess(pid)
    if name in _WINDOWS_SHELL_APPS:
        return executable.name.lower() == name and executable.is_relative_to(
            windows / "SystemApps"
        )
    return executable.name.lower() == name and executable.parent in {
        windows,
        windows / "System32",
        windows / "SysWOW64",
    }


def has_unmanaged_processes(session_id: int) -> bool | None:
    """只看目标会话。未知时交给用户确认，不能据此自动注销。"""
    try:
        rows = [
            (pid, name.lower(), token)
            for session, pid, name, token in win32ts.WTSEnumerateProcesses(
                win32ts.WTS_CURRENT_SERVER_HANDLE, 1, 0
            )
            if session == session_id
        ]
        if not rows:
            return None
        supervised = supervised_processes(session_id) | desktop_task_processes(
            session_id
        )
        unknown = False
        for pid, name, token in rows:
            if pid in supervised:
                continue
            try:
                if process_session(pid) == session_id and not _windows_shell(
                    pid, name, token
                ):
                    return True
            except psutil.NoSuchProcess:
                continue
            except (OSError, Win32Error, psutil.AccessDenied):
                if psutil.pid_exists(pid):
                    unknown = True
        return None if unknown else False
    except (OSError, Win32Error):
        return None
