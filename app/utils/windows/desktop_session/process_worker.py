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
from logging.handlers import RotatingFileHandler
from pathlib import Path
from tempfile import TemporaryFile

import win32pipe
from pywintypes import error as Win32Error

from .launcher import connect_executor_pipe, receive, send
from .native import handle_scope, process_session


def run(pipe) -> None:
    launch = receive(pipe)
    if "open" in launch:
        os.startfile(launch["open"])
        send(pipe, {"pid": 0})
        send(pipe, {"returnCode": 0})
        return

    if launch["capture"]:
        with TemporaryFile() as stdout, TemporaryFile() as stderr:
            run_process(pipe, launch, stdout, stderr)
    else:
        stream = subprocess.PIPE if launch.get("drain") else subprocess.DEVNULL
        run_process(pipe, launch, stream, stream)


def run_process(pipe, launch: dict, stdout, stderr) -> None:
    from app.utils.windows.process import WindowsTaskProcessJob

    job = WindowsTaskProcessJob(kill_on_close=True)
    try:
        process = subprocess.Popen(
            launch["argv"],
            cwd=launch["cwd"],
            stdin=subprocess.DEVNULL,
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
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                threading.Thread(
                    target=discard_output, args=(stream,), daemon=True
                ).start()
        send(pipe, {"pid": process.pid})
        # 允许引导程序退出后，Job 继续持有派生的游戏或被跟踪的脚本。
        while process.poll() is None or (
            launch["retain"] and job.has_active_processes()
        ):
            if win32pipe.PeekNamedPipe(pipe, 0)[1] and receive(pipe)["stop"]:
                break
            time.sleep(0.05)
        job.kill()
        code = process.wait()
        if launch["capture"]:
            for name, stream in (("stdout", stdout), ("stderr", stderr)):
                stream.seek(0)
                while chunk := stream.read(24 * 1024):
                    send(pipe, {name: base64.b64encode(chunk).decode("ascii")})
        send(pipe, {"returnCode": code})
    finally:
        job.close()


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
