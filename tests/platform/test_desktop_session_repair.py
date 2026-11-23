"""分身连接取消或写入失败时恢复已更改的 Windows 设置。"""

import io
import os
import subprocess
import sys
from contextlib import ExitStack, nullcontext
from types import SimpleNamespace
from uuid import uuid4

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="需要 Windows 事件")


@pytest.mark.parametrize("commit", [True, False])
def test_repair_reads_exit_status_from_finished_windows_process(commit):
    import win32con

    from app.utils.windows.desktop_session import repair

    status = 0 if commit else repair.ROLLED_BACK
    with subprocess.Popen(
        [sys.executable, "-I", "-c", f"raise SystemExit({status})"]
    ) as child:
        operation = repair.EnvironmentRepair()
        operation._process = operation._handles.enter_context(
            repair.handle_scope(
                repair.win32api.OpenProcess(
                    win32con.SYNCHRONIZE | win32con.PROCESS_QUERY_LIMITED_INFORMATION,
                    False,
                    child.pid,
                )
            )
        )
        assert child.wait(timeout=5) == status
        operation.finish(commit=commit)


@pytest.mark.parametrize("result", ["cancel", "failure", "commit"])
@pytest.mark.parametrize("disabled", [True, False])
def test_repair_restores_configuration_when_connection_is_not_confirmed(
    monkeypatch, result, disabled
):
    from app.utils.windows.desktop_session import repair

    events = repair.win32event
    name = rf"Local\AUTO-MAS-repair-test-{uuid4().hex}"
    rdp = {repair.RDP_DENY: (1, repair.winreg.REG_DWORD)}
    child_enabled = False
    service = repair.win32service
    original_start_type = (
        service.SERVICE_DISABLED if disabled else service.SERVICE_AUTO_START
    )
    service_start_type = original_start_type
    service_state = service.SERVICE_STOPPED
    change_log = []

    def write_rdp(_key, value_name, _reserved, kind, value):
        rdp[value_name] = value, kind
        change_log.append(("rdp", value))

    def set_child(*, enabled):
        nonlocal child_enabled
        if enabled and result == "failure":
            raise OSError("child session enable failed")
        child_enabled = enabled
        change_log.append(("child", enabled))

    def set_start_type(_service, _service_type, start_type, *_):
        nonlocal service_start_type
        assert disabled
        service_start_type = start_type

    def start_service(*_):
        nonlocal service_state
        assert service_start_type == (
            service.SERVICE_DEMAND_START if disabled else original_start_type
        )
        service_state = service.SERVICE_RUNNING

    def stop_service(_service, control):
        nonlocal service_state
        assert control == service.SERVICE_CONTROL_STOP
        service_state = service.SERVICE_STOPPED

    changes = frozenset(
        {
            "rdp_local_disabled",
            "child_enabled",
            "term_service_disabled" if disabled else "term_service_stopped",
        }
    )
    checks = [
        {"code": code, "ok": False, "required": True}
        for code in changes | {"rdp_listener"}
    ]
    monkeypatch.setattr(repair, "IS_ELEVATED", True)
    monkeypatch.setattr(repair, "probe", lambda **_: (checks, 3389))
    monkeypatch.setattr(service, "OpenSCManager", lambda *_: 1)
    monkeypatch.setattr(service, "OpenService", lambda *_: 2)
    monkeypatch.setattr(service, "CloseServiceHandle", lambda *_: None)
    monkeypatch.setattr(
        service, "QueryServiceConfig", lambda _: (0, service_start_type)
    )
    monkeypatch.setattr(service, "QueryServiceStatus", lambda _: (0, service_state))
    monkeypatch.setattr(service, "ChangeServiceConfig", set_start_type)
    monkeypatch.setattr(service, "StartService", start_service)
    monkeypatch.setattr(service, "ControlService", stop_service)
    monkeypatch.setattr(repair.winreg, "OpenKey", lambda *_: nullcontext(rdp))
    monkeypatch.setattr(repair.winreg, "QueryValueEx", lambda key, value: key[value])
    monkeypatch.setattr(repair.winreg, "SetValueEx", write_rdp)
    monkeypatch.setattr(repair, "child_sessions_enabled", lambda: child_enabled)
    monkeypatch.setattr(repair, "set_child_sessions_enabled", set_child)
    create_mutex = events.CreateMutex
    monkeypatch.setattr(
        events, "CreateMutex", lambda attrs, owner, _: create_mutex(attrs, owner, name)
    )
    wait = events.WaitForMultipleObjects

    def respond(handles, wait_all, timeout):
        if timeout == repair.DECISION_TIMEOUT_MS:
            events.SetEvent(commit if result == "commit" else cancel)
        return wait(handles, wait_all, timeout)

    monkeypatch.setattr(events, "WaitForMultipleObjects", respond)
    with ExitStack() as handles:
        ready, commit, cancel = (
            handles.enter_context(
                repair.handle_scope(
                    events.CreateEvent(None, True, False, name + suffix)
                )
            )
            for suffix in ("-ready", "-commit", "-cancel")
        )
        if result == "failure":
            assert repair._run(os.getpid(), name, changes) == repair.ROLLED_BACK
        else:
            assert repair._run(os.getpid(), name, changes) == (
                0 if result == "commit" else repair.ROLLED_BACK
            )
            assert events.WaitForSingleObject(ready, 0) == events.WAIT_OBJECT_0

    assert change_log[0] == ("rdp", 0)
    assert rdp[repair.RDP_DENY] == (
        0 if result == "commit" else 1,
        repair.winreg.REG_DWORD,
    )
    assert child_enabled is (result == "commit")
    assert service_start_type == (
        service.SERVICE_DEMAND_START
        if disabled and result == "commit"
        else original_start_type
    )
    assert service_state == (
        service.SERVICE_RUNNING if result == "commit" else service.SERVICE_STOPPED
    )


@pytest.mark.parametrize(
    "registered_session,current_child,logoff_requested,remaining_child",
    [
        (None, 42, True, 42),
        (42, 42, None, 42),
        (42, 42, False, 42),
        (42, 42, True, None),
        (42, 43, True, 43),
    ],
)
def test_close_after_disconnect_logs_off_only_registered_session(
    tmp_path,
    monkeypatch,
    registered_session,
    current_child,
    logoff_requested,
    remaining_child,
):
    from app.core.desktop_session import host

    session = current_child
    reports = []

    def current_session():
        return session

    def logoff(expected):
        nonlocal session
        assert expected == session == registered_session
        session = None

    def close_viewer():
        raise host.comtypes.COMError(-1, "ActiveX is already disconnected", None)

    instance = host.Host(tmp_path)
    instance.report = lambda event, **fields: reports.append((event, fields))
    instance.session_id = registered_session
    instance.viewer = SimpleNamespace(close=close_viewer)
    monkeypatch.setattr(host, "child_session", current_session)
    monkeypatch.setattr(host, "logoff_child", logoff)

    instance.report_viewer("state", state="disconnected", code="connect_timeout")
    instance.command({"action": "close", "logoff": logoff_requested})

    assert session == remaining_child
    assert reports[-1] == ("state", {"state": "idle"})


def test_host_stdin_eof_disconnects_without_logging_off(tmp_path, monkeypatch):
    from app.core.desktop_session import host

    instance = host.Host(tmp_path)
    instance.report = lambda *_args, **_fields: None
    instance.session_id = 42
    disconnected = []
    instance.viewer = SimpleNamespace(
        close=lambda: disconnected.append(True), pump_until=lambda _: None
    )
    monkeypatch.setattr(host.sys, "stdin", SimpleNamespace(buffer=io.BytesIO()))
    monkeypatch.setattr(host, "bind", lambda *_: lambda _: None)
    monkeypatch.setattr(
        host, "logoff_child", lambda _: pytest.fail("EOF should preserve the session")
    )

    instance.run()

    assert disconnected == [True]


def test_connect_with_existing_child_leaves_it_running(tmp_path, monkeypatch):
    from app.core.desktop_session import host

    reports = []

    def logoff(_):
        pytest.fail("已有的 Windows 子会话不能被注销")

    instance = host.Host(tmp_path)
    instance.report = lambda event, **fields: reports.append((event, fields))
    instance.report_environment = lambda _: None
    monkeypatch.setattr(host, "probe", lambda: ([], 3389))
    monkeypatch.setattr(host, "child_session", lambda: 42)
    monkeypatch.setattr(host, "logoff_child", logoff)
    monkeypatch.setattr(
        host.credentials, "current_identity", lambda: ("account", "sid")
    )
    monkeypatch.setattr(host.credentials, "load", lambda *_: object())
    monkeypatch.setattr(host.credentials, "validate", lambda _: None)

    instance.command({"action": "connect"})
    assert reports[-1] == (
        "state",
        {"state": "idle", "code": "existing_child_session", "existingSessionId": 42},
    )
    instance.command({"action": "connect", "adoptSessionId": 43})
    assert reports[-1] == (
        "state",
        {"state": "idle", "code": "session_changed", "existingSessionId": 42},
    )
    instance.command({"action": "close"})
    assert reports[-1] == ("state", {"state": "idle"})


@pytest.mark.parametrize("passes_recheck", [True, False])
def test_environment_repair_finishes_before_password_check(
    tmp_path, monkeypatch, passes_recheck
):
    from app.core.desktop_session import host

    reports = []
    applied = False
    committed = False

    def probe(**_):
        return [
            {
                "code": "child_enabled",
                "required": True,
                "ok": applied and passes_recheck,
            }
        ], 3389

    def apply(changes):
        nonlocal applied
        assert changes == {"child_enabled"}
        applied = True

    def finish(*, commit):
        nonlocal applied, committed
        committed = commit
        applied = commit

    def load(*_):
        assert applied and committed
        raise host.credentials.CredentialError("password_required")

    monkeypatch.setattr(host, "probe", probe)
    monkeypatch.setattr(host, "child_session", lambda: None)
    monkeypatch.setattr(
        host, "EnvironmentRepair", lambda: SimpleNamespace(start=apply, finish=finish)
    )
    monkeypatch.setattr(
        host.credentials, "current_identity", lambda: ("account", "sid")
    )
    monkeypatch.setattr(host.credentials, "load", load)
    instance = host.Host(tmp_path)
    instance.report_environment = lambda _: None
    instance.report = lambda event, **fields: reports.append((event, fields))

    instance.command({"action": "connect"})
    assert reports[-1] == ("state", {"state": "idle", "code": "environment_blocked"})
    assert not applied
    if passes_recheck:
        instance.command({"action": "repair", "approvedRepairs": ["child_enabled"]})
        assert reports[-1] == ("repair_finished", {})
        with pytest.raises(host.credentials.CredentialError, match="password_required"):
            instance.command({"action": "connect"})
    else:
        with pytest.raises(host.RepairError, match="environment_recheck_failed"):
            instance.command({"action": "repair", "approvedRepairs": ["child_enabled"]})
    instance.command({"action": "close"})
    assert applied is passes_recheck


@pytest.mark.parametrize("password_valid", [True, False])
def test_home_connection_failure_keeps_only_verified_credentials(
    tmp_path, monkeypatch, password_valid
):
    from app.core.desktop_session import host

    reports = []
    saved = []

    def validate(_):
        if not password_valid:
            raise host.credentials.CredentialError("password_invalid")

    def viewer(**options):
        def open_viewer(_):
            options["report"](
                "state",
                state="disconnected",
                code="rdp_disconnected",
                nativeCodes=(516, 0),
            )

        return SimpleNamespace(parent_session=1, open=open_viewer)

    monkeypatch.setattr(
        host,
        "probe",
        lambda: (
            [{"code": "home_edition", "ok": True, "required": False, "value": "Core"}],
            3389,
        ),
    )
    monkeypatch.setattr(host, "child_session", lambda: None)
    monkeypatch.setattr(host, "RdpViewer", viewer)
    monkeypatch.setattr(
        host.credentials, "current_identity", lambda: ("account", "sid")
    )
    monkeypatch.setattr(host.credentials, "validate", validate)
    monkeypatch.setattr(host.credentials, "encode", lambda _: "encrypted")
    monkeypatch.setattr(
        host.credentials,
        "save",
        lambda _, account, encoded: saved.append((account, encoded)),
    )
    instance = host.Host(tmp_path)
    instance.report_environment = lambda _: None
    instance.report = lambda event, **fields: reports.append((event, fields))
    command = {
        "action": "connect",
        "mode": "proxy",
        "resolution": "1080p",
        "owner": "1",
        "bounds": [0, 0, 100, 100],
        "password": "test-password",
    }

    if password_valid:
        instance.command(command)
        assert saved == [("account", "encrypted")]
        assert reports[-1][1]["code"] == "rdp_home_compatibility"
    else:
        with pytest.raises(host.credentials.CredentialError, match="password_invalid"):
            instance.command(command)
        assert not saved
        assert instance.viewer is None


def test_security_event_matches_current_local_rdp_attempt():
    from datetime import UTC, datetime

    from app.utils.windows.desktop_session.logon_events import matching_failure

    xml = """<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event">
      <System><TimeCreated SystemTime="2026-11-16T16:20:04.1234567Z"/></System>
      <EventData>
        <Data Name="TargetUserSid">S-1-0-0</Data>
        <Data Name="TargetUserName">desktop-user</Data>
        <Data Name="TargetDomainName">test-pc</Data>
        <Data Name="LogonType">3</Data>
        <Data Name="IpAddress">::ffff:127.0.0.1</Data>
        <Data Name="Status">0xc000006d</Data>
        <Data Name="SubStatus">0xc000006a</Data>
      </EventData></Event>"""
    start = datetime(2026, 11, 16, 16, 20, 4, tzinfo=UTC)
    account = r"test-pc\desktop-user"
    sid = "S-1-5-21-42"
    assert matching_failure(xml, start, account, sid, remote=True) == {
        "time": "2026-11-16T16:20:04.123456+00:00",
        "status": "0xC000006D",
        "substatus": "0xC000006A",
    }
    assert (
        matching_failure(xml, start.replace(second=5), account, sid, remote=True)
        is None
    )
    assert matching_failure(xml, start, r"test-pc\other-user", sid, remote=True) is None
    assert (
        matching_failure(
            xml.replace("::ffff:127.0.0.1", "192.0.2.10"),
            start,
            account,
            sid,
            remote=True,
        )
        is None
    )
