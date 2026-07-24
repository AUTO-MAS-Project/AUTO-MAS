"""Durable multi-root generations for the future Config v2 persistence path.

``CURRENT`` is the only durable commit point.  Published generations are
immutable, and an interrupted staging or publication remains inspectable but
is never selected automatically.

On Windows, publication uses ``MoveFileExW(MOVEFILE_WRITE_THROUGH)`` and never
silently downgrades a failed durable move.  This closes process-visible flush
and rename gaps, but it cannot prove survival across storage-controller power
loss; that remains a platform qualification boundary.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import stat
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import BinaryIO, Callable, Collection, Iterator, Literal, Mapping
from uuid import UUID, uuid4

GENERATION_STORE_SCHEMA_VERSION = 2
DEFAULT_MAX_ROOTS = 64
DEFAULT_MAX_ROOT_BYTES = 32 * 1024 * 1024
DEFAULT_MAX_TOTAL_BYTES = 128 * 1024 * 1024
DEFAULT_LOCK_TIMEOUT_SECONDS = 15.0
DEFAULT_LOCK_RETRY_SECONDS = 0.05
# Keep a margin below the historical Win32 260-character path boundary.  The
# store still uses pathlib/os APIs throughout, so opting into extended-path
# prefixes at one publication call would not make the complete operation safe.
WINDOWS_SAFE_PATH_LIMIT = 240

FAULT_POINTS = (
    "before_staging_write",
    "after_staging_write",
    "before_generation_rename",
    "after_generation_rename",
    "before_current_replace",
    "after_current_replace",
)

_MAX_REVISION = (1 << 63) - 1
_MAX_CURRENT_BYTES = 16 * 1024
_MAX_MANIFEST_BYTES = 1024 * 1024
_ROOT_NAME_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}", re.ASCII)
_GENERATION_PATTERN = re.compile(r"g-([0-9]{20})-([0-9a-f]{32})", re.ASCII)
_STAGING_PATTERN = re.compile(
    r"\.pending-(g-[0-9]{20}-[0-9a-f]{32})",
    re.ASCII,
)
_CURRENT_TEMP_PATTERN = re.compile(
    r"\.CURRENT\.([0-9a-f]{32})\.([0-9a-f]{32})\.tmp",
    re.ASCII,
)
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}", re.ASCII)
_TRANSACTION_PATTERN = re.compile(r"[0-9a-f]{32}", re.ASCII)
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}

_UNSET = object()
_PROCESS_LOCKS_GUARD = threading.Lock()
_PROCESS_LOCKS: dict[str, threading.RLock] = {}

FaultHook = Callable[[str], None]


class GenerationStoreError(RuntimeError):
    """Base error for generation persistence without configuration contents."""

    error_code = "generation_store_error"


class GenerationIntegrityError(GenerationStoreError):
    """On-disk state is missing, damaged, unexpected, or unsafe."""

    error_code = "generation_integrity_error"


class GenerationConflictError(GenerationStoreError):
    """A CAS precondition or transaction identity is stale."""

    error_code = "generation_conflict"


class NoCommittedGenerationError(GenerationStoreError):
    """The store has no valid ``CURRENT`` commit point."""

    error_code = "no_committed_generation"


class GenerationRecoveryRequiredError(GenerationIntegrityError):
    """A missing ``CURRENT`` has retained state that requires explicit recovery."""

    error_code = "generation_recovery_required"


class GenerationPathLengthError(GenerationStoreError):
    """A derived generation-store path exceeds the supported Windows budget."""

    error_code = "generation_path_length"

    def __init__(
        self,
        *,
        role: str,
        actual_utf16_chars: int,
        limit_utf16_chars: int,
    ) -> None:
        self.role = role
        self.actual_utf16_chars = actual_utf16_chars
        self.limit_utf16_chars = limit_utf16_chars
        super().__init__(
            "configuration generation path exceeds the Windows safe limit: "
            f"role={role}, actual={actual_utf16_chars}, "
            f"limit={limit_utf16_chars}; choose a shorter configuration "
            "directory"
        )


class GenerationDurabilityError(GenerationStoreError):
    """A required flush or write-through move failed."""

    error_code = "generation_durability_error"


class GenerationLockError(GenerationStoreError):
    """The cross-thread or cross-process generation lock failed."""

    error_code = "generation_lock_error"


class GenerationLockTimeoutError(GenerationLockError):
    """The generation lock was not acquired before its explicit deadline."""

    error_code = "generation_lock_timeout"


@dataclass(frozen=True)
class GenerationSnapshot:
    """One validated immutable generation."""

    generation: str
    revision: int
    parent_generation: str | None
    parent_revision: int
    parent_manifest_sha256: str | None
    transaction_id: str
    rollback_of: str | None
    root_set_sha256: str
    request_cas_sha256: str
    manifest_sha256: str
    roots: Mapping[str, bytes] = field(repr=False)


@dataclass(frozen=True)
class OrphanRecord:
    """Read-only description of state not reachable from ``CURRENT``."""

    kind: Literal["published", "staging", "current-temp"]
    name: str
    generation: str | None
    revision: int | None
    valid: bool


@dataclass(frozen=True)
class _RootRecord:
    name: str
    file_name: str
    size_bytes: int
    sha256: str

    def as_manifest(self) -> dict[str, object]:
        return {
            "name": self.name,
            "file": self.file_name,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class _GenerationRecord:
    generation: str
    revision: int
    parent_generation: str | None
    parent_revision: int
    parent_manifest_sha256: str | None
    transaction_id: str
    rollback_of: str | None
    root_set_sha256: str
    request_cas_sha256: str
    manifest_sha256: str
    roots: tuple[_RootRecord, ...] = field(repr=False)


def ensure_windows_path_budget(
    directory: Path,
    *,
    required_roots: Collection[str],
    max_roots: int = DEFAULT_MAX_ROOTS,
) -> None:
    """Fail before filesystem writes when Win32 paths would be unsafe.

    This remains a no-op outside Windows.  The directory is intentionally not
    included in the exception text because it can be user-controlled.
    """
    normalized_roots = _normalize_required_roots(
        required_roots,
        max_roots=max_roots,
    )
    _ensure_windows_path_budget(
        Path(os.path.abspath(os.fspath(directory))),
        root_names=normalized_roots,
    )


def _ensure_windows_path_budget(
    directory: Path,
    *,
    root_names: Collection[str],
) -> None:
    if not _uses_windows_legacy_path_limit():
        return

    longest_root_name = max(root_names, key=_utf16_char_count)
    generation = f"g-{_MAX_REVISION:020d}-{'f' * 32}"
    root_file_name = _root_file_name(longest_root_name)
    transaction_hex = "f" * 32
    candidates = {
        "staging-root": (
            directory
            / "staging"
            / f".pending-{generation}"
            / "roots"
            / root_file_name
        ),
        "published-root": (
            directory
            / "generations"
            / generation
            / "roots"
            / root_file_name
        ),
        "current-temp": directory
        / f".CURRENT.{transaction_hex}.{transaction_hex}.tmp",
    }
    role, path = max(
        candidates.items(),
        key=lambda item: _utf16_char_count(item[1]),
    )
    actual_utf16_chars = _utf16_char_count(path)
    if actual_utf16_chars > WINDOWS_SAFE_PATH_LIMIT:
        raise GenerationPathLengthError(
            role=role,
            actual_utf16_chars=actual_utf16_chars,
            limit_utf16_chars=WINDOWS_SAFE_PATH_LIMIT,
        )


def _uses_windows_legacy_path_limit() -> bool:
    return os.name == "nt"


def _utf16_char_count(value: Path | str) -> int:
    return len(os.fspath(value).encode("utf-16-le")) // 2


class AtomicGenerationStore:
    """Persist complete Config v2 roots as immutable atomic generations.

    This class is intentionally not wired into ``ConfigManager`` yet.  It is a
    transport-neutral storage boundary for a later production integration.
    """

    def __init__(
        self,
        directory: Path,
        *,
        required_roots: Collection[str],
        max_roots: int = DEFAULT_MAX_ROOTS,
        max_root_bytes: int = DEFAULT_MAX_ROOT_BYTES,
        max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
        lock_timeout_seconds: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
        lock_retry_seconds: float = DEFAULT_LOCK_RETRY_SECONDS,
        fault_hook: FaultHook | None = None,
    ) -> None:
        if max_roots < 1:
            raise ValueError("max_roots must be positive")
        if max_root_bytes < 1:
            raise ValueError("max_root_bytes must be positive")
        if max_total_bytes < max_root_bytes:
            raise ValueError("max_total_bytes must not be smaller than one root")
        if lock_timeout_seconds <= 0:
            raise ValueError("lock_timeout_seconds must be positive")
        if lock_retry_seconds <= 0:
            raise ValueError("lock_retry_seconds must be positive")

        self.directory = Path(os.path.abspath(os.fspath(directory)))
        self.generations_directory = self.directory / "generations"
        self.staging_directory = self.directory / "staging"
        self.current_path = self.directory / "CURRENT"
        self.lock_path = self.directory / "LOCK"
        self.max_roots = max_roots
        self.max_root_bytes = max_root_bytes
        self.max_total_bytes = max_total_bytes
        self.required_roots = _normalize_required_roots(
            required_roots,
            max_roots=max_roots,
        )
        _ensure_windows_path_budget(
            self.directory,
            root_names=self.required_roots,
        )
        self.root_set_sha256 = _root_set_sha256(self.required_roots)
        self.lock_timeout_seconds = float(lock_timeout_seconds)
        self.lock_retry_seconds = float(lock_retry_seconds)
        self._fault_hook = fault_hook
        self._prepare_layout()

    def read_current(self) -> GenerationSnapshot:
        """Read and fully validate the generation selected by ``CURRENT``."""
        self._validate_layout()
        snapshot = self._load_current_optional()
        if snapshot is None:
            raise NoCommittedGenerationError("no committed configuration generation")
        return snapshot

    def inspect_generation(self, generation: str) -> GenerationSnapshot:
        """Validate one published generation without changing ``CURRENT``."""
        self._validate_layout()
        _parse_generation_name(generation)
        return self._validate_generation(
            self.generations_directory / generation,
            expected_generation=generation,
        )

    def list_orphans(self) -> tuple[OrphanRecord, ...]:
        """List published and staging state not reachable from ``CURRENT``.

        Invalid orphan state is reported as ``valid=False``.  Corruption in
        ``CURRENT`` or its committed lineage still fails closed.
        """
        self._validate_layout()
        current = self._read_current_pointer_optional()
        lineage = (
            set(self._load_committed_lineage(current))
            if current is not None
            else set()
        )
        orphans: list[OrphanRecord] = []

        for path in self._iter_published_paths():
            revision, _ = _parse_generation_name(path.name)
            if path.name in lineage:
                continue
            try:
                self._validate_generation(
                    path,
                    expected_generation=path.name,
                )
            except GenerationStoreError:
                valid = False
            else:
                valid = True
            orphans.append(
                OrphanRecord(
                    kind="published",
                    name=path.name,
                    generation=path.name,
                    revision=revision,
                    valid=valid,
                )
            )

        for path in self._iter_staging_paths():
            generation = _parse_staging_name(path.name)
            revision, _ = _parse_generation_name(generation)
            try:
                self._validate_generation(
                    path,
                    expected_generation=generation,
                )
            except GenerationStoreError:
                valid = False
            else:
                valid = True
            orphans.append(
                OrphanRecord(
                    kind="staging",
                    name=path.name,
                    generation=generation,
                    revision=revision,
                    valid=valid,
                )
            )

        for path in self._iter_current_temp_paths():
            generation: str | None = None
            revision: int | None = None
            try:
                generation, revision = self._validate_current_temp(path)
            except GenerationStoreError:
                valid = False
            else:
                valid = True
            orphans.append(
                OrphanRecord(
                    kind="current-temp",
                    name=path.name,
                    generation=generation,
                    revision=revision,
                    valid=valid,
                )
            )

        return tuple(
            sorted(
                orphans,
                key=lambda item: (
                    item.revision if item.revision is not None else _MAX_REVISION,
                    item.kind,
                    item.name,
                ),
            )
        )

    def commit(
        self,
        roots: Mapping[str, bytes],
        *,
        expected_generation: str | None | object = _UNSET,
        expected_revision: int | object = _UNSET,
        transaction_id: UUID | str | None = None,
    ) -> GenerationSnapshot:
        """Commit a complete immutable root mapping.

        Passing ``expected_generation=None`` and ``expected_revision=0`` is a
        CAS assertion that the store is empty.  Omitting either argument leaves
        that part of the CAS unconstrained.  Supplying ``transaction_id`` makes
        a retry after a successful ``CURRENT`` replacement idempotent.
        """
        _validate_cas_arguments(expected_generation, expected_revision)
        normalized_roots = self._normalize_roots(roots)
        root_records = self._build_root_records(normalized_roots)
        requested_transaction = transaction_id is not None
        transaction_hex = _normalize_transaction_id(transaction_id)

        with self._exclusive_lock():
            current = self._load_current_optional()
            if current is not None:
                self._load_committed_lineage(current)
            transaction_hex = self._choose_transaction_id(
                transaction_hex,
                requested=requested_transaction,
                current=current,
                roots=normalized_roots,
                expected_generation=expected_generation,
                expected_revision=expected_revision,
                rollback_of=None,
            )
            if (
                current is not None
                and current.transaction_id == transaction_hex
                and self._is_idempotent_retry(
                    current,
                    roots=normalized_roots,
                    expected_generation=expected_generation,
                    expected_revision=expected_revision,
                    rollback_of=None,
                )
            ):
                return current

            self._check_cas(
                current,
                expected_generation=expected_generation,
                expected_revision=expected_revision,
            )
            return self._commit_locked(
                current,
                roots=normalized_roots,
                root_records=root_records,
                transaction_hex=transaction_hex,
                rollback_of=None,
            )

    def rollback(
        self,
        target_generation: str,
        *,
        expected_generation: str,
        expected_revision: int,
        transaction_id: UUID | str | None = None,
    ) -> GenerationSnapshot:
        """Recommit a prior committed generation at a higher revision."""
        _parse_generation_name(target_generation)
        _validate_cas_arguments(expected_generation, expected_revision)
        requested_transaction = transaction_id is not None
        transaction_hex = _normalize_transaction_id(transaction_id)

        with self._exclusive_lock():
            current = self._load_current_optional()
            if current is None:
                raise NoCommittedGenerationError(
                    "cannot rollback without a committed generation"
                )

            lineage = self._load_committed_lineage(current)
            try:
                target_record = lineage[target_generation]
            except KeyError as exc:
                raise GenerationConflictError(
                    "rollback target is not in the committed lineage"
                ) from exc
            if (
                target_record.generation == current.generation
                or target_record.revision >= current.revision
            ):
                raise GenerationConflictError(
                    "rollback target must be a strict committed ancestor"
                )

            target = self._validate_generation(
                self.generations_directory / target_generation,
                expected_generation=target_generation,
                expected_manifest_sha256=target_record.manifest_sha256,
            )
            normalized_roots = dict(target.roots)
            root_records = self._build_root_records(normalized_roots)
            transaction_hex = self._choose_transaction_id(
                transaction_hex,
                requested=requested_transaction,
                current=current,
                roots=normalized_roots,
                expected_generation=expected_generation,
                expected_revision=expected_revision,
                rollback_of=target_generation,
            )
            if (
                current.transaction_id == transaction_hex
                and self._is_idempotent_retry(
                    current,
                    roots=normalized_roots,
                    expected_generation=expected_generation,
                    expected_revision=expected_revision,
                    rollback_of=target_generation,
                )
            ):
                return current

            self._check_cas(
                current,
                expected_generation=expected_generation,
                expected_revision=expected_revision,
            )
            return self._commit_locked(
                current,
                roots=normalized_roots,
                root_records=root_records,
                transaction_hex=transaction_hex,
                rollback_of=target_generation,
            )

    def recover_initial_generation(
        self,
        *,
        generation: str,
        manifest_sha256: str,
    ) -> GenerationSnapshot:
        """Explicitly restore a missing CURRENT for one verified genesis.

        Recovery never chooses an orphan itself.  An operator must confirm both
        the immutable generation identity and its manifest hash, and the store
        must contain no competing published or staging state.
        """
        _parse_generation_name(generation)
        if (
            not isinstance(manifest_sha256, str)
            or _SHA256_PATTERN.fullmatch(manifest_sha256) is None
        ):
            raise ValueError("manifest_sha256 must be a lowercase SHA-256")

        with self._exclusive_lock():
            current = self._read_current_pointer_optional()
            if current is not None:
                raise GenerationConflictError(
                    "CURRENT already exists; initial recovery cannot replace it"
                )

            published_paths = self._iter_published_paths()
            staging_paths = self._iter_staging_paths()
            if (
                len(published_paths) != 1
                or published_paths[0].name != generation
                or staging_paths
            ):
                raise GenerationRecoveryRequiredError(
                    "initial recovery requires exactly one published generation "
                    "and no staging state"
                )

            candidate = self._validate_generation(
                published_paths[0],
                expected_generation=generation,
                expected_manifest_sha256=manifest_sha256,
            )
            if (
                candidate.revision != 1
                or candidate.parent_generation is not None
                or candidate.parent_revision != 0
                or candidate.rollback_of is not None
            ):
                raise GenerationRecoveryRequiredError(
                    "initial recovery candidate is not an immutable genesis"
                )

            for current_temp in self._iter_current_temp_paths():
                try:
                    temp_generation, temp_revision = self._validate_current_temp(
                        current_temp
                    )
                except GenerationStoreError:
                    raise GenerationRecoveryRequiredError(
                        "CURRENT temporary evidence is invalid"
                    ) from None
                if (
                    temp_generation != candidate.generation
                    or temp_revision != candidate.revision
                ):
                    raise GenerationRecoveryRequiredError(
                        "CURRENT temporary evidence differs from the genesis"
                    )

            self._publish_current_locked(candidate, expected_current=None)
            confirmed = self._read_current_pointer_optional()
            if (
                confirmed is None
                or confirmed.generation != candidate.generation
                or confirmed.revision != candidate.revision
                or confirmed.manifest_sha256 != candidate.manifest_sha256
            ):
                raise GenerationIntegrityError(
                    "initial recovery CURRENT confirmation differs"
                )
            return confirmed

    def _commit_locked(
        self,
        current: GenerationSnapshot | None,
        *,
        roots: Mapping[str, bytes],
        root_records: tuple[_RootRecord, ...],
        transaction_hex: str,
        rollback_of: str | None,
    ) -> GenerationSnapshot:
        revision = self._next_revision(current)
        generation = f"g-{revision:020d}-{transaction_hex}"
        staging_path = self.staging_directory / f".pending-{generation}"
        generation_path = self.generations_directory / generation
        if _lexical_stat(staging_path) is not None:
            raise GenerationConflictError(
                "transaction staging path already exists"
            )
        if _lexical_stat(generation_path) is not None:
            raise GenerationConflictError(
                "generation path already exists"
            )

        staging_path.mkdir()
        roots_directory = staging_path / "roots"
        roots_directory.mkdir()
        self._fault("before_staging_write")

        for record in root_records:
            _write_new_bytes(
                roots_directory / record.file_name,
                roots[record.name],
            )
        _fsync_directory(roots_directory)

        manifest = {
            "schema_version": GENERATION_STORE_SCHEMA_VERSION,
            "kind": "config-generation",
            "revision": revision,
            "generation": generation,
            "parent": current.generation if current is not None else None,
            "parent_revision": current.revision if current is not None else 0,
            "parent_manifest_sha256": (
                current.manifest_sha256 if current is not None else None
            ),
            "transaction_id": transaction_hex,
            "rollback_of": rollback_of,
            "root_set_sha256": self.root_set_sha256,
            "request_cas_sha256": _request_cas_sha256(
                current.generation if current is not None else None,
                current.revision if current is not None else 0,
            ),
            "roots": [record.as_manifest() for record in root_records],
        }
        _write_new_bytes(
            staging_path / "manifest.json",
            _serialize_json(manifest),
        )
        _fsync_directory(staging_path)
        _fsync_directory(self.staging_directory)
        self._validate_generation(
            staging_path,
            expected_generation=generation,
        )
        self._fault("after_staging_write")

        self._fault("before_generation_rename")
        self._validate_generation(
            staging_path,
            expected_generation=generation,
        )
        if _lexical_stat(generation_path) is not None:
            raise GenerationConflictError(
                "generation appeared before publication"
            )
        _durable_move(
            staging_path,
            generation_path,
            replace_existing=False,
        )
        _fsync_directory(self.staging_directory)
        _fsync_directory(self.generations_directory)
        self._fault("after_generation_rename")

        published = self._validate_generation(
            generation_path,
            expected_generation=generation,
        )
        self._load_committed_lineage(published)
        self._publish_current_locked(published, expected_current=current)
        return published

    def _publish_current_locked(
        self,
        snapshot: GenerationSnapshot,
        *,
        expected_current: GenerationSnapshot | None,
    ) -> None:
        """Publish one validated snapshot as CURRENT while the store lock is held."""
        self._assert_current_unchanged(expected_current)
        current_payload = {
            "schema_version": GENERATION_STORE_SCHEMA_VERSION,
            "kind": "config-current",
            "generation": snapshot.generation,
            "revision": snapshot.revision,
            "manifest_sha256": snapshot.manifest_sha256,
        }
        current_temp = self.directory / (
            f".CURRENT.{snapshot.transaction_id}.{uuid4().hex}.tmp"
        )
        current_bytes = _serialize_json(current_payload)
        _write_new_bytes(current_temp, current_bytes)

        self._fault("before_current_replace")
        self._assert_current_unchanged(expected_current)
        if (
            _read_plain_bytes(
                current_temp,
                max_bytes=_MAX_CURRENT_BYTES,
                label="CURRENT temporary file",
            )
            != current_bytes
        ):
            raise GenerationIntegrityError(
                "CURRENT temporary file integrity differs"
            )
        temp_generation, temp_revision = self._validate_current_temp(current_temp)
        if (
            temp_generation != snapshot.generation
            or temp_revision != snapshot.revision
        ):
            raise GenerationIntegrityError(
                "CURRENT temporary identity differs"
            )
        current_stat = _lexical_stat(self.current_path)
        if current_stat is not None and not _is_plain_file_stat(current_stat):
            raise GenerationIntegrityError("CURRENT is not a plain file")
        _durable_move(
            current_temp,
            self.current_path,
            replace_existing=expected_current is not None,
        )
        _fsync_directory(self.directory)
        self._fault("after_current_replace")

    def _choose_transaction_id(
        self,
        transaction_hex: str,
        *,
        requested: bool,
        current: GenerationSnapshot | None,
        roots: Mapping[str, bytes],
        expected_generation: str | None | object,
        expected_revision: int | object,
        rollback_of: str | None,
    ) -> str:
        while True:
            occurrences = self._transaction_occurrences(transaction_hex)
            if not occurrences:
                return transaction_hex
            if (
                current is not None
                and current.transaction_id == transaction_hex
                and self._is_idempotent_retry(
                    current,
                    roots=roots,
                    expected_generation=expected_generation,
                    expected_revision=expected_revision,
                    rollback_of=rollback_of,
                )
            ):
                return transaction_hex
            if requested:
                raise GenerationConflictError(
                    "transaction identifier is already reserved"
                )
            transaction_hex = uuid4().hex

    def _is_idempotent_retry(
        self,
        current: GenerationSnapshot,
        *,
        roots: Mapping[str, bytes],
        expected_generation: str | None | object,
        expected_revision: int | object,
        rollback_of: str | None,
    ) -> bool:
        if current.rollback_of != rollback_of or dict(current.roots) != dict(roots):
            return False
        if expected_generation is _UNSET or expected_revision is _UNSET:
            return False
        if (
            expected_generation != current.parent_generation
            or expected_revision != current.parent_revision
        ):
            return False
        return current.request_cas_sha256 == _request_cas_sha256(
            current.parent_generation,
            current.parent_revision,
        )

    def _transaction_occurrences(self, transaction_hex: str) -> tuple[str, ...]:
        occurrences: list[str] = []
        for path in self._iter_published_paths():
            _, existing_transaction = _parse_generation_name(path.name)
            if existing_transaction == transaction_hex:
                occurrences.append(path.name)
        for path in self._iter_staging_paths():
            generation = _parse_staging_name(path.name)
            _, existing_transaction = _parse_generation_name(generation)
            if existing_transaction == transaction_hex:
                occurrences.append(path.name)
        return tuple(occurrences)

    def _check_cas(
        self,
        current: GenerationSnapshot | None,
        *,
        expected_generation: str | None | object,
        expected_revision: int | object,
    ) -> None:
        actual_generation = current.generation if current is not None else None
        actual_revision = current.revision if current is not None else 0
        if (
            expected_generation is not _UNSET
            and expected_generation != actual_generation
        ):
            raise GenerationConflictError(
                "CURRENT generation does not match the CAS precondition"
            )
        if expected_revision is not _UNSET:
            if expected_revision != actual_revision:
                raise GenerationConflictError(
                    "CURRENT revision does not match the CAS precondition"
                )

    def _next_revision(self, current: GenerationSnapshot | None) -> int:
        maximum = current.revision if current is not None else 0
        for path in self._iter_published_paths():
            record = self._validate_generation_manifest(
                path,
                expected_generation=path.name,
            )
            maximum = max(maximum, record.revision)
        for path in self._iter_staging_paths():
            generation = _parse_staging_name(path.name)
            revision, _ = _parse_generation_name(generation)
            maximum = max(maximum, revision)
        if maximum >= _MAX_REVISION:
            raise GenerationStoreError("configuration revision space is exhausted")
        return maximum + 1

    def _load_current_optional(self) -> GenerationSnapshot | None:
        snapshot = self._read_current_pointer_optional()
        if snapshot is not None:
            return snapshot
        if (
            self._iter_published_paths()
            or self._iter_staging_paths()
            or self._iter_current_temp_paths()
        ):
            raise GenerationRecoveryRequiredError(
                "CURRENT is missing while retained generation state exists"
            )
        return None

    def _read_current_pointer_optional(self) -> GenerationSnapshot | None:
        current_stat = _lexical_stat(self.current_path)
        if current_stat is None:
            return None
        if not _is_plain_file_stat(current_stat):
            raise GenerationIntegrityError("CURRENT is not a plain file")
        current_bytes = _read_plain_bytes(
            self.current_path,
            max_bytes=_MAX_CURRENT_BYTES,
            label="CURRENT",
        )
        try:
            current = json.loads(current_bytes.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            raise GenerationIntegrityError("CURRENT is unreadable") from None
        required_fields = {
            "schema_version",
            "kind",
            "generation",
            "revision",
            "manifest_sha256",
        }
        if not isinstance(current, dict) or set(current) != required_fields:
            raise GenerationIntegrityError("CURRENT fields differ")
        generation = current["generation"]
        revision = current["revision"]
        manifest_sha256 = current["manifest_sha256"]
        if (
            current["schema_version"] != GENERATION_STORE_SCHEMA_VERSION
            or current["kind"] != "config-current"
            or not isinstance(generation, str)
            or not isinstance(revision, int)
            or isinstance(revision, bool)
            or revision < 1
            or revision > _MAX_REVISION
            or not isinstance(manifest_sha256, str)
            or _SHA256_PATTERN.fullmatch(manifest_sha256) is None
        ):
            raise GenerationIntegrityError("CURRENT integrity metadata is invalid")
        parsed_revision, _ = _parse_generation_name(generation)
        if parsed_revision != revision:
            raise GenerationIntegrityError("CURRENT revision and generation differ")

        snapshot = self._validate_generation(
            self.generations_directory / generation,
            expected_generation=generation,
            expected_manifest_sha256=manifest_sha256,
        )
        if snapshot.revision != revision:
            raise GenerationIntegrityError("CURRENT and manifest revisions differ")
        return snapshot

    def _assert_current_unchanged(
        self,
        expected: GenerationSnapshot | None,
    ) -> None:
        actual = self._read_current_pointer_optional()
        if expected is None:
            if actual is not None:
                raise GenerationConflictError(
                    "CURRENT changed before atomic replacement"
                )
            return
        if (
            actual is None
            or actual.generation != expected.generation
            or actual.revision != expected.revision
            or actual.manifest_sha256 != expected.manifest_sha256
        ):
            raise GenerationConflictError(
                "CURRENT changed before atomic replacement"
            )

    def _load_committed_lineage(
        self,
        current: GenerationSnapshot,
    ) -> dict[str, _GenerationRecord]:
        lineage: dict[str, _GenerationRecord] = {}
        transaction_ids: set[str] = set()
        child = self._validate_generation_manifest(
            self.generations_directory / current.generation,
            expected_generation=current.generation,
            expected_manifest_sha256=current.manifest_sha256,
        )
        while True:
            if child.generation in lineage:
                raise GenerationIntegrityError(
                    "committed generation lineage contains a cycle"
                )
            if child.transaction_id in transaction_ids:
                raise GenerationIntegrityError(
                    "committed generation lineage reuses a transaction identifier"
                )
            lineage[child.generation] = child
            transaction_ids.add(child.transaction_id)
            if child.parent_generation is None:
                if child.parent_revision != 0:
                    raise GenerationIntegrityError(
                        "first generation has invalid parent revision"
                    )
                break

            parent = self._validate_generation_manifest(
                self.generations_directory / child.parent_generation,
                expected_generation=child.parent_generation,
            )
            if (
                parent.revision != child.parent_revision
                or parent.manifest_sha256 != child.parent_manifest_sha256
                or parent.revision >= child.revision
            ):
                raise GenerationIntegrityError(
                    "committed generation parent metadata differs"
                )
            child = parent

        for record in lineage.values():
            if record.rollback_of is None:
                continue
            target = lineage.get(record.rollback_of)
            if target is None or target.revision >= record.revision:
                raise GenerationIntegrityError(
                    "generation rollback target is not a strict ancestor"
                )
            if target.roots != record.roots:
                raise GenerationIntegrityError(
                    "generation rollback roots differ from the target"
                )
        return lineage

    def _validate_generation(
        self,
        generation_path: Path,
        *,
        expected_generation: str,
        expected_manifest_sha256: str | None = None,
    ) -> GenerationSnapshot:
        record = self._validate_generation_manifest(
            generation_path,
            expected_generation=expected_generation,
            expected_manifest_sha256=expected_manifest_sha256,
        )
        roots_directory = generation_path / "roots"
        root_values: dict[str, bytes] = {}
        for root_record in record.roots:
            root_path = roots_directory / root_record.file_name
            content = _read_plain_bytes(
                root_path,
                max_bytes=self.max_root_bytes,
                label="generation root",
            )
            if len(content) != root_record.size_bytes:
                raise GenerationIntegrityError("generation root size mismatch")
            if hashlib.sha256(content).hexdigest() != root_record.sha256:
                raise GenerationIntegrityError("generation root hash mismatch")
            root_values[root_record.name] = content

        return GenerationSnapshot(
            generation=record.generation,
            revision=record.revision,
            parent_generation=record.parent_generation,
            parent_revision=record.parent_revision,
            parent_manifest_sha256=record.parent_manifest_sha256,
            transaction_id=record.transaction_id,
            rollback_of=record.rollback_of,
            root_set_sha256=record.root_set_sha256,
            request_cas_sha256=record.request_cas_sha256,
            manifest_sha256=record.manifest_sha256,
            roots=MappingProxyType(root_values),
        )

    def _validate_generation_manifest(
        self,
        generation_path: Path,
        *,
        expected_generation: str,
        expected_manifest_sha256: str | None = None,
    ) -> _GenerationRecord:
        """Validate immutable metadata without retaining historical root bytes."""
        expected_revision, expected_transaction = _parse_generation_name(
            expected_generation
        )
        generation_stat = _lexical_stat(generation_path)
        if (
            generation_stat is None
            or not _is_plain_directory_stat(generation_stat)
        ):
            raise GenerationIntegrityError(
                "generation directory is missing or unsafe"
            )

        actual_entries = {path.name for path in generation_path.iterdir()}
        if actual_entries != {"manifest.json", "roots"}:
            raise GenerationIntegrityError(
                "generation contains unexpected entries"
            )
        manifest_path = generation_path / "manifest.json"
        roots_directory = generation_path / "roots"
        roots_stat = _lexical_stat(roots_directory)
        if roots_stat is None or not _is_plain_directory_stat(roots_stat):
            raise GenerationIntegrityError(
                "generation roots directory is missing or unsafe"
            )

        manifest_bytes = _read_plain_bytes(
            manifest_path,
            max_bytes=_MAX_MANIFEST_BYTES,
            label="generation manifest",
        )
        manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
        if (
            expected_manifest_sha256 is not None
            and manifest_sha256 != expected_manifest_sha256
        ):
            raise GenerationIntegrityError("generation manifest hash mismatch")
        try:
            manifest = json.loads(manifest_bytes.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            raise GenerationIntegrityError(
                "generation manifest is unreadable"
            ) from None
        required_fields = {
            "schema_version",
            "kind",
            "revision",
            "generation",
            "parent",
            "parent_revision",
            "parent_manifest_sha256",
            "transaction_id",
            "rollback_of",
            "root_set_sha256",
            "request_cas_sha256",
            "roots",
        }
        if not isinstance(manifest, dict) or set(manifest) != required_fields:
            raise GenerationIntegrityError("generation manifest fields differ")

        revision = manifest["revision"]
        generation = manifest["generation"]
        parent = manifest["parent"]
        parent_revision = manifest["parent_revision"]
        parent_manifest_sha256 = manifest["parent_manifest_sha256"]
        transaction_id = manifest["transaction_id"]
        rollback_of = manifest["rollback_of"]
        root_set_sha256 = manifest["root_set_sha256"]
        request_cas_sha256 = manifest["request_cas_sha256"]
        if (
            manifest["schema_version"] != GENERATION_STORE_SCHEMA_VERSION
            or manifest["kind"] != "config-generation"
            or not isinstance(revision, int)
            or isinstance(revision, bool)
            or revision != expected_revision
            or generation != expected_generation
            or transaction_id != expected_transaction
            or not isinstance(parent_revision, int)
            or isinstance(parent_revision, bool)
            or parent_revision < 0
            or parent_revision >= revision
            or not isinstance(transaction_id, str)
            or _TRANSACTION_PATTERN.fullmatch(transaction_id) is None
            or not isinstance(root_set_sha256, str)
            or _SHA256_PATTERN.fullmatch(root_set_sha256) is None
            or root_set_sha256 != self.root_set_sha256
            or not isinstance(request_cas_sha256, str)
            or _SHA256_PATTERN.fullmatch(request_cas_sha256) is None
        ):
            raise GenerationIntegrityError(
                "generation identity metadata is invalid"
            )
        if parent is None:
            if parent_revision != 0 or parent_manifest_sha256 is not None:
                raise GenerationIntegrityError(
                    "first generation parent metadata is invalid"
                )
        elif not isinstance(parent, str):
            raise GenerationIntegrityError(
                "generation parent metadata is invalid"
            )
        else:
            parsed_parent_revision, _ = _parse_generation_name(parent)
            if (
                parsed_parent_revision != parent_revision
                or not isinstance(parent_manifest_sha256, str)
                or _SHA256_PATTERN.fullmatch(parent_manifest_sha256) is None
            ):
                raise GenerationIntegrityError(
                    "generation parent integrity metadata differs"
                )
        if request_cas_sha256 != _request_cas_sha256(
            parent,
            parent_revision,
        ):
            raise GenerationIntegrityError(
                "generation request CAS metadata differs"
            )
        if rollback_of is not None:
            if not isinstance(rollback_of, str):
                raise GenerationIntegrityError(
                    "generation rollback metadata is invalid"
                )
            _parse_generation_name(rollback_of)

        records = self._validate_manifest_roots(manifest["roots"])
        expected_files = {record.file_name for record in records}
        actual_files = {path.name for path in roots_directory.iterdir()}
        if actual_files != expected_files:
            raise GenerationIntegrityError(
                "generation root file set differs"
            )

        for record in records:
            root_path = roots_directory / record.file_name
            root_stat = _lexical_stat(root_path)
            if root_stat is None or not _is_plain_file_stat(root_stat):
                raise GenerationIntegrityError(
                    "generation root is missing or unsafe"
                )
            if root_stat.st_size != record.size_bytes:
                raise GenerationIntegrityError("generation root size mismatch")

        return _GenerationRecord(
            generation=generation,
            revision=revision,
            parent_generation=parent,
            parent_revision=parent_revision,
            parent_manifest_sha256=parent_manifest_sha256,
            transaction_id=transaction_id,
            rollback_of=rollback_of,
            root_set_sha256=root_set_sha256,
            request_cas_sha256=request_cas_sha256,
            manifest_sha256=manifest_sha256,
            roots=records,
        )

    def _validate_manifest_roots(
        self,
        value: object,
    ) -> tuple[_RootRecord, ...]:
        if (
            not isinstance(value, list)
            or len(value) != len(self.required_roots)
            or len(value) > self.max_roots
        ):
            raise GenerationIntegrityError(
                "generation root count is invalid"
            )
        records: list[_RootRecord] = []
        seen_casefolded: set[str] = set()
        total_bytes = 0
        for item in value:
            if not isinstance(item, dict) or set(item) != {
                "name",
                "file",
                "size_bytes",
                "sha256",
            }:
                raise GenerationIntegrityError(
                    "generation root metadata fields differ"
                )
            name = item["name"]
            file_name = item["file"]
            size_bytes = item["size_bytes"]
            sha256 = item["sha256"]
            if not isinstance(name, str):
                raise GenerationIntegrityError(
                    "generation root name is invalid"
                )
            try:
                _validate_root_name(name)
            except ValueError:
                raise GenerationIntegrityError(
                    "generation root name is invalid"
                ) from None
            folded = name.casefold()
            if folded in seen_casefolded:
                raise GenerationIntegrityError(
                    "generation root names collide"
                )
            seen_casefolded.add(folded)
            if (
                file_name != _root_file_name(name)
                or not isinstance(size_bytes, int)
                or isinstance(size_bytes, bool)
                or size_bytes < 0
                or size_bytes > self.max_root_bytes
                or not isinstance(sha256, str)
                or _SHA256_PATTERN.fullmatch(sha256) is None
            ):
                raise GenerationIntegrityError(
                    "generation root integrity metadata is invalid"
                )
            total_bytes += size_bytes
            if total_bytes > self.max_total_bytes:
                raise GenerationIntegrityError(
                    "generation total size exceeds the configured limit"
                )
            records.append(
                _RootRecord(
                    name=name,
                    file_name=file_name,
                    size_bytes=size_bytes,
                    sha256=sha256,
                )
            )
        if [record.name for record in records] != sorted(
            (record.name for record in records),
            key=lambda name: (name.casefold(), name),
        ):
            raise GenerationIntegrityError(
                "generation root order is not canonical"
            )
        if tuple(record.name for record in records) != self.required_roots:
            raise GenerationIntegrityError(
                "generation root set differs from the required schema"
            )
        return tuple(records)

    def _normalize_roots(
        self,
        roots: Mapping[str, bytes],
    ) -> dict[str, bytes]:
        if not isinstance(roots, Mapping):
            raise TypeError("roots must be a mapping")
        if len(roots) != len(self.required_roots):
            raise ValueError("root set differs from the required schema")
        normalized: dict[str, bytes] = {}
        seen_casefolded: set[str] = set()
        total_bytes = 0
        for name, content in roots.items():
            _validate_root_name(name)
            if len(normalized) >= self.max_roots:
                raise ValueError("root count exceeds the configured limit")
            folded = name.casefold()
            if folded in seen_casefolded:
                raise ValueError("root names collide on Windows")
            seen_casefolded.add(folded)
            if not isinstance(content, bytes):
                raise TypeError("root values must be bytes")
            if len(content) > self.max_root_bytes:
                raise ValueError("root size exceeds the configured limit")
            total_bytes += len(content)
            if total_bytes > self.max_total_bytes:
                raise ValueError("total root size exceeds the configured limit")
            normalized[name] = bytes(content)
        normalized = dict(
            sorted(
                normalized.items(),
                key=lambda item: (item[0].casefold(), item[0]),
            )
        )
        if tuple(normalized) != self.required_roots:
            raise ValueError("root set differs from the required schema")
        return normalized

    @staticmethod
    def _build_root_records(
        roots: Mapping[str, bytes],
    ) -> tuple[_RootRecord, ...]:
        return tuple(
            _RootRecord(
                name=name,
                file_name=_root_file_name(name),
                size_bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
            )
            for name, content in roots.items()
        )

    def _iter_published_paths(self) -> tuple[Path, ...]:
        paths: list[Path] = []
        for path in self.generations_directory.iterdir():
            path_stat = _lexical_stat(path)
            if (
                path_stat is None
                or not _is_plain_directory_stat(path_stat)
            ):
                raise GenerationIntegrityError(
                    "generations directory contains an unsafe entry"
                )
            _parse_generation_name(path.name)
            paths.append(path)
        return tuple(sorted(paths, key=lambda item: item.name))

    def _iter_staging_paths(self) -> tuple[Path, ...]:
        paths: list[Path] = []
        for path in self.staging_directory.iterdir():
            path_stat = _lexical_stat(path)
            if (
                path_stat is None
                or not _is_plain_directory_stat(path_stat)
            ):
                raise GenerationIntegrityError(
                    "staging directory contains an unsafe entry"
                )
            _parse_staging_name(path.name)
            paths.append(path)
        return tuple(sorted(paths, key=lambda item: item.name))

    def _iter_current_temp_paths(self) -> tuple[Path, ...]:
        paths: list[Path] = []
        for path in self.directory.iterdir():
            if _CURRENT_TEMP_PATTERN.fullmatch(path.name) is None:
                continue
            path_stat = _lexical_stat(path)
            if path_stat is None or not _is_plain_file_stat(path_stat):
                raise GenerationIntegrityError(
                    "CURRENT temporary entry is unsafe"
                )
            paths.append(path)
        return tuple(sorted(paths, key=lambda item: item.name))

    def _validate_current_temp(self, path: Path) -> tuple[str, int]:
        match = _CURRENT_TEMP_PATTERN.fullmatch(path.name)
        if match is None:
            raise GenerationIntegrityError("CURRENT temporary name is invalid")
        content = _read_plain_bytes(
            path,
            max_bytes=_MAX_CURRENT_BYTES,
            label="CURRENT temporary file",
        )
        try:
            payload = json.loads(content.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            raise GenerationIntegrityError(
                "CURRENT temporary file is unreadable"
            ) from None
        required_fields = {
            "schema_version",
            "kind",
            "generation",
            "revision",
            "manifest_sha256",
        }
        if not isinstance(payload, dict) or set(payload) != required_fields:
            raise GenerationIntegrityError(
                "CURRENT temporary fields differ"
            )
        generation = payload["generation"]
        revision = payload["revision"]
        manifest_sha256 = payload["manifest_sha256"]
        if (
            payload["schema_version"] != GENERATION_STORE_SCHEMA_VERSION
            or payload["kind"] != "config-current"
            or not isinstance(generation, str)
            or not isinstance(revision, int)
            or isinstance(revision, bool)
            or not isinstance(manifest_sha256, str)
            or _SHA256_PATTERN.fullmatch(manifest_sha256) is None
        ):
            raise GenerationIntegrityError(
                "CURRENT temporary integrity metadata is invalid"
            )
        parsed_revision, transaction_id = _parse_generation_name(generation)
        if (
            revision != parsed_revision
            or transaction_id != match.group(1)
        ):
            raise GenerationIntegrityError(
                "CURRENT temporary identity metadata differs"
            )
        record = self._validate_generation_manifest(
            self.generations_directory / generation,
            expected_generation=generation,
            expected_manifest_sha256=manifest_sha256,
        )
        if record.revision != revision:
            raise GenerationIntegrityError(
                "CURRENT temporary revision differs"
            )
        return generation, revision

    def _fault(self, point: str) -> None:
        if point not in FAULT_POINTS:
            raise AssertionError("unknown generation store fault point")
        if self._fault_hook is not None:
            self._fault_hook(point)

    def _prepare_layout(self) -> None:
        _ensure_plain_directory_tree(self.directory)
        _ensure_plain_directory(self.generations_directory, create=True)
        _ensure_plain_directory(self.staging_directory, create=True)
        _ensure_lock_file(self.lock_path)
        self._validate_layout()

    def _validate_layout(self) -> None:
        _validate_plain_ancestor_chain(self.directory)
        _ensure_plain_directory(self.directory, create=False)
        _ensure_plain_directory(self.generations_directory, create=False)
        _ensure_plain_directory(self.staging_directory, create=False)
        lock_stat = _lexical_stat(self.lock_path)
        if lock_stat is None or not _is_plain_file_stat(lock_stat):
            raise GenerationIntegrityError("LOCK is not a plain file")
        current_stat = _lexical_stat(self.current_path)
        if current_stat is not None and not _is_plain_file_stat(current_stat):
            raise GenerationIntegrityError("CURRENT is not a plain file")
        allowed_entries = {"generations", "staging", "LOCK"}
        if current_stat is not None:
            allowed_entries.add("CURRENT")
        for path in self.directory.iterdir():
            if path.name in allowed_entries:
                continue
            if _CURRENT_TEMP_PATTERN.fullmatch(path.name) is not None:
                path_stat = _lexical_stat(path)
                if path_stat is not None and _is_plain_file_stat(path_stat):
                    continue
            raise GenerationIntegrityError(
                "persistence directory contains an unexpected entry"
            )

    @contextmanager
    def _exclusive_lock(self) -> Iterator[None]:
        process_lock = _process_lock_for(self.lock_path)
        deadline = time.monotonic() + self.lock_timeout_seconds
        if not process_lock.acquire(timeout=self.lock_timeout_seconds):
            raise GenerationLockTimeoutError(
                "configuration store lock acquisition timed out"
            )
        try:
            self._validate_layout()
            try:
                lock_file = self.lock_path.open("r+b")
            except OSError as exc:
                raise GenerationIntegrityError("LOCK cannot be opened") from exc
            with lock_file:
                opened_stat = os.fstat(lock_file.fileno())
                current_stat = _lexical_stat(self.lock_path)
                if (
                    current_stat is None
                    or not _is_plain_file_stat(current_stat)
                    or not _same_file_identity(current_stat, opened_stat)
                ):
                    raise GenerationIntegrityError(
                        "LOCK changed while it was being opened"
                    )
                if lock_file.seek(0, os.SEEK_END) == 0:
                    lock_file.write(b"\0")
                    lock_file.flush()
                    os.fsync(lock_file.fileno())
                lock_file.seek(0)
                _lock_one_byte(
                    lock_file,
                    deadline=deadline,
                    retry_interval=self.lock_retry_seconds,
                )
                try:
                    self._validate_layout()
                    yield
                finally:
                    lock_file.seek(0)
                    _unlock_one_byte(lock_file)
        finally:
            process_lock.release()


def _normalize_required_roots(
    value: Collection[str],
    *,
    max_roots: int,
) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Collection):
        raise TypeError("required_roots must be a collection of root names")
    if not value:
        raise ValueError("required_roots must not be empty")
    if len(value) > max_roots:
        raise ValueError("required root count exceeds the configured limit")

    normalized: list[str] = []
    seen_casefolded: set[str] = set()
    for name in value:
        _validate_root_name(name)
        folded = name.casefold()
        if folded in seen_casefolded:
            raise ValueError("required root names collide on Windows")
        seen_casefolded.add(folded)
        normalized.append(name)
    return tuple(sorted(normalized, key=lambda name: (name.casefold(), name)))


def _root_set_sha256(required_roots: tuple[str, ...]) -> str:
    return hashlib.sha256(
        _serialize_json(
            {
                "kind": "config-root-set",
                "roots": list(required_roots),
                "schema_version": GENERATION_STORE_SCHEMA_VERSION,
            }
        )
    ).hexdigest()


def _request_cas_sha256(
    parent_generation: str | None,
    parent_revision: int,
) -> str:
    return hashlib.sha256(
        _serialize_json(
            {
                "kind": "config-request-cas",
                "parent_generation": parent_generation,
                "parent_revision": parent_revision,
                "schema_version": GENERATION_STORE_SCHEMA_VERSION,
            }
        )
    ).hexdigest()


def _normalize_transaction_id(value: UUID | str | None) -> str:
    if value is None:
        return uuid4().hex
    try:
        return UUID(str(value)).hex
    except (ValueError, AttributeError, TypeError):
        raise ValueError("transaction_id must be a UUID") from None


def _validate_cas_arguments(
    expected_generation: str | None | object,
    expected_revision: int | object,
) -> None:
    if expected_generation is not _UNSET and expected_generation is not None:
        if (
            not isinstance(expected_generation, str)
            or _GENERATION_PATTERN.fullmatch(expected_generation) is None
        ):
            raise ValueError("expected_generation must be a generation name")
    if expected_revision is not _UNSET and (
        not isinstance(expected_revision, int)
        or isinstance(expected_revision, bool)
        or expected_revision < 0
        or expected_revision > _MAX_REVISION
    ):
        raise ValueError("expected_revision must be a non-negative integer")


def _validate_root_name(name: object) -> None:
    if not isinstance(name, str) or _ROOT_NAME_PATTERN.fullmatch(name) is None:
        raise ValueError("root name does not match the strict whitelist")
    if name.upper() in _WINDOWS_RESERVED_NAMES:
        raise ValueError("root name is reserved on Windows")


def _root_file_name(root_name: str) -> str:
    return f"{root_name}.bin"


def _parse_generation_name(value: str) -> tuple[int, str]:
    if not isinstance(value, str):
        raise GenerationIntegrityError("generation name is invalid")
    match = _GENERATION_PATTERN.fullmatch(value)
    if match is None:
        raise GenerationIntegrityError("generation name is invalid")
    revision = int(match.group(1))
    if revision < 1 or revision > _MAX_REVISION:
        raise GenerationIntegrityError("generation revision is invalid")
    return revision, match.group(2)


def _parse_staging_name(value: str) -> str:
    match = _STAGING_PATTERN.fullmatch(value)
    if match is None:
        raise GenerationIntegrityError("staging name is invalid")
    return match.group(1)


def _serialize_json(payload: object) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _write_new_bytes(path: Path, content: bytes) -> None:
    _validate_plain_ancestor_chain(path.parent)
    parent_stat = _lexical_stat(path.parent)
    if parent_stat is None or not _is_plain_directory_stat(parent_stat):
        raise GenerationIntegrityError("write parent is missing or unsafe")
    if _lexical_stat(path) is not None:
        raise GenerationConflictError("write target already exists")
    with path.open("xb") as stream:
        opened_stat = os.fstat(stream.fileno())
        if not _is_plain_file_stat(opened_stat):
            raise GenerationIntegrityError("new file is not a plain file")
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def _read_plain_bytes(path: Path, *, max_bytes: int, label: str) -> bytes:
    _validate_plain_ancestor_chain(path.parent)
    lexical_stat = _lexical_stat(path)
    if lexical_stat is None or not _is_plain_file_stat(lexical_stat):
        raise GenerationIntegrityError(f"{label} is missing or unsafe")
    if lexical_stat.st_size < 0 or lexical_stat.st_size > max_bytes:
        raise GenerationIntegrityError(f"{label} size is invalid")
    try:
        stream = path.open("rb")
    except OSError as exc:
        raise GenerationIntegrityError(f"{label} cannot be opened") from exc
    with stream:
        opened_stat = os.fstat(stream.fileno())
        current_stat = _lexical_stat(path)
        if (
            not _is_plain_file_stat(opened_stat)
            or current_stat is None
            or not _is_plain_file_stat(current_stat)
            or not _same_file_identity(current_stat, opened_stat)
        ):
            raise GenerationIntegrityError(
                f"{label} changed while it was being opened"
            )
        content = stream.read(max_bytes + 1)
        final_stat = os.fstat(stream.fileno())
        if (
            len(content) > max_bytes
            or len(content) != opened_stat.st_size
            or opened_stat.st_size != final_stat.st_size
            or opened_stat.st_mtime_ns != final_stat.st_mtime_ns
        ):
            raise GenerationIntegrityError(f"{label} changed while it was read")
        return content


def _ensure_plain_directory_tree(path: Path) -> None:
    missing: list[Path] = []
    cursor = path
    while _lexical_stat(cursor) is None:
        missing.append(cursor)
        parent = cursor.parent
        if parent == cursor:
            raise GenerationIntegrityError(
                "cannot find an existing plain directory ancestor"
            )
        cursor = parent
    _validate_plain_ancestor_chain(cursor)
    for directory in reversed(missing):
        try:
            directory.mkdir()
        except FileExistsError:
            pass
        _ensure_plain_directory(directory, create=False)


def _validate_plain_ancestor_chain(path: Path) -> None:
    cursor = path
    while True:
        path_stat = _lexical_stat(cursor)
        if path_stat is None or not _is_plain_directory_stat(path_stat):
            raise GenerationIntegrityError(
                "store path contains a missing or unsafe directory"
            )
        parent = cursor.parent
        if parent == cursor:
            return
        cursor = parent


def _ensure_plain_directory(path: Path, *, create: bool) -> None:
    path_stat = _lexical_stat(path)
    if path_stat is not None:
        if not _is_plain_directory_stat(path_stat):
            raise GenerationIntegrityError(
                "persistence directory is not a plain directory"
            )
        return
    if not create:
        raise GenerationIntegrityError("persistence directory is missing")
    try:
        path.mkdir()
    except FileExistsError:
        pass
    path_stat = _lexical_stat(path)
    if path_stat is None or not _is_plain_directory_stat(path_stat):
        raise GenerationIntegrityError(
            "persistence directory could not be created safely"
        )


def _ensure_lock_file(lock_path: Path) -> None:
    lock_stat = _lexical_stat(lock_path)
    if lock_stat is None:
        try:
            descriptor = os.open(
                lock_path,
                os.O_RDWR | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError:
            pass
        else:
            try:
                os.write(descriptor, b"\0")
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        lock_stat = _lexical_stat(lock_path)
    if lock_stat is None or not _is_plain_file_stat(lock_stat):
        raise GenerationIntegrityError("LOCK is not a plain file")


def _lexical_stat(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def _is_reparse_point(path_stat: os.stat_result) -> bool:
    attributes = getattr(path_stat, "st_file_attributes", 0)
    reparse_attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(attributes & reparse_attribute)


def _is_plain_file_stat(path_stat: os.stat_result) -> bool:
    return (
        stat.S_ISREG(path_stat.st_mode)
        and not _is_reparse_point(path_stat)
        and getattr(path_stat, "st_nlink", 1) == 1
    )


def _is_plain_directory_stat(path_stat: os.stat_result) -> bool:
    return stat.S_ISDIR(path_stat.st_mode) and not _is_reparse_point(path_stat)


def _same_file_identity(
    left: os.stat_result,
    right: os.stat_result,
) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _durable_move(
    source: Path,
    destination: Path,
    *,
    replace_existing: bool,
) -> None:
    """Publish a path without silently dropping write-through failures."""
    try:
        if os.name == "nt":
            _move_file_ex_windows(
                source,
                destination,
                replace_existing=replace_existing,
            )
        elif replace_existing:
            os.replace(source, destination)
        else:
            os.rename(source, destination)
    except OSError as exc:
        raise GenerationDurabilityError(
            "durable generation publication failed"
        ) from exc


def _move_file_ex_windows(
    source: Path,
    destination: Path,
    *,
    replace_existing: bool,
) -> None:
    import ctypes
    from ctypes import wintypes

    move_file_ex = ctypes.WinDLL(
        "kernel32",
        use_last_error=True,
    ).MoveFileExW
    move_file_ex.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
    ]
    move_file_ex.restype = wintypes.BOOL

    movefile_replace_existing = 0x00000001
    movefile_write_through = 0x00000008
    flags = movefile_write_through
    if replace_existing:
        flags |= movefile_replace_existing
    if not move_file_ex(
        os.fspath(source),
        os.fspath(destination),
        flags,
    ):
        error = ctypes.get_last_error()
        raise OSError(error, ctypes.FormatError(error))


def _fsync_directory(path: Path) -> None:
    """Flush POSIX directory metadata; Windows moves are write-through above."""
    if os.name == "nt":
        return
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError as exc:
        raise GenerationDurabilityError(
            "persistence directory cannot be opened for flush"
        ) from exc
    try:
        os.fsync(descriptor)
    except OSError as exc:
        raise GenerationDurabilityError(
            "persistence directory flush failed"
        ) from exc
    finally:
        os.close(descriptor)


def _process_lock_for(lock_path: Path) -> threading.RLock:
    key = os.path.normcase(os.path.abspath(os.fspath(lock_path)))
    with _PROCESS_LOCKS_GUARD:
        lock = _PROCESS_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _PROCESS_LOCKS[key] = lock
        return lock


def _lock_one_byte(
    lock_file: BinaryIO,
    *,
    deadline: float,
    retry_interval: float,
) -> None:
    while True:
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(
                    lock_file.fileno(),
                    fcntl.LOCK_EX | fcntl.LOCK_NB,
                )
            return
        except OSError as exc:
            if exc.errno not in {
                errno.EACCES,
                errno.EAGAIN,
                errno.EDEADLK,
            }:
                raise GenerationLockError(
                    "configuration store lock operation failed"
                ) from exc
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise GenerationLockTimeoutError(
                    "configuration store lock acquisition timed out"
                ) from None
            time.sleep(min(retry_interval, remaining))


def _unlock_one_byte(lock_file: BinaryIO) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            return
        import fcntl

        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    except OSError as exc:
        raise GenerationLockError(
            "configuration store unlock operation failed"
        ) from exc


__all__ = [
    "FAULT_POINTS",
    "AtomicGenerationStore",
    "GenerationConflictError",
    "GenerationDurabilityError",
    "GenerationIntegrityError",
    "GenerationLockError",
    "GenerationLockTimeoutError",
    "GenerationPathLengthError",
    "GenerationRecoveryRequiredError",
    "GenerationSnapshot",
    "GenerationStoreError",
    "NoCommittedGenerationError",
    "OrphanRecord",
    "ensure_windows_path_budget",
]
