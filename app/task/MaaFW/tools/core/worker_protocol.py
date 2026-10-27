"""宿主与 MaaFW worker 子进程之间的协议：事件格式、共用常量、传输与分帧。

worker（``runner/worker.py``）跑在运行池的隔离 venv 里，``runner.py`` 一导入就加载 ``maa``，宿主
引用不了它的常量，以前只好在宿主里复制一份（信号截图的 kind、``[MaaFW 详情] `` 前缀、日志去向的
几组文案）。两边共用的东西都放这里。只依赖标准库：它在 worker 的导入闭包里（见 MaaFW/AGENTS.md），
宿主导入它也不会拉起 runner 子树。

传输（宿主 ``tools/embedded/runner_task.py`` ↔ ``runner/worker.py``）：

- **job**：宿主把运行计划等写进 worker 的 stdin（UTF-8 JSON），写完就关；不落盘——计划里可能有
  解密后的密码选项。``decode_job`` / ``encode_job`` 是两头的读写。
- **事件**：宿主建一个只进不出的 Windows 命名管道（``WorkerEventServer``，名字随机、只有一个实例），
  名字与一次性令牌随 job 交给 worker；worker 按名字打开（``EventChannelClient``），第一条消息是带
  令牌的 ``hello``，之后一个事件一条消息。消息按帧传（``encode_message`` / ``FrameDecoder``）：4 字节
  大端头，最高位表示后面还有分片，其余 31 位是本片长度；单片不超过 ``MAX_FRAGMENT_BYTES``，整条消息
  不限长——不再像 stdout 那样受单行上限约束。接收端只为内存设一道 ``MAX_MESSAGE_BYTES``：超过的整条
  丢掉、记一句，后面照常读，不会因为一条超长消息停止读取、让 worker 写满缓冲卡住。
- **stdout**：只剩 MaaFramework 的原生诊断，宿主照旧逐行写进 ``.worker.log``。
- **建不起通道时退回旧格式**：宿主建管道失败（job 里不带通道）、worker 打不开、或打开后写入出错
  （宿主关了管道），worker 都改成一行一个 JSON 事件写 stdout（旧格式），宿主一直按行解析 stdout，
  这次运行照常进行；原因各记一行进 ``.worker.log``。退回而不是报错，是因为旧格式是跑了很久的路径，
  而通道建不起来的原因（安全软件拦截之类）用户自己处理不了；job 仍然走 stdin，退回也不会让密码落盘。
  非 Windows 上没有这条通道，直接用旧格式。

选命名管道而不选本机套接字：

- **写的一方没了，已写进去的还在**。worker 原生崩溃、被结束时，管道里已写入的字节宿主照样读得出，
  读完才是 EOF；结果事件写出去之后、``runner.shutdown()`` 里原生崩溃也不会丢结果。Windows 上套接字
  在对端异常退出时收到 RST，接收方还没读走的数据会被直接丢掉——实测宿主读取稍有滞后（50 ms）时
  10 次里 10 次丢事件、连结果一起丢；命名管道同样的实验 60 次 0 丢失。这也是 stdout 管道一直以来
  的语义。
- **句柄不必可继承**：worker 按名字打开管道，宿主建管道、worker 打开管道都不带安全属性，两端句柄
  都不可继承；worker 拉起的 agent、adb，以及宿主同时拉起的模拟器、游戏都拿不到。常驻的继承者会让
  读的一方等不到 EOF（本机吃过这个亏）。
- 没有端口：不占端口、不受本机防火墙规则影响，也没有别的进程抢端口的问题。

宿主一侧用一个后台线程做阻塞读（重叠 I/O 加短轮询，随时能停），不依赖事件循环的实现；读进来的
事件交给事件循环，事件循环处理不过来时线程先停读，worker 的写跟着等（与 stdout 管道写满时一样）。
worker 退出后宿主把管道里剩下的读完、读到 EOF 就结束；从没连上的立刻结束。

日志事件带两个字段：``audience``（``ui`` 进界面，``worker_log`` 只进 ``.worker.log``）与 ``level``。
runner 自己知道去向的日志（``[MaaFW 详情]`` 详情行、``[MaaFW Tasker]`` 回声、失败原文回显）发出时就
标好 ``audience``，失败 / 告警类的带 ``warning`` / ``error`` 级别；只传文案的（agent 与环境准备转来的
输出等）由 worker 在发出时按 ``forwards_to_ui`` 判。宿主照字段办，不再自己按文案猜；不带
``audience`` 的旧格式事件与 stdout 上的原生诊断仍按 ``forwards_to_ui`` 的原规则判，规则只在这里写一份。
"""

from __future__ import annotations

import asyncio
import hmac
import json
import os
import re
import secrets
import struct
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, Mapping

if sys.platform == "win32":
    import _winapi
else:  # pragma: no cover - MaaFW 内置运行只在 Windows 上跑；别处直接用 stdout 旧格式
    _winapi = None

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
_LEVELS = frozenset({LEVEL_INFO, LEVEL_WARNING, LEVEL_ERROR})

#: job 里交给 worker 的事件通道：``{"pipe": <管道名>, "token": <一次性令牌>}``；没有就走 stdout。
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
# runner 自己发的这几类现在发出时就标好 audience；这两组规则留给只传文案的日志（agent 环境
# 准备转来的详情行等）与不带 audience 的旧格式事件。
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

    worker 给只传文案的日志定 ``audience`` 时用它；宿主只对不带 ``audience`` 的旧格式事件和
    stdout 上的原生诊断用它。
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
    """一条日志事件；不指定（或指定了不认识的）``audience`` 时按 ``log_audience`` 判。"""

    return {
        "type": EVENT_LOG,
        "message": message,
        "audience": audience if audience in _AUDIENCES else log_audience(message),
        "level": level if level in _LEVELS else LEVEL_INFO,
    }


def error_event(message: str) -> dict[str, Any]:
    return {
        "type": EVENT_ERROR,
        "message": message,
        "audience": log_audience(message),
        "level": LEVEL_ERROR,
    }


def with_log_fields(event: dict[str, Any]) -> dict[str, Any]:
    """日志 / 错误事件补上 ``audience`` 与 ``level``（已带合法值的不动），其它类型原样返回。

    worker 的 ``_emit`` 发出前过一遍：只传了 ``type`` 与 ``message`` 的事件（``_emit_log``、
    ``{"type": "error", ...}``）也带着这两个字段到宿主。
    """

    kind = event.get("type")
    if kind not in (EVENT_LOG, EVENT_ERROR):
        return event
    if event.get("audience") in _AUDIENCES and event.get("level") in _LEVELS:
        return event
    completed = dict(event)
    if completed.get("audience") not in _AUDIENCES:
        completed["audience"] = log_audience(str(completed.get("message") or ""))
    if completed.get("level") not in _LEVELS:
        completed["level"] = LEVEL_ERROR if kind == EVENT_ERROR else LEVEL_INFO
    return completed


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
# 通道：Windows 命名管道
# ---------------------------------------------------------------------------

#: 管道名前缀。worker 只打开这个前缀下的名字：job 里给的不对就不打开，不往任意路径写。
PIPE_NAME_PREFIX = "\\\\.\\pipe\\auto-mas-maafw-"
#: worker 打开管道时实例正被占用（别的连接还没断开）最多等这么久；正常一次就打开。
CHANNEL_CONNECT_TIMEOUT_SECONDS = 5.0
#: 连上之后多久内必须发来带令牌的 hello，否则宿主关掉通道（worker 随即退回 stdout）。
CHANNEL_HANDSHAKE_TIMEOUT_SECONDS = 10.0
#: worker 退出后宿主最多再读这么久。已写进管道的一读就完、读到 EOF 立刻结束；这一条只防写端
#: 意外留在别的进程里（两端句柄都不可继承，正常不会）。
CHANNEL_DRAIN_SECONDS = 5.0
_PIPE_REJECT_REMOTE_CLIENTS = 0x0000_0008
#: 管道的入向缓冲。写满后 worker 的写等宿主读走，与 stdout 管道写满时一样。
_PIPE_BUFFER_BYTES = 1 << 20
_READ_CHUNK_BYTES = 256 * 1024
#: 读进来、事件循环还没处理完的字节超过这么多时读线程先停读：worker 的写跟着等，内存不无限涨。
_PENDING_HIGH_WATER_BYTES = 32 << 20
#: 读线程等 I/O 时多久看一次要不要停（被关闭、握手超时、收尾超时）。
_POLL_MILLISECONDS = 100


def event_channel_supported() -> bool:
    """这个平台上有没有事件通道（没有就整次运行用 stdout 旧格式）。"""

    return _winapi is not None


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


class EventChannelClient:
    """worker 一侧的事件通道：按名字打开宿主的管道、阻塞写；写不进去抛 ``OSError``（调用方据此退回 stdout）。

    ``send`` 不加锁，调用方（worker 的 ``_emit``）负责串行：一条消息要整条写完再写下一条。
    """

    def __init__(self, handle: int) -> None:
        self._handle: int | None = handle

    @classmethod
    def connect(
        cls,
        spec: Mapping[str, Any],
        *,
        timeout: float = CHANNEL_CONNECT_TIMEOUT_SECONDS,
    ) -> EventChannelClient:
        name = spec.get("pipe")
        token = spec.get("token")
        if (
            not isinstance(name, str)
            or not name.startswith(PIPE_NAME_PREFIX)
            or not isinstance(token, str)
            or not token
        ):
            raise ValueError(f"job 里的事件通道参数不完整: pipe={name!r}")
        if _winapi is None:
            raise OSError("MaaFW 事件通道（命名管道）只在 Windows 上可用")
        client = cls(_open_pipe_for_write(name, timeout))
        try:
            client.send(hello_event(token))
        except BaseException:
            client.close()
            raise
        return client

    def send(self, event: Mapping[str, Any]) -> None:
        handle = self._handle
        if handle is None:
            raise OSError("MaaFW 事件通道已关闭")
        _write_all(handle, encode_message(event))

    def close(self) -> None:
        """关掉写端（可重复调用）。宿主读完已写进去的就读到 EOF。"""

        handle, self._handle = self._handle, None
        if handle is not None:
            _winapi.CloseHandle(handle)


def _open_pipe_for_write(name: str, timeout: float) -> int:
    deadline = time.monotonic() + timeout
    while True:
        try:
            # 安全属性传 NULL：句柄不可继承，MaaFramework 原生层起 adb / agent 时
            # （bInheritHandles=TRUE）带不走它
            return _winapi.CreateFile(
                name,
                _winapi.GENERIC_WRITE,
                0,
                _winapi.NULL,
                _winapi.OPEN_EXISTING,
                0,
                _winapi.NULL,
            )
        except OSError as exc:
            if exc.winerror != _winapi.ERROR_PIPE_BUSY:
                raise
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"MaaFW 事件通道 {timeout:g} s 内一直被占用: {name}")
        try:
            _winapi.WaitNamedPipe(name, max(1, int(min(remaining, 0.5) * 1000)))
        except OSError as exc:
            if exc.winerror != _winapi.ERROR_SEM_TIMEOUT:
                raise


def _write_all(handle: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written, _err = _winapi.WriteFile(handle, view)
        if written <= 0:
            raise OSError(f"MaaFW 事件通道写入 0 字节（还剩 {len(view)} 字节）")
        view = view[written:]


# 读线程交给事件循环的东西：(_Q_EVENT, 事件) / (_Q_NOTE, 给 .worker.log 的说明) /
# (_Q_CREDIT, 一批事件对应的字节数：处理完就还给读线程) / (_Q_CONNECTED, None) / (_Q_END, None)
_Q_EVENT = "event"
_Q_NOTE = "note"
_Q_CREDIT = "credit"
_Q_CONNECTED = "connected"
_Q_END = "end"


class _Interrupted(Exception):
    """读线程不再等：被关闭（``note`` 为 None），或握手 / 收尾超时（``note`` 写进 .worker.log）。"""

    def __init__(self, note: str | None) -> None:
        super().__init__(note)
        self.note = note


class WorkerEventServer:
    """宿主一侧的事件通道：只进不出、只有一个实例的命名管道，由一个后台线程读。

    线程等 worker 打开管道、核对第一条消息里的令牌，之后读到的事件经 ``events`` 交出。线程结束
    （EOF、令牌不对、握手超时、数据损坏、被关闭）时关掉管道：worker 再写就出错、改走 stdout，不会
    对着没人读的管道写满卡住。``events`` 没被调用就走到 ``close`` 的（比如 worker 没起来）由
    ``close`` 直接关管道。
    """

    def __init__(self, handle: int, name: str, token: str) -> None:
        self._handle: int | None = handle
        self._name = name
        self._token = token
        self._lock = threading.Lock()
        self._room = threading.Condition()
        self._pending_bytes = 0
        self._stop = threading.Event()
        self._drain_deadline: float | None = None
        self._thread: threading.Thread | None = None
        #: 收到了带对令牌的 hello（事件循环里置位）。
        self.connected = False

    @classmethod
    def open(cls) -> WorkerEventServer:
        if _winapi is None:
            raise OSError("MaaFW 事件通道（命名管道）只在 Windows 上可用")
        name = f"{PIPE_NAME_PREFIX}{os.getpid()}-{secrets.token_hex(16)}"
        handle = _winapi.CreateNamedPipe(
            name,
            # 只进不出；FIRST_PIPE_INSTANCE：同名管道已存在（被别人抢先建了）就失败
            _winapi.PIPE_ACCESS_INBOUND
            | _winapi.FILE_FLAG_OVERLAPPED
            | _winapi.FILE_FLAG_FIRST_PIPE_INSTANCE,
            # 字节流、阻塞模式，拒绝远程连接
            _PIPE_REJECT_REMOTE_CLIENTS,
            1,
            0,
            _PIPE_BUFFER_BYTES,
            0,
            # 安全属性 NULL：句柄不可继承（宿主同时拉起的模拟器、游戏带不走），默认 DACL
            _winapi.NULL,
        )
        return cls(handle, name, secrets.token_hex(16))

    @property
    def spec(self) -> dict[str, Any]:
        """随 job 交给 worker 的连接参数。"""

        return {"pipe": self._name, "token": self._token}

    def worker_exited(self) -> None:
        """worker 已经退出：管道里剩下的读完就结束；从没连上的不再等。"""

        if self._drain_deadline is None:
            self._drain_deadline = time.monotonic() + CHANNEL_DRAIN_SECONDS

    def close(self) -> None:
        """停止读取、关掉管道（可重复调用）。读线程在跑时由它在一个轮询周期内关。"""

        self._stop.set()
        with self._room:
            self._room.notify_all()
        with self._lock:
            if self._thread is None:
                self._close_handle_locked()

    async def events(
        self, on_note: Callable[[str], None]
    ) -> AsyncIterator[dict[str, Any]]:
        """逐条产出 worker 发来的事件；``on_note`` 收给 ``.worker.log`` 看的说明（在事件循环里调）。

        不管怎么结束（EOF、出错、被取消）都先关掉管道。
        """

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

        def post(kind: str, value: Any = None) -> None:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, (kind, value))
            except RuntimeError:
                # 事件循环已经关了：没人收了，不再读
                self._stop.set()

        start_error: BaseException | None = None
        with self._lock:
            if self._handle is None or self._stop.is_set():
                return
            thread = threading.Thread(
                target=self._pump,
                args=(post,),
                name="maafw-event-channel",
                daemon=True,
            )
            try:
                thread.start()
            except RuntimeError as exc:
                start_error = exc
                self._stop.set()
                self._close_handle_locked()
            else:
                self._thread = thread
        if start_error is not None:
            on_note(
                f"MaaFW 事件通道读取线程起不来（{start_error!r}），本次运行事件改走标准输出"
            )
            return
        try:
            while True:
                kind, value = await queue.get()
                if kind == _Q_EVENT:
                    yield value
                elif kind == _Q_CREDIT:
                    self._release(value)
                elif kind == _Q_NOTE:
                    on_note(value)
                elif kind == _Q_CONNECTED:
                    self.connected = True
                else:
                    return
        finally:
            self.close()

    # -- 读线程 ---------------------------------------------------------------

    def _pump(self, post: Callable[..., None]) -> None:
        try:
            self._serve(post)
        except _Interrupted as exc:
            if exc.note:
                post(_Q_NOTE, exc.note)
        except Exception as exc:  # noqa: BLE001 - 线程里的错只能交给 .worker.log
            post(
                _Q_NOTE,
                "MaaFW 事件通道读取出错，停止读取（之后的事件 worker 改走标准输出）: "
                f"{exc!r}",
            )
        finally:
            with self._lock:
                self._close_handle_locked()
            post(_Q_END)

    def _serve(self, post: Callable[..., None]) -> None:
        handle = self._handle
        if handle is None or not self._wait_for_worker(handle):
            return
        decoder = FrameDecoder()
        handshake_deadline: float | None = (
            time.monotonic() + CHANNEL_HANDSHAKE_TIMEOUT_SECONDS
        )
        while True:
            # 数据一直在来时 _read_chunk 不会等到轮询超时：每读一块都先看一次要不要停
            self._check_interrupt(handshake_deadline)
            self._wait_for_room()
            data = self._read_chunk(handle, handshake_deadline)
            if data is None:
                # EOF：worker 关了管道或已退出，它写进去的都读完了
                if handshake_deadline is not None:
                    post(_Q_NOTE, "MaaFW worker 打开事件通道后没发来握手就关闭了")
                elif decoder.pending_bytes:
                    post(
                        _Q_NOTE,
                        f"MaaFW 事件通道结束时有 {decoder.pending_bytes} 字节"
                        "不成整条消息，已丢弃",
                    )
                return
            if not data:
                continue
            items = decoder.feed(data)
            with self._room:
                self._pending_bytes += len(data)
            for item in items:
                if isinstance(item, DroppedMessage):
                    post(_Q_NOTE, item.reason)
                    continue
                if handshake_deadline is not None:
                    if not is_valid_hello(item, self._token):
                        raise _Interrupted(
                            "MaaFW 事件通道收到一个令牌不对的连接，已关闭通道"
                            "（本次运行事件改走标准输出）"
                        )
                    handshake_deadline = None
                    post(_Q_CONNECTED)
                    continue
                post(_Q_EVENT, item)
            post(_Q_CREDIT, len(data))
            if decoder.error is not None:
                # 坏处之前的消息上面已经交出去了；之后的字节对不齐，不再读
                raise _Interrupted(
                    "MaaFW 事件通道数据损坏，停止读取"
                    f"（之后的事件 worker 改走标准输出）: {decoder.error}"
                )

    def _wait_for_worker(self, handle: int) -> bool:
        """等 worker 打开管道；被关闭、或 worker 已退出还没连上时返回 False。"""

        try:
            overlapped = _winapi.ConnectNamedPipe(handle, overlapped=True)
        except OSError as exc:
            if exc.winerror == _winapi.ERROR_NO_DATA:
                # worker 打开过又关了（多半已退出）：它写进去的还在管道里，照样读
                return True
            raise
        while True:
            if (
                _winapi.WaitForSingleObject(overlapped.event, _POLL_MILLISECONDS)
                == _winapi.WAIT_OBJECT_0
            ):
                overlapped.GetOverlappedResult(True)
                return True
            if self._stop.is_set() or self._drain_deadline is not None:
                # worker 退出前打开过的话上面早就等到了：不会再来了
                overlapped.cancel()
                try:
                    _transferred, err = overlapped.GetOverlappedResult(True)
                except OSError:
                    return False
                return err == 0 and not self._stop.is_set()

    def _read_chunk(
        self, handle: int, handshake_deadline: float | None
    ) -> bytes | None:
        """读一块；EOF 返回 None。被关闭或超时抛 ``_Interrupted``。"""

        try:
            overlapped, _err = _winapi.ReadFile(
                handle, _READ_CHUNK_BYTES, overlapped=True
            )
        except OSError as exc:
            if exc.winerror == _winapi.ERROR_BROKEN_PIPE:
                return None
            raise
        while (
            _winapi.WaitForSingleObject(overlapped.event, _POLL_MILLISECONDS)
            != _winapi.WAIT_OBJECT_0
        ):
            try:
                self._check_interrupt(handshake_deadline)
            except _Interrupted:
                overlapped.cancel()
                try:
                    overlapped.GetOverlappedResult(True)
                except OSError:
                    pass
                raise
        try:
            overlapped.GetOverlappedResult(True)
        except OSError as exc:
            if exc.winerror == _winapi.ERROR_BROKEN_PIPE:
                return None
            raise
        return overlapped.getbuffer()

    def _check_interrupt(self, handshake_deadline: float | None) -> None:
        if self._stop.is_set():
            raise _Interrupted(None)
        now = time.monotonic()
        if handshake_deadline is not None and now >= handshake_deadline:
            raise _Interrupted(
                f"MaaFW 事件通道打开后 {CHANNEL_HANDSHAKE_TIMEOUT_SECONDS:g} s 内没收到握手，"
                "已关闭通道（本次运行事件改走标准输出）"
            )
        drain_deadline = self._drain_deadline
        if drain_deadline is not None and now >= drain_deadline:
            raise _Interrupted(
                f"MaaFW worker 退出 {CHANNEL_DRAIN_SECONDS:g} s 后事件通道仍未结束，停止读取"
            )

    def _wait_for_room(self) -> None:
        with self._room:
            while self._pending_bytes > _PENDING_HIGH_WATER_BYTES:
                if self._stop.is_set():
                    raise _Interrupted(None)
                self._room.wait(_POLL_MILLISECONDS / 1000)

    def _release(self, size: int) -> None:
        with self._room:
            self._pending_bytes -= size
            self._room.notify_all()

    def _close_handle_locked(self) -> None:
        handle, self._handle = self._handle, None
        if handle is not None:
            _winapi.CloseHandle(handle)
