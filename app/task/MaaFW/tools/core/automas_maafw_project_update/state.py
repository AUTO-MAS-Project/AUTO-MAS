"""Durable operation state and process-safe locks for MaaFW updates."""

from __future__ import annotations

import json
import hashlib
import os
import re
import socket
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:  # Windows uses byte-range locks; POSIX uses the equivalent lockf API.
    import msvcrt  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - exercised on POSIX CI only
    msvcrt = None

try:
    import fcntl  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - exercised on Windows CI only
    fcntl = None

from urllib.parse import urlsplit


DEFAULT_OPERATION_ROOT = Path.cwd() / "data" / "maafw_update_operations"
DEFAULT_CACHE_ROOT = Path.cwd() / "data" / "maafw_update_cache"
DEFAULT_PROJECT_LOCK_ROOT = Path.cwd() / "data" / "maafw_project_locks"
DEFAULT_PLAN_ROOT = Path.cwd() / "data" / "maafw_update_plans"
LOCK_STALE_SECONDS = 30 * 60
_SAFE_ID_RE = re.compile(r"^[0-9a-fA-F]{24,128}$")
_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_LOCAL_LOCK_GUARD = threading.RLock()
_LOCAL_LOCKS: dict[str, dict[str, Any]] = {}


def _safe_id(raw: str, *, label: str, minimum_hex: int = 32) -> str:
    """Return a path-safe UUID/hex identifier, rejecting traversal IDs."""

    value = str(raw or "").strip()
    if not value:
        raise ValueError(f"{label} is required")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError):
        parsed = None
    if parsed is not None and value.lower() in {
        parsed.hex,
        str(parsed).lower(),
    }:
        return parsed.hex
    if len(value) >= minimum_hex and _SAFE_ID_RE.fullmatch(value):
        return value.lower()
    raise ValueError(f"{label} must be a UUID or hexadecimal identifier")


def redact_url(raw_url: str) -> str:
    """Persist only URL origin/path; query strings may contain CDKs/tokens."""

    value = str(raw_url or "").strip()
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "<redacted-url>"
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return "<redacted-url>"
    host = parsed.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme.lower()}://{host}{port}{parsed.path or '/'}"


def redact_text(value: Any) -> str:
    text = str(value or "")
    return _URL_RE.sub(lambda match: redact_url(match.group(0)), text)


def _redact_payload(value: Any, key: str = "") -> Any:
    lowered = key.casefold()
    if lowered in {"url", "downloadurl", "finalurl", "sourceurl"}:
        return redact_url(str(value))
    if lowered in {"error", "lasterror", "rollbackerror"}:
        return redact_text(value)
    if isinstance(value, dict):
        return {str(k): _redact_payload(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_payload(item, key) for item in value]
    return value


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


@dataclass
class DurableFileLock:
    """Cross-process one-byte advisory lock with durable owner metadata.

    The lock file is intentionally never deleted and ownership is provided by
    the OS byte-range lock.  That means a crashed downloader releases the
    lock automatically; wall-clock stale-file deletion is unsafe for a valid
    long-running download and is therefore not used.
    """

    path: Path
    timeout: float | None = None
    # Kept as a compatibility argument for old direct callers.  It is not
    # consulted: advisory locks are released by process close, not a timer.
    stale_after: float = LOCK_STALE_SECONDS
    token: str = ""
    acquired: bool = False
    _handle: Any = None
    allow_foreign_same_pid_reentry: bool = False
    _local_key: str = ""
    _local_reentrant: bool = False
    _object_count: int = 0

    def acquire(self) -> "DurableFileLock":
        self.path = self.path.expanduser().resolve(strict=False)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local_key = (
            str(self.path).casefold() if os.name == "nt" else str(self.path)
        )
        if self.acquired:
            with _LOCAL_LOCK_GUARD:
                local = _LOCAL_LOCKS.get(self._local_key)
                if (
                    local is not None
                    and local.get("ownerThread") == threading.get_ident()
                ):
                    local["count"] = int(local.get("count") or 0) + 1
                    self._object_count += 1
                    self.token = str(local.get("token") or self.token)
                    self._local_reentrant = True
                    return self
            raise RuntimeError("update lock object is already owned by another thread")
        self.token = uuid.uuid4().hex
        deadline = (
            None if self.timeout is None else time.monotonic() + max(0.0, self.timeout)
        )
        owner = {
            "token": self.token,
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "thread": threading.get_ident(),
            "createdAt": time.time(),
        }
        while True:
            local_busy = False
            with _LOCAL_LOCK_GUARD:
                local = _LOCAL_LOCKS.get(self._local_key)
                if local is not None:
                    if local.get("ownerThread") == threading.get_ident():
                        local["count"] = int(local.get("count") or 0) + 1
                        self.token = str(local.get("token") or "")
                        self.acquired = True
                        self._object_count = 1
                        self._local_reentrant = True
                        return self
                    # Advisory locks such as POSIX lockf are process-wide;
                    # enforce thread exclusion explicitly before trying OS
                    # acquisition so unrelated worker threads cannot pass.
                    local_busy = True
            if local_busy:
                if deadline is not None and time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"update lock busy: {self.path} (local owner thread)"
                    )
                time.sleep(0.05)
                continue
            handle = None
            try:
                handle = self.path.open("a+b")
                # Windows msvcrt.locking requires a byte to exist at the
                # locked offset.  POSIX lockf uses the same byte region.
                if self.path.stat().st_size == 0:
                    handle.write(b"\0")
                    handle.flush()
                    os.fsync(handle.fileno())
                handle.seek(0)
                self._try_acquire_os_lock(handle)
                handle.seek(0)
                handle.truncate()
                handle.write(json.dumps(owner, sort_keys=True).encode("utf-8"))
                handle.flush()
                os.fsync(handle.fileno())
                self._handle = handle
                with _LOCAL_LOCK_GUARD:
                    _LOCAL_LOCKS[self._local_key] = {
                        "token": self.token,
                        "handle": handle,
                        "count": 1,
                        "ownerThread": threading.get_ident(),
                    }
                self.acquired = True
                self._object_count = 1
                return self
            except (BlockingIOError, PermissionError, OSError) as exc:
                if handle is not None:
                    try:
                        handle.close()
                    except OSError:
                        pass
                # msvcrt raises OSError(EACCES/EDEADLK) for a busy range;
                # unrelated errors (bad path, disk full) must not spin.
                if not self._is_lock_busy(exc):
                    raise
                # The host reservation and updater service may run in the
                # same process.  Treat an owner record from this PID as a
                # re-entry; do not close the owner's handle from this guard.
                owner_record = self._owner_record()
                if self.allow_foreign_same_pid_reentry and (
                    owner_record.get("pid") == os.getpid()
                    and str(owner_record.get("host") or "") == socket.gethostname()
                ):
                    self.token = str(owner_record.get("token") or "")
                    self.acquired = True
                    return self
                if deadline is not None and time.monotonic() >= deadline:
                    details = self._owner_details()
                    raise TimeoutError(f"update lock busy: {self.path} ({details})")
                time.sleep(0.05)

    def release(self) -> None:
        if not self.acquired:
            return
        handle = self._handle
        orphan_handle = None
        with _LOCAL_LOCK_GUARD:
            local = _LOCAL_LOCKS.get(self._local_key)
            if local is not None and (
                local.get("ownerThread") == threading.get_ident()
                or local.get("handle") is handle
            ):
                local["count"] = max(0, int(local.get("count") or 0) - 1)
                self._object_count = max(0, self._object_count - 1)
                if self._object_count:
                    self._local_reentrant = self._object_count > 1
                    return
                self._local_reentrant = False
                self.acquired = False
                self._handle = None
                if not local["count"]:
                    orphan_handle = local.get("handle")
                    _LOCAL_LOCKS.pop(self._local_key, None)
                else:
                    # Another lock object in this thread still owns the OS
                    # handle; it will release it when its own count reaches 0.
                    return
        if orphan_handle is not None:
            try:
                self._release_os_lock(orphan_handle)
            finally:
                orphan_handle.close()
            return
        self._handle = None
        self.acquired = False
        if handle is None:
            return
        try:
            self._release_os_lock(handle)
        finally:
            handle.close()

    def __enter__(self) -> "DurableFileLock":
        return self.acquire()

    def __exit__(self, _type: Any, _value: Any, _traceback: Any) -> None:
        self.release()

    def _try_acquire_os_lock(self, handle: Any) -> None:
        if os.name == "nt":
            if msvcrt is None:  # pragma: no cover - defensive
                raise RuntimeError("Windows lock provider is unavailable")
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return
        if fcntl is None:  # pragma: no cover - defensive
            raise RuntimeError("POSIX lock provider is unavailable")
        fcntl.lockf(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB, 1, 0, os.SEEK_SET)

    def _release_os_lock(self, handle: Any) -> None:
        try:
            if os.name == "nt":
                if msvcrt is not None:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            elif fcntl is not None:
                fcntl.lockf(handle.fileno(), fcntl.LOCK_UN, 1, 0, os.SEEK_SET)
        except OSError:
            # Closing the descriptor still releases an advisory lock after a
            # partial shutdown; release remains best effort.
            pass

    @staticmethod
    def _is_lock_busy(exc: OSError) -> bool:
        if isinstance(exc, BlockingIOError):
            return True
        return getattr(exc, "errno", None) in {11, 13, 16, 35, 36, 11}

    def _owner_details(self) -> str:
        value = self._owner_record()
        if not value:
            return "unknown owner"
        return f"pid={value.get('pid')}, host={value.get('host')}"

    def _owner_record(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return value if isinstance(value, dict) else {}


@dataclass
class UpdateOperationStore:
    operation_id: str
    root: Path = DEFAULT_OPERATION_ROOT

    def __post_init__(self) -> None:
        self.operation_id = _safe_id(self.operation_id, label="operation id")
        self.root = self.root.expanduser().resolve(strict=False)

    @property
    def directory(self) -> Path:
        directory = (self.root / self.operation_id).resolve(strict=False)
        if not directory.is_relative_to(self.root):
            raise ValueError("operation directory escapes operation root")
        return directory

    @property
    def state_path(self) -> Path:
        return self.directory / "state.json"

    @property
    def journal_path(self) -> Path:
        return self.directory / "journal.jsonl"

    @classmethod
    def create(
        cls,
        *,
        root: Path | None = None,
        operation_id: str | None = None,
        **initial: Any,
    ) -> "UpdateOperationStore":
        value = _safe_id(
            str(operation_id or uuid.uuid4().hex),
            label="operation id",
        )
        store = cls(value, root or DEFAULT_OPERATION_ROOT)
        state = {
            "schemaVersion": 1,
            "operationId": value,
            "createdAt": time.time(),
            "updatedAt": time.time(),
            "status": "discovered",
            **initial,
        }
        state = _redact_payload(state)
        store.directory.mkdir(parents=True, exist_ok=True)
        with operation_lock(store.root, store.operation_id, timeout=None):
            if store.state_path.exists():
                raise FileExistsError(f"update operation already exists: {value}")
            _atomic_json_write(store.state_path, state)
            store._append_unlocked("discovered", state)
        return store

    @classmethod
    def open(
        cls, operation_id: str, *, root: Path | None = None
    ) -> "UpdateOperationStore":
        store = cls(
            _safe_id(str(operation_id).strip(), label="operation id"),
            root or DEFAULT_OPERATION_ROOT,
        )
        if not store.state_path.is_file():
            raise FileNotFoundError(f"update operation does not exist: {operation_id}")
        return store

    def read(self) -> dict[str, Any]:
        state = self._read_state()
        self._validate_journal()
        return state

    def _read_state(self) -> dict[str, Any]:
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"update operation state is unreadable: {self.operation_id}"
            ) from exc
        if not isinstance(value, dict) or value.get("operationId") != self.operation_id:
            raise RuntimeError(
                f"update operation state is invalid: {self.operation_id}"
            )
        return value

    def _validate_journal(self) -> None:
        if not self.journal_path.is_file():
            return
        try:
            lines = self.journal_path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as exc:
            raise RuntimeError(
                f"update operation journal is unreadable: {self.operation_id}"
            ) from exc
        for line in lines:
            try:
                record = json.loads(line)
            except (TypeError, ValueError) as exc:
                raise RuntimeError(
                    f"update operation journal is corrupt: {self.operation_id}"
                ) from exc
            if (
                not isinstance(record, dict)
                or record.get("operationId") != self.operation_id
            ):
                raise RuntimeError(
                    f"update operation journal is invalid: {self.operation_id}"
                )

    def update(self, status: str | None = None, **fields: Any) -> dict[str, Any]:
        with operation_lock(self.root, self.operation_id, timeout=None):
            state = self._read_state()
            self._validate_journal()
            if status:
                state["status"] = status
            state.update(_redact_payload(fields))
            state["updatedAt"] = time.time()
            state = _redact_payload(state)
            _atomic_json_write(self.state_path, state)
            self._append_unlocked(str(state.get("status") or "updated"), state)
            return state

    def append(self, event: str, payload: dict[str, Any] | None = None) -> None:
        with operation_lock(self.root, self.operation_id, timeout=None):
            self._append_unlocked(event, payload)

    def _append_unlocked(
        self, event: str, payload: dict[str, Any] | None = None
    ) -> None:
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "at": time.time(),
            "event": str(event),
            "operationId": self.operation_id,
            "payload": _redact_payload(payload or {}),
        }
        with self.journal_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def request(
        self, *, pause: bool | None = None, cancel: bool | None = None
    ) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        if pause is not None:
            fields["pauseRequested"] = bool(pause)
        if cancel is not None:
            fields["cancelRequested"] = bool(cancel)
        return self.update(**fields)

    def mark_recovery_required(self, error: str) -> dict[str, Any]:
        """Persist a fail-closed state even when the journal is corrupt."""

        with operation_lock(self.root, self.operation_id, timeout=None):
            state = self._read_state()
            state.update(
                {
                    "status": "recovery_required",
                    "recoveryRequired": True,
                    "error": redact_text(error)[:500],
                    "updatedAt": time.time(),
                }
            )
            _atomic_json_write(self.state_path, state)
            # Do not append to a corrupt journal.  The state file itself is
            # the authoritative fail-closed marker until manual repair.
            return state


@dataclass
class UpdatePlanStore:
    """Durable, URL-free update plan used between discovery and execution."""

    plan_id: str
    root: Path = DEFAULT_PLAN_ROOT

    def __post_init__(self) -> None:
        self.plan_id = _safe_id(self.plan_id, label="plan id")
        self.root = self.root.expanduser().resolve(strict=False)

    @property
    def directory(self) -> Path:
        directory = (self.root / self.plan_id).resolve(strict=False)
        if not directory.is_relative_to(self.root):
            raise ValueError("plan directory escapes plan root")
        return directory

    @property
    def state_path(self) -> Path:
        return self.directory / "plan.json"

    @classmethod
    def create(
        cls,
        *,
        root: Path | None = None,
        plan_id: str | None = None,
        **initial: Any,
    ) -> "UpdatePlanStore":
        value = _safe_id(str(plan_id or uuid.uuid4().hex), label="plan id")
        store = cls(value, root or DEFAULT_PLAN_ROOT)
        state = _redact_payload(
            {
                "schemaVersion": 1,
                "planId": value,
                "createdAt": time.time(),
                "updatedAt": time.time(),
                "status": "planned",
                **initial,
            }
        )
        store.directory.mkdir(parents=True, exist_ok=True)
        with plan_lock(store.root, store.plan_id, timeout=None):
            if store.state_path.exists():
                raise FileExistsError(f"update plan already exists: {value}")
            _atomic_json_write(store.state_path, state)
        return store

    @classmethod
    def open(cls, plan_id: str, *, root: Path | None = None) -> "UpdatePlanStore":
        store = cls(_safe_id(plan_id, label="plan id"), root or DEFAULT_PLAN_ROOT)
        if not store.state_path.is_file():
            raise FileNotFoundError(f"update plan does not exist: {plan_id}")
        return store

    def read(self) -> dict[str, Any]:
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"update plan state is unreadable: {self.plan_id}"
            ) from exc
        if not isinstance(value, dict) or value.get("planId") != self.plan_id:
            raise RuntimeError(f"update plan state is invalid: {self.plan_id}")
        return value

    def update(self, status: str | None = None, **fields: Any) -> dict[str, Any]:
        with plan_lock(self.root, self.plan_id, timeout=None):
            state = self.read()
            if status:
                state["status"] = status
            state.update(_redact_payload(fields))
            state["updatedAt"] = time.time()
            state = _redact_payload(state)
            _atomic_json_write(self.state_path, state)
            return state


def operation_lock(
    root: Path, operation_id: str, *, timeout: float | None = None
) -> DurableFileLock:
    safe_operation_id = _safe_id(operation_id, label="operation id")
    operation_root = root.expanduser().resolve(strict=False)
    path = (operation_root / safe_operation_id / "operation.lock").resolve(strict=False)
    if not path.is_relative_to(operation_root):
        raise ValueError("operation lock escapes operation root")
    return DurableFileLock(
        path,
        timeout=timeout,
    )


def plan_lock(
    root: Path, plan_id: str, *, timeout: float | None = None
) -> DurableFileLock:
    safe_plan_id = _safe_id(plan_id, label="plan id")
    plan_root = root.expanduser().resolve(strict=False)
    path = (plan_root / safe_plan_id / "plan.lock").resolve(strict=False)
    if not path.is_relative_to(plan_root):
        raise ValueError("plan lock escapes plan root")
    return DurableFileLock(path, timeout=timeout)


def artifact_lock(
    root: Path, artifact_id: str, *, timeout: float | None = None
) -> DurableFileLock:
    safe_artifact_id = _safe_id(artifact_id, label="artifact id", minimum_hex=24)
    artifact_root = root.expanduser().resolve(strict=False)
    path = (artifact_root / safe_artifact_id / "artifact.lock").resolve(strict=False)
    if not path.is_relative_to(artifact_root):
        raise ValueError("artifact lock escapes cache root")
    return DurableFileLock(
        path,
        timeout=timeout,
    )


def project_lock(
    project_path: Path,
    *,
    timeout: float | None = None,
    project_lock_already_held: bool = False,
) -> DurableFileLock:
    normalized = str(project_path.resolve(strict=False)).casefold()
    key = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return DurableFileLock(
        (DEFAULT_PROJECT_LOCK_ROOT / f"{key}.lock").resolve(),
        timeout=timeout,
        allow_foreign_same_pid_reentry=project_lock_already_held,
    )


def request_update_pause(
    operation_id: str, *, root: Path | None = None
) -> dict[str, Any]:
    return UpdateOperationStore.open(operation_id, root=root).request(pause=True)


def resume_update(operation_id: str, *, root: Path | None = None) -> dict[str, Any]:
    return UpdateOperationStore.open(operation_id, root=root).request(
        pause=False, cancel=False
    )


def cancel_update(operation_id: str, *, root: Path | None = None) -> dict[str, Any]:
    return UpdateOperationStore.open(operation_id, root=root).request(cancel=True)


def discard_update_artifact(
    operation_id: str,
    *,
    root: Path | None = None,
    cache_root: Path | None = None,
) -> dict[str, Any]:
    store = UpdateOperationStore.open(operation_id, root=root)
    state = store.read()
    if int(state.get("leaseCount") or 0) > 0 or state.get("references"):
        raise RuntimeError("update artifact is still referenced")
    raw_artifact_dir = str(state.get("artifactDir") or "").strip()
    if not raw_artifact_dir:
        return store.update("cancelled", cancelRequested=False, discarded=True)
    raw_artifact_dir_path = Path(raw_artifact_dir).expanduser()
    if raw_artifact_dir_path.is_symlink():
        raise RuntimeError("update artifact path cannot be a symlink")
    artifact_dir = raw_artifact_dir_path.resolve(strict=False)
    cache = (cache_root or DEFAULT_CACHE_ROOT).resolve()
    if (
        not artifact_dir.is_absolute()
        or not artifact_dir.is_relative_to(cache)
        or artifact_dir.parent != cache
    ):
        raise RuntimeError("update artifact path is outside cache")
    with artifact_lock(cache, artifact_dir.name, timeout=None):
        latest = store.read()
        if int(latest.get("leaseCount") or 0) > 0 or latest.get("references"):
            raise RuntimeError("update artifact is still referenced")
        if artifact_dir.exists() or artifact_dir.is_symlink():
            _remove_tree_within(artifact_dir, cache)
        return store.update("cancelled", cancelRequested=False, discarded=True)


def _remove_tree_within(path: Path, root: Path) -> None:
    base = root.expanduser().resolve(strict=False)
    raw = path.expanduser().absolute()
    if raw.is_symlink():
        if not raw.is_relative_to(base) or raw == base:
            raise RuntimeError("refusing to remove symlink outside cache root")
        raw.unlink(missing_ok=True)
        return
    target = raw.resolve(strict=False)
    if not target.is_absolute() or not target.is_relative_to(base) or target == base:
        raise RuntimeError("refusing to remove path outside cache root")
    if target.is_file():
        target.unlink(missing_ok=True)
        return
    if target.is_dir():
        for child in target.iterdir():
            _remove_tree_within(child, base)
        target.rmdir()


def list_recovery_operations(root: Path | None = None) -> list[UpdateOperationStore]:
    operation_root = (root or DEFAULT_OPERATION_ROOT).resolve()
    if not operation_root.is_dir():
        return []
    result: list[UpdateOperationStore] = []
    for directory in operation_root.iterdir():
        if directory.is_dir() and (directory / "state.json").is_file():
            try:
                result.append(UpdateOperationStore(directory.name, operation_root))
            except ValueError:
                continue
    return result


__all__ = [
    "DEFAULT_CACHE_ROOT",
    "DEFAULT_OPERATION_ROOT",
    "DEFAULT_PLAN_ROOT",
    "DEFAULT_PROJECT_LOCK_ROOT",
    "DurableFileLock",
    "UpdateOperationStore",
    "UpdatePlanStore",
    "artifact_lock",
    "cancel_update",
    "discard_update_artifact",
    "list_recovery_operations",
    "operation_lock",
    "plan_lock",
    "project_lock",
    "request_update_pause",
    "resume_update",
]
