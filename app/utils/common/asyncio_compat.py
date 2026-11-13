"""Python 3.12 Windows 连接收尾兼容，不改变事件循环或异常上报入口。"""

import socket
import sys
from asyncio import BaseProtocol, sslproto
from ipaddress import ip_address
from typing import Any

_PROTOCOL_KINDS = {
    ("uvicorn.protocols.http.h11_impl", "H11Protocol"): "http",
    ("uvicorn.protocols.http.httptools_impl", "HttpToolsProtocol"): "http",
    ("uvicorn.protocols.websockets.websockets_impl", "WebSocketProtocol"): "websocket",
    ("uvicorn.protocols.websockets.wsproto_impl", "WSProtocol"): "websocket",
    ("anyio._backends._asyncio", "StreamProtocol"): "anyio_stream",
    ("asyncio.streams", "StreamReaderProtocol"): "stream",
}


def _connection_diagnostic(
    *,
    protocol: BaseProtocol,
    server_side: bool,
    family: socket.AddressFamily,
    peer: tuple | None,
) -> str:
    """只保留有限分类，不输出地址、端口、类型名或对象 repr。"""
    tls = isinstance(protocol, sslproto.SSLProtocol)
    if isinstance(protocol, sslproto.SSLProtocol):
        protocol = protocol._app_protocol
    protocol_type = type(protocol)
    protocol_kind = _PROTOCOL_KINDS.get(
        (protocol_type.__module__, protocol_type.__name__), "other"
    )
    family_kind = {socket.AF_INET: "ipv4", socket.AF_INET6: "ipv6"}.get(family, "other")
    peer_scope = "not_ip"
    if family_kind != "other":
        peer_scope = (
            "unavailable"
            if peer is None
            else "loopback"
            if ip_address(peer[0]).is_loopback
            else "non_loopback"
        )
    role = "server" if server_side else "client"
    return (
        f"连接收尾诊断: role={role}, protocol={protocol_kind}, "
        f"tls={tls}, family={family_kind}, peer={peer_scope}"
    )


def _call_connection_lost(transport: Any, exc: Exception | None) -> None:
    if transport._called_connection_lost:
        return
    sock = transport._sock
    diagnostic = None
    try:
        # SSLProtocol.connection_lost 会清空内部协议，必须先保存脱敏分类。
        if isinstance(sock, socket.socket):
            diagnostic = _connection_diagnostic(
                protocol=transport._protocol,
                server_side=transport._server is not None,
                family=sock.family,
                peer=transport.get_extra_info("peername"),
            )
        transport._protocol.connection_lost(exc)
    finally:
        try:
            # 沿用 CPython 的 shutdown 顺序，避免对端仍有重叠读取时直接关闭。
            if hasattr(sock, "shutdown") and sock.fileno() != -1:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError as error:
                    # 10022 的来源尚未确定，保留原异常；备注随既有日志进入 Sentry，
                    # 不再额外记录一次，遥测开关和脱敏策略继续由原入口负责。
                    if diagnostic is not None:
                        error.add_note(diagnostic)
                    raise
        finally:
            try:
                sock.close()
            finally:
                transport._sock = None
                try:
                    if transport._server is not None:
                        transport._server._detach()
                finally:
                    transport._server = None
                    transport._called_connection_lost = True


def install_windows_connection_cleanup() -> None:
    """在创建事件循环前安装一次，覆盖后端各 Windows Proactor 连接。"""
    if sys.platform != "win32":
        return

    from asyncio import proactor_events

    # 项目锁定 Python 3.12；此处依赖其 _detach() 无参契约。升级 Python 时应重新
    # 核对并移除兼容实现，前提是上游已保证任意 shutdown 失败后仍完成资源清理。
    setattr(
        proactor_events._ProactorBasePipeTransport,
        "_call_connection_lost",
        _call_connection_lost,
    )
