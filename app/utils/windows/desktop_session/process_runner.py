"""主会话对分身进程的启动、退出观察和停止控制。"""

import asyncio
import base64
import json
import time
from collections.abc import Awaitable, Callable, Mapping
from contextlib import suppress
from contextvars import ContextVar
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
_action_callback = ContextVar("desktop_action_callback", default=False)


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


class DesktopInput:
    def __init__(self, process: "DesktopProcess") -> None:
        self._process = process
        self._pending = bytearray()
        self._closed = False

    def write(self, data: bytes) -> None:
        if self._closed:
            raise BrokenPipeError
        self._pending.extend(data)

    async def drain(self) -> None:
        data = bytes(self._pending)
        self._pending.clear()
        await self._process.send_control(
            {"input": base64.b64encode(data).decode("ascii")}
        )

    def close(self) -> None:
        # 交互输入只用于短指令，进程退出或停止时由执行器关闭写端。
        self._closed = True


class DesktopProcess:
    def __init__(
        self,
        pid: int,
        pipe,
        worker,
        on_log: Callable[[str], None] | None = None,
        *,
        stream_limit: int | None = None,
        merge: bool = False,
        on_restart: Callable[[], Awaitable[None]] | None = None,
        interactive: bool = False,
    ) -> None:
        self.pid = pid
        self._pipe = pipe
        self._worker = worker
        self._stopping = False
        self._on_log = on_log
        self._on_restart = on_restart
        self._write_lock = asyncio.Lock()
        self._restarting: asyncio.Task | None = None
        self.stdin = DesktopInput(self) if interactive else None
        self.stdout = asyncio.StreamReader(limit=stream_limit) if stream_limit else None
        self.stderr = (
            asyncio.StreamReader(limit=stream_limit)
            if stream_limit and not merge
            else None
        )
        self.returncode: int | None = None
        self._exited = asyncio.Event()
        self._result: tuple[int, bytes, bytes] | None = None
        self._completion = asyncio.create_task(self._observe())

    async def _observe(self) -> tuple[int, bytes, bytes]:
        output = {"stdout": bytearray(), "stderr": bytearray()}
        try:
            while "returnCode" not in (response := await _read(self._pipe)):
                if "log" in response:
                    if self._on_log is not None:
                        # 复用本机启动器的回调契约，让回调能同步等主循环交付进度。
                        await asyncio.to_thread(self._on_log, response["log"])
                elif "restart" in response:
                    if self._on_restart is None:
                        raise RuntimeError("分身任务没有注册重启操作")
                    token = _action_callback.set(True)
                    try:
                        self._restarting = asyncio.create_task(self._on_restart())
                        await self._restarting
                    except asyncio.CancelledError:
                        if not self._stopping:
                            raise
                        self.returncode = 1
                        return 1, b"", b""
                    finally:
                        self._restarting = None
                        _action_callback.reset(token)
                    await self.send_control({"restart": True})
                elif "eof" in response:
                    stream = self.stdout if response["eof"] == "stdout" else self.stderr
                    if stream is not None:
                        stream.feed_eof()
                elif "exitCode" in response:
                    self.returncode = int(response["exitCode"])
                    self._result = (
                        self.returncode,
                        bytes(output["stdout"]),
                        bytes(output["stderr"]),
                    )
                    self._exited.set()
                else:
                    name, chunk = next(iter(response.items()))
                    data = base64.b64decode(chunk)
                    stream = self.stdout if name == "stdout" else self.stderr
                    if stream is None:
                        output[name].extend(data)
                    else:
                        stream.feed_data(data)
                        # 交出事件循环，让上层及时读取长时间运行中的输出。
                        await asyncio.sleep(0)
            self.returncode = int(response["returnCode"])
            return (
                self.returncode,
                bytes(output["stdout"]),
                bytes(output["stderr"]),
            )
        finally:
            self._exited.set()
            for stream in (self.stdout, self.stderr):
                if stream is not None:
                    stream.feed_eof()
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

    async def send_control(self, message: dict) -> None:
        async with self._write_lock:
            await _write(self._pipe, message, deadline=time.monotonic() + 5)

    async def wait_result(self) -> tuple[int, bytes, bytes]:
        await self._exited.wait()
        if self._result is not None:
            return self._result
        return await self.wait()

    async def wait_exit(self) -> int:
        await self._exited.wait()
        if self.returncode is None:
            code, _, _ = await self.wait()
            return code
        return self.returncode

    async def stop(self) -> None:
        if not self._completion.done() and not self._stopping:
            self._stopping = True
            if self._restarting is not None:
                self._restarting.cancel()
            try:
                await self.send_control({"stop": True})
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
    stream_limit: int | None = None,
    stdin: bytes | None = None,
    interactive: bool = False,
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
            "stream": stream_limit is not None,
            "interactive": interactive,
            "stdin": base64.b64encode(stdin).decode("ascii")
            if stdin is not None
            else None,
        },
        stream_limit=stream_limit,
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
    on_restart: Callable[[], Awaitable[None]] | None = None,
) -> tuple[int, bytes, bytes]:
    from app.utils.common.process.scope import current_process_scope

    async def run() -> tuple[int, bytes, bytes]:
        if (scope := current_process_scope.get()) is not None:
            scope.ensure_can_start()
        process = await _launch(
            desktop,
            {"action": action, "arguments": arguments, "root": str(desktop.root)},
            on_log=on_log,
            worker_module=worker_module,
            on_restart=on_restart,
        )
        try:
            return await process.wait()
        finally:
            await process.stop()

    if _action_callback.get():
        return await run()
    async with _action_lock:
        return await run()


async def _launch(
    desktop: DesktopProcessTarget,
    request: dict,
    *,
    on_log: Callable[[str], None] | None = None,
    worker_module: str = "app.utils.windows.desktop_session.process_worker",
    stream_limit: int | None = None,
    on_restart: Callable[[], Awaitable[None]] | None = None,
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
        process = DesktopProcess(
            int(result["pid"]),
            pipe,
            worker,
            on_log,
            stream_limit=stream_limit,
            merge=request.get("merge", False),
            on_restart=on_restart,
            interactive=request.get("interactive", False),
        )
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
