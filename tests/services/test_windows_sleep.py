"""隔离 Win32 电源边界，绝不让测试机器睡眠。"""

import ctypes
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.services.windows import power


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "success,privilege_error", [(True, False), (False, False), (True, True)]
)
async def test_sleep_keeps_wake_events_and_restores_shutdown_privilege(
    monkeypatch, success, privilege_error
):
    token = SimpleNamespace(Close=Mock())
    previous = [(23, 0)]
    adjust = Mock(return_value=previous)
    monkeypatch.setitem(
        sys.modules,
        "win32api",
        SimpleNamespace(
            GetCurrentProcess=lambda: 1,
            GetLastError=lambda: 1300 if privilege_error else 0,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "win32con",
        SimpleNamespace(
            TOKEN_ADJUST_PRIVILEGES=0x20, TOKEN_QUERY=8, SE_PRIVILEGE_ENABLED=2
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "win32security",
        SimpleNamespace(
            SE_SHUTDOWN_NAME="SeShutdownPrivilege",
            OpenProcessToken=lambda *args: token,
            LookupPrivilegeValue=lambda *args: 23,
            AdjustTokenPrivileges=adjust,
        ),
    )
    monkeypatch.setitem(
        sys.modules, "winerror", SimpleNamespace(ERROR_NOT_ALL_ASSIGNED=1300)
    )
    suspend = Mock(return_value=success)
    monkeypatch.setattr(
        ctypes,
        "WinDLL",
        lambda *args, **kwargs: SimpleNamespace(SetSuspendState=suspend),
        raising=False,
    )
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 5, raising=False)
    monkeypatch.setattr(
        ctypes, "WinError", lambda code: OSError(code, "native error"), raising=False
    )
    monkeypatch.setattr(
        subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args, 0)
    )
    controller = power.WindowsPowerController()
    if privilege_error:
        with pytest.raises(PermissionError):
            await controller.execute("Sleep")
    elif success:
        await controller.execute("Sleep")
    else:
        with pytest.raises(OSError):
            await controller.execute("Sleep")
    if privilege_error:
        suspend.assert_not_called()
    else:
        suspend.assert_called_once_with(False, False, False)
        assert suspend.argtypes == [ctypes.c_ubyte, ctypes.c_ubyte, ctypes.c_ubyte]
        assert suspend.restype is ctypes.c_ubyte
    assert adjust.call_args.args == (token, False, previous)
    token.Close.assert_called_once()
