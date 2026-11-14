"""Electron 持有的父会话进程，负责预览、凭据和子执行器启动。"""

import ctypes as C
import json
import logging
import os
import queue
import sys
import threading
import time
import traceback
from ctypes import wintypes as W
from logging.handlers import RotatingFileHandler
from pathlib import Path
from uuid import uuid4

import comtypes.client
import win32api
import win32con
import win32event
from pywintypes import error as Win32Error

from app.utils.windows.desktop_session import audio, credentials
from app.utils.windows.desktop_session.environment import probe
from app.utils.windows.desktop_session.launcher import (
    client_pid,
    create_executor_pipe,
    receive,
    run_executor,
    send,
)
from app.utils.windows.desktop_session.native import (
    SYSTEM32,
    bind,
    child_session,
    logoff_child,
    primary_size,
    set_dpi_awareness,
    user32,
)
from app.utils.windows.desktop_session.viewer import RdpViewer


class Host:
    def __init__(self, root: Path, source: Path) -> None:
        self.root = root
        self.source = source
        self.commands: queue.SimpleQueue[dict] = queue.SimpleQueue()
        self.viewer: RdpViewer | None = None
        self.session_id: int | None = None
        self.executor_request: dict | None = None
        self.executor_pipe = None
        self.executor_registration = None
        self.executor_pid: int | None = None
        self.executor_process = None
        self.executor_deadline = 0.0
        self.next_sample = 0.0
        self.next_audio = 0.0
        self.volume = 0
        self.audio_state = None
        self.connection_baseline = None
        self.dead = False
        self.correlation = uuid4().hex
        path = root / "debug" / "desktop-session" / "host.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            path, maxBytes=2 * 1024 * 1024, backupCount=4, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        self.log = logging.getLogger("desktop_session.host")
        self.log.setLevel(logging.INFO)
        self.log.addHandler(handler)

    def report(self, event: str, **fields) -> None:
        row = {"event": event, "correlation": self.correlation, **fields}
        self.log.info("%s", json.dumps(row, ensure_ascii=False))
        try:
            print(json.dumps(row), flush=True)
        except OSError:
            self.dead = True

    def read_commands(self) -> None:
        for line in sys.stdin:
            try:
                self.commands.put(json.loads(line))
            except ValueError:
                self.commands.put({"action": "invalid"})
        self.commands.put({"action": "eof"})

    def start(self, command: dict) -> None:
        password = command.pop("password", None)
        if self.viewer is not None:
            raise RuntimeError("already_started")
        checks, port = probe()
        self.report("diagnostics", checks=checks)
        if any(row["required"] and not row["ok"] for row in checks):
            self.report("state", state="idle", code="environment_blocked")
            return

        account, _ = credentials.current_identity()
        path = self.root / "config" / "desktop-session" / "credentials.json"
        credential = (
            credentials.Credential(account, password)
            if password is not None
            else credentials.load(path, account)
        )
        credentials.validate(credential)
        # 连接事件只暂存密文，密码随本次调用结束释放引用。
        encrypted = credentials.encode(credential) if password is not None else None

        def connected() -> None:
            assert self.viewer is not None
            self.session_id = self.viewer.session_id
            if encrypted is not None:
                try:
                    credentials.save(path, account, encrypted)
                except credentials.CredentialError as exc:
                    self.report(
                        "credential_warning", code=exc.code, nativeCode=exc.native_code
                    )

        self.viewer = RdpViewer(
            mode=command["mode"],
            port=port,
            size=primary_size() if command["resolution"] == "primary" else (1920, 1080),
            owner=int(command["owner"]),
            bounds=tuple(command["bounds"]),
            report=self.report,
            tick=self.tick,
            on_connected=connected,
        )
        try:
            self.connection_baseline = child_session()
            if self.connection_baseline is not None:
                self.report(
                    "existing_child_session", sessionId=self.connection_baseline
                )
            self.report(
                "state",
                state="connecting",
                pid=os.getpid(),
                parentSessionId=self.viewer.parent_session,
            )
            self.viewer.open(credential)
        except BaseException:
            self.viewer.close()
            self.viewer = None
            raise

    def launch(self, command: dict) -> None:
        if (
            self.executor_pipe is not None
            or self.viewer is None
            or self.viewer.phase != "connected"
        ):
            raise RuntimeError("executor_unavailable")
        assert self.session_id is not None
        self.executor_request = command
        name, self.executor_pipe = create_executor_pipe()
        try:
            self.executor_registration = run_executor(
                self.session_id,
                source=self.source,
                root=self.root,
                account=credentials.current_identity()[0],
                pipe_name=name,
            )
        except BaseException:
            self.executor_pipe.Close()
            self.executor_pipe = None
            self.executor_request = None
            raise
        self.executor_deadline = time.monotonic() + 30
        self.report("executor_launch", sessionId=self.session_id)

    def clear_registration(self) -> None:
        if self.executor_registration is None:
            return
        folder, name = self.executor_registration
        self.executor_registration = None
        try:
            folder.DeleteTask(name, 0)
        except Exception as exc:
            self.report(
                "registration_cleanup_failed", nativeCode=getattr(exc, "hresult", None)
            )

    def poll_executor(self) -> None:
        import win32pipe

        pipe = self.executor_pipe
        if pipe is None:
            process = self.executor_process
            if process is not None and win32event.WaitForSingleObject(process, 0) == 0:
                process.Close()
                self.executor_process = None
                self.report("executor_interrupted", sessionId=self.session_id)
            return
        assert self.session_id is not None
        try:
            if self.executor_request is not None and self.executor_pid is None:
                try:
                    win32pipe.ConnectNamedPipe(pipe, None)
                except Win32Error as exc:
                    if (
                        exc.winerror in (231, 536)
                        and time.monotonic() < self.executor_deadline
                    ):
                        return
                    if exc.winerror != 535:  # ERROR_PIPE_CONNECTED
                        raise
                self.executor_pid = client_pid(pipe, self.session_id)
                self.executor_process = win32api.OpenProcess(
                    win32con.SYNCHRONIZE, False, self.executor_pid
                )
            if (
                self.executor_request is not None
                and time.monotonic() >= self.executor_deadline
            ):
                raise TimeoutError("executor_handshake_timeout")
            if not win32pipe.PeekNamedPipe(pipe, 0)[1]:
                return
            message = receive(pipe)
            if self.executor_request is not None:
                if (
                    message.get("pid") != self.executor_pid
                    or message.get("sessionId") != self.session_id
                ):
                    raise RuntimeError("executor_session_mismatch")
                if (
                    self.viewer is None
                    or tuple(message.get("size", ())) != self.viewer.size
                ):
                    raise RuntimeError("desktop_size_changed")
                request, self.executor_request = self.executor_request, None
                send(
                    pipe,
                    {key: request[key] for key in ("environment", "token", "port")}
                    | {"root": str(self.root)},
                )
                self.report(
                    "executor_ready",
                    pid=self.executor_pid,
                    sessionId=self.session_id,
                    size=message["size"],
                )
                self.clear_registration()
            elif (
                message.get("released") is True
                and message.get("sessionId") == self.session_id
            ):
                pipe.Close()
                self.executor_pipe = self.executor_pid = None
                if self.executor_process is not None:
                    self.executor_process.Close()
                    self.executor_process = None
                self.report("executor_released", sessionId=self.session_id)
        except (OSError, RuntimeError, Win32Error) as exc:
            self.report(
                "executor_error",
                code=type(exc).__name__,
                started=self.executor_request is None,
                nativeCode=getattr(exc, "winerror", None),
                location=[
                    f"{frame.name}:{frame.lineno}"
                    for frame in traceback.extract_tb(exc.__traceback__)[-5:]
                ],
            )
            pipe.Close()
            self.executor_pipe = self.executor_pid = self.executor_request = None
            self.clear_registration()

    def close(self) -> None:
        if self.executor_pipe is not None or self.executor_process is not None:
            raise RuntimeError("executor_running")
        session = self.session_id
        if self.viewer and session is None:
            # 连接期间可能在最后一次轮询后产生会话。只注销连接发起后观察到的分身。
            current = child_session()
            if current not in (
                None,
                0,
                self.viewer.parent_session,
                self.connection_baseline,
            ):
                session = current
        if session is not None:
            start = time.monotonic()
            logoff_child(session)
            self.report(
                "logoff",
                sessionId=session,
                durationMs=round((time.monotonic() - start) * 1000),
            )
        if self.viewer is not None:
            self.viewer.close()
            self.viewer = None
        self.session_id = None
        self.report("state", state="idle")

    def command(self, command: dict) -> None:
        action = command["action"]
        if action == "check":
            checks, _ = probe()
            self.report("diagnostics", checks=checks)
        elif action == "connect":
            self.start(command)
        elif action == "execute":
            self.launch(command)
        elif action == "close":
            self.close()
        elif action == "eof":
            self.dead = True
        elif self.viewer is not None:
            if action == "bounds":
                self.viewer.position(tuple(command["bounds"]))
            elif action == "window":
                self.viewer.set_window_state(command["state"])
            elif action == "volume":
                self.volume = command["volume"]
                self.next_audio = 0

    def tick(self) -> None:
        while not self.commands.empty():
            command = self.commands.get_nowait()
            action = command.get("action")
            try:
                self.command(command)
            except credentials.CredentialError as exc:
                self.report(
                    "state", state="idle", code=exc.code, nativeCode=exc.native_code
                )
            except Exception as exc:
                info = getattr(exc, "excepinfo", None)
                self.report(
                    "command_error",
                    action=action,
                    code=type(exc).__name__,
                    location=[
                        f"{frame.name}:{frame.lineno}"
                        for frame in traceback.extract_tb(exc.__traceback__)[-5:]
                    ],
                    nativeCode=info[5]
                    if info
                    else getattr(exc, "hresult", getattr(exc, "winerror", None)),
                )
                if action == "connect":
                    self.report("state", state="idle", code="connection_failed")
        if self.dead:
            bind(user32, "PostQuitMessage", None, C.c_int)(0)
            return
        self.poll_executor()
        if self.viewer is None:
            return
        now = time.monotonic()
        if now >= self.next_sample:
            self.next_sample = now + 1
            self.viewer.sample()
        if self.viewer.phase == "connected" and now >= self.next_audio:
            self.next_audio = now + 2
            try:
                current = (self.volume, audio.apply(os.getpid(), self.volume))
            except (OSError, comtypes.COMError):
                current = (self.volume, 0)
            if current != self.audio_state:
                self.audio_state = current
                self.report("audio", volume=current[0], sessions=current[1])

    def run(self) -> None:
        threading.Thread(target=self.read_commands, daemon=True).start()
        self.report("ready", pid=os.getpid())
        while not self.dead:
            self.tick()
            viewer = self.viewer
            if viewer is None:
                time.sleep(0.05)
                continue
            viewer.pump_until(lambda: self.viewer is not viewer)
        if self.executor_pipe is not None:
            self.executor_pipe.Close()
        if self.executor_process is not None:
            self.executor_process.Close()
        self.clear_registration()
        if self.viewer is not None:
            self.viewer.close()


def main() -> None:
    root = Path(sys.argv[1]).resolve(strict=True)
    set_dpi_awareness()
    comtypes.client.gen_dir = None
    ole = C.WinDLL("ole32", winmode=SYSTEM32)
    bind(ole, "OleInitialize", C.HRESULT, W.LPVOID)(None)
    try:
        Host(root, Path(__file__).resolve().parents[3]).run()
    finally:
        bind(ole, "OleUninitialize", None)()


if __name__ == "__main__":
    main()
