"""主会话对分身进程的启动、退出观察和停止控制。"""

import asyncio
import base64
import json
import time
from collections.abc import Callable, Mapping
from contextlib import suppress
from pathlib import Path

import pythoncom
import win32api
import win32con
import win32event
import win32pipe
from pywintypes import error as Win32Error

from app.utils.common.process.session import DesktopProcessTarget

from .credentials import current_identity
from .launcher import (
    client_pid,
    create_executor_pipe,
    message_chunks,
    read_chunk,
    run_executor,
    write_chunk,
)

_action_lock = asyncio.Lock()


async def _read(pipe, *, deadline: float | None = None) -> dict:
    payload = bytearray()
    while True:
        while not win32pipe.PeekNamedPipe(pipe, 0)[1]:
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("等待分身进程响应超时")
            await asyncio.sleep(0.05)
        chunk = read_chunk(pipe)
        payload.extend(chunk)
        if chunk.endswith(b"\n"):
            break
    response = json.loads(payload)
    if "error" in response:
        raise RuntimeError(
            f"分身进程执行失败：{response['error']} ({response['nativeCode']})"
        )
    return response


async def _write(pipe, message: dict, *, deadline: float) -> None:
    for chunk in message_chunks(message):
        while not write_chunk(pipe, chunk):
            if time.monotonic() >= deadline:
                raise TimeoutError("等待分身进程读取请求超时")
            await asyncio.sleep(0.05)


class DesktopProcess:
    def __init__(
        self, pid: int, pipe, worker, on_log: Callable[[str], None] | None = None
    ) -> None:
        self.pid = pid
        self._pipe = pipe
        self._worker = worker
        self._stopping = False
        self._on_log = on_log
        self._completion = asyncio.create_task(self._observe())

    async def _observe(self) -> tuple[int, bytes, bytes]:
        output = {"stdout": bytearray(), "stderr": bytearray()}
        try:
            while "returnCode" not in (response := await _read(self._pipe)):
                if "log" in response:
                    if self._on_log is not None:
                        # 复用本机启动器的回调契约，让回调能同步等主循环交付进度。
                        await asyncio.to_thread(self._on_log, response["log"])
                else:
                    name, chunk = next(iter(response.items()))
                    output[name].extend(base64.b64decode(chunk))
            return (
                int(response["returnCode"]),
                bytes(output["stdout"]),
                bytes(output["stderr"]),
            )
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

    async def wait(self) -> tuple[int, bytes, bytes]:
        return await asyncio.shield(self._completion)

    async def stop(self) -> None:
        if not self._completion.done() and not self._stopping:
            self._stopping = True
            try:
                await _write(self._pipe, {"stop": True}, deadline=time.monotonic() + 1)
            except (OSError, Win32Error):
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
    desktop: DesktopProcessTarget,
    *,
    argv: list[str],
    cwd: Path | None,
    capture: bool = False,
    merge: bool = False,
    retain: bool = False,
    drain: bool = False,
    env: Mapping[str, str] | None = None,
) -> DesktopProcess:
    return await _launch(
        desktop,
        {
            "argv": argv,
            "cwd": str(cwd) if cwd is not None else None,
            "capture": capture,
            "merge": merge,
            "retain": retain,
            "drain": drain,
            "env": dict(env) if env is not None else None,
        },
    )


async def open_in_desktop(desktop: DesktopProcessTarget, target: str) -> None:
    process = await _launch(desktop, {"open": target})
    try:
        await process.wait()
    finally:
        await process.stop()


async def run_desktop_action(
    desktop: DesktopProcessTarget,
    action: str,
    arguments: dict[str, str | bool | float | None],
    on_log: Callable[[str], None] | None = None,
    *,
    worker_module: str,
) -> tuple[int, bytes, bytes]:
    from app.utils.common.process.scope import current_process_scope

    async with _action_lock:
        if (scope := current_process_scope.get()) is not None:
            scope.ensure_can_start()
        process = await _launch(
            desktop,
            {"action": action, "arguments": arguments, "root": str(desktop.root)},
            on_log=on_log,
            worker_module=worker_module,
        )
        try:
            return await process.wait()
        finally:
            await process.stop()


async def _launch(
    desktop: DesktopProcessTarget,
    request: dict,
    *,
    on_log: Callable[[str], None] | None = None,
    worker_module: str = "app.utils.windows.desktop_session.process_worker",
) -> DesktopProcess:
    name, pipe = create_executor_pipe()
    worker = None
    owned = False
    pythoncom.CoInitialize()
    try:
        folder, registration = run_executor(
            desktop.session_id,
            source=desktop.source,
            root=desktop.root,
            account=current_identity()[0],
            pipe_name=name,
            worker_module=worker_module,
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
                client_pid(pipe, desktop.session_id),
            )
            await _write(pipe, request, deadline=deadline)
            result = await _read(pipe, deadline=deadline)
        finally:
            with suppress(pythoncom.com_error):
                folder.DeleteTask(registration, 0)
            del folder
        process = DesktopProcess(int(result["pid"]), pipe, worker, on_log=on_log)
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
