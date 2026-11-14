"""由 Task Scheduler 在经核验的桌面分身内启动同版 MAS 后端。"""

import argparse
import json
import logging
import os
import sys
import threading
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .ownership import EXECUTOR_SESSION, EXECUTOR_TOKEN, data_owner


def main() -> None:
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = sys.stderr
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-id", type=int, required=True)
    parser.add_argument("--parent-pid", type=int, required=True)
    parser.add_argument("--pipe", required=True)
    parser.add_argument("--diagnostics", type=Path, required=True)
    args = parser.parse_args()
    try:
        run(args)
    except (Exception, SystemExit) as exc:
        sink = RotatingFileHandler(
            args.diagnostics, maxBytes=256 * 1024, backupCount=2, encoding="utf-8"
        )
        log = logging.getLogger("desktop_session.executor")
        log.addHandler(sink)
        log.error(
            "%s",
            json.dumps(
                {
                    "pid": os.getpid(),
                    "expectedSessionId": args.session_id,
                    "code": type(exc).__name__,
                    "nativeCode": getattr(exc, "winerror", None),
                    "location": [
                        f"{frame.name}:{frame.lineno}"
                        for frame in traceback.extract_tb(exc.__traceback__)[-6:]
                    ],
                }
            ),
        )
        raise SystemExit(1) from None


def run(args: argparse.Namespace) -> None:
    from pywintypes import error as Win32Error
    from win32pipe import PeekNamedPipe

    from app.utils.common.process.session import bind_process_session
    from app.utils.windows.desktop_session.launcher import (
        connect_executor_pipe,
        receive,
        send,
    )
    from app.utils.windows.desktop_session.native import (
        handle_scope,
        primary_size,
        process_session,
        set_dpi_awareness,
    )

    if args.session_id <= 0 or args.session_id != process_session(os.getpid()):
        raise SystemExit("executor_session_mismatch")
    bind_process_session(args.session_id)
    set_dpi_awareness()
    with handle_scope(connect_executor_pipe(args.pipe, args.parent_pid)) as pipe:
        send(
            pipe,
            {"pid": os.getpid(), "sessionId": args.session_id, "size": primary_size()},
        )
        launch = receive(pipe)
        root = Path(launch["root"]).resolve(strict=True)
        os.chdir(root)
        os.environ.update(
            {
                EXECUTOR_SESSION: str(args.session_id),
                EXECUTOR_TOKEN: launch["token"],
                "AUTO_MAS_ENV": launch["environment"],
            }
        )

        stop_watcher = threading.Event()

        def watch_parent() -> None:
            while not stop_watcher.wait(0.25):
                try:
                    PeekNamedPipe(pipe, 0)
                except (OSError, Win32Error):
                    # 父进程关闭时走后端收尾流程。避免阻塞读取占住同步管道句柄。
                    from app.core import Config

                    if Config.server is not None:
                        Config.server.should_exit = True
                    else:
                        os._exit(1)
                    return

        with data_owner(root):
            watcher = threading.Thread(target=watch_parent, daemon=True)
            watcher.start()
            try:
                from main import main as run_backend

                run_backend(port=int(launch["port"]))
            finally:
                stop_watcher.set()
                watcher.join()
        send(pipe, {"released": True, "sessionId": args.session_id})


if __name__ == "__main__":
    main()
