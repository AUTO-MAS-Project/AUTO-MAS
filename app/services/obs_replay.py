#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2026 AUTO-MAS Team

"""OBS replay-buffer integration used by failed task recordings.

Only temporary task copies are managed below ``data``. Manual capture leaves
files in OBS output. Missing OBS or failed copying never changes task results.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
import threading
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from app.models.schema import ObsReplayCheckOut
from app.utils import get_logger

logger = get_logger("OBS回放")

_OBS_URL = "ws://127.0.0.1"
_OBS_RPC_VERSION = 1
_OUTPUTS_SUBSCRIPTION = 1 << 6
_CONNECT_TIMEOUT = 3.0
_REQUEST_TIMEOUT = 5.0
_SAVE_EVENT_TIMEOUT = 30.0
_QUEUE_TIMEOUT = 60.0
# 电源操作前的收尾窗口（system.py），不受进程退出期限约束。
_DRAIN_TIMEOUT = 30.0
# 后端退出时 stop() 从开始到返回的硬上限。外层期限：Electron 只给 Runtime 发
# shutdown 并等 30 秒（frontend/electron/services/backendService.ts 的
# RUNTIME_SHUTDOWN_TIMEOUT_MS），Runtime 从 POST /api/core/close 到后端进程退出
# 只等 --shutdown-timeout（缺省 5 秒，Electron 未传；runtime 仓
# internal/cli/backend.go 的 backendShutdownTimeoutDefault、
# internal/backend/control.go 的 closeCtx），超时即强制回收进程树。这 5 秒要
# 覆盖 main.py shutdown_services() 的全部步骤（停任务、DesktopGuard、本服务、
# RuntimeTasks 等）和 uvicorn 退出，所以本服务只占 2 秒：前 1 秒等在途
# 保存完成，余下留给取消生效与关闭 OBS 连接。被放弃的线程是守护线程：能跑完就
# 各自收尾，进程先退出留下的半成品由下次启动时的 cleanup_temporary 清理。
_STOP_TIMEOUT = 2.0
_STOP_CANCEL_RESERVE = 1.0
_COPY_CANCEL_TIMEOUT = 2.0
_COPY_CHUNK_SIZE = 1024 * 1024


class ObsReplayError(RuntimeError):
    """Raised when OBS cannot provide a replay or the local copy failed."""


@dataclass(frozen=True)
class ObsReplayOptions:
    """Connection and retention settings for one replay operation."""

    port: int = 4455
    password: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        if isinstance(self.port, bool) or not isinstance(self.port, int):
            raise ValueError("OBS端口必须是整数")
        if not 1 <= self.port <= 65535:
            raise ValueError("OBS端口范围无效")


@dataclass(eq=False)
class _CopyOperation:
    """Blocking file work in a daemon thread, with cooperative cancellation."""

    cancel_event: threading.Event = field(default_factory=threading.Event)
    future: asyncio.Future[Any] | None = None


class _CopyCancelled(Exception):
    pass


def _normal_path(path: str | Path) -> str:
    """Return a case-insensitive path key without following missing targets."""

    raw = os.path.expanduser(str(path))
    try:
        normalized = os.path.abspath(os.path.normpath(raw))
    except (OSError, ValueError):
        normalized = raw
    return normalized.replace("\\", "/").casefold()


def _copy_file_chunked(
    source: Path, destination: Path, cancel_event: threading.Event
) -> None:
    """Copy one file and fsync it, checking cancellation between chunks."""

    try:
        with source.open("rb") as source_file, destination.open("wb") as target:
            while True:
                if cancel_event.is_set():
                    raise _CopyCancelled
                chunk = source_file.read(_COPY_CHUNK_SIZE)
                if not chunk:
                    break
                target.write(chunk)
            target.flush()
            os.fsync(target.fileno())
        if cancel_event.is_set():
            raise _CopyCancelled
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def _auth_response(password: str, salt: str, challenge: str) -> str:
    secret = base64.b64encode(
        hashlib.sha256((password + salt).encode("utf-8")).digest()
    ).decode("ascii")
    return base64.b64encode(
        hashlib.sha256((secret + challenge).encode("utf-8")).digest()
    ).decode("ascii")


class _ObsProtocolError(ObsReplayError):
    pass


class _ObsClient:
    """Small single-flight OBS WebSocket v5 client.

    One client is used by one service operation at a time.  Unmatched events
    are retained so an event delivered before its request response is not lost.
    """

    def __init__(self, port: int, password: str):
        self.port = port
        self.password = password
        self.websocket: ClientConnection | None = None
        self._events: deque[dict[str, Any]] = deque(maxlen=64)
        self._request_number = 0

    async def connect(self) -> None:
        try:
            self.websocket = await asyncio.wait_for(
                connect(
                    f"{_OBS_URL}:{self.port}",
                    proxy=None,
                    open_timeout=_CONNECT_TIMEOUT,
                    close_timeout=_CONNECT_TIMEOUT,
                ),
                timeout=_CONNECT_TIMEOUT,
            )
            hello = await self._recv_json(_CONNECT_TIMEOUT)
            if hello.get("op") != 0:
                raise _ObsProtocolError("OBS握手失败")
            data = hello.get("d") or {}
            auth = data.get("authentication") or {}
            identify_data: dict[str, Any] = {
                "rpcVersion": _OBS_RPC_VERSION,
                "eventSubscriptions": _OUTPUTS_SUBSCRIPTION,
            }
            if auth:
                challenge = auth.get("challenge")
                salt = auth.get("salt")
                if not isinstance(challenge, str) or not isinstance(salt, str):
                    raise _ObsProtocolError("OBS认证信息无效")
                identify_data["authentication"] = _auth_response(
                    self.password, salt, challenge
                )
            await self._send_json({"op": 1, "d": identify_data}, _REQUEST_TIMEOUT)
            deadline = asyncio.get_running_loop().time() + _REQUEST_TIMEOUT
            while True:
                message = await self._recv_json(max(0.01, deadline - time.monotonic()))
                if message.get("op") == 2:
                    return
                self._remember_event(message)
                if time.monotonic() >= deadline:
                    raise _ObsProtocolError("OBS识别超时")
        except ObsReplayError:
            await self.close()
            raise
        except asyncio.CancelledError:
            await self.close()
            raise
        except Exception as exc:
            await self.close()
            raise ObsReplayError(f"OBS连接失败：{type(exc).__name__}") from exc

    async def close(self) -> None:
        websocket = self.websocket
        self.websocket = None
        if websocket is not None:
            try:
                await websocket.close()
            except Exception:
                logger.debug("OBS连接关闭失败")

    async def _recv_json(self, timeout: float) -> dict[str, Any]:
        if self.websocket is None:
            raise _ObsProtocolError("OBS连接未建立")
        try:
            raw = await asyncio.wait_for(self.websocket.recv(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise _ObsProtocolError("OBS请求超时") from exc
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if isinstance(exc, ConnectionClosed) and exc.rcvd and exc.rcvd.code == 4009:
                raise ObsReplayError("OBS认证失败，请检查密码") from exc
            raise ObsReplayError(f"OBS通信失败：{type(exc).__name__}") from exc
        try:
            message = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise _ObsProtocolError("OBS响应格式无效") from exc
        if not isinstance(message, dict):
            raise _ObsProtocolError("OBS响应格式无效")
        return message

    async def _send_json(self, message: dict[str, Any], timeout: float) -> None:
        if self.websocket is None:
            raise _ObsProtocolError("OBS连接未建立")
        try:
            await asyncio.wait_for(
                self.websocket.send(json.dumps(message, ensure_ascii=False)),
                timeout=timeout,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise ObsReplayError(f"OBS通信失败：{type(exc).__name__}") from exc

    def _remember_event(self, message: dict[str, Any]) -> None:
        if message.get("op") == 5 and isinstance(message.get("d"), dict):
            self._events.append(message)

    async def request(
        self,
        request_type: str,
        request_data: dict[str, Any] | None = None,
        *,
        raise_for_status: bool = True,
    ) -> dict[str, Any]:
        self._request_number += 1
        request_id = f"auto-mas-{self._request_number}-{uuid.uuid4().hex}"
        data: dict[str, Any] = {"requestType": request_type, "requestId": request_id}
        if request_data is not None:
            data["requestData"] = request_data
        await self._send_json({"op": 6, "d": data}, _REQUEST_TIMEOUT)
        deadline = time.monotonic() + _REQUEST_TIMEOUT
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise _ObsProtocolError("OBS请求超时")
            message = await self._recv_json(remaining)
            if message.get("op") == 5:
                self._remember_event(message)
                continue
            if message.get("op") != 7:
                continue
            response = message.get("d")
            if (
                not isinstance(response, dict)
                or response.get("requestId") != request_id
            ):
                continue
            status = response.get("requestStatus") or {}
            if not status.get("result", False) and raise_for_status:
                raise _ObsProtocolError("OBS请求失败")
            result = response.get("responseData")
            return result if isinstance(result, dict) else {}

    def _clear_events(self, event_type: str) -> None:
        self._events = deque(
            (
                event
                for event in self._events
                if event.get("d", {}).get("eventType") != event_type
            ),
            maxlen=64,
        )

    async def wait_event(self, event_type: str, timeout: float) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while True:
            for index, message in enumerate(self._events):
                data = message.get("d") or {}
                if data.get("eventType") == event_type:
                    del self._events[index]
                    event_data = data.get("eventData")
                    return event_data if isinstance(event_data, dict) else {}
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ObsReplayError("等待OBS回放保存事件超时")
            message = await self._recv_json(remaining)
            self._remember_event(message)

    async def last_replay_path(self) -> str | None:
        result = await self.request("GetLastReplayBufferReplay", raise_for_status=False)
        value = result.get("savedReplayPath")
        return value if isinstance(value, str) and value else None

    async def replay_status(self) -> tuple[bool, str]:
        result = await self.request("GetReplayBufferStatus")
        active = bool(result.get("outputActive", False))
        return active, str(result.get("outputState", ""))

    async def version(self) -> str:
        result = await self.request("GetVersion")
        return str(result.get("obsVersion", ""))

    async def save_replay(self) -> dict[str, Any]:
        self._clear_events("ReplayBufferSaved")
        await self.request("SaveReplayBuffer")
        return await self.wait_event("ReplayBufferSaved", _SAVE_EVENT_TIMEOUT)


class ObsReplayService:
    """采集 OBS 原件或本轮临时副本；长期归档由历史模块负责。"""

    def __init__(self, root: Path | None = None):
        self.root = Path.cwd() if root is None else Path(root)
        self.directory = self.root / "data" / "history-capture"
        self._obs_lock = asyncio.Lock()
        self._save_tasks: set[asyncio.Task[Any]] = set()
        self._copy_operations: set[_CopyOperation] = set()
        self._connections: set[_ObsClient] = set()
        self._closing = False

    async def cleanup_temporary(self) -> None:
        """启动时仅清理本服务遗留的临时副本，OBS输出完全不参与。"""

        def clean() -> None:
            if self.directory.is_symlink() or self.directory.is_junction():
                raise ObsReplayError("回放临时目录不能是链接")
            if not self.directory.is_dir():
                return
            for path in self.directory.iterdir():
                if path.is_symlink() or not path.is_file():
                    continue
                if (
                    re.fullmatch(
                        r"[0-9a-f]{32}(?:\.[^/\\]+)?|\.[0-9a-f]{32}\.part", path.name
                    )
                    is None
                ):
                    continue
                try:
                    path.unlink()
                except OSError as error:
                    logger.warning(f"回放临时副本清理失败：{path}: {error}")

        await asyncio.to_thread(clean)

    @asynccontextmanager
    async def _client(self, options: ObsReplayOptions) -> AsyncIterator[_ObsClient]:
        client = _ObsClient(options.port, options.password)
        self._connections.add(client)
        try:
            await client.connect()
            yield client
        finally:
            self._connections.discard(client)
            await client.close()

    async def check(self, options: ObsReplayOptions) -> ObsReplayCheckOut:
        """仅检查连接及回放缓冲，不创建本地归档。"""
        try:
            async with self._client(options) as client:
                version = await client.version()
                active, _ = await client.replay_status()
                previous = await client.last_replay_path()
                return ObsReplayCheckOut(
                    connected=True,
                    replayActive=active,
                    version=version,
                    directory=str(Path(previous).parent) if previous else "",
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug(f"OBS检查失败：{type(exc).__name__}")
            return ObsReplayCheckOut(code=500, status="error", message=str(exc))

    async def capture(
        self, options: ObsReplayOptions, *, temporary_copy: bool = True
    ) -> Path:
        """及时保存缓冲；手动测试直接返回 OBS 原件，任务得到可移动副本。"""
        if self._closing:
            raise ObsReplayError("回放服务正在停止")
        current = asyncio.current_task()
        if current is not None:
            self._save_tasks.add(current)
        try:
            async with self._queued_lock(self._obs_lock, _QUEUE_TIMEOUT):
                async with self._client(options) as client:
                    active, _ = await client.replay_status()
                    if not active:
                        raise ObsReplayError("OBS回放缓冲未开启")
                    old_path = await client.last_replay_path()
                    old_key = (
                        _normal_path(Path(old_path).resolve(strict=False))
                        if old_path
                        else None
                    )
                    source = await self._resolve_saved_source(
                        client,
                        await client.save_replay(),
                        old_key=old_key,
                    )
            if not temporary_copy:
                return source
            await asyncio.to_thread(self.directory.mkdir, parents=True, exist_ok=True)
            token = uuid.uuid4().hex
            target = self.directory / f"{token}{source.suffix}"
            temporary = self.directory / f".{token}.part"
            try:
                await self._copy_to(source, temporary)
                if self._closing:
                    raise ObsReplayError("回放服务正在停止")
                # 复制线程只写 .part，发布由仍在途的协程执行，取消后不能迟到发布。
                temporary.rename(target)
                return target
            finally:
                with suppress(OSError):
                    temporary.unlink(missing_ok=True)
        except asyncio.CancelledError:
            raise
        except ObsReplayError:
            raise
        except Exception as exc:
            logger.opt(exception=True).warning(f"OBS回放采集失败：{type(exc).__name__}")
            raise ObsReplayError(f"OBS回放采集失败：{type(exc).__name__}") from exc
        finally:
            if current is not None:
                self._save_tasks.discard(current)

    @staticmethod
    @asynccontextmanager
    async def _queued_lock(lock: asyncio.Lock, timeout: float) -> AsyncIterator[None]:
        try:
            await asyncio.wait_for(lock.acquire(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise ObsReplayError("回放保存排队超时") from exc
        try:
            yield
        finally:
            lock.release()

    async def _resolve_saved_source(
        self,
        client: _ObsClient,
        event_data: dict[str, Any],
        *,
        old_key: str | None,
    ) -> Path:
        deadline = time.monotonic() + _SAVE_EVENT_TIMEOUT
        while True:
            candidate = self._event_path(event_data)
            if candidate is None:
                candidate = await client.last_replay_path()
            if candidate is None:
                raise ObsReplayError("OBS未返回回放文件路径")
            source = Path(candidate)
            if source.is_symlink():
                raise ObsReplayError("OBS回放源文件无效")
            if not source.is_absolute():
                source = (Path.cwd() / source).resolve(strict=False)
            else:
                source = source.resolve(strict=False)
            if old_key is not None and _normal_path(source) == old_key:
                # OBS normally creates a timestamped path.  Ignore an event
                # that repeats the path observed before SaveReplayBuffer.
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ObsReplayError("OBS回放路径未更新")
                event_data = await client.wait_event("ReplayBufferSaved", remaining)
                continue
            if source.is_file() and not source.is_symlink():
                return source
            if time.monotonic() >= deadline:
                raise ObsReplayError("OBS回放文件不存在")
            await asyncio.sleep(0.1)

    @staticmethod
    def _event_path(event_data: dict[str, Any]) -> str | None:
        value = event_data.get("savedReplayPath")
        return value if isinstance(value, str) and value else None

    async def _copy_to(self, source: Path, temporary: Path) -> None:
        # OBS 输出可能在慢盘上；取消后复制线程只负责停止复制和删除临时文件，
        # 不会发布副本或元数据。
        try:
            await self._run_file_work(
                _copy_file_chunked, source, temporary, name="obs-replay-copy"
            )
        except _CopyCancelled as exc:
            raise ObsReplayError("回放文件复制已取消") from exc

    async def _run_file_work(self, function: Any, *args: Any, name: str) -> Any:
        """Run blocking file work in a daemon thread with a bounded cancel wait.

        The default executor is non-daemon: ``asyncio.run`` and interpreter
        exit join it, so a blocked write would hold up backend shutdown.  On
        cancellation the worker is told to stop and waited for at most
        ``_COPY_CANCEL_TIMEOUT``; an abandoned worker cleans up its own files.
        """

        operation = _CopyOperation()
        self._copy_operations.add(operation)
        loop = asyncio.get_running_loop()
        future = operation.future = loop.create_future()

        def finish(result: Any, error: BaseException | None) -> None:
            if not future.done():
                if error is None:
                    future.set_result(result)
                else:
                    future.set_exception(error)

        def work() -> None:
            result = error = None
            try:
                result = function(*args, operation.cancel_event)
            except BaseException as exc:
                error = exc
            with suppress(RuntimeError):
                loop.call_soon_threadsafe(finish, result, error)

        try:
            threading.Thread(target=work, name=name, daemon=True).start()
            return await asyncio.shield(future)
        except asyncio.CancelledError:
            operation.cancel_event.set()
            try:
                await asyncio.wait_for(asyncio.shield(future), _COPY_CANCEL_TIMEOUT)
            except asyncio.TimeoutError:
                logger.warning(f"{name} 取消超时，继续退出；线程停止后自行清理文件")
            except BaseException:
                pass
            future.cancel()
            raise
        finally:
            self._copy_operations.discard(operation)

    async def drain(self, timeout: float = _DRAIN_TIMEOUT) -> bool:
        """Wait for currently registered saves, returning false on timeout."""

        # 让调度层刚注册的后台保存先进入服务，避免错判为没有在途任务。
        await asyncio.sleep(0)
        if timeout < 0:
            timeout = 0
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            tasks = [task for task in self._save_tasks if not task.done()]
            if not tasks:
                return True
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                logger.warning("OBS回放保存收尾超时")
                return False
            done, _ = await asyncio.wait(tasks, timeout=remaining)
            if not done:
                logger.warning("OBS回放保存收尾超时")
                return False

    async def stop(self) -> None:
        """Reject new saves and finish or cancel all in-flight operations.

        Every step shares one deadline of ``_STOP_TIMEOUT`` seconds.  Work that
        has not settled by then is abandoned: file workers are daemon threads
        that leave either a complete replay or nothing behind if they get to
        finish; leftovers from a process that exits first are swept on the next
        start.
        """

        loop = asyncio.get_running_loop()
        deadline = loop.time() + _STOP_TIMEOUT

        async def wait_until_deadline(tasks: list[asyncio.Task[Any]]) -> bool:
            remaining = deadline - loop.time()
            if remaining > 0:
                await asyncio.wait(tasks, timeout=remaining)
            return all(task.done() for task in tasks)

        await asyncio.sleep(0)
        self._closing = True
        settled = await self.drain(max(0.0, _STOP_TIMEOUT - _STOP_CANCEL_RESERVE))
        if not settled:
            for operation in tuple(self._copy_operations):
                operation.cancel_event.set()
            tasks = [task for task in self._save_tasks if not task.done()]
            for task in tasks:
                task.cancel()
            settled = not tasks or await wait_until_deadline(tasks)
        for operation in tuple(self._copy_operations):
            operation.cancel_event.set()
        clients = tuple(self._connections)
        if clients:
            closing = [asyncio.create_task(client.close()) for client in clients]
            if not await wait_until_deadline(closing):
                settled = False
                for task in closing:
                    task.cancel()
        if not settled:
            logger.warning("OBS回放服务未在退出期限内收尾，已放弃等待")


ObsReplay = ObsReplayService()


__all__ = [
    "ObsReplay",
    "ObsReplayError",
    "ObsReplayOptions",
    "ObsReplayService",
]
