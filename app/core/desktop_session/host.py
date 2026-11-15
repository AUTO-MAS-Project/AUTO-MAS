"""Electron 持有的父会话进程，负责预览和凭据。"""

import ctypes as C
import json
import logging
import os
import platform
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

from app.utils.windows.desktop_session import audio, credentials
from app.utils.windows.desktop_session.environment import probe, version_details
from app.utils.windows.desktop_session.native import (
    SYSTEM32,
    bind,
    child_session,
    enable_child_sessions,
    logoff_child,
    primary_size,
    set_dpi_awareness,
    user32,
)
from app.utils.windows.desktop_session.viewer import RdpViewer
from app.utils.windows.host import IS_ELEVATED


class Host:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.commands: queue.SimpleQueue[dict] = queue.SimpleQueue()
        self.viewer: RdpViewer | None = None
        self.session_id: int | None = None
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

    def report_environment(self, action: str) -> None:
        windows = sys.getwindowsversion()
        architecture = platform.machine().upper()
        self.report(
            "startup_environment",
            action=action,
            windowsClientRelease=(
                ("Windows 11" if windows.build >= 22000 else "Windows 10")
                if windows.product_type == 1 and windows.major == 10
                else None
            ),
            windowsVersion=[windows.major, windows.minor, windows.build],
            windowsProductType=windows.product_type,
            architecture=architecture
            if architecture in {"AMD64", "ARM64", "X86"}
            else "unknown",
            pythonVersion=list(sys.version_info[:3]),
            pythonBits=C.sizeof(C.c_void_p) * 8,
            elevated=IS_ELEVATED,
            **version_details(),
        )

    def start(self, command: dict) -> None:
        password = command.pop("password", None)
        self.report_environment("connect")
        if self.viewer is not None:
            raise RuntimeError("already_started")
        checks, port = probe()
        if not any(row["required"] and not row["ok"] for row in checks) and any(
            row["code"] == "child_enabled" and row["value"] is False for row in checks
        ):
            try:
                enable_child_sessions()
            except (OSError, AttributeError) as exc:
                self.report(
                    "child_enable_failed", nativeCode=getattr(exc, "winerror", None)
                )
            checks, port = probe()
        self.report("diagnostics", checks=checks)
        if any(
            not row["ok"] and (row["required"] or row["code"] == "child_enabled")
            for row in checks
        ):
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

    def close(self, orphaned_session: int | None = None) -> None:
        session = self.session_id if orphaned_session is None else orphaned_session
        viewer, self.viewer = self.viewer, None
        if viewer is not None:
            # 先断开 ActiveX，避免正在登录的连接在注销检查后又创建分身。
            viewer.close()
        if viewer is not None and session is None:
            # 连接期间可能在最后一次轮询后产生会话。只注销连接发起后观察到的分身。
            current = child_session()
            if current not in (
                None,
                0,
                viewer.parent_session,
                self.connection_baseline,
            ):
                session = current
        if session is not None:
            self.session_id = session
            start = time.monotonic()
            logoff_child(session)
            if child_session() == session:
                raise RuntimeError("logoff_unconfirmed")
            self.report(
                "logoff",
                sessionId=session,
                durationMs=round((time.monotonic() - start) * 1000),
            )
        self.session_id = None
        self.report("state", state="idle")

    def command(self, command: dict) -> None:
        action = command["action"]
        if action == "check":
            self.report_environment("check")
            checks, _ = probe()
            self.report("diagnostics", checks=checks)
        elif action == "connect":
            self.start(command)
        elif action == "close":
            self.close(command.get("orphanedSessionId"))
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
                elif action == "close":
                    self.report("state", state="disconnected", code="logoff_failed")
        if self.dead:
            bind(user32, "PostQuitMessage", None, C.c_int)(0)
            return
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
        if self.viewer is not None or self.session_id is not None:
            self.close()


def main() -> None:
    root = Path(sys.argv[1]).resolve(strict=True)
    set_dpi_awareness()
    comtypes.client.gen_dir = None
    ole = C.WinDLL("ole32", winmode=SYSTEM32)
    bind(ole, "OleInitialize", C.HRESULT, W.LPVOID)(None)
    try:
        Host(root).run()
    finally:
        bind(ole, "OleUninitialize", None)()


if __name__ == "__main__":
    main()
