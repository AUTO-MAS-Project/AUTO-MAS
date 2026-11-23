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
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from uuid import uuid4

import comtypes.client

from app.utils.windows.desktop_session import audio, credentials
from app.utils.windows.desktop_session.environment import (
    is_home_edition,
    probe,
    repair_plan,
    version_details,
)
from app.utils.windows.desktop_session.logon_events import recent_failure
from app.utils.windows.desktop_session.native import (
    SYSTEM32,
    bind,
    child_session,
    logoff_child,
    primary_size,
    set_dpi_awareness,
    user32,
)
from app.utils.windows.desktop_session.repair import EnvironmentRepair, RepairError
from app.utils.windows.desktop_session.viewer import RdpViewer
from app.utils.windows.host import IS_ELEVATED


def connection_failure(
    code: str, native_codes: tuple[int, ...], logon_error: int | None, *, home: bool
) -> str:
    if logon_error == -1073741260:  # STATUS_ACCOUNT_LOCKED_OUT
        return "account_locked"
    if code == "rdp_disconnected":
        reason, extended = native_codes
        if reason == 3335:  # SSL_ERR_ACCOUNT_LOCKED_OUT
            return "account_locked"
        if reason in {
            2055,
            2567,
            2823,
            3079,
            3591,
            3847,
            4615,
            6151,
            7175,
            8455,
            8711,
        } or extended in {9, 10, 768}:
            return "rdp_authentication_failed"
        if logon_error is None and (reason in {1, 2} or extended in {1, 2, 11, 12}):
            return code
    if logon_error is not None:
        return "rdp_authentication_failed"
    if code in {"rdp_disconnected", "rdp_fatal", "connect_timeout"}:
        return "rdp_home_compatibility" if home else "rdp_connection_failed"
    return code


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
        self.home_edition = False
        self.rdp_logon: tuple[datetime, str, str] | None = None
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
        for line in sys.stdin.buffer:
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
        self.report_diagnostics(checks)
        if self.environment_blocked(checks):
            self.report("state", state="idle", code="environment_blocked")
            return

        self.home_edition = any(
            row["code"] == "home_edition" and is_home_edition(row["value"])
            for row in checks
        )
        try:
            self.connect(command, password, port)
        except BaseException:
            if self.viewer is not None:
                self.close_session(None)
            raise

    @staticmethod
    def environment_blocked(checks: list[dict[str, object]]) -> bool:
        return any(row["required"] and not row["ok"] for row in checks)

    def report_diagnostics(self, checks: list[dict[str, object]]) -> None:
        self.report("diagnostics", checks=checks, repairs=sorted(repair_plan(checks)))

    def report_viewer(self, event: str, **fields) -> None:
        if (
            event == "state"
            and fields["state"] == "disconnected"
            and self.session_id is None
        ):
            fields["code"] = connection_failure(
                fields["code"],
                fields.get("nativeCodes", ()),
                fields.get("logonError"),
                home=self.home_edition,
            )
            if self.rdp_logon is not None:
                failure = recent_failure(*self.rdp_logon, remote=True)
                if failure:
                    self.report("authentication_failure", **failure)
                    codes = {failure["status"], failure["substatus"]}
                    fields["code"] = (
                        "account_locked"
                        if "0xC0000234" in codes
                        else "rdp_authentication_failed"
                    )
        self.report(event, **fields)

    def repair_environment(
        self, checks: list[dict[str, object]], changes: frozenset[str]
    ) -> None:
        repair = EnvironmentRepair()
        repair.start(changes)
        try:
            refreshed, _ = probe(include_account=False)
        except BaseException:
            repair.finish(commit=False)
            raise
        if self.environment_blocked(refreshed):
            self.report("repair_recheck_failed", checks=refreshed)
            try:
                repair.finish(commit=False)
            finally:
                failures = [row for row in refreshed if not row["ok"]]
                failed_codes = {row["code"] for row in failures}
                visible_checks = failures + [
                    row for row in checks if row["code"] not in failed_codes
                ]
                self.report("diagnostics", checks=visible_checks, repairs=[])
            raise RepairError("environment_recheck_failed")

        repair.finish(commit=True)
        self.report_diagnostics(
            refreshed
            + [
                row
                for row in checks
                if str(row["code"]).startswith(
                    ("account_source_", "microsoft_internet_")
                )
                or row["code"] == "hello_only"
            ]
        )

    def repair(self, approved: frozenset[str]) -> None:
        checks, _ = probe()
        changes = repair_plan(checks)
        if not changes or changes != approved:
            self.report_diagnostics(checks)
            self.report("repair_finished", code="environment_changed")
            return
        self.repair_environment(checks, changes)
        self.report("repair_finished")

    def connect(self, command: dict, password: str | None, port: int) -> None:
        account, sid = credentials.current_identity()
        path = self.root / "config" / "desktop-session" / "credentials.json"
        credential = (
            credentials.Credential(account, password)
            if password is not None
            else credentials.load(path, account)
        )
        started = datetime.now(UTC)
        try:
            credentials.validate(credential)
        except credentials.CredentialError as exc:
            if exc.native_code is not None:
                failure = recent_failure(started, account, sid, remote=False)
                if failure:
                    self.report("authentication_failure", **failure)
            raise

        approved = command.get("adoptSessionId")
        current = child_session()
        if current != approved:
            self.report(
                "state",
                state="idle",
                code="existing_child_session"
                if approved is None
                else "session_changed",
                existingSessionId=current,
            )
            return

        if password is not None:
            try:
                credentials.save(path, account, credentials.encode(credential))
            except credentials.CredentialError as exc:
                self.report(
                    "credential_warning", code=exc.code, nativeCode=exc.native_code
                )

        def connected() -> None:
            assert self.viewer is not None
            self.session_id = self.viewer.session_id

        self.viewer = RdpViewer(
            mode=command["mode"],
            port=port,
            size=primary_size() if command["resolution"] == "primary" else (1920, 1080),
            owner=int(command["owner"]),
            bounds=tuple(command["bounds"]),
            report=self.report_viewer,
            tick=self.tick,
            on_connected=connected,
            adopt_session_id=approved,
        )
        self.report(
            "state",
            state="connecting",
            pid=os.getpid(),
            parentSessionId=self.viewer.parent_session,
        )
        self.rdp_logon = (datetime.now(UTC), account, sid)
        self.viewer.open(credential)

    def close(
        self, orphaned_session: int | None = None, *, logoff: bool = False
    ) -> None:
        self.close_session(orphaned_session, logoff=logoff)
        self.report("state", state="idle")

    def close_session(
        self, orphaned_session: int | None, *, logoff: bool = False
    ) -> None:
        session = self.session_id if orphaned_session is None else orphaned_session
        viewer = self.viewer
        if viewer is not None:
            # 先断开 ActiveX，避免正在登录的连接在注销检查后又创建分身。
            try:
                viewer.close()
            except comtypes.COMError as exc:
                self.report("viewer_close_error", nativeCode=exc.hresult)
        # 只注销本次登录成功后登记的会话，或由 Electron 转交的已登记会话。
        self.viewer = None
        self.rdp_logon = None
        if session is not None and logoff:
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

    def command(self, command: dict) -> None:
        action = command["action"]
        if action == "check":
            self.report_environment("check")
            checks, _ = probe()
            self.report_diagnostics(checks)
        elif action == "connect":
            self.start(command)
        elif action == "repair":
            self.repair(frozenset(command["approvedRepairs"]))
        elif action == "close":
            orphaned = command.get("orphanedSessionId")
            only_if_idle = command.get("onlyIfIdle") is True
            if only_if_idle:
                from app.utils.windows.desktop_session.inventory import (
                    has_unmanaged_processes,
                )

                session = self.session_id if orphaned is None else orphaned
                if session is not None:
                    unmanaged = has_unmanaged_processes(session)
                    if unmanaged is not False:
                        code = "close_blocked" if unmanaged else "close_unverified"
                        self.report("command_error", action="close", code=code)
                        return
            self.close(
                orphaned, logoff=command.get("logoff") is True and not only_if_idle
            )
        elif action == "park_for_prompt":
            if self.viewer is not None:
                self.viewer.set_window_state("hidden")
            self.report("prompt_parked", promptId=command.get("promptId"))
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
            except RepairError as exc:
                self.report("repair_error", code=str(exc))
                if action == "repair":
                    self.report("repair_finished", code=str(exc))
                elif action != "connect":
                    self.report("command_error", action=action, code=str(exc))
                else:
                    self.report("state", state="idle", code=str(exc))
            except Exception as exc:
                info = getattr(exc, "excepinfo", None)
                self.report(
                    "command_error",
                    action=action,
                    **(
                        {"promptId": command.get("promptId")}
                        if action == "park_for_prompt"
                        else {}
                    ),
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
            self.close(logoff=False)


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
