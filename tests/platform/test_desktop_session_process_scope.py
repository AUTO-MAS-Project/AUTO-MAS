"""主后端通过桌面分身控制入口登记进程管理范围。"""

import os
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

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
    lifecycle.install_control(app)
    path = "/internal/desktop-session/process-scope"
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
    assert not operations.terminate_process(process, force=True)
    process.kill.assert_not_called()
