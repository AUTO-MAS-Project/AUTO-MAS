"""宿主与 MaaFW worker 子进程之间的协议：事件格式、共用常量、传输与分帧。

worker（``runner/worker.py``）跑在运行池的隔离 venv 里，``runner.py`` 一导入就加载 ``maa``，宿主
引用不了它的常量，以前只好在宿主里复制一份（信号截图的 kind、``[MaaFW 详情] `` 前缀、日志去向的
几组文案）。两边共用的东西都放这里。只依赖标准库：它在 worker 的导入闭包里（见 MaaFW/AGENTS.md），
宿主导入它也不会拉起 runner 子树。

传输（宿主 ``tools/embedded/runner_task.py`` ↔ ``runner/worker.py``）：

- **job**：宿主把运行计划等写进 worker 的 stdin（UTF-8 JSON），写完就关；不落盘——计划里可能有
  解密后的密码选项。``decode_job`` / ``encode_job`` 是两头的读写。
- **事件**：宿主在 ``127.0.0.1`` 上临时监听一个端口（``WorkerEventServer``），端口与一次性令牌随
  job 交给 worker；worker 连回来（``EventChannelClient``），第一条消息是带令牌的 ``hello``，之后
  一个事件一条消息。消息按帧传（``encode_message`` / ``FrameDecoder``）：4 字节大端头，最高位表示
  后面还有分片，其余 31 位是本片长度；单片不超过 ``MAX_FRAGMENT_BYTES``，整条消息不限长——不再像
  stdout 那样受单行上限约束。接收端只为内存设一道 ``MAX_MESSAGE_BYTES``：超过的整条丢掉、记一句，
  后面照常读，不会因为一条超长消息停止读取、让 worker 写满缓冲卡住。
- **stdout**：只剩 MaaFramework 的原生诊断，宿主照旧逐行写进 ``.worker.log``。
- **建不起通道时退回旧格式**：宿主监听失败（job 里不带端口）、worker 连不上、或连上后发送出错，
  worker 都改成一行一个 JSON 事件写 stdout（旧格式），宿主一直按行解析 stdout，这次运行照常进行；
  原因各记一行进 ``.worker.log``。退回而不是报错，是因为旧格式是跑了很久的路径，而本机回环被安全
  软件拦住这类原因用户自己处理不了；job 仍然走 stdin，退回也不会让密码落盘。

选套接字而不选专用管道：Python 建的套接字默认不可继承（PEP 446，Windows 上建时就带
``WSA_FLAG_NO_HANDLE_INHERIT``，这里再显式设一次），worker 拉起的 agent、adb，以及宿主同时拉起的
模拟器、游戏都拿不到它的句柄。管道要传给 worker 就得先设成可继承，宿主在那一刻并发拉起的其它进程
会一起带走；常驻的继承者会让读的一方永远等不到 EOF（本机吃过这个亏）。宿主也不靠 EOF 收尾：worker
退出后最多再等几秒就取消读取。

日志事件带两个字段：``audience``（``ui`` 进界面，``worker_log`` 只进 ``.worker.log``）与 ``level``。
去向由 worker 在发出时判定（``log_audience``），宿主照字段办，不再自己按文案猜；不带 ``audience`` 的
旧格式事件与 stdout 上的原生诊断仍按 ``forwards_to_ui`` 的原规则判，规则只在这里写一份。
"""

from __future__ import annotations

import asyncio
import hmac
import json
import os
import re
import secrets
import socket
import struct
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, Mapping

#: 第 1 版是一行一个 JSON 事件写 stdout（现在的退回格式），第 2 版起事件走独立通道。
PROTOCOL_VERSION = 2

# ---------------------------------------------------------------------------
# 事件
# ---------------------------------------------------------------------------

EVENT_HELLO = "hello"
EVENT_LOG = "log"
EVENT_ERROR = "error"
EVENT_RESULT = "result"

AUDIENCE_UI = "ui"
AUDIENCE_WORKER_LOG = "worker_log"
_AUDIENCES = frozenset({AUDIENCE_UI, AUDIENCE_WORKER_LOG})

LEVEL_INFO = "info"
LEVEL_WARNING = "warning"
LEVEL_ERROR = "error"

#: job 里交给 worker 的事件通道：``{"host": ..., "port": ..., "token": ...}``；没有就走 stdout。
JOB_EVENT_CHANNEL_KEY = "eventChannel"

# ---------------------------------------------------------------------------
# 宿主与 worker 共用的常量
# ---------------------------------------------------------------------------

#: 带这个前缀的日志只进 ``.worker.log`` / 后端日志，不进界面（runner、agent 环境准备都用它）。
DETAIL_LOG_PREFIX = "[MaaFW 详情] "

#: 信号取值（``MaaFWRunResult.signal``）。worker 的 ``run_signal`` 与宿主的 ``signal_notice`` 都引这里。
SERVER_MAINTENANCE = "server_maintenance"
CLIENT_UPDATE_REQUIRED = "client_update_required"
#: 信号证据截图文件名里的 kind。只用小写字母：问题包导出按
#: ``<时分秒>.<kind>-<HHMMSS>-<任务>.png`` 收截图，kind 部分是 ``[a-z]+``，带连字符就收不进去。
#: 宿主按这些 kind 认证据图（``runner_task._signal_evidence_shot``）。
SIGNAL_SCREENSHOT_KINDS = {
    SERVER_MAINTENANCE: "maintenance",
    CLIENT_UPDATE_REQUIRED: "clientupdate",
}

# ---------------------------------------------------------------------------
# 日志去向：进界面还是只进 .worker.log
# ---------------------------------------------------------------------------

#: 界面上一条 worker 日志的字符上限；超过的大段 JSON / 回溯不进界面（完整内容在 .worker.log）。
UI_LOG_MAX_CHARS = 1200

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
_VERBOSE_FRAMEWORK_LOG_MARKERS = (
    "Transceiver::send] send canceled",
    "Transceiver::send_and_recv] failed to send req",
    "AgentClient::connect] failed to send_and_recv",
    "after convert, x_point:",
)
_NATIVE_FRAMEWORK_LOG_MARKERS = (
    "MaaNS::",
    "PipelineParser.cpp",
    "Context.cpp",
    "Tasker.cpp",
    "Node.cpp",
    "Transceiver.cpp",
    "AgentClient.cpp",
)
_FRAMEWORK_DEBUG_PAYLOAD_MARKERS = (
    "override_pipeline",
    "task_ptr->entry()",
    '"expected":',
    '"pipeline_override":',
)

# 这三条都是内部原样回显：Python 异常原文、框架通知里的入口名回声。runner
# 另发一条整理过的「任务失败: <任务>: <最后停在哪>」，那条要实时进任务日志——
# 否则失败任务在日志里就像凭空消失，要等收尾摘要才知道出了事。
_RAW_FAILURE_UI_LOG_MARKERS = (
    "MaaFW 任务执行失败:",
    "[MaaFW Tasker] 失败:",
    "任务执行失败: <entry=",
)
# 只进 *.worker.log、不进界面的 runner 行：
# - 「[MaaFW 详情] 」前缀：完整任务配置（options / override_nodes）、超过每任务
#   上限后的 focus 文案；
# - 「[MaaFW Tasker] 开始/成功: <entry>」：英文入口名，和它前面的
#   「正在运行任务: <标签>」/「任务完成: <标签>」重复。
# 「任务失败:」「MaaFW 任务完成:」「正在运行任务:」不在这里，宿主与 runner 的
# 入口跟踪按它们匹配。
_WORKER_LOG_ONLY_MARKERS = (
    DETAIL_LOG_PREFIX,
    "[MaaFW Tasker] 开始:",
    "[MaaFW Tasker] 成功:",
)
_NATIVE_FRAMEWORK_STATUS_RE = re.compile(
    r"(?:\*\*)?\[\d{4}-\d{2}-\d{2}[^\]]*\]\[(?:ERR|WARN|INFO|DEBUG)\]",
    re.IGNORECASE,
)
_FRAMEWORK_COORDINATE_RE = re.compile(
    r"(?:^|\]\s*)x:\s*-?\d+,\s*y:\s*-?\d+,\s*width:\s*\d+,\s*height:\s*\d+",
    re.IGNORECASE,
)


def strip_ansi(message: str) -> str:
    """去掉终端颜色控制符。"""

    return _ANSI_ESCAPE_RE.sub("", str(message or ""))


def forwards_to_ui(message: str) -> bool:
    """一条 worker 日志 / 原生诊断该不该进界面（不该的只进 ``.worker.log``）。

    worker 发日志事件时用它定 ``audience``；宿主只对不带 ``audience`` 的旧格式事件和 stdout 上的
    原生诊断用它。
    """

    if any(marker in message for marker in _RAW_FAILURE_UI_LOG_MARKERS):
        return False
    if message.startswith(_WORKER_LOG_ONLY_MARKERS):
        return False
    cleaned = strip_ansi(message).strip()
    if _FRAMEWORK_COORDINATE_RE.search(cleaned):
        return False
    if any(marker in cleaned for marker in _VERBOSE_FRAMEWORK_LOG_MARKERS):
        return False
    # Native MaaFramework diagnostics are always retained in the per-run
    # ``*.worker.log`` / ``*.maafw.log`` files.  They are intentionally not
    # copied into the user facing script log: one failed override can otherwise
    # emit the same parser backtrace once per task and hide the actionable summary.
    if any(marker in cleaned for marker in _NATIVE_FRAMEWORK_LOG_MARKERS):
        return False
    if _NATIVE_FRAMEWORK_STATUS_RE.search(cleaned) and ".cpp" in cleaned:
        return False
    # Some MaaFramework/Agent diagnostics do not include a C++ source marker
    # but embed an entire pipeline JSON document in one line.  Keep the full
    # payload in the per-run ``*.maafw.log`` and leave the normal task page to
    # the concise runner error that follows it.
    if len(cleaned) > UI_LOG_MAX_CHARS and (
        any(marker in cleaned for marker in _FRAMEWORK_DEBUG_PAYLOAD_MARKERS)
        or cleaned.startswith(("{", "["))
    ):
        return False
    return True


def log_audience(message: str) -> str:
    """按 ``forwards_to_ui`` 的规则给一条日志定去向。"""

    return AUDIENCE_UI if forwards_to_ui(message) else AUDIENCE_WORKER_LOG


def log_event(
    message: str, *, audience: str | None = None, level: str = LEVEL_INFO
) -> dict[str, Any]:
    """一条日志事件；不指定 ``audience`` 时按 ``log_audience`` 判。"""

    return {
        "type": EVENT_LOG,
        "message": message,
        "audience": audience if audience in _AUDIENCES else log_audience(message),
        "level": level,
    }


def error_event(message: str) -> dict[str, Any]:
    return {
        "type": EVENT_ERROR,
        "message": message,
        "audience": log_audience(message),
        "level": LEVEL_ERROR,
    }


def event_audience(event: Mapping[str, Any]) -> str:
    """日志 / 错误事件的去向：带了合法 ``audience`` 就照它，旧格式按文案的原规则判。"""

    audience = event.get("audience")
    if audience in _AUDIENCES:
        return str(audience)
    return log_audience(str(event.get("message") or ""))


# ---------------------------------------------------------------------------
# job
# ---------------------------------------------------------------------------


def encode_job(
    payload: Any, *, event_channel: Mapping[str, Any] | None = None
) -> bytes:
    """宿主写进 worker stdin 的 job。``payload`` 是 ``MaaFWRunnerJobPayload`` 或同形状的映射。"""

    if hasattr(payload, "model_dump"):
        data = payload.model_dump(mode="json")
    else:
        data = dict(payload)
    if event_channel is not None:
        data[JOB_EVENT_CHANNEL_KEY] = dict(event_channel)
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


def decode_job(raw: bytes) -> dict[str, Any]:
    """worker 读 job：stdin 读到 EOF 的全部字节。"""

    if not raw.strip():
        raise ValueError("MaaFW worker 没有从标准输入读到 job")
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("MaaFW worker 的 job 不是 JSON 对象")
    return data


# ---------------------------------------------------------------------------
# 分帧
# ---------------------------------------------------------------------------

_HEADER = struct.Struct(">I")
_MORE_FRAGMENTS = 0x8000_0000
_LENGTH_MASK = 0x7FFF_FFFF
#: 发送端单片上限；接收端见到更长的分片就当流坏了（不再可能对齐下一帧）。
MAX_FRAGMENT_BYTES = 1 << 20
#: 接收端为内存设的整条消息上限：超过的丢掉、记一句，后面照常读。
MAX_MESSAGE_BYTES = 64 << 20


class ProtocolError(ValueError):
    """通道上的字节流坏了，无法再对齐到下一条消息。"""


@dataclass(frozen=True)
class DroppedMessage:
    """接收端丢掉的一条消息（超长、不是 JSON 对象）；``reason`` 写进 ``.worker.log``。"""

    reason: str


def encode_message(event: Mapping[str, Any]) -> bytes:
    """把一个事件编成若干分片（JSON，UTF-8）。"""

    body = json.dumps(event, ensure_ascii=False).encode("utf-8")
    if len(body) <= MAX_FRAGMENT_BYTES:
        return _HEADER.pack(len(body)) + body
    chunks: list[bytes] = []
    view = memoryview(body)
    for offset in range(0, len(body), MAX_FRAGMENT_BYTES):
        piece = view[offset : offset + MAX_FRAGMENT_BYTES]
        more = offset + MAX_FRAGMENT_BYTES < len(body)
        chunks.append(_HEADER.pack(len(piece) | (_MORE_FRAGMENTS if more else 0)))
        chunks.append(bytes(piece))
    return b"".join(chunks)


class FrameDecoder:
    """增量解帧：``feed`` 收任意切分的字节，返回其中完整的消息。

    流坏了（分片长度超限）时，坏处之前已经完整的消息照常返回，``error`` 记下原因、之后不再
    解析；再 ``feed`` 直接抛这个错。调用方处理完返回的消息后看 ``error``。
    """

    def __init__(
        self,
        *,
        max_message_bytes: int = MAX_MESSAGE_BYTES,
        max_fragment_bytes: int = MAX_FRAGMENT_BYTES,
    ) -> None:
        self._max_message = max_message_bytes
        self._max_fragment = max_fragment_bytes
        self._buffer = bytearray()
        self._parts: list[bytes] = []
        self._size = 0
        self._dropping = False
        self.error: ProtocolError | None = None

    @property
    def pending_bytes(self) -> int:
        """还没凑成整条消息的字节数（流结束时不为 0 说明最后一条不完整）。"""

        return len(self._buffer) + self._size

    def feed(self, data: bytes) -> list[dict[str, Any] | DroppedMessage]:
        if self.error is not None:
            raise self.error
        self._buffer += data
        items: list[dict[str, Any] | DroppedMessage] = []
        offset = 0
        buffer = self._buffer
        while len(buffer) - offset >= _HEADER.size:
            (header,) = _HEADER.unpack_from(buffer, offset)
            length = header & _LENGTH_MASK
            if length > self._max_fragment:
                self.error = ProtocolError(
                    f"分片长度 {length} 字节超过上限 {self._max_fragment} 字节"
                )
                break
            end = offset + _HEADER.size + length
            if len(buffer) < end:
                break
            self._size += length
            if not self._dropping:
                if self._size > self._max_message:
                    self._dropping = True
                    self._parts.clear()
                else:
                    self._parts.append(bytes(buffer[offset + _HEADER.size : end]))
            offset = end
            if header & _MORE_FRAGMENTS:
                continue
            items.append(self._finish_message())
        if offset:
            del buffer[:offset]
        return items

    def _finish_message(self) -> dict[str, Any] | DroppedMessage:
        size, dropping, parts = self._size, self._dropping, self._parts
        self._size, self._dropping, self._parts = 0, False, []
        if dropping:
            return DroppedMessage(
                f"worker 发来一条 {size} 字节的消息，超过 {self._max_message} 字节，已丢弃"
            )
        try:
            event = json.loads(b"".join(parts).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return DroppedMessage(
                f"worker 发来一条无法解析的消息（{size} 字节）：{exc}"
            )
        if not isinstance(event, dict):
            return DroppedMessage(f"worker 发来的消息不是 JSON 对象（{size} 字节）")
        return event


# ---------------------------------------------------------------------------
# 通道：worker 一侧
# ---------------------------------------------------------------------------

#: worker 连回宿主的超时。连接在内核里就完成了，正常是毫秒级；超时只兜回环被拦的情况。
CHANNEL_CONNECT_TIMEOUT_SECONDS = 5.0


class EventChannelClient:
    """worker 一侧的事件通道：阻塞套接字，``send`` 出错抛 ``OSError``（调用方据此退回 stdout）。"""

    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock

    @classmethod
    def connect(
        cls,
        spec: Mapping[str, Any],
        *,
        timeout: float = CHANNEL_CONNECT_TIMEOUT_SECONDS,
    ) -> EventChannelClient:
        host = str(spec.get("host") or "")
        port = spec.get("port")
        token = spec.get("token")
        if not host or not isinstance(port, int) or not isinstance(token, str):
            raise ValueError(f"job 里的事件通道参数不完整: host={host!r} port={port!r}")
        sock = socket.create_connection((host, port), timeout=timeout)
        try:
            # 默认就不可继承（PEP 446）；显式再设一次，免得 MaaFramework 原生层起 adb / agent
            # 时（bInheritHandles=TRUE）把它带走，常驻的 adb server 会让宿主等不到 EOF。
            sock.set_inheritable(False)
            sock.settimeout(None)
            sock.sendall(encode_message(hello_event(token)))
        except BaseException:
            sock.close()
            raise
        return cls(sock)

    def send(self, event: Mapping[str, Any]) -> None:
        self._sock.sendall(encode_message(event))

    def close(self) -> None:
        try:
            self._sock.shutdown(socket.SHUT_WR)
        except OSError:
            pass
        self._sock.close()


def hello_event(token: str) -> dict[str, Any]:
    return {
        "type": EVENT_HELLO,
        "token": token,
        "protocol": PROTOCOL_VERSION,
        "pid": os.getpid(),
    }


def is_valid_hello(event: Mapping[str, Any], token: str) -> bool:
    received = event.get("token")
    return (
        event.get("type") == EVENT_HELLO
        and isinstance(received, str)
        and hmac.compare_digest(received.encode("utf-8"), token.encode("utf-8"))
    )


# ---------------------------------------------------------------------------
# 通道：宿主一侧
# ---------------------------------------------------------------------------

#: 连上来之后多久内必须发来 hello；别的本机进程连到这个端口不说话时不会挡住 worker。
CHANNEL_HANDSHAKE_TIMEOUT_SECONDS = 10.0
_RECV_BYTES = 256 * 1024


class WorkerEventServer:
    """宿主一侧：``127.0.0.1`` 临时端口上等 worker 连回来，核对令牌后逐条产出事件。

    只接受一个通过握手的连接，之后不再监听。读到 EOF（worker 关闭或退出）、流坏了
    （``ProtocolError``）或被取消时 ``events`` 结束并关掉套接字；没走到 ``events`` 的路径
    （比如 worker 没起来）由调用方 ``close``。
    """

    def __init__(self, listener: socket.socket, token: str) -> None:
        self._listener: socket.socket | None = listener
        self._conn: socket.socket | None = None
        self._token = token
        self._port = int(listener.getsockname()[1])
        self.connected = asyncio.Event()

    @classmethod
    def open(cls) -> WorkerEventServer:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            listener.set_inheritable(False)
            # Windows 上别的进程带 SO_REUSEADDR 能绑到同一端口、抢走连接；独占绑定挡住它。
            exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
            if exclusive is not None:
                listener.setsockopt(socket.SOL_SOCKET, exclusive, 1)
            listener.bind(("127.0.0.1", 0))
            listener.listen(4)
            listener.setblocking(False)
        except BaseException:
            listener.close()
            raise
        return cls(listener, secrets.token_hex(16))

    @property
    def spec(self) -> dict[str, Any]:
        """随 job 交给 worker 的连接参数。"""

        return {"host": "127.0.0.1", "port": self._port, "token": self._token}

    async def events(
        self, on_note: Callable[[str], None]
    ) -> AsyncIterator[dict[str, Any]]:
        """接受 worker 的连接并逐条产出事件；``on_note`` 收给 ``.worker.log`` 看的说明。

        不管怎么结束（EOF、出错、被取消）都先关掉监听与连接：worker 再发送就会出错、改走
        stdout，不会对着一个没人读的连接写满缓冲卡住。
        """

        loop = asyncio.get_running_loop()
        try:
            accepted = await self._accept(loop, on_note)
            if accepted is None:
                return
            conn, decoder, pending = accepted
            while True:
                for item in pending:
                    if isinstance(item, DroppedMessage):
                        on_note(item.reason)
                    else:
                        yield item
                if decoder.error is not None:
                    # 坏处之前的消息上面已经交出去了；之后的字节对不齐，不再读
                    on_note(
                        "MaaFW 事件通道数据损坏，停止读取"
                        f"（之后的事件 worker 改走标准输出）: {decoder.error}"
                    )
                    return
                try:
                    data = await loop.sock_recv(conn, _RECV_BYTES)
                except OSError as exc:
                    # worker 被结束或崩溃时连接是被重置的（不是正常关闭），这一行就是在说这个
                    on_note(
                        f"MaaFW 事件通道读取中断（worker 异常退出或被结束）: {exc!r}"
                    )
                    return
                if not data:
                    if decoder.pending_bytes:
                        on_note(
                            f"MaaFW 事件通道结束时有 {decoder.pending_bytes} 字节"
                            "不成整条消息，已丢弃"
                        )
                    return
                pending = decoder.feed(data)
        finally:
            self.close()

    async def _accept(
        self, loop: asyncio.AbstractEventLoop, on_note: Callable[[str], None]
    ) -> (
        tuple[socket.socket, FrameDecoder, list[dict[str, Any] | DroppedMessage]] | None
    ):
        """等到一个带对令牌的连接；返回连接、它的解帧器与 hello 之后已经读到的消息。"""

        while True:
            listener = self._listener
            if listener is None:
                return None
            try:
                conn, _address = await loop.sock_accept(listener)
            except OSError as exc:
                # 监听出错就不再等连接：worker 连不上会退回 stdout，事件照样送到
                on_note(f"MaaFW 事件通道停止监听: {exc!r}")
                return None
            conn.set_inheritable(False)
            decoder = FrameDecoder()
            try:
                items = await asyncio.wait_for(
                    self._read_first(loop, conn, decoder),
                    timeout=CHANNEL_HANDSHAKE_TIMEOUT_SECONDS,
                )
            except (asyncio.TimeoutError, OSError, ProtocolError) as exc:
                conn.close()
                on_note(f"MaaFW 事件通道收到一个没有完成握手的连接，已断开: {exc!r}")
                continue
            except BaseException:
                conn.close()
                raise
            first = items[0] if items else None
            if not isinstance(first, dict) or not is_valid_hello(first, self._token):
                conn.close()
                on_note("MaaFW 事件通道收到一个令牌不对的连接，已断开")
                continue
            self._conn = conn
            self._close_listener()
            self.connected.set()
            return conn, decoder, items[1:]

    @staticmethod
    async def _read_first(
        loop: asyncio.AbstractEventLoop, conn: socket.socket, decoder: FrameDecoder
    ) -> list[dict[str, Any] | DroppedMessage]:
        while True:
            data = await loop.sock_recv(conn, _RECV_BYTES)
            if not data:
                return []
            items = decoder.feed(data)
            if items:
                return items
            if decoder.error is not None:
                raise decoder.error

    def _close_listener(self) -> None:
        listener, self._listener = self._listener, None
        if listener is not None:
            listener.close()

    def close(self) -> None:
        """关掉监听与连接（可重复调用）。连接一关 worker 再发送就出错，随即退回 stdout。"""

        self._close_listener()
        conn, self._conn = self._conn, None
        if conn is not None:
            conn.close()
