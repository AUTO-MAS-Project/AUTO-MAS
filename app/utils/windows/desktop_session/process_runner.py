"""主会话对分身进程的启动、退出观察和停止控制。"""

import asyncio
import time
from contextlib import suppress
from pathlib import Path

import pythoncom
import win32api
import win32con
import win32event
import win32pipe
from pywintypes import error as Win32Error

from .credentials import current_identity
from .launcher import client_pid, create_executor_pipe, receive, run_executor, send


async def _read(pipe, *, deadline: float | None = None) -> dict:
    while not win32pipe.PeekNamedPipe(pipe, 0)[1]:
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError("等待分身进程响应超时")
        await asyncio.sleep(0.05)
    response = receive(pipe)
    if "error" in response:
        raise RuntimeError(
            f"分身进程执行失败：{response['error']} ({response['nativeCode']})"
        )
    return response


class DesktopProcess:
    def __init__(self, pid: int, pipe, worker) -> None:
        self.pid = pid
        self._pipe = pipe
        self._worker = worker
        self._stopping = False
        self._completion = asyncio.create_task(self._observe())

    async def _observe(self) -> int:
        try:
            return int((await _read(self._pipe))["returnCode"])
        finally:
            # 关闭控制管道会让执行器收尾。先等进程退出再释放主端的任务资源。
            self._pipe.Close()
            try:
                await asyncio.to_thread(_wait_worker, self._worker)
            finally:
                self._worker.Close()

    @property
    def running(self) -> bool:
        if not self._completion.done():
            return True
        self._completion.result()
        return False

    async def stop(self) -> None:
        if not self._completion.done() and not self._stopping:
            self._stopping = True
            try:
                send(self._pipe, {"stop": True})
            except Win32Error:
                # 执行器可能已经退出，由观察任务确认退出结果。
                pass
        try:
            await asyncio.wait_for(asyncio.shield(self._completion), timeout=5)
        except TimeoutError:
            win32api.TerminateProcess(self._worker, 1)
            with suppress(Win32Error):
                await asyncio.shield(self._completion)


def _wait_worker(worker) -> None:
    if win32event.WaitForSingleObject(worker, 3000) == win32event.WAIT_TIMEOUT:
        win32api.TerminateProcess(worker, 1)
        if win32event.WaitForSingleObject(worker, 3000) == win32event.WAIT_TIMEOUT:
            raise TimeoutError("分身进程执行器未退出")


async def launch_desktop_process(
    session_id: int,
    *,
    source: Path,
    root: Path,
    argv: list[str],
    cwd: Path | None,
) -> DesktopProcess:
    name, pipe = create_executor_pipe()
    worker = None
    owned = False
    pythoncom.CoInitialize()
    try:
        folder, registration = run_executor(
            session_id,
            source=source,
            root=root,
            account=current_identity()[0],
            pipe_name=name,
        )
        deadline = time.monotonic() + 30
        try:
            while True:
                try:
                    win32pipe.ConnectNamedPipe(pipe, None)
                    break
                except Win32Error as error:
                    if error.winerror == 535:  # ERROR_PIPE_CONNECTED
                        break
                    if error.winerror not in (231, 536) or time.monotonic() >= deadline:
                        raise
                    await asyncio.sleep(0.05)
            worker = win32api.OpenProcess(
                win32con.SYNCHRONIZE | win32con.PROCESS_TERMINATE,
                False,
                client_pid(pipe, session_id),
            )
            send(pipe, {"argv": argv, "cwd": str(cwd) if cwd is not None else None})
            result = await _read(pipe, deadline=deadline)
        finally:
            with suppress(pythoncom.com_error):
                folder.DeleteTask(registration, 0)
            del folder
        process = DesktopProcess(int(result["pid"]), pipe, worker)
        owned = True
        return process
    finally:
        pythoncom.CoUninitialize()
        if not owned:
            pipe.Close()
            if worker is not None:
                try:
                    await asyncio.to_thread(_wait_worker, worker)
                finally:
                    worker.Close()
