"""在已核验的子会话内启动和监督一次桌面进程。"""

import argparse
import base64
import logging
import os
import subprocess
import sys
import threading
import time
import traceback
from collections.abc import Callable
from contextlib import closing, suppress
from importlib import import_module
from logging.handlers import RotatingFileHandler
from pathlib import Path
from queue import Empty, Queue
from tempfile import TemporaryFile

import win32api
import win32con
import win32pipe
from pywintypes import error as Win32Error

from .launcher import connect_executor_pipe, receive, send
from .native import handle_scope, process_session

WINDOW_ACTIONS = {
    "activate_process_window": "activate_window",
    "minimize_process_window": "minimize_window",
    "maximize_process_window": "maximize_window",
    "show_process_window": "show_window",
    "hide_process_window": "hide_window",
    "close_process_window": "close_window",
}


def run(pipe) -> None:
    launch = receive(pipe)
    action = launch.get("action")
    if action in WINDOW_ACTIONS:
        send(pipe, {"pid": os.getpid()})
        code = run_window_action(action, launch["arguments"])
        send(pipe, {"returnCode": code})
        return
    if action == "has_process_window":
        from app.utils.common.process.manager import is_process_running
        from app.utils.common.process.session import configure_parent_scope

        session_id = process_session(os.getpid())
        configure_parent_scope(lambda: session_id)
        send(pipe, {"pid": os.getpid()})
        code = int(not is_process_running(launch["arguments"]["name"]))
        send(pipe, {"returnCode": code})
        return
    if action == "input_desktop_unavailable":
        from app.utils.windows.display import input_desktop_unavailable

        send(pipe, {"pid": os.getpid()})
        if reason := input_desktop_unavailable():
            send(
                pipe,
                {"stdout": base64.b64encode(reason.encode("utf-8")).decode("ascii")},
            )
        send(pipe, {"returnCode": 0})
        return
    if "open" in launch:
        os.startfile(launch["open"])
        send(pipe, {"pid": 0})
        send(pipe, {"returnCode": 0})
        return

    if launch.get("stream"):
        stdout = subprocess.PIPE if launch["stream_stdout"] else subprocess.DEVNULL
        stderr = subprocess.PIPE if launch["stream_stderr"] else subprocess.DEVNULL
        run_process(pipe, launch, stdout, stderr)
    elif launch["capture"]:
        with TemporaryFile() as stdout, TemporaryFile() as stderr:
            run_process(pipe, launch, stdout, stderr)
    else:
        stream = subprocess.PIPE if launch.get("drain") else subprocess.DEVNULL
        run_process(pipe, launch, stream, stream)


def run_window_action(action: str, arguments: dict) -> int:
    from app.utils.common.process.manager import get_main_window_handle, window
    from app.utils.common.process.operations import managed_process

    pid = int(arguments["pid"])
    if process_session(pid) != process_session(os.getpid()):
        return 1
    process = managed_process(pid)
    hwnd = (
        get_main_window_handle(
            process.pid,
            arguments.get("title") or None,
            arguments.get("class") or None,
        )
        if process is not None
        else None
    )
    operation = getattr(window, WINDOW_ACTIONS[action])
    return int(not (hwnd and operation(hwnd)))


def run_process(pipe, launch: dict, stdout, stderr) -> None:
    from app.utils.windows.process import WindowsTaskProcessJob

    owned = launch.get("owned", True)
    job = WindowsTaskProcessJob(kill_on_close=owned)
    process = None
    try:
        process = subprocess.Popen(
            launch["argv"],
            cwd=launch["cwd"],
            stdin=subprocess.PIPE
            if launch.get("interactive") or launch.get("stdin") is not None
            else subprocess.DEVNULL,
            stdout=stdout,
            stderr=subprocess.STDOUT if launch["merge"] else stderr,
            env=launch["env"],
            creationflags=job.creation_flags | subprocess.CREATE_NO_WINDOW,
        )
        try:
            job.assign(process.pid, suspended=True, breakaway=False)
        except BaseException:
            process.kill()
            process.wait()
            raise
        output: Queue[tuple[str, bytes | None]] | None = (
            Queue(maxsize=64) if launch.get("stream") else None
        )
        readers = []
        for name, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
            if stream is not None and output is not None:
                reader = threading.Thread(
                    target=stream_output, args=(name, stream, output), daemon=True
                )
                readers.append(reader)
                reader.start()
            elif stream is not None:
                threading.Thread(
                    target=discard_output, args=(stream,), daemon=True
                ).start()
        if launch.get("stop_root_only"):
            # 主端取得同一个进程对象的句柄后才继续，避免用可复用的 PID 做兜底。
            with closing(
                win32api.OpenProcess(
                    win32con.SYNCHRONIZE | win32con.PROCESS_TERMINATE,
                    False,
                    process.pid,
                )
            ) as root:
                send(pipe, {"pid": process.pid, "rootHandle": int(root)})
                if receive(pipe) != {"rootHandleReceived": True}:
                    raise RuntimeError("主端未确认分身进程句柄")
        else:
            send(pipe, {"pid": process.pid})
        if process.stdin is not None and launch.get("stdin") is not None:
            threading.Thread(
                target=write_input,
                args=(process.stdin, base64.b64decode(launch["stdin"])),
                daemon=True,
            ).start()
        if output is not None:
            supervise_streamed_process(pipe, launch, process, job, output, readers)
            return
        # 允许引导程序退出后，Job 继续持有派生的游戏或被跟踪的脚本。
        exit_sent = False
        stop = False
        while process.poll() is None or (
            launch["retain"] and job.has_active_processes()
        ):
            if win32pipe.PeekNamedPipe(pipe, 0)[1]:
                message = receive(pipe)
                if message.get("release") and not owned:
                    send(pipe, {"returnCode": process.poll() or 0})
                    return
                if message.get("stop"):
                    if launch.get("stop_root_only"):
                        stop_root(pipe, process)
                        return
                    stop = True
                    break
                if message.get("terminateRoot") and process.poll() is None:
                    process.terminate()
            if launch["retain"] and not exit_sent and process.poll() is not None:
                if launch["capture"]:
                    send_capture(pipe, stdout, stderr)
                send(pipe, {"exitCode": process.returncode})
                exit_sent = True
            time.sleep(0.05)
        if owned or stop:
            job.kill()
        code = process.wait()
        if launch["capture"] and not exit_sent:
            send_capture(pipe, stdout, stderr)
        send(pipe, {"returnCode": code})
    finally:
        try:
            if (
                launch.get("stop_root_only")
                and process is not None
                and process.poll() is None
            ):
                process.terminate()
                process.wait(timeout=3)
        finally:
            job.close()


def send_capture(pipe, stdout, stderr) -> None:
    for name, stream in (("stdout", stdout), ("stderr", stderr)):
        # Windows 子进程可能继承文件句柄，父端读取时保留其写入偏移。
        offset = stream.tell()
        remaining = os.fstat(stream.fileno()).st_size
        stream.seek(0)
        try:
            while remaining and (chunk := stream.read(min(remaining, 24 * 1024))):
                send(pipe, {name: base64.b64encode(chunk).decode("ascii")})
                remaining -= len(chunk)
        finally:
            stream.seek(offset)


def stop_root(pipe, process) -> None:
    if process.poll() is None:
        process.terminate()
    send(pipe, {"returnCode": process.wait(timeout=3)})


def supervise_streamed_process(pipe, launch, process, job, output, readers) -> None:
    exit_sent = False
    while True:
        if win32pipe.PeekNamedPipe(pipe, 0)[1]:
            message = receive(pipe)
            if message.get("release") and not launch.get("owned", True):
                send(pipe, {"returnCode": process.poll() or 0})
                return
            if message.get("stop"):
                if launch.get("stop_root_only"):
                    stop_root(pipe, process)
                    return
                job.kill()
            elif message.get("terminateRoot") and process.poll() is None:
                process.terminate()
            elif "input" in message and process.stdin is not None:
                with suppress(BrokenPipeError):
                    process.stdin.write(base64.b64decode(message["input"]))
                    process.stdin.flush()
        code = process.poll()
        if code is not None and not exit_sent:
            send(pipe, {"exitCode": code})
            exit_sent = True
            if not launch["retain"] and launch.get("owned", True):
                job.kill()
        try:
            name, chunk = output.get(timeout=0.05)
        except Empty:
            if (
                exit_sent
                and not job.has_active_processes()
                and not any(reader.is_alive() for reader in readers)
                and output.empty()
            ):
                break
        else:
            if chunk is None:
                send(pipe, {"eof": name})
            else:
                send(pipe, {name: base64.b64encode(chunk).decode("ascii")})
    send(pipe, {"returnCode": process.wait()})


def write_input(stream, data: bytes) -> None:
    with suppress(BrokenPipeError), stream:
        stream.write(data)


def stream_output(name: str, stream, output: Queue[tuple[str, bytes | None]]) -> None:
    with stream:
        while chunk := stream.read1(24 * 1024):
            output.put((name, chunk))
    output.put((name, None))


def discard_output(stream) -> None:
    with stream:
        while stream.read(65536):
            pass


def main(handle_request: Callable = run) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-id", type=int, required=True)
    parser.add_argument("--parent-pid", type=int, required=True)
    parser.add_argument("--pipe", required=True)
    parser.add_argument("--diagnostics", type=Path, required=True)
    parser.add_argument("--handler-module")
    args = parser.parse_args()
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = sys.stderr
    if args.session_id <= 0 or process_session(os.getpid()) != args.session_id:
        raise SystemExit("executor_session_mismatch")
    try:
        with handle_scope(connect_executor_pipe(args.pipe, args.parent_pid)) as pipe:
            try:
                if args.handler_module is not None:
                    handle_request = import_module(args.handler_module).run_action
                handle_request(pipe)
            except Exception as error:
                with suppress(OSError, Win32Error):
                    send(
                        pipe,
                        {
                            "error": type(error).__name__,
                            "nativeCode": getattr(error, "winerror", None),
                        },
                    )
                raise
    except Exception as error:
        # 只保留异常类型、系统错误码和代码位置，避免记录命令行参数。
        logger = logging.getLogger(__name__)
        with closing(
            RotatingFileHandler(
                args.diagnostics, maxBytes=256 * 1024, backupCount=2, encoding="utf-8"
            )
        ) as handler:
            logger.addHandler(handler)
            logger.error(
                "%s (%s) at %s",
                type(error).__name__,
                getattr(error, "winerror", None),
                ", ".join(
                    f"{frame.name}:{frame.lineno}"
                    for frame in traceback.extract_tb(error.__traceback__)[-5:]
                ),
            )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
