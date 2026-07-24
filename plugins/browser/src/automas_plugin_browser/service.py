from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import math
import re
import secrets
import threading
import time
import uuid
from concurrent.futures import Executor, Future
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from queue import Empty, Queue
from typing import Any, Callable

import psutil
from pydantic import ValidationError

from .backend import BrowserDriverHandle, PreparedBinaries, SeleniumBrowserBackend
from .errors import BrowserRuntimeError
from .models import BrowserOpenOptions, BrowserOpenRequest, BrowserPrepareRequest
from .schema import Config
from .validation import validate_browser_url


_QUARANTINE_FILE = ".auto-mas-quarantine.json"
_DEFAULT_CLOSE_TIMEOUT_SECONDS = 15.0
_DEFAULT_SHUTDOWN_TIMEOUT_SECONDS = 30.0


class _DaemonExecutor(Executor):
    """单工作线程执行器；第三方驱动永久卡死时不阻塞解释器退出。"""

    def __init__(self, name: str) -> None:
        self._queue: Queue[
            tuple[Future[Any], Callable[..., Any], tuple[Any, ...], dict[str, Any]] | None
        ] = Queue()
        self._lock = threading.Lock()
        self._shutdown = False
        self._worker = threading.Thread(
            target=self._run,
            name=name,
            daemon=True,
        )
        self._worker.start()

    def submit(
        self,
        fn: Callable[..., Any],
        /,
        *args: Any,
        **kwargs: Any,
    ) -> Future[Any]:
        with self._lock:
            if self._shutdown:
                raise RuntimeError("执行器已关闭")
            future: Future[Any] = Future()
            self._queue.put((future, fn, args, kwargs))
            return future

    def shutdown(
        self,
        wait: bool = True,
        *,
        cancel_futures: bool = False,
    ) -> None:
        with self._lock:
            first_shutdown = not self._shutdown
            self._shutdown = True
            if first_shutdown and cancel_futures:
                while True:
                    try:
                        item = self._queue.get_nowait()
                    except Empty:
                        break
                    if item is not None:
                        item[0].cancel()
            if first_shutdown:
                self._queue.put(None)
        if wait and threading.current_thread() is not self._worker:
            self._worker.join()

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            future, func, args, kwargs = item
            if not future.set_running_or_notify_cancel():
                continue
            try:
                result = func(*args, **kwargs)
            except BaseException as exc:
                future.set_exception(exc)
            else:
                future.set_result(result)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _storage_segment(value: str) -> str:
    prefix = re.sub(r"[^A-Za-z0-9_.-]", "_", value).strip("._-")[:32] or "profile"
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def _profile_log_id(profile_key: tuple[str, str, str]) -> str:
    raw = "\0".join(profile_key).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:10]


@dataclass(slots=True)
class _SessionRecord:
    session_id: str
    session_token: str
    options: BrowserOpenOptions
    profile_path: Path
    handle: BrowserDriverHandle
    executor: _DaemonExecutor
    started_at: str
    last_status: dict[str, Any]
    operation_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    closing: bool = False
    closed: bool = False
    orphaned: bool = False
    handoff_lease_id: str = ""
    handoff_lease_token: str = ""


class BrowserRuntime:
    """管理持久 Profile、Selenium 会话和跨插件调用。"""

    contract_version = 1

    def __init__(
        self,
        *,
        config: Config,
        data_dir: Path,
        logger: Any,
        backend: SeleniumBrowserBackend | None = None,
        prepare_timeout_seconds: float | None = None,
        launch_timeout_seconds: float | None = None,
        operation_timeout_seconds: float | None = None,
        close_timeout_seconds: float = _DEFAULT_CLOSE_TIMEOUT_SECONDS,
        shutdown_timeout_seconds: float = _DEFAULT_SHUTDOWN_TIMEOUT_SECONDS,
    ) -> None:
        self._config = config
        self._data_dir = data_dir
        self._profiles_root = data_dir / "profiles"
        self._assets_root = data_dir / "selenium"
        self._logger = logger
        self._backend = backend or SeleniumBrowserBackend()
        self._sessions: dict[str, _SessionRecord] = {}
        self._profile_sessions: dict[tuple[str, str, str], str] = {}
        self._opening_tasks: set[asyncio.Task[Any]] = set()
        self._registry_lock = asyncio.Lock()
        self._prepare_lock = asyncio.Lock()
        self._prepare_executor = _DaemonExecutor("browser-prepare")
        self._prepared_binaries: dict[tuple[str, str], PreparedBinaries] = {}
        self._prepare_attempts_lock = threading.Lock()
        self._prepare_attempts: dict[Path, Future[Any]] = {}
        self._cleanup_guard = threading.Lock()
        self._cleanup_inflight: set[str] = set()
        self._prepare_timeout_seconds = self._normalize_timeout(
            prepare_timeout_seconds,
            default=float(config.manager_timeout_seconds) + 5.0,
        )
        self._launch_timeout_seconds = self._normalize_timeout(
            launch_timeout_seconds,
            default=float(config.manager_timeout_seconds),
        )
        self._operation_timeout_seconds = self._normalize_timeout(
            operation_timeout_seconds,
            default=float(config.page_load_timeout_seconds) + 5.0,
        )
        self._close_timeout_seconds = self._normalize_timeout(
            close_timeout_seconds,
            default=_DEFAULT_CLOSE_TIMEOUT_SECONDS,
        )
        self._shutdown_timeout_seconds = self._normalize_timeout(
            shutdown_timeout_seconds,
            default=_DEFAULT_SHUTDOWN_TIMEOUT_SECONDS,
        )
        self._stopping = False

    def snapshot(self) -> dict[str, Any]:
        selenium_available = importlib.util.find_spec("selenium") is not None
        return {
            "contract_version": self.contract_version,
            "available": selenium_available,
            "reason": "" if selenium_available else "Selenium 未安装",
            "engines": ["managed-chrome", "chrome", "edge"],
            "features": [
                "profile.persistent",
                "storage.persistent",
                "profile.single-writer",
                "session.capability-token",
                "window.visible",
                "window.activate",
                "headless",
                "navigation",
                "screenshot.cdp",
                "script.execute",
                "cdp.execute",
                "automation.external-debugger-handoff",
            ],
            "cookie_export_api": False,
            "trust_model": "in-process plugins are privileged",
            "automation_bridges": {
                "m7a": {
                    "external_session": "adapter-required",
                    "mode": "debugger-attach",
                    "upstream_supported": False,
                    "reason": "原版 M7A 需要 MAS-compatible external-owner 适配",
                },
                "sra": {
                    "external_session": "adapter-required",
                    "mode": "debugger-attach",
                    "upstream_supported": False,
                    "reason": "SRA 2.16.1 需要 MAS-compatible external-session 适配",
                },
            },
        }

    async def prepare(self, request: dict[str, Any] | None = None) -> dict[str, Any]:
        self._ensure_running("prepare")
        try:
            parsed = BrowserPrepareRequest.model_validate(request or {})
        except ValidationError as exc:
            raise BrowserRuntimeError(
                "INVALID_REQUEST",
                "浏览器准备参数无效",
                operation="prepare",
                safe_details={"error_count": exc.error_count()},
            ) from exc

        prepared = await self._prepare_binaries(parsed)
        return {
            "requested_mode": prepared.requested_mode,
            "resolved_mode": prepared.resolved_mode,
            "browser_version": prepared.browser_version,
            "browser_ready": bool(prepared.browser_path),
            "driver_ready": bool(prepared.driver_path),
        }

    async def open_session(self, request: dict[str, Any]) -> dict[str, Any]:
        options = self._resolve_open_options(request)
        current_task = asyncio.current_task()
        await self._track_opening(current_task)
        try:
            return await self._open_session(options)
        finally:
            await self._untrack_opening(current_task)

    async def _open_session(self, options: BrowserOpenOptions) -> dict[str, Any]:
        while True:
            session_id = uuid.uuid4().hex
            session_token = secrets.token_urlsafe(32)
            existing: _SessionRecord | None = None

            async with self._registry_lock:
                self._ensure_running("open_session")
                existing_id = self._profile_sessions.get(options.profile_key)
                if existing_id is None:
                    self._profile_sessions[options.profile_key] = session_id
                    break
                existing = self._sessions.get(existing_id)

            if (
                existing is not None
                and options.reuse_policy == "reuse"
                and self._token_matches(existing, options.session_token)
            ):
                existing.last_status = await self._run(
                    existing,
                    self._backend.status,
                    existing.handle,
                    allow_leased=True,
                )
                if existing.last_status.get("alive"):
                    return self._session_info(
                        existing,
                        reused=True,
                        include_token=True,
                    )
                await self.close_session(
                    existing.session_id,
                    session_token=existing.session_token,
                )
                continue

            raise BrowserRuntimeError(
                "PROFILE_BUSY",
                "浏览器 Profile 已被活动会话占用",
                operation="open_session",
                retryable=True,
                safe_details={"profile_ref": _profile_log_id(options.profile_key)},
            )

        executor: _DaemonExecutor | None = None
        open_future: Future[Any] | None = None
        late_cleanup_attached = False
        handle: BrowserDriverHandle | None = None
        record: _SessionRecord | None = None
        profile_path: Path | None = None
        try:
            binaries = await self._prepare_binaries(
                BrowserPrepareRequest(
                    browser_mode=options.browser_mode,
                    browser_version=options.browser_version,
                )
            )
            profile_path = self._ensure_profile(options, binaries.resolved_mode)
            executor = _DaemonExecutor(f"browser-{session_id[:8]}")
            open_future = executor.submit(
                partial(
                    self._backend.open,
                    self._config,
                    options,
                    profile_path,
                    binaries,
                    session_id,
                ),
            )
            try:
                async with asyncio.timeout(self._launch_timeout_seconds):
                    handle = await asyncio.shield(
                        asyncio.wrap_future(open_future)
                    )
            except TimeoutError as exc:
                raise BrowserRuntimeError(
                    "LAUNCH_TIMEOUT",
                    "浏览器会话启动超时",
                    operation="open_session",
                    retryable=True,
                    safe_details={
                        "timeout_seconds": self._launch_timeout_seconds,
                        "profile_quarantine_required": True,
                    },
                ) from exc

            record = _SessionRecord(
                session_id=session_id,
                session_token=session_token,
                options=options,
                profile_path=profile_path,
                handle=handle,
                executor=executor,
                started_at=_utc_now(),
                last_status={
                    "alive": True,
                    "url": options.initial_url,
                    "title": "",
                    "driver_pid": handle.driver_pid,
                    "window_handle": None,
                },
            )
            async with self._registry_lock:
                if self._stopping:
                    raise BrowserRuntimeError(
                        "RUNTIME_STOPPING",
                        "浏览器运行时正在停止",
                        operation="open_session",
                        retryable=True,
                    )
                self._sessions[session_id] = record

            record.last_status = await self._run(
                record,
                self._backend.status,
                record.handle,
            )
            if record.last_status.get("alive") is not True:
                raise BrowserRuntimeError(
                    "LAUNCH_FAILED",
                    "浏览器会话启动后首次状态检查即不可用",
                    operation="open_session",
                    retryable=True,
                    safe_details={
                        "error_type": str(
                            record.last_status.get("error_type") or "DeadOnArrival"
                        ),
                        "mode": binaries.resolved_mode,
                    },
                )
        except BaseException as open_error:
            if record is not None and self._sessions.get(session_id) is record:
                try:
                    await asyncio.shield(
                        self.close_session(
                            session_id,
                            session_token=session_token,
                        )
                    )
                except BaseException:
                    self._logger.exception(
                        f"[browser] 打开会话失败后的回收异常: session={session_id}"
                    )
            elif handle is not None and executor is not None:
                try:
                    close_future = executor.submit(self._backend.close, handle)
                    async with asyncio.timeout(self._close_timeout_seconds):
                        await asyncio.shield(asyncio.wrap_future(close_future))
                    handle = None
                except BaseException as exc:
                    close_error = (
                        exc
                        if isinstance(exc, BrowserRuntimeError)
                        else self._close_error(exc)
                    )
                    if profile_path is not None:
                        record = await self._retain_failed_open(
                            session_id=session_id,
                            session_token=session_token,
                            options=options,
                            profile_path=profile_path,
                            handle=handle,
                            executor=executor,
                            error=close_error,
                        )
                    self._logger.exception(
                        f"[browser] 未注册会话回收失败，Profile 已隔离: session={session_id}"
                    )
            elif (
                profile_path is not None
                and open_future is not None
                and executor is not None
                and (
                    isinstance(open_error, asyncio.CancelledError)
                    or (
                        isinstance(open_error, BrowserRuntimeError)
                        and open_error.code == "LAUNCH_TIMEOUT"
                    )
                )
            ):
                quarantine_error = (
                    open_error
                    if isinstance(open_error, BrowserRuntimeError)
                    else BrowserRuntimeError(
                        "LAUNCH_CANCELLED",
                        "浏览器会话启动被取消且驱动退出状态未知",
                        operation="open_session",
                        retryable=True,
                        safe_details={
                            "surviving_processes": [],
                            "process_scan_complete": False,
                            "profile_quarantine_required": True,
                        },
                    )
                )
                self._write_profile_quarantine_payload(
                    profile_path=profile_path,
                    session_id=session_id,
                    profile_key=options.profile_key,
                    error=quarantine_error,
                )
                self._start_process_cleanup(
                    session_id,
                    profile_path=profile_path,
                    profile_key=options.profile_key,
                )
                self._attach_late_open_cleanup(
                    future=open_future,
                    profile_path=profile_path,
                    session_id=session_id,
                    session_token=session_token,
                    options=options,
                    profile_key=options.profile_key,
                    executor=executor,
                )
                late_cleanup_attached = True
            elif (
                profile_path is not None
                and isinstance(open_error, BrowserRuntimeError)
                and open_error.safe_details.get("profile_quarantine_required") is True
            ):
                self._write_profile_quarantine_payload(
                    profile_path=profile_path,
                    session_id=session_id,
                    profile_key=options.profile_key,
                    error=open_error,
                )
            retained = record is not None and self._sessions.get(session_id) is record
            if not retained and not late_cleanup_attached:
                await self._release_failed_open(options.profile_key, session_id)
                if executor is not None:
                    executor.shutdown(wait=False, cancel_futures=True)
            raise

        profile_ref = _profile_log_id(options.profile_key)
        self._logger.info(
            "[browser] 会话已打开: session={}, owner={}, namespace={}, profile_ref={}".format(
                session_id,
                options.owner_instance_id,
                options.namespace,
                profile_ref,
            )
        )
        return self._session_info(record, include_token=True)

    async def session_status(
        self,
        session_id: str,
        *,
        session_token: str,
    ) -> dict[str, Any]:
        record = self._require_session(session_id, session_token)
        record.last_status = await self._run(
            record,
            self._backend.status,
            record.handle,
            allow_leased=True,
        )
        return self._session_info(record)

    async def navigate(
        self,
        session_id: str,
        url: str,
        *,
        session_token: str,
    ) -> dict[str, Any]:
        try:
            target_url = validate_browser_url(url)
        except ValueError as exc:
            raise BrowserRuntimeError(
                "INVALID_REQUEST",
                str(exc),
                operation="navigate",
            ) from exc
        record = self._require_session(session_id, session_token)
        record.last_status = await self._run(
            record,
            self._backend.navigate,
            record.handle,
            target_url,
        )
        return self._session_info(record)

    async def activate(
        self,
        session_id: str,
        *,
        session_token: str,
    ) -> bool:
        record = self._require_session(session_id, session_token)
        return bool(await self._run(record, self._backend.activate, record.handle))

    async def capture(
        self,
        session_id: str,
        *,
        session_token: str,
        image_format: str = "jpeg",
        quality: int = 90,
    ) -> bytes:
        if image_format not in {"jpeg", "png", "webp"}:
            raise BrowserRuntimeError(
                "INVALID_REQUEST",
                "截图格式仅支持 jpeg、png 或 webp",
                operation="capture",
            )
        if not 1 <= quality <= 100:
            raise BrowserRuntimeError(
                "INVALID_REQUEST",
                "截图质量必须在 1 到 100 之间",
                operation="capture",
            )
        record = self._require_session(session_id, session_token)
        return await self._run(
            record,
            self._backend.capture,
            record.handle,
            image_format,
            quality,
        )

    async def execute_script(
        self,
        session_id: str,
        script: str,
        *args: Any,
        session_token: str,
    ) -> Any:
        if not str(script or "").strip():
            raise BrowserRuntimeError(
                "INVALID_REQUEST",
                "浏览器脚本不能为空",
                operation="execute_script",
            )
        record = self._require_session(session_id, session_token)
        return await self._run(
            record,
            self._backend.execute_script,
            record.handle,
            script,
            *args,
        )

    async def execute_cdp(
        self,
        session_id: str,
        command: str,
        params: dict[str, Any] | None = None,
        *,
        session_token: str,
    ) -> dict[str, Any]:
        normalized_command = str(command or "").strip()
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9.]{1,127}", normalized_command):
            raise BrowserRuntimeError(
                "INVALID_REQUEST",
                "CDP 命令名称无效",
                operation="execute_cdp",
            )
        record = self._require_session(session_id, session_token)
        return await self._run(
            record,
            self._backend.execute_cdp,
            record.handle,
            normalized_command,
            dict(params or {}),
        )

    async def automation_handoff(
        self,
        session_id: str,
        *,
        session_token: str,
    ) -> dict[str, Any]:
        record = self._require_session(session_id, session_token)
        async with record.operation_lock:
            if record.closing or record.closed or record.orphaned:
                raise BrowserRuntimeError(
                    "SESSION_UNAVAILABLE",
                    "浏览器会话当前不可接管",
                    operation="automation_handoff",
                    retryable=True,
                )
            if record.handoff_lease_token:
                raise BrowserRuntimeError(
                    "HANDOFF_BUSY",
                    "浏览器会话已被自动化引擎接管",
                    operation="automation_handoff",
                    retryable=True,
                )
            if record.options.automation_engine not in {"m7a", "sra"}:
                raise BrowserRuntimeError(
                    "HANDOFF_UNAVAILABLE",
                    "该会话未以外部自动化接管模式启动",
                    operation="automation_handoff",
                )
            address = record.handle.debugger_address.strip()
            if not address or ":" not in address:
                raise BrowserRuntimeError(
                    "HANDOFF_UNAVAILABLE",
                    "浏览器未提供可附着的调试地址",
                    operation="automation_handoff",
                    retryable=True,
                )
            host, raw_port = address.rsplit(":", 1)
            try:
                port = int(raw_port)
            except ValueError as exc:
                raise BrowserRuntimeError(
                    "HANDOFF_UNAVAILABLE",
                    "浏览器调试端口无效",
                    operation="automation_handoff",
                ) from exc
            lease_id = uuid.uuid4().hex
            lease_token = secrets.token_urlsafe(32)
            record.handoff_lease_id = lease_id
            record.handoff_lease_token = lease_token

        engine = record.options.automation_engine
        common_environment = {
            "AUTO_MAS_BROWSER_DEBUGGER_ADDRESS": address,
            "AUTO_MAS_BROWSER_PATH": record.handle.binaries.browser_path,
            "AUTO_MAS_BROWSER_DRIVER_PATH": record.handle.binaries.driver_path,
            "AUTO_MAS_BROWSER_RUNTIME_OWNS_BROWSER": "1",
            "AUTO_MAS_BROWSER_LEASE_ID": lease_id,
        }
        result: dict[str, Any] = {
            "engine": engine,
            "exclusive": True,
            "browser_may_exit_on_engine_error": True,
            "lease_id": lease_id,
            "lease_token": lease_token,
            "debugger_address": address,
            "debugger_host": host,
            "debugger_port": port,
            "browser_mode": record.handle.binaries.resolved_mode,
            "browser_version": record.handle.binaries.browser_version,
            "browser_path": record.handle.binaries.browser_path,
            "driver_path": record.handle.binaries.driver_path,
            "driver_pid": record.handle.driver_pid,
            "window_handle": record.last_status.get("window_handle"),
            "headless": record.options.headless,
            "viewport": {
                "width": record.options.window_width,
                "height": record.options.window_height,
                "device_scale_factor": 1,
            },
            "runtime_owns_browser": True,
            "environment": common_environment,
            "config_patch": {},
        }
        if engine == "m7a":
            result["config_patch"] = {
                "cloud_game_enable": True,
                "browser_type": (
                    "edge"
                    if record.handle.binaries.resolved_mode == "edge"
                    else "chrome"
                ),
                "browser_debug_port": port,
                "browser_headless_enable": record.options.headless,
                "browser_persistent_enable": True,
                "browser_dump_cookies_enable": False,
                "after_finish": None,
            }
            result.update(
                {
                    "compatibility": "requires-mas-external-owner-build",
                    "upstream_supported": False,
                    "required_changes": [
                        "attach the explicit debugger_address without process cleanup",
                        "do not kill chromedriver processes by the shared executable path",
                        "do not close or terminate a runtime-owned browser",
                        "do not dump browser cookies outside the MAS profile",
                    ],
                }
            )
        else:
            result.update(
                {
                    "compatibility": "requires-mas-external-session-build",
                    "upstream_supported": False,
                    "required_changes": [
                        "attach debugger_address instead of webdriver.Edge()",
                        "reuse one BrowserOperator across single tasks",
                        "do not read or write SRA cookie JSON",
                        "do not close a runtime-owned browser",
                    ],
                }
            )
        return result

    async def release_automation_handoff(
        self,
        session_id: str,
        *,
        session_token: str,
        lease_token: str,
    ) -> dict[str, Any]:
        record = self._require_session(session_id, session_token)
        async with record.operation_lock:
            candidate = str(lease_token or "")
            if not record.handoff_lease_token or not secrets.compare_digest(
                record.handoff_lease_token,
                candidate,
            ):
                raise BrowserRuntimeError(
                    "HANDOFF_FORBIDDEN",
                    "自动化接管租约无效",
                    operation="release_automation_handoff",
                )
            record.handoff_lease_id = ""
            record.handoff_lease_token = ""
            future = record.executor.submit(self._backend.status, record.handle)
            try:
                async with asyncio.timeout(self._operation_timeout_seconds):
                    record.last_status = await asyncio.shield(
                        asyncio.wrap_future(future)
                    )
            except TimeoutError as exc:
                error = BrowserRuntimeError(
                    "OPERATION_TIMEOUT",
                    "释放自动化接管后读取浏览器状态超时，Profile 已隔离",
                    operation="release_automation_handoff",
                    retryable=True,
                    safe_details={
                        "timeout_seconds": self._operation_timeout_seconds,
                        "surviving_processes": [],
                        "process_scan_complete": False,
                    },
                )
                self._mark_record_orphaned(record, error)
                raise error from exc
        return self._session_info(record)

    async def close_session(
        self,
        session_id: str,
        *,
        session_token: str,
    ) -> dict[str, Any]:
        normalized_id = str(session_id or "").strip()
        async with self._registry_lock:
            record = self._sessions.get(normalized_id)
        if record is None:
            return {"session_id": normalized_id, "closed": True, "already_closed": True}
        if not self._token_matches(record, session_token):
            raise BrowserRuntimeError(
                "SESSION_FORBIDDEN",
                "浏览器会话凭据无效",
                operation="close_session",
            )
        return await self._close_record(record)

    async def shutdown(self) -> list[dict[str, Any]]:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._shutdown_timeout_seconds
        current_task = asyncio.current_task()
        async with self._registry_lock:
            self._stopping = True
            opening = [
                task
                for task in self._opening_tasks
                if task is not current_task and not task.done()
            ]
        for task in opening:
            task.cancel()
        if opening:
            opening_wait = min(5.0, max(0.0, deadline - loop.time()) / 3.0)
            await asyncio.wait(opening, timeout=opening_wait)

        remaining = max(0.01, deadline - loop.time())
        results = await self._close_many(
            list(self._sessions.values()),
            timeout_seconds=remaining,
        )
        with self._prepare_attempts_lock:
            active_prepares = list(self._prepare_attempts.items())
        for attempt_root, future in active_prepares:
            if not future.done():
                self._abort_prepare(attempt_root)
                if future.done():
                    callback = getattr(self._backend, "mark_prepare_done", None)
                    if callable(callback):
                        callback(attempt_root)
        self._prepare_executor.shutdown(wait=False, cancel_futures=True)
        return results

    async def close_owner_sessions(self, owner_instance_id: str) -> list[dict[str, Any]]:
        owner = str(owner_instance_id or "").strip()
        records = [
            item
            for item in list(self._sessions.values())
            if item.options.owner_instance_id == owner
        ]
        return await self._close_many(records)

    async def close_all(self) -> list[dict[str, Any]]:
        return await self._close_many(list(self._sessions.values()))

    def list_sessions(self) -> list[dict[str, Any]]:
        """供 provider 内部诊断；不注册到未鉴权 HTTP 网关。"""
        return [self._session_info(item) for item in list(self._sessions.values())]

    def list_profiles(self) -> list[dict[str, Any]]:
        """供 provider 内部诊断；不注册到未鉴权 HTTP 网关。"""
        if not self._profiles_root.exists():
            return []

        active_keys = set(self._profile_sessions)
        result: list[dict[str, Any]] = []
        for manifest_path in self._profiles_root.rglob("profile.json"):
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(payload, dict):
                continue
            key = (
                str(payload.get("owner_instance_id") or ""),
                str(payload.get("namespace") or ""),
                str(payload.get("profile_id") or ""),
            )
            if not all(key):
                continue
            result.append(
                {
                    "owner_instance_id": key[0],
                    "namespace": key[1],
                    "profile_id": key[2],
                    "engine": str(payload.get("engine") or ""),
                    "created_at": str(payload.get("created_at") or ""),
                    "active": key in active_keys,
                }
            )
        return sorted(
            result,
            key=lambda item: (
                item["owner_instance_id"],
                item["namespace"],
                item["profile_id"],
            ),
        )

    async def _prepare_binaries(
        self,
        request: BrowserPrepareRequest,
    ) -> PreparedBinaries:
        async with self._prepare_lock:
            cache_key = (
                request.browser_mode or self._config.browser_mode,
                request.browser_version or self._config.managed_browser_version,
            )
            cached = self._prepared_binaries.get(cache_key)
            if cached is not None:
                return cached

            executor = self._prepare_executor
            attempt_root = self._assets_root / f"attempt-{uuid.uuid4().hex}"
            future = executor.submit(
                partial(
                    self._backend.prepare,
                    self._config,
                    request,
                    attempt_root,
                )
            )
            with self._prepare_attempts_lock:
                self._prepare_attempts[attempt_root] = future

            def mark_prepare_done(_completed: Future[Any]) -> None:
                callback = getattr(self._backend, "mark_prepare_done", None)
                if callable(callback):
                    callback(attempt_root)
                with self._prepare_attempts_lock:
                    if self._prepare_attempts.get(attempt_root) is _completed:
                        self._prepare_attempts.pop(attempt_root, None)

            future.add_done_callback(mark_prepare_done)
            try:
                async with asyncio.timeout(self._prepare_timeout_seconds):
                    prepared = await asyncio.shield(asyncio.wrap_future(future))
                self._prepared_binaries[cache_key] = prepared
                return prepared
            except TimeoutError as exc:
                self._abort_prepare(attempt_root)
                if future.done():
                    mark_prepare_done(future)
                self._replace_prepare_executor(executor)
                raise BrowserRuntimeError(
                    "PREPARE_TIMEOUT",
                    "浏览器或 WebDriver 准备超时",
                    operation="prepare",
                    retryable=True,
                    safe_details={
                        "timeout_seconds": self._prepare_timeout_seconds,
                    },
                ) from exc
            except asyncio.CancelledError:
                self._abort_prepare(attempt_root)
                if future.done():
                    mark_prepare_done(future)
                self._replace_prepare_executor(executor)
                raise

    def _abort_prepare(self, attempt_root: Path) -> None:
        callback = getattr(self._backend, "abort_prepare", None)
        if callable(callback):
            callback(attempt_root)

    async def _track_opening(self, task: asyncio.Task[Any] | None) -> None:
        async with self._registry_lock:
            self._ensure_running("open_session")
            if task is not None:
                self._opening_tasks.add(task)

    async def _untrack_opening(self, task: asyncio.Task[Any] | None) -> None:
        if task is None:
            return
        async with self._registry_lock:
            self._opening_tasks.discard(task)

    def _resolve_open_options(self, request: dict[str, Any]) -> BrowserOpenOptions:
        try:
            parsed = BrowserOpenRequest.model_validate(request)
            return BrowserOpenOptions(
                owner_instance_id=parsed.owner_instance_id,
                namespace=parsed.namespace,
                profile_id=parsed.profile_id or self._config.default_profile_id,
                initial_url=parsed.initial_url or self._config.home_url,
                browser_mode=parsed.browser_mode or self._config.browser_mode,
                browser_version=(
                    parsed.browser_version or self._config.managed_browser_version
                ),
                headless=(
                    self._config.headless if parsed.headless is None else parsed.headless
                ),
                app_mode=(
                    self._config.app_mode if parsed.app_mode is None else parsed.app_mode
                ),
                window_width=parsed.window_width or self._config.window_width,
                window_height=parsed.window_height or self._config.window_height,
                page_load_timeout_seconds=(
                    parsed.page_load_timeout_seconds
                    or self._config.page_load_timeout_seconds
                ),
                preferences=parsed.preferences,
                extra_arguments=parsed.extra_arguments,
                reuse_policy=parsed.reuse_policy,
                session_token=parsed.session_token,
                automation_engine=parsed.automation_engine,
            )
        except ValidationError as exc:
            raise BrowserRuntimeError(
                "INVALID_REQUEST",
                "浏览器会话参数无效",
                operation="open_session",
                safe_details={"error_count": exc.error_count()},
            ) from exc
        except ValueError as exc:
            raise BrowserRuntimeError(
                "INVALID_REQUEST",
                str(exc),
                operation="open_session",
            ) from exc

    def _ensure_profile(self, options: BrowserOpenOptions, engine: str) -> Path:
        profile_path = (
            self._profiles_root
            / _storage_segment(options.owner_instance_id)
            / _storage_segment(options.namespace)
            / _storage_segment(options.profile_id)
        )
        manifest_path = profile_path / "profile.json"
        expected = {
            "owner_instance_id": options.owner_instance_id,
            "namespace": options.namespace,
            "profile_id": options.profile_id,
            "engine": engine,
        }
        profile_path.mkdir(parents=True, exist_ok=True)
        self._assert_profile_not_quarantined(profile_path, options.profile_key)
        if manifest_path.exists():
            try:
                current = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise BrowserRuntimeError(
                    "PROFILE_CORRUPT",
                    "浏览器 Profile 元数据损坏",
                    operation="open_session",
                ) from exc
            identity_keys = ("owner_instance_id", "namespace", "profile_id")
            if not isinstance(current, dict) or any(
                current.get(key) != expected[key] for key in identity_keys
            ):
                raise BrowserRuntimeError(
                    "PROFILE_CORRUPT",
                    "浏览器 Profile 标识与存储目录不一致",
                    operation="open_session",
                )
            if current.get("engine") != engine:
                raise BrowserRuntimeError(
                    "PROFILE_ENGINE_MISMATCH",
                    "浏览器 Profile 与请求的 Chromium 引擎不一致",
                    operation="open_session",
                )
            return profile_path

        payload = {**expected, "created_at": _utc_now()}
        temp_path = manifest_path.with_suffix(".json.tmp")
        try:
            temp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temp_path.replace(manifest_path)
        except OSError as exc:
            raise BrowserRuntimeError(
                "PERSISTENCE_FAILED",
                "浏览器 Profile 元数据写入失败",
                operation="open_session",
                retryable=True,
            ) from exc
        return profile_path

    def _assert_profile_not_quarantined(
        self,
        profile_path: Path,
        profile_key: tuple[str, str, str],
    ) -> None:
        marker_path = profile_path / _QUARANTINE_FILE
        if not marker_path.exists():
            return
        try:
            payload = json.loads(marker_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}

        processes = payload.get("processes") if isinstance(payload, dict) else None
        process_list = processes if isinstance(processes, list) else []
        descriptors_gone = not any(
            self._process_descriptor_alive(item)
            for item in process_list
            if isinstance(item, dict)
        )
        can_auto_recover = bool(
            isinstance(payload, dict)
            and payload.get("can_auto_recover") is True
            and isinstance(processes, list)
        )
        session_id = str(payload.get("session_id") or "") if isinstance(payload, dict) else ""
        confirm_session_gone = getattr(self._backend, "confirm_session_gone", None)
        tag_confirmed_gone = bool(
            session_id
            and callable(confirm_session_gone)
            and confirm_session_gone(session_id)
        )
        if descriptors_gone and (can_auto_recover or tag_confirmed_gone):
            self._clear_profile_quarantine(profile_path)
            if not marker_path.exists():
                return

        raise BrowserRuntimeError(
            "PROFILE_QUARANTINED",
            "浏览器 Profile 因上次进程未确认退出而处于隔离状态",
            operation="open_session",
            retryable=True,
            safe_details={"profile_ref": _profile_log_id(profile_key)},
        )

    def _write_profile_quarantine(
        self,
        record: _SessionRecord,
        error: BrowserRuntimeError,
    ) -> None:
        self._write_profile_quarantine_payload(
            profile_path=record.profile_path,
            session_id=record.session_id,
            profile_key=record.options.profile_key,
            error=error,
            handle=record.handle,
        )

    def _write_profile_quarantine_payload(
        self,
        *,
        profile_path: Path,
        session_id: str,
        profile_key: tuple[str, str, str],
        error: BrowserRuntimeError,
        handle: BrowserDriverHandle | None = None,
    ) -> None:
        raw_processes = error.safe_details.get("surviving_processes")
        processes: list[dict[str, Any]] = []
        if isinstance(raw_processes, list):
            for item in raw_processes:
                if not isinstance(item, dict):
                    continue
                pid = item.get("pid")
                created_at = item.get("created_at")
                if not isinstance(pid, int) or pid <= 0:
                    continue
                processes.append(
                    {
                        "pid": pid,
                        "created_at": (
                            float(created_at)
                            if isinstance(created_at, (int, float))
                            else None
                        ),
                        "executable": str(item.get("executable") or ""),
                        "name": str(item.get("name") or "").casefold(),
                    }
                )
        if (
            handle is not None
            and handle.driver_pid is not None
            and handle.driver_create_time is not None
            and handle.driver_executable
            and handle.driver_name
            and not any(item["pid"] == handle.driver_pid for item in processes)
        ):
            processes.append(
                {
                    "pid": handle.driver_pid,
                    "created_at": handle.driver_create_time,
                    "executable": handle.driver_executable,
                    "name": handle.driver_name.casefold(),
                }
            )
        payload = {
            "session_id": session_id,
            "recorded_at": _utc_now(),
            "error_code": error.code,
            "can_auto_recover": bool(
                processes
                and error.safe_details.get("process_scan_complete") is True
            ),
            "processes": processes,
        }
        marker_path = profile_path / _QUARANTINE_FILE
        temp_path = marker_path.with_suffix(".json.tmp")
        try:
            temp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temp_path.replace(marker_path)
        except OSError:
            self._logger.exception(
                "[browser] 无法持久化 Profile 隔离标记: profile_ref={}".format(
                    _profile_log_id(profile_key)
                )
            )

    def _clear_profile_quarantine(self, profile_path: Path) -> None:
        marker_path = profile_path / _QUARANTINE_FILE
        try:
            marker_path.unlink(missing_ok=True)
        except OSError:
            self._logger.exception("[browser] 无法清除 Profile 隔离标记")

    @staticmethod
    def _process_descriptor_alive(payload: dict[str, Any]) -> bool:
        pid = payload.get("pid")
        if not isinstance(pid, int) or pid <= 0:
            return True
        try:
            process = psutil.Process(pid)
            expected_created_at = payload.get("created_at")
            if isinstance(expected_created_at, (int, float)):
                if abs(process.create_time() - float(expected_created_at)) >= 0.01:
                    return False
            else:
                return True
            expected_name = str(payload.get("name") or "").casefold()
            if expected_name and process.name().casefold() != expected_name:
                return False
            expected_executable = str(payload.get("executable") or "")
            if expected_executable:
                actual = str(process.exe() or "")
                if Path(actual).resolve() != Path(expected_executable).resolve():
                    return False
            return process.is_running()
        except psutil.NoSuchProcess:
            return False
        except (OSError, psutil.Error):
            return True

    async def _run(
        self,
        record: _SessionRecord,
        func: Any,
        *args: Any,
        allow_leased: bool = False,
    ) -> Any:
        async with record.operation_lock:
            if record.closed:
                raise BrowserRuntimeError(
                    "SESSION_CLOSED",
                    "浏览器会话已关闭",
                    operation=getattr(func, "__name__", "session_operation"),
                )
            if record.closing or record.orphaned:
                raise BrowserRuntimeError(
                    "SESSION_UNAVAILABLE",
                    "浏览器会话正在关闭或处于残留隔离状态",
                    operation=getattr(func, "__name__", "session_operation"),
                    retryable=True,
                )
            if record.handoff_lease_token and not allow_leased:
                raise BrowserRuntimeError(
                    "SESSION_LEASED",
                    "浏览器会话正由外部自动化引擎独占",
                    operation=getattr(func, "__name__", "session_operation"),
                    retryable=True,
                )
            future = record.executor.submit(func, *args)
            try:
                async with asyncio.timeout(self._operation_timeout_seconds):
                    return await asyncio.shield(asyncio.wrap_future(future))
            except TimeoutError as exc:
                error = BrowserRuntimeError(
                    "OPERATION_TIMEOUT",
                    "浏览器会话操作超时，Profile 已隔离",
                    operation=getattr(func, "__name__", "session_operation"),
                    retryable=True,
                    safe_details={
                        "timeout_seconds": self._operation_timeout_seconds,
                        "surviving_processes": [],
                        "process_scan_complete": False,
                    },
                )
                self._mark_record_orphaned(record, error)
                raise error from exc

    async def _close_record(self, record: _SessionRecord) -> dict[str, Any]:
        try:
            async with asyncio.timeout(self._close_timeout_seconds):
                error: BrowserRuntimeError | None = None
                async with record.operation_lock:
                    if record.closed:
                        return {
                            "session_id": record.session_id,
                            "closed": True,
                            "already_closed": True,
                        }
                    record.closing = True
                    future = record.executor.submit(
                        self._backend.close,
                        record.handle,
                    )
                    try:
                        await asyncio.shield(asyncio.wrap_future(future))
                    except BrowserRuntimeError as exc:
                        error = exc
                    except Exception as exc:
                        error = self._close_error(exc)

                    if error is not None:
                        record.closing = False
                        record.orphaned = True
                        self._write_profile_quarantine(record, error)
                    else:
                        record.closing = False
                        record.closed = True
                        self._clear_profile_quarantine(record.profile_path)
        except TimeoutError as exc:
            error = BrowserRuntimeError(
                "CLOSE_TIMEOUT",
                "浏览器会话关闭超时，Profile 已隔离",
                operation="close_session",
                retryable=True,
                safe_details={
                    "timeout_seconds": self._close_timeout_seconds,
                    "surviving_processes": [],
                    "process_scan_complete": False,
                },
            )
            self._mark_record_orphaned(record, error)
            raise error from exc
        except asyncio.CancelledError:
            error = BrowserRuntimeError(
                "CLOSE_CANCELLED",
                "浏览器会话关闭被取消，Profile 已隔离",
                operation="close_session",
                retryable=True,
                safe_details={
                    "surviving_processes": [],
                    "process_scan_complete": False,
                },
            )
            self._mark_record_orphaned(record, error)
            raise

        if error is not None:
            raise error

        async with self._registry_lock:
            self._sessions.pop(record.session_id, None)
            current = self._profile_sessions.get(record.options.profile_key)
            if current == record.session_id:
                self._profile_sessions.pop(record.options.profile_key, None)
        record.executor.shutdown(wait=False, cancel_futures=True)

        profile_ref = _profile_log_id(record.options.profile_key)
        self._logger.info(
            "[browser] 会话已关闭: session={}, owner={}, namespace={}, profile_ref={}".format(
                record.session_id,
                record.options.owner_instance_id,
                record.options.namespace,
                profile_ref,
            )
        )
        return {
            "session_id": record.session_id,
            "closed": True,
            "already_closed": False,
        }

    async def _retain_failed_open(
        self,
        *,
        session_id: str,
        session_token: str,
        options: BrowserOpenOptions,
        profile_path: Path,
        handle: BrowserDriverHandle,
        executor: _DaemonExecutor,
        error: BrowserRuntimeError,
    ) -> _SessionRecord | None:
        record = _SessionRecord(
            session_id=session_id,
            session_token=session_token,
            options=options,
            profile_path=profile_path,
            handle=handle,
            executor=executor,
            started_at=_utc_now(),
            last_status={
                "alive": True,
                "url": "",
                "title": "",
                "driver_pid": handle.driver_pid,
                "window_handle": None,
            },
            orphaned=True,
        )
        self._write_profile_quarantine(record, error)
        async with self._registry_lock:
            if self._profile_sessions.get(options.profile_key) != session_id:
                return None
            self._sessions[session_id] = record
        return record

    async def _release_failed_open(
        self,
        profile_key: tuple[str, str, str],
        session_id: str,
    ) -> None:
        async with self._registry_lock:
            if self._profile_sessions.get(profile_key) == session_id:
                self._profile_sessions.pop(profile_key, None)

    def _attach_late_open_cleanup(
        self,
        *,
        future: Future[Any],
        profile_path: Path,
        session_id: str,
        session_token: str,
        options: BrowserOpenOptions,
        profile_key: tuple[str, str, str],
        executor: _DaemonExecutor,
    ) -> None:
        """启动调用迟到时回收其进程；确认无残留后解除 Profile 隔离。"""
        loop = asyncio.get_running_loop()

        def finalize(completed: Future[Any]) -> None:
            handle: BrowserDriverHandle | None = None
            try:
                result = completed.result()
                if isinstance(result, BrowserDriverHandle):
                    handle = result
                    self._backend.close(result)
                else:
                    self._backend.cleanup_session(session_id)
            except BaseException as exc:
                try:
                    self._backend.cleanup_session(session_id)
                except BaseException as cleanup_exc:
                    exc = cleanup_exc
                else:
                    self._clear_profile_quarantine(profile_path)
                    self._schedule_late_open_release(
                        loop=loop,
                        profile_key=profile_key,
                        session_id=session_id,
                        executor=executor,
                    )
                    self._logger.info(
                        "[browser] 迟到启动异常已确认无残留并解除 Profile 隔离: "
                        f"session={session_id}"
                    )
                    return
                error = (
                    exc
                    if isinstance(exc, BrowserRuntimeError)
                    else self._close_error(exc)
                )
                self._write_profile_quarantine_payload(
                    profile_path=profile_path,
                    session_id=session_id,
                    profile_key=profile_key,
                    error=error,
                )
                if handle is not None:
                    self._schedule_late_open_retention(
                        loop=loop,
                        session_id=session_id,
                        session_token=session_token,
                        options=options,
                        profile_path=profile_path,
                        handle=handle,
                        executor=executor,
                    )
                else:
                    self._schedule_late_open_release(
                        loop=loop,
                        profile_key=profile_key,
                        session_id=session_id,
                        executor=executor,
                    )
                self._logger.warning(
                    f"[browser] 迟到启动回收失败，Profile 保持隔离: session={session_id}"
                )
                return

            self._clear_profile_quarantine(profile_path)
            self._schedule_late_open_release(
                loop=loop,
                profile_key=profile_key,
                session_id=session_id,
                executor=executor,
            )
            self._logger.info(
                f"[browser] 迟到启动已回收并解除 Profile 隔离: session={session_id}"
            )

        def schedule(completed: Future[Any]) -> None:
            cleanup_executor = _DaemonExecutor(
                f"browser-late-cleanup-{session_id[:8]}"
            )
            cleanup_future = cleanup_executor.submit(finalize, completed)

            def finish_cleanup(task: Future[Any]) -> None:
                try:
                    task.result()
                except BaseException as exc:
                    self._logger.warning(
                        "[browser] 迟到启动回收任务异常: "
                        f"session={session_id}, error={type(exc).__name__}"
                    )
                finally:
                    cleanup_executor.shutdown(
                        wait=False,
                        cancel_futures=True,
                    )

            cleanup_future.add_done_callback(finish_cleanup)

        future.add_done_callback(schedule)

    def _schedule_late_open_retention(
        self,
        *,
        loop: asyncio.AbstractEventLoop,
        session_id: str,
        session_token: str,
        options: BrowserOpenOptions,
        profile_path: Path,
        handle: BrowserDriverHandle,
        executor: _DaemonExecutor,
    ) -> None:
        def schedule() -> None:
            task = asyncio.create_task(
                self._retain_late_open(
                    session_id=session_id,
                    session_token=session_token,
                    options=options,
                    profile_path=profile_path,
                    handle=handle,
                    executor=executor,
                )
            )
            task.add_done_callback(self._consume_async_result)

        try:
            loop.call_soon_threadsafe(schedule)
        except RuntimeError:
            executor.shutdown(wait=False, cancel_futures=True)

    async def _retain_late_open(
        self,
        *,
        session_id: str,
        session_token: str,
        options: BrowserOpenOptions,
        profile_path: Path,
        handle: BrowserDriverHandle,
        executor: _DaemonExecutor,
    ) -> None:
        record = _SessionRecord(
            session_id=session_id,
            session_token=session_token,
            options=options,
            profile_path=profile_path,
            handle=handle,
            executor=executor,
            started_at=_utc_now(),
            last_status={
                "alive": True,
                "url": "",
                "title": "",
                "driver_pid": handle.driver_pid,
                "window_handle": None,
            },
            orphaned=True,
        )
        async with self._registry_lock:
            current = self._profile_sessions.get(options.profile_key)
            if current not in {None, session_id}:
                executor.shutdown(wait=False, cancel_futures=True)
                return
            self._profile_sessions[options.profile_key] = session_id
            self._sessions[session_id] = record

    def _schedule_late_open_release(
        self,
        *,
        loop: asyncio.AbstractEventLoop,
        profile_key: tuple[str, str, str],
        session_id: str,
        executor: _DaemonExecutor,
    ) -> None:
        def schedule() -> None:
            task = asyncio.create_task(
                self._release_late_open(
                    profile_key=profile_key,
                    session_id=session_id,
                    executor=executor,
                )
            )
            task.add_done_callback(self._consume_async_result)

        try:
            loop.call_soon_threadsafe(schedule)
        except RuntimeError:
            executor.shutdown(wait=False, cancel_futures=True)

    async def _release_late_open(
        self,
        *,
        profile_key: tuple[str, str, str],
        session_id: str,
        executor: _DaemonExecutor,
    ) -> None:
        await self._release_failed_open(profile_key, session_id)
        executor.shutdown(wait=False, cancel_futures=True)

    def _mark_record_orphaned(
        self,
        record: _SessionRecord,
        error: BrowserRuntimeError,
    ) -> None:
        if record.closed:
            return
        should_cleanup = not record.orphaned
        record.closing = False
        record.orphaned = True
        self._write_profile_quarantine(record, error)
        if should_cleanup:
            self._start_process_cleanup(
                record.session_id,
                record=record,
                profile_path=record.profile_path,
                profile_key=record.options.profile_key,
            )

    def _start_process_cleanup(
        self,
        session_id: str,
        *,
        record: _SessionRecord | None = None,
        profile_path: Path | None = None,
        profile_key: tuple[str, str, str] | None = None,
    ) -> None:
        with self._cleanup_guard:
            if session_id in self._cleanup_inflight:
                return
            self._cleanup_inflight.add(session_id)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        executor = _DaemonExecutor(f"browser-cleanup-{session_id[:8]}")

        def cleanup_until_safe() -> None:
            attempts = 0
            while True:
                try:
                    self._backend.cleanup_session(session_id)
                    return
                except Exception as exc:
                    attempts += 1
                    if attempts == 1 or attempts % 20 == 0:
                        self._logger.warning(
                            "[browser] 后台进程回收仍在重试: "
                            f"session={session_id}, error={type(exc).__name__}"
                        )
                    time.sleep(min(1.0, 0.1 * attempts))

        future = executor.submit(cleanup_until_safe)

        def finish(completed: Future[Any]) -> None:
            try:
                completed.result()
            except BaseException as exc:
                self._logger.warning(
                    "[browser] 超时后的进程回收未能确认完成: "
                    f"session={session_id}, error={type(exc).__name__}"
                )
            else:
                if loop is None and profile_path is not None:
                    self._clear_profile_quarantine(profile_path)
                if loop is not None:
                    try:
                        loop.call_soon_threadsafe(
                            self._schedule_background_cleanup_success,
                            session_id,
                            profile_path,
                            profile_key,
                            record,
                        )
                    except RuntimeError:
                        if profile_path is not None:
                            self._clear_profile_quarantine(profile_path)
            finally:
                with self._cleanup_guard:
                    self._cleanup_inflight.discard(session_id)
                executor.shutdown(wait=False, cancel_futures=True)

        future.add_done_callback(finish)

    def _schedule_background_cleanup_success(
        self,
        session_id: str,
        profile_path: Path | None,
        profile_key: tuple[str, str, str] | None,
        record: _SessionRecord | None,
    ) -> None:
        task = asyncio.create_task(
            self._finalize_background_cleanup(
                session_id=session_id,
                profile_path=profile_path,
                profile_key=profile_key,
                record=record,
            )
        )
        task.add_done_callback(self._consume_async_result)

    async def _finalize_background_cleanup(
        self,
        *,
        session_id: str,
        profile_path: Path | None,
        profile_key: tuple[str, str, str] | None,
        record: _SessionRecord | None,
    ) -> None:
        executor_to_stop: _DaemonExecutor | None = None
        async with self._registry_lock:
            current_record = self._sessions.get(session_id)
            if current_record is not None:
                record = current_record
            if record is not None:
                record.closing = False
                record.orphaned = False
                record.closed = True
                executor_to_stop = record.executor
                if self._sessions.get(session_id) is record:
                    self._sessions.pop(session_id, None)
                if profile_key is None:
                    profile_key = record.options.profile_key
                if profile_path is None:
                    profile_path = record.profile_path
            if profile_key is not None:
                if self._profile_sessions.get(profile_key) == session_id:
                    self._profile_sessions.pop(profile_key, None)

        if profile_path is not None:
            self._clear_profile_quarantine(profile_path)
        if executor_to_stop is not None:
            executor_to_stop.shutdown(wait=False, cancel_futures=True)
        self._logger.info(
            f"[browser] 后台进程回收完成并解除 Profile 隔离: session={session_id}"
        )

    def _replace_prepare_executor(self, executor: _DaemonExecutor) -> None:
        if self._prepare_executor is executor:
            self._prepare_executor = _DaemonExecutor("browser-prepare")
        executor.shutdown(wait=False, cancel_futures=True)

    @staticmethod
    def _consume_async_result(task: asyncio.Task[Any]) -> None:
        try:
            task.exception()
        except BaseException:
            pass

    @staticmethod
    def _normalize_timeout(value: float | None, *, default: float) -> float:
        timeout = default if value is None else float(value)
        if not math.isfinite(timeout) or timeout <= 0:
            timeout = default
        return max(0.01, timeout)

    async def _close_many(
        self,
        records: list[_SessionRecord],
        *,
        timeout_seconds: float | None = None,
    ) -> list[dict[str, Any]]:
        if not records:
            return []

        tasks = {
            asyncio.create_task(
                self.close_session(
                    record.session_id,
                    session_token=record.session_token,
                )
            ): record
            for record in records
        }
        timeout = self._normalize_timeout(
            timeout_seconds,
            default=self._close_timeout_seconds + 1.0,
        )
        done, pending = await asyncio.wait(tasks, timeout=timeout)
        results: dict[str, dict[str, Any]] = {}

        for task in done:
            record = tasks[task]
            try:
                results[record.session_id] = task.result()
            except BrowserRuntimeError as exc:
                results[record.session_id] = {
                    "session_id": record.session_id,
                    "closed": False,
                    "error": exc.to_dict(),
                }
            except BaseException as exc:
                error = self._close_error(exc)
                self._mark_record_orphaned(record, error)
                results[record.session_id] = {
                    "session_id": record.session_id,
                    "closed": False,
                    "error": error.to_dict(),
                }

        for task in pending:
            record = tasks[task]
            task.cancel()
            task.add_done_callback(self._consume_async_result)
            error = BrowserRuntimeError(
                "SHUTDOWN_TIMEOUT",
                "浏览器运行时停止期限已到，Profile 已隔离",
                operation="shutdown",
                retryable=True,
                safe_details={
                    "timeout_seconds": timeout,
                    "surviving_processes": [],
                    "process_scan_complete": False,
                },
            )
            self._mark_record_orphaned(record, error)
            results[record.session_id] = {
                "session_id": record.session_id,
                "closed": False,
                "error": error.to_dict(),
            }

        return [results[record.session_id] for record in records]

    def _require_session(
        self,
        session_id: str,
        session_token: str,
    ) -> _SessionRecord:
        normalized_id = str(session_id or "").strip()
        record = self._sessions.get(normalized_id)
        if record is None or record.closed:
            raise BrowserRuntimeError(
                "SESSION_CLOSED",
                "浏览器会话不存在或已关闭",
                operation="session_operation",
                safe_details={"session_id": normalized_id},
            )
        if not self._token_matches(record, session_token):
            raise BrowserRuntimeError(
                "SESSION_FORBIDDEN",
                "浏览器会话凭据无效",
                operation="session_operation",
            )
        return record

    def _ensure_running(self, operation: str) -> None:
        if self._stopping:
            raise BrowserRuntimeError(
                "RUNTIME_STOPPING",
                "浏览器运行时正在停止",
                operation=operation,
                retryable=True,
            )

    @staticmethod
    def _token_matches(record: _SessionRecord, token: str | None) -> bool:
        candidate = str(token or "")
        return bool(candidate) and secrets.compare_digest(record.session_token, candidate)

    @staticmethod
    def _close_error(exc: BaseException) -> BrowserRuntimeError:
        return BrowserRuntimeError(
            "CLOSE_FAILED",
            "浏览器会话关闭失败",
            operation="close_session",
            retryable=True,
            safe_details={"error_type": type(exc).__name__},
        )

    @staticmethod
    def _session_info(
        record: _SessionRecord,
        *,
        reused: bool = False,
        include_token: bool = False,
    ) -> dict[str, Any]:
        status = record.last_status
        if record.orphaned:
            state = "orphaned"
        elif record.closing:
            state = "closing"
        elif record.handoff_lease_token:
            state = "leased"
        elif status.get("alive") and not record.closed:
            state = "running"
        else:
            state = "closed"
        result = {
            "session_id": record.session_id,
            "state": state,
            "owner_instance_id": record.options.owner_instance_id,
            "namespace": record.options.namespace,
            "profile_id": record.options.profile_id,
            "browser_mode": record.handle.binaries.resolved_mode,
            "headless": record.options.headless,
            "automation_engine": record.options.automation_engine,
            "automation_state": (
                "leased" if record.handoff_lease_token else "idle"
            ),
            "url": str(status.get("url") or ""),
            "title": str(status.get("title") or ""),
            "driver_pid": status.get("driver_pid"),
            "window_handle": status.get("window_handle"),
            "started_at": record.started_at,
            "reused": reused,
        }
        if include_token:
            result["session_token"] = record.session_token
        return result
