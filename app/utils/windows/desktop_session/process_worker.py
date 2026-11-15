"""在已核验的子会话内启动和监督一次桌面进程。"""

import argparse
import logging
import os
import subprocess
import sys
import time
import traceback
from contextlib import closing, suppress
from logging.handlers import RotatingFileHandler
from pathlib import Path

import win32pipe
from pywintypes import error as Win32Error

from .launcher import connect_executor_pipe, receive, send
from .native import handle_scope, process_session


def run(pipe) -> None:
    from app.utils.windows.process import WindowsTaskProcessJob

    job = WindowsTaskProcessJob(kill_on_close=True)
    try:
        launch = receive(pipe)
        process = subprocess.Popen(
            launch["argv"],
            cwd=launch["cwd"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=job.creation_flags | subprocess.CREATE_NO_WINDOW,
        )
        try:
            job.assign(process.pid, suspended=True, breakaway=False)
        except BaseException:
            process.kill()
            process.wait()
            raise
        send(pipe, {"pid": process.pid})
        while process.poll() is None:
            if win32pipe.PeekNamedPipe(pipe, 0)[1] and receive(pipe)["stop"]:
                break
            time.sleep(0.05)
        job.kill()
        send(pipe, {"returnCode": process.wait()})
    finally:
        job.close()


def main() -> None:
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
                run(pipe)
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
