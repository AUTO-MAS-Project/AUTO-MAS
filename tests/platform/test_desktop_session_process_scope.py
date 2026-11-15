"""主后端通过桌面分身控制入口登记进程管理范围。"""

import os
from pathlib import Path
from unittest.mock import Mock

import psutil
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.desktop_session import install_control
from app.core.desktop_session import lifecycle
from app.utils.common.process import operations, session


@pytest.mark.skipif(os.name != "nt", reason="桌面分身仅在 Windows 使用 WTS")
@pytest.mark.parametrize("restored", [False, True])
def test_parent_scope_tracks_only_the_registered_child(monkeypatch, restored):
    from app.utils.windows.desktop_session import native

    child_id = 7
    monkeypatch.setattr(native, "child_session", lambda: child_id)
    monkeypatch.setattr(
        native, "process_session", lambda pid: 1 if pid == os.getpid() else 7
    )
    monkeypatch.setattr(session, "_parent_scope", None)
    monkeypatch.setattr(lifecycle, "_control_token", "test-control-token")
    monkeypatch.setattr(lifecycle, "_parent_child_session", "7" if restored else "")

    app = FastAPI()
    install_control(app)
    path = "/internal/desktop-session/process-scope"
    assert path not in app.openapi()["paths"]
    headers = {lifecycle.CONTROL_HEADER: "test-control-token"}
    with TestClient(app, client=("127.0.0.1", 12345)) as client:
        assert session.process_in_scope(100) is (not restored)
        if not restored:
            assert client.post(path, json={"sessionId": 7}).status_code == 403
            assert client.post(
                path, headers=headers, json={"sessionId": None, "connecting": True}
            ).is_success
            assert session.process_in_scope(100)
            child_id = 8
            assert not session.process_in_scope(100)
            assert client.post(path, headers=headers, json={"sessionId": 8}).is_success
        assert not session.process_in_scope(100)
        assert client.post(path, headers=headers, json={"sessionId": None}).is_success
        assert session.process_in_scope(100)


@pytest.mark.skipif(os.name != "nt", reason="桌面分身仅在 Windows 使用 WTS")
def test_process_operations_filter_and_recheck_scope(monkeypatch):
    from app.utils.windows.desktop_session import native

    process = Mock(pid=100)
    monkeypatch.setattr(operations.psutil, "process_iter", lambda _: iter([process]))
    monkeypatch.setattr(native, "process_session", lambda pid: 7)
    monkeypatch.setattr(session, "_parent_scope", None)
    assert list(operations.iter_processes(["pid"])) == [process]

    session.configure_parent_scope(lambda: 1)
    assert list(operations.iter_processes(["pid"])) == []
    token = session.desktop_process_target.set(
        session.DesktopProcessTarget(7, Path.cwd(), Path.cwd())
    )
    try:
        assert list(operations.iter_processes(["pid"])) == [process]
    finally:
        session.desktop_process_target.reset(token)
    assert not operations.terminate_process(process, force=True)
    process.kill.assert_not_called()


@pytest.mark.skipif(os.name != "nt", reason="桌面分身仅在 Windows 使用 WTS")
def test_managed_process_separates_exited_from_out_of_scope(monkeypatch):
    from app.utils.windows.desktop_session import native

    monkeypatch.setattr(native, "process_session", lambda pid: 2)
    monkeypatch.setattr(session, "_parent_scope", None)

    exited = Mock()
    exited.create_time.side_effect = psutil.NoSuchProcess(100)
    monkeypatch.setattr(operations.psutil, "Process", lambda pid: exited)
    # 自己退出：调用方按「无事可做」处理。
    assert operations.managed_process(100) is None

    alive = Mock(pid=100)
    alive.create_time.return_value = 20
    alive.is_running.return_value = True
    monkeypatch.setattr(operations.psutil, "Process", lambda pid: alive)
    session.configure_parent_scope(lambda: 1)
    # 仍在运行但不归本会话管：不能当成已结束。
    with pytest.raises(ProcessLookupError):
        operations.managed_process(100)

    # PID 在另一会话被复用，旧快照对应的进程已退出。
    assert operations.managed_process(100, expected_create_time=10) is None

    # 打开进程后自然退出，WTS 已无法查询该 PID。
    def session_after_exit(pid):
        raise OSError(87, "进程已退出")

    monkeypatch.setattr(native, "process_session", session_after_exit)
    alive.is_running.return_value = False
    assert operations.managed_process(100, expected_create_time=20) is None
