"""通过 Task Scheduler 启动子会话执行器，并核验跨会话通道。"""

import ctypes as C
import json
import os
import subprocess
import sys
from ctypes import wintypes as W
from pathlib import Path
from uuid import uuid4

import pywintypes
import win32api
import win32con
import win32file
import win32pipe
import win32security

from .native import (
    bind,
    checked,
    child_session,
    handle_scope,
    kernel32,
    process_session,
    session_state,
)


def send(pipe, data: dict) -> None:
    win32file.WriteFile(pipe, json.dumps(data).encode("utf-8"))


def receive(pipe) -> dict:
    _, data = win32file.ReadFile(pipe, 65536)
    return json.loads(data)


def connect_executor_pipe(name: str, parent_pid: int):
    pipe = win32file.CreateFile(
        name,
        win32con.GENERIC_READ | win32con.GENERIC_WRITE,
        0,
        None,
        win32con.OPEN_EXISTING,
        0,
        None,
    )
    try:
        get_pid = bind(
            kernel32,
            "GetNamedPipeServerProcessId",
            W.BOOL,
            W.HANDLE,
            C.POINTER(W.ULONG),
        )
        pid = W.ULONG()
        checked(get_pid(int(pipe), C.byref(pid)), "GetNamedPipeServerProcessId")
        # 从内核读取管道服务器 PID。子会话的低权限令牌可能无法查询父进程。
        if pid.value != parent_pid:
            raise RuntimeError("executor_parent_mismatch")
        win32pipe.SetNamedPipeHandleState(
            pipe, win32pipe.PIPE_READMODE_MESSAGE, None, None
        )
    except BaseException:
        pipe.Close()
        raise
    return pipe


def run_executor(
    session_id: int,
    *,
    source: Path,
    root: Path,
    account: str,
    pipe_name: str,
):
    import pythoncom
    import win32com.client

    from app.utils.windows.host import IS_ELEVATED

    from .credentials import current_identity

    if (
        session_id in (0, process_session(os.getpid()))
        or child_session() != session_id
        or session_state(session_id) != 0
    ):
        raise RuntimeError("session_changed")
    scheduler = win32com.client.Dispatch("Schedule.Service")
    scheduler.Connect()
    folder = scheduler.GetFolder("\\")
    task = scheduler.NewTask(0)
    task.Principal.UserId = account
    task.Principal.LogonType = 3  # TASK_LOGON_INTERACTIVE_TOKEN
    # 控制端需要持有执行器的等待和终止句柄，双方使用同级权限。
    task.Principal.RunLevel = int(IS_ELEVATED)
    task.Settings.AllowDemandStart = True
    task.Settings.DisallowStartIfOnBatteries = False
    task.Settings.StopIfGoingOnBatteries = False
    task.Settings.ExecutionTimeLimit = "PT0S"
    task.Settings.Hidden = True
    action = task.Actions.Create(0)
    interpreter = Path(sys.executable).with_name("pythonw.exe")
    action.Path = str(interpreter) if interpreter.is_file() else sys.executable
    action.WorkingDirectory = str(source)
    action.Arguments = subprocess.list2cmdline(
        [
            "-m",
            "app.utils.windows.desktop_session.process_worker",
            "--session-id",
            str(session_id),
            "--pipe",
            pipe_name,
            "--parent-pid",
            str(os.getpid()),
            "--diagnostics",
            str(root / "debug" / "desktop-session" / "executor-start.log"),
        ]
    )
    name = f"AUTO-MAS-DesktopSession-{uuid4().hex}"
    registration = folder.RegisterTaskDefinition(
        name, task, 2, account, pythoncom.Empty, 3, pythoncom.Empty
    )
    try:
        # TASK_RUN_USE_SESSION_ID | TASK_RUN_USER_SID
        registration.RunEx(None, 4 | 8, session_id, current_identity()[1])
    except BaseException:
        folder.DeleteTask(name, 0)
        raise
    return folder, name


def create_executor_pipe():
    from .credentials import current_identity

    _, sid = current_identity()
    attributes = pywintypes.SECURITY_ATTRIBUTES()
    attributes.SECURITY_DESCRIPTOR = (
        win32security.ConvertStringSecurityDescriptorToSecurityDescriptor(
            f"D:P(A;;GA;;;{sid})",
            1,
        )
    )
    name = rf"\\.\pipe\AUTO-MAS-DesktopSession-{uuid4().hex}"
    pipe = win32pipe.CreateNamedPipe(
        name,
        win32pipe.PIPE_ACCESS_DUPLEX | 0x00080000,  # FILE_FLAG_FIRST_PIPE_INSTANCE
        win32pipe.PIPE_TYPE_MESSAGE
        | win32pipe.PIPE_READMODE_MESSAGE
        | win32pipe.PIPE_NOWAIT
        | 8,
        1,
        65536,
        65536,
        0,
        attributes,  # PIPE_REJECT_REMOTE_CLIENTS
    )
    return name, pipe


def client_pid(pipe, expected_session: int) -> int:
    from .credentials import current_identity

    get_pid = bind(
        kernel32, "GetNamedPipeClientProcessId", W.BOOL, W.HANDLE, C.POINTER(W.ULONG)
    )
    pid = W.ULONG()
    checked(get_pid(int(pipe), C.byref(pid)), "GetNamedPipeClientProcessId")
    if process_session(pid.value) != expected_session:
        raise RuntimeError("executor_session_mismatch")
    with handle_scope(win32api.OpenProcess(0x1000, False, pid.value)) as process:
        with handle_scope(
            win32security.OpenProcessToken(process, win32con.TOKEN_QUERY)
        ) as token:
            sid = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
            if win32security.ConvertSidToStringSid(sid) != current_identity()[1]:
                raise RuntimeError("executor_account_mismatch")
    return pid.value
