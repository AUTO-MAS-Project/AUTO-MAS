#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2026 AUTO-MAS Team

"""OBS replay-buffer integration used by failed task recordings.

The service deliberately owns only a small, private directory below ``data``.
OBS is treated as an optional local service: a missing OBS instance or a
failed copy must never change the result of the task that requested a replay.
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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from app.models.schema import ObsReplayCheckOut, ReplayRecord
from app.utils import get_logger

logger = get_logger("OBS回放")

_OBS_URL = "ws://127.0.0.1"
_OBS_RPC_VERSION = 1
_OUTPUTS_SUBSCRIPTION = 1 << 6
_CONNECT_TIMEOUT = 3.0
_REQUEST_TIMEOUT = 5.0
_SAVE_EVENT_TIMEOUT = 30.0
_QUEUE_TIMEOUT = 60.0
_STOP_TIMEOUT = 30.0
_COPY_CANCEL_TIMEOUT = 2.0
_COPY_CHUNK_SIZE = 1024 * 1024
_METADATA_PREFIX = "mas-replay-"


class ObsReplayError(RuntimeError):
    """Raised when OBS cannot provide a replay or the local copy failed."""


@dataclass(frozen=True)
class ObsReplayOptions:
    """Connection and retention settings for one replay operation."""

    port: int = 4455
    password: str = field(default="", repr=False)
    max_replay_count: int = 3

    def __post_init__(self) -> None:
        if isinstance(self.port, bool) or not isinstance(self.port, int):
            raise ValueError("OBS端口必须是整数")
        if not 1 <= self.port <= 65535:
            raise ValueError("OBS端口范围无效")
        if isinstance(self.max_replay_count, bool) or not isinstance(
            self.max_replay_count, int
        ):
            raise ValueError("回放保留数量必须是整数")
        if not 1 <= self.max_replay_count <= 20:
            raise ValueError("回放保留数量必须在1到20之间")


@dataclass(eq=False)
class _CopyOperation:
    """A copy running in a worker thread, with cooperative cancellation."""

    cancel_event: threading.Event = field(default_factory=threading.Event)
    future: asyncio.Future[None] | None = None


class _CopyCancelled(Exception):
    pass


def _safe_name(value: str, *, limit: int = 64) -> str:
    value = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "-", value).strip("-._")
    return (value or "replay")[:limit]


def _normal_path(path: str | Path) -> str:
    """Return a case-insensitive path key without following missing targets."""

    raw = os.path.expanduser(str(path))
    try:
        normalized = os.path.abspath(os.path.normpath(raw))
    except (OSError, ValueError):
        normalized = raw
    return normalized.replace("\\", "/").casefold()


def _is_direct_file(path: Path, directory: Path) -> bool:
    """Check that a managed path is a regular direct child of our directory."""

    if path.is_symlink() or not path.is_file():
        return False
    try:
        return path.resolve(strict=True).parent == directory.resolve(strict=True)
    except (FileNotFoundError, OSError, RuntimeError):
        return False


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


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Write metadata in the same directory and publish it with os.replace."""

    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.part")
    try:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with temporary.open("x", encoding="utf-8", newline="\n") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _delete_managed_file(path: Path, directory: Path) -> bool:
    if not _is_direct_file(path, directory):
        return False
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return True
    except OSError:
        return False


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
    """Save OBS replay-buffer files and maintain a bounded local archive."""

    def __init__(self, root: Path | None = None):
        self.root = Path.cwd() if root is None else Path(root)
        self.directory = self.root / "data" / "replays"
        self._obs_lock = asyncio.Lock()
        self._storage_lock = asyncio.Lock()
        self._save_tasks: set[asyncio.Task[Any]] = set()
        self._copy_operations: set[_CopyOperation] = set()
        self._connections: set[_ObsClient] = set()
        self._closing = False

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
        """Check the local OBS connection and replay-buffer state."""

        try:
            async with self._client(options) as client:
                version = await client.version()
                active, _ = await client.replay_status()
                return ObsReplayCheckOut(
                    connected=True,
                    replayActive=active,
                    version=version,
                    directory=str(self.directory),
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug(f"OBS检查失败：{type(exc).__name__}")
            return ObsReplayCheckOut(
                code=500,
                status="error",
                message=str(exc),
                connected=False,
                replayActive=False,
                version="",
                directory=str(self.directory),
            )

    async def save(
        self, options: ObsReplayOptions, record: ReplayRecord
    ) -> ReplayRecord:
        """Save one replay and publish its metadata after a complete copy."""

        current_task = asyncio.current_task()
        if self._closing:
            raise ObsReplayError("回放服务正在停止")
        if current_task is not None:
            self._save_tasks.add(current_task)
        try:
            return await self._save_impl(options, record)
        except asyncio.CancelledError:
            raise
        except ObsReplayError:
            raise
        except Exception as exc:
            logger.opt(exception=True).warning(f"OBS回放保存失败：{type(exc).__name__}")
            raise ObsReplayError(f"OBS回放保存失败：{type(exc).__name__}") from exc
        finally:
            if current_task is not None:
                self._save_tasks.discard(current_task)

    async def _save_impl(
        self, options: ObsReplayOptions, record: ReplayRecord
    ) -> ReplayRecord:
        self._ensure_directory()
        async with self._queued_lock(self._obs_lock, _QUEUE_TIMEOUT):
            async with self._client(options) as client:
                version = await client.version()
                active, _ = await client.replay_status()
                if not active:
                    raise ObsReplayError("OBS回放缓冲未开启")
                old_path = await client.last_replay_path()
                old_key = (
                    _normal_path(Path(old_path).resolve(strict=False))
                    if old_path
                    else None
                )
                event_data = await client.save_replay()
                source = await self._resolve_saved_source(
                    client,
                    event_data,
                    old_key=old_key,
                )
        # 文件复制独立于 OBS 请求，下一账号失败时仍能及时保存缓冲。
        return await self._archive_copy(options, record, source, version)

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

    async def _archive_copy(
        self,
        options: ObsReplayOptions,
        record: ReplayRecord,
        source: Path,
        version: str,
    ) -> ReplayRecord:
        source = source.resolve(strict=False)
        if source.is_symlink() or not source.is_file():
            raise ObsReplayError("OBS回放源文件无效")
        token = uuid.uuid4().hex
        name = _safe_name(str(record.replayId))
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        target = self.directory / f"{name}-{timestamp}-{token}{source.suffix}"
        temporary = self.directory / f".{target.name}.{token}.part"
        metadata = self.directory / f"{_METADATA_PREFIX}{token}.json"
        try:
            await self._copy_to(source, temporary)
            async with self._storage_lock:
                await self._thread_join(os.replace, temporary, target)
                published = record.model_copy(update={"filePath": str(target)})
                payload = published.model_dump(mode="json")
                payload["sourcePath"] = str(source)
                payload["obsVersion"] = version
                await self._thread_join(_write_json_atomic, metadata, payload)
                await self._retain(options.max_replay_count)
            return published
        except asyncio.CancelledError:
            # 磁盘读取仍阻塞时临时文件可能被线程持有；线程结束后自行清理。
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
            _delete_managed_file(target, self.directory)
            _delete_managed_file(metadata, self.directory)
            raise
        except ObsReplayError:
            temporary.unlink(missing_ok=True)
            _delete_managed_file(target, self.directory)
            _delete_managed_file(metadata, self.directory)
            raise
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            _delete_managed_file(target, self.directory)
            _delete_managed_file(metadata, self.directory)
            raise ObsReplayError(f"回放文件复制失败：{type(exc).__name__}") from exc

    async def _copy_to(self, source: Path, temporary: Path) -> None:
        operation = _CopyOperation()
        self._copy_operations.add(operation)
        loop = asyncio.get_running_loop()
        future = operation.future = loop.create_future()

        def finish(error: BaseException | None) -> None:
            if not future.done():
                if error is None:
                    future.set_result(None)
                else:
                    future.set_exception(error)

        def copy() -> None:
            error = None
            try:
                _copy_file_chunked(source, temporary, operation.cancel_event)
            except BaseException as exc:
                error = exc
            with suppress(RuntimeError):
                loop.call_soon_threadsafe(finish, error)

        # OBS 输出可能在慢盘上。守护线程不会让关闭进程再等默认线程池的无限 join；
        # 取消后它只负责停止复制和删除临时文件，不会发布副本或元数据。
        try:
            threading.Thread(target=copy, name="obs-replay-copy", daemon=True).start()
            await asyncio.shield(future)
        except asyncio.CancelledError:
            operation.cancel_event.set()
            try:
                await asyncio.wait_for(asyncio.shield(future), _COPY_CANCEL_TIMEOUT)
            except asyncio.TimeoutError:
                logger.warning(
                    "回放复制取消超时，继续退出；复制线程停止后将清理临时文件"
                )
            except BaseException:
                pass
            future.cancel()
            raise
        except _CopyCancelled as exc:
            raise ObsReplayError("回放文件复制已取消") from exc
        finally:
            self._copy_operations.discard(operation)

    @staticmethod
    async def _thread_join(function: Any, *args: Any) -> Any:
        task = asyncio.create_task(asyncio.to_thread(function, *args))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            try:
                await asyncio.shield(task)
            except BaseException:
                pass
            raise

    async def _read_records(self) -> list[tuple[Path, ReplayRecord]]:
        records: list[tuple[Path, ReplayRecord]] = []
        published_times: dict[Path, int] = {}
        if self.directory.is_symlink() or not self.directory.is_dir():
            return records
        directory = self.directory.resolve(strict=False)
        for metadata in self.directory.glob(f"{_METADATA_PREFIX}*.json"):
            if metadata.is_symlink() or not metadata.is_file():
                continue
            try:
                payload = json.loads(metadata.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    continue
                record = ReplayRecord.model_validate(payload)
                file_path = Path(record.filePath)
                token = metadata.stem.removeprefix(_METADATA_PREFIX)
                if not re.fullmatch(
                    r"[0-9a-f]{32}", token
                ) or not file_path.stem.endswith(f"-{token}"):
                    continue
                if not file_path.is_absolute():
                    file_path = (Path.cwd() / file_path).resolve(strict=False)
                if not _is_direct_file(file_path, directory):
                    continue
                record = record.model_copy(update={"filePath": str(file_path)})
                published_times[metadata] = metadata.stat().st_mtime_ns
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
            records.append((metadata, record))
        # 按副本发布顺序保留，慢复制不能在发布时立即被较早完成的副本挤掉。
        records.sort(key=lambda pair: published_times[pair[0]], reverse=True)
        return records

    def _ensure_directory(self) -> None:
        if self.directory.is_symlink():
            raise ObsReplayError("回放目录无效")
        self.directory.mkdir(parents=True, exist_ok=True)

    async def list_replays(self, history_path: str | None = None) -> list[ReplayRecord]:
        """Return published records, newest first, optionally by history path."""

        async with self._storage_lock:
            self._ensure_directory()
            records = await self._read_records()
        if history_path is None:
            return [record for _, record in records]
        wanted = _normal_path(history_path)
        return [
            record
            for _, record in records
            if any(_normal_path(path) == wanted for path in record.historyPaths)
        ]

    async def _retain(self, max_replay_count: int) -> None:
        records = await self._read_records()
        for metadata, record in records[max_replay_count:]:
            file_path = Path(record.filePath)
            if not _is_direct_file(file_path, self.directory.resolve(strict=False)):
                continue
            if _delete_managed_file(file_path, self.directory.resolve(strict=False)):
                _delete_managed_file(metadata, self.directory.resolve(strict=False))

    async def drain(self, timeout: float = _STOP_TIMEOUT) -> bool:
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
        """Reject new saves and finish or cancel all in-flight operations."""

        await asyncio.sleep(0)
        self._closing = True
        if not await self.drain(_STOP_TIMEOUT):
            for operation in tuple(self._copy_operations):
                operation.cancel_event.set()
            tasks = [task for task in self._save_tasks if not task.done()]
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
        for operation in tuple(self._copy_operations):
            operation.cancel_event.set()
        clients = tuple(self._connections)
        if clients:
            await asyncio.gather(
                *(client.close() for client in clients), return_exceptions=True
            )


ObsReplay = ObsReplayService()


__all__ = [
    "ObsReplay",
    "ObsReplayError",
    "ObsReplayOptions",
    "ObsReplayService",
]
