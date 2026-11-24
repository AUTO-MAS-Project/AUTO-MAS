"""在真实连接上注入已观测的 shutdown 故障，守护资源释放和诊断隐私。"""

import asyncio
import socket
import ssl
from asyncio import proactor_events, sslproto
from unittest.mock import patch

import pytest
from sentry_sdk import Client
from sentry_sdk.utils import event_from_exception

from app.services import telemetry
from app.utils.common import asyncio_compat


class ShutdownSocket(socket.socket):
    failure: OSError | None = None

    def shutdown(self, how: int) -> None:
        if self.failure is not None:
            raise self.failure
        super().shutdown(how)


class ConnectionProtocol(asyncio.Protocol):
    def __init__(self, failure: Exception | None = None) -> None:
        self.losses: list[Exception | None] = []
        self.failure = failure

    def connection_lost(self, exc: Exception | None) -> None:
        self.losses.append(exc)
        if self.failure is not None:
            raise self.failure


@pytest.fixture
def patched_cleanup(monkeypatch):
    transport_type = proactor_events._ProactorBasePipeTransport
    monkeypatch.setattr(
        transport_type, "_call_connection_lost", transport_type._call_connection_lost
    )
    with patch.object(asyncio_compat.sys, "platform", "win32"):
        asyncio_compat.install_windows_connection_cleanup()
        asyncio_compat.install_windows_connection_cleanup()


def exercise_connection(*, shutdown_error=None, protocol=None):
    """只替换 socket.shutdown 边界，其余连接与服务器生命周期真实执行。"""
    if protocol is None:
        protocol = ConnectionProtocol()
    with asyncio.Runner() as runner:
        loop = runner.get_loop()
        errors = []
        loop.set_exception_handler(lambda _loop, context: errors.append(context))
        server = runner.run(loop.create_server(asyncio.Protocol, "127.0.0.1", 0))
        left, right = socket.socketpair()
        sock = ShutdownSocket(fileno=left.detach())
        sock.failure = shutdown_error
        transport = proactor_events._ProactorBasePipeTransport(
            loop=loop, sock=sock, protocol=protocol, server=server
        )
        try:
            loop.call_soon(transport._call_connection_lost, None)
            runner.run(asyncio.sleep(0))
            assert sock.fileno() == -1
            server.close()
            runner.run(asyncio.wait_for(server.wait_closed(), timeout=0.5))
            # 重复收尾不得重复通知协议或减少服务端连接计数。
            transport._call_connection_lost(None)
            assert protocol.losses == [None]
            return errors
        finally:
            sock.close()
            right.close()
            server.close()


@pytest.mark.parametrize("winerror", [None, 10022, 10054])
def test_shutdown_failure_still_releases_connection(patched_cleanup, winerror):
    error = None
    if winerror is not None:
        error_type = ConnectionResetError if winerror == 10054 else OSError
        error = error_type(22, "invalid socket shutdown")
        error.winerror = winerror
    errors = exercise_connection(shutdown_error=error)
    if error is None:
        assert errors == []
    else:
        assert len(errors) == 1
        assert errors[0]["exception"] is error
        assert "连接收尾诊断: role=server" in error.__notes__[0]


def test_protocol_failure_still_propagates_after_cleanup(patched_cleanup):
    error = RuntimeError("protocol failed")
    errors = exercise_connection(protocol=ConnectionProtocol(failure=error))
    assert len(errors) == 1
    assert errors[0]["exception"] is error


def test_diagnostic_survives_sentry_without_private_type_or_object_data(
    patched_cleanup,
):
    secret = "private-token@example.invalid/path"

    def forbidden_repr(self):
        raise AssertionError("诊断不得读取对象 repr")

    protocol_type = type(
        secret,
        (ConnectionProtocol,),
        {"__module__": secret, "__repr__": forbidden_repr},
    )
    error = OSError(22, "invalid socket shutdown")
    error.winerror = 10022
    exercise_connection(shutdown_error=error, protocol=protocol_type())
    # dsn=None，不安装集成、不发送事件，只经过真实 SDK 序列化和应用脱敏。
    with Client(
        dsn=None,
        default_integrations=False,
        include_local_variables=False,
        include_source_context=False,
    ) as client:
        event, hint = event_from_exception(error, client_options=client.options)
    sanitized = telemetry.sanitize_event(event, hint)
    assert sanitized is not None
    value = sanitized["exception"]["values"][-1]["value"]
    assert "role=server, protocol=other, tls=False" in value
    assert secret not in value
    assert "127.0.0.1" not in value
    assert "::1" not in value
    for exception in sanitized["exception"]["values"]:
        for frame in exception["stacktrace"]["frames"]:
            assert "vars" not in frame


def test_tls_client_diagnostic_classifies_inner_protocol():
    with asyncio.Runner() as runner:
        loop = runner.get_loop()
        reader = asyncio.StreamReader(loop=loop)
        protocol = sslproto.SSLProtocol(
            loop=loop,
            app_protocol=asyncio.StreamReaderProtocol(reader, loop=loop),
            sslcontext=ssl.create_default_context(),
            waiter=None,
        )
        diagnostic = asyncio_compat._connection_diagnostic(
            protocol=protocol,
            server_side=False,
            family=socket.AF_INET,
            peer=None,
        )
        assert diagnostic == (
            "连接收尾诊断: role=client, protocol=stream, "
            "tls=True, family=ipv4, peer=unavailable"
        )


def test_non_windows_keeps_original_cleanup():
    transport_type = proactor_events._ProactorBasePipeTransport
    original = transport_type._call_connection_lost
    with patch.object(asyncio_compat.sys, "platform", "linux"):
        asyncio_compat.install_windows_connection_cleanup()
    assert transport_type._call_connection_lost is original
