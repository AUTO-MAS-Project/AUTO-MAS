"""Fail-closed Config v2 authoritative generation bootstrap.

The first authoritative start migrates only from the immutable r6 original
snapshot.  Every later start loads the validated ``CURRENT`` generation and
never falls back to mutable legacy JSON files.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from uuid import UUID, uuid4

from .compat import (
    LEGACY_ROOT_FILE_NAMES,
    LegacyOriginalSnapshot,
    ensure_legacy_original_snapshot,
)
from .persistence import (
    AtomicGenerationStore,
    ConfigGenerationCoordinator,
    DecodedGenerationSnapshot,
    GenerationSnapshot,
    NoCommittedGenerationError,
    ensure_windows_path_budget,
)
from .production import (
    PRODUCTION_ROOT_NAMES,
    PRODUCTION_ROOT_SCHEMA,
    ProductionRoots,
    legacy_production_roots_to_wire,
    production_wire_roots_to_legacy,
)
from .v2.manager import config_manager

AUTHORITATIVE_STORE_DIRECTORY_NAME = ".config-v2-authoritative"
ROLLBACK_EXPORT_DIRECTORY_NAME = ".config-v2-r6-rollback"
_MAX_ORIGINAL_SNAPSHOT_GENERATION = f"original-{'f' * 24}"


class AuthoritativeConfigurationError(RuntimeError):
    """Authoritative bootstrap failed without retaining configuration data."""

    error_code = "authoritative_configuration_error"


class LegacySnapshotDecodeError(AuthoritativeConfigurationError):
    """One immutable legacy root is not a valid JSON object."""

    error_code = "legacy_snapshot_decode_error"


class AuthoritativeRuntimeOwnershipError(AuthoritativeConfigurationError):
    """Another runtime already owns the process-global prepare hook."""

    error_code = "authoritative_runtime_ownership_error"


class RollbackExportError(AuthoritativeConfigurationError):
    """A rollback bundle target exists or could not be published completely."""

    error_code = "rollback_export_error"


@dataclass(frozen=True)
class AuthoritativeRuntimeState:
    """Payload-free identity of the active authoritative generation."""

    source_snapshot_generation: str
    generation: str
    revision: int
    transaction_id: str
    initialized_from: str


_OWNER_LOCK = threading.Lock()
_OWNER: object | None = None


def _claim_owner(token: object) -> None:
    global _OWNER
    with _OWNER_LOCK:
        if _OWNER is None:
            _OWNER = token
            return
        if _OWNER is token:
            return
        raise AuthoritativeRuntimeOwnershipError(
            "another authoritative configuration runtime owns the process hook"
        )


def _release_owner(token: object) -> None:
    global _OWNER
    with _OWNER_LOCK:
        if _OWNER is not token:
            raise AuthoritativeRuntimeOwnershipError(
                "authoritative configuration runtime ownership changed"
            )
        _OWNER = None


def load_legacy_original_roots(
    snapshot: LegacyOriginalSnapshot,
) -> Mapping[str, object | None]:
    """Read and integrity-check the eight immutable legacy JSON roots.

    The snapshot creator already validates its manifest.  This function
    rechecks each byte payload against the manifest while reading, closing the
    validation/use gap without ever rendering configuration values.
    """

    try:
        manifest = json.loads(snapshot.manifest_path.read_text(encoding="utf-8"))
        records = manifest["roots"]
    except (KeyError, OSError, UnicodeError, json.JSONDecodeError, TypeError):
        raise LegacySnapshotDecodeError(
            "legacy original snapshot manifest cannot be decoded"
        ) from None
    if (
        not isinstance(records, list)
        or len(records) != len(LEGACY_ROOT_FILE_NAMES)
    ):
        raise LegacySnapshotDecodeError(
            "legacy original snapshot root metadata differs"
        )

    roots: dict[str, object | None] = {}
    for expected_name, record in zip(
        LEGACY_ROOT_FILE_NAMES,
        records,
        strict=True,
    ):
        if (
            not isinstance(record, dict)
            or record.get("name") != expected_name
            or not isinstance(record.get("exists"), bool)
        ):
            raise LegacySnapshotDecodeError(
                f"legacy original root metadata is invalid: root={expected_name}"
            )
        if not record["exists"]:
            roots[expected_name] = None
            continue

        expected_size = record.get("size_bytes")
        expected_hash = record.get("sha256")
        if (
            not isinstance(expected_size, int)
            or isinstance(expected_size, bool)
            or expected_size < 0
            or not isinstance(expected_hash, str)
        ):
            raise LegacySnapshotDecodeError(
                f"legacy original root integrity is invalid: root={expected_name}"
            )

        path = snapshot.generation_path / "files" / expected_name
        try:
            content = path.read_bytes()
        except OSError:
            raise LegacySnapshotDecodeError(
                f"legacy original root cannot be read: root={expected_name}"
            ) from None
        if (
            len(content) != expected_size
            or hashlib.sha256(content).hexdigest() != expected_hash
        ):
            raise LegacySnapshotDecodeError(
                f"legacy original root integrity mismatch: root={expected_name}"
            )
        try:
            payload = json.loads(content.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise LegacySnapshotDecodeError(
                f"legacy original root is not valid JSON: root={expected_name}"
            ) from None
        if not isinstance(payload, dict):
            raise LegacySnapshotDecodeError(
                f"legacy original root is not an object: root={expected_name}"
            )
        roots[expected_name] = payload

    return MappingProxyType(roots)


def ensure_authoritative_path_budget(config_directory: Path) -> None:
    """Reject unsafe Windows paths before capturing any r6 configuration."""
    store_directory = (
        Path(config_directory)
        / AUTHORITATIVE_STORE_DIRECTORY_NAME
        / _MAX_ORIGINAL_SNAPSHOT_GENERATION
    )
    ensure_windows_path_budget(
        store_directory,
        required_roots=PRODUCTION_ROOT_NAMES,
    )


class AuthoritativeConfigurationRuntime:
    """Own the eight native roots and their durable generation lifecycle."""

    def __init__(self, config_directory: Path) -> None:
        self.config_directory = Path(config_directory).resolve(strict=False)
        self._owner_token = object()
        self._snapshot: LegacyOriginalSnapshot | None = None
        self._store: AtomicGenerationStore | None = None
        self._coordinator: ConfigGenerationCoordinator | None = None
        self._roots: ProductionRoots | None = None
        self._current: GenerationSnapshot | DecodedGenerationSnapshot | None = None
        self._state: AuthoritativeRuntimeState | None = None
        self._owns_hook = False

    @property
    def roots(self) -> ProductionRoots:
        if self._roots is None:
            raise RuntimeError("authoritative configuration is not initialized")
        return self._roots

    @property
    def state(self) -> AuthoritativeRuntimeState:
        if self._state is None:
            raise RuntimeError("authoritative configuration is not initialized")
        return self._state

    @property
    def store_directory(self) -> Path:
        snapshot = self._snapshot
        if snapshot is None:
            raise RuntimeError("authoritative configuration is not initialized")
        # The immutable original generation is part of the path, binding
        # CURRENT to the exact r6 source without a second non-atomic sidecar.
        return (
            self.config_directory
            / AUTHORITATIVE_STORE_DIRECTORY_NAME
            / snapshot.generation
        )

    async def initialize(self) -> AuthoritativeRuntimeState:
        if self._state is not None:
            return self._state

        ensure_authoritative_path_budget(self.config_directory)
        snapshot = ensure_legacy_original_snapshot(self.config_directory)
        self._snapshot = snapshot
        store = AtomicGenerationStore(
            self.store_directory,
            required_roots=PRODUCTION_ROOT_NAMES,
        )
        coordinator = ConfigGenerationCoordinator(
            store,
            required_roots=PRODUCTION_ROOT_NAMES,
            schema=PRODUCTION_ROOT_SCHEMA,
        )
        self._store = store
        self._coordinator = coordinator

        roots: ProductionRoots | None = None
        initialized_from: str
        try:
            try:
                current: GenerationSnapshot | DecodedGenerationSnapshot = (
                    coordinator.load_current()
                )
            except NoCommittedGenerationError:
                legacy_roots = load_legacy_original_roots(snapshot)
                wires = legacy_production_roots_to_wire(legacy_roots)
                roots = ProductionRoots(wires)
                await roots.activate()
                current = await coordinator.commit(
                    roots.roots,
                    expected_generation=None,
                    expected_revision=0,
                    transaction_id=uuid4(),
                )
                initialized_from = "legacy-original"
            else:
                roots = ProductionRoots(current.roots)
                await roots.activate()
                initialized_from = "current-generation"

            _claim_owner(self._owner_token)
            self._owns_hook = True
            self._roots = roots
            self._current = current
            config_manager.configure_prepare_commit_hook(self._prepare_commit)
            self._state = self._make_state(initialized_from)
            return self._state
        except BaseException:
            if self._owns_hook:
                config_manager.configure_prepare_commit_hook(None)
                self._owns_hook = False
                _release_owner(self._owner_token)
            if roots is not None:
                roots.dispose()
            self._roots = None
            self._current = None
            self._state = None
            raise

    async def _prepare_commit(self, transaction_id: UUID) -> None:
        coordinator = self._coordinator
        current = self._current
        roots = self._roots
        if coordinator is None or current is None or roots is None:
            raise AuthoritativeConfigurationError(
                "authoritative prepare hook is not initialized"
            )
        committed = await coordinator.commit_transaction(
            roots.roots,
            expected_generation=current.generation,
            expected_revision=current.revision,
        )
        if committed.transaction_id != transaction_id.hex:
            raise AuthoritativeConfigurationError(
                "durable generation transaction identity differs"
            )
        self._current = committed
        self._state = self._make_state("current-generation")

    def _make_state(self, initialized_from: str) -> AuthoritativeRuntimeState:
        snapshot = self._snapshot
        current = self._current
        if snapshot is None or current is None:
            raise RuntimeError("authoritative runtime state is incomplete")
        return AuthoritativeRuntimeState(
            source_snapshot_generation=snapshot.generation,
            generation=current.generation,
            revision=current.revision,
            transaction_id=current.transaction_id,
            initialized_from=initialized_from,
        )

    def export_r6_rollback_bundle(
        self,
        export_parent: Path | None = None,
    ) -> Path:
        """Publish all eight ciphertext-only legacy JSON roots atomically.

        The returned directory is a standalone rollback bundle.  It never
        overwrites live ``config`` files, the frozen r6 release, or an existing
        bundle.  A failed staging directory is retained for diagnosis.
        """

        coordinator = self._coordinator
        if coordinator is None or self._state is None:
            raise RuntimeError("authoritative configuration is not initialized")
        decoded = coordinator.load_current()
        legacy = production_wire_roots_to_legacy(decoded.roots)

        parent = (
            self.config_directory / ROLLBACK_EXPORT_DIRECTORY_NAME
            if export_parent is None
            else Path(export_parent).resolve(strict=False)
        )
        parent.mkdir(parents=True, exist_ok=True)
        final_path = parent / f"r6-rollback-{decoded.generation}"
        if final_path.exists():
            raise RollbackExportError(
                "r6 rollback bundle target already exists"
            )

        staging_path = Path(
            tempfile.mkdtemp(prefix=".pending-r6-rollback-", dir=str(parent))
        )
        root_records: list[dict[str, object]] = []
        try:
            for file_name in LEGACY_ROOT_FILE_NAMES:
                payload = legacy[file_name]
                content = (
                    json.dumps(
                        payload,
                        ensure_ascii=False,
                        sort_keys=True,
                        indent=4,
                    )
                    + "\n"
                ).encode("utf-8")
                path = staging_path / file_name
                with path.open("xb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                root_records.append(
                    {
                        "name": file_name,
                        "size_bytes": len(content),
                        "sha256": hashlib.sha256(content).hexdigest(),
                    }
                )

            manifest = {
                "schema_version": 1,
                "kind": "auto-mas-r6-config-rollback",
                "source_snapshot_generation": (
                    self.state.source_snapshot_generation
                ),
                "source_generation": decoded.generation,
                "source_revision": decoded.revision,
                "roots": root_records,
            }
            manifest_bytes = (
                json.dumps(
                    manifest,
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=4,
                )
                + "\n"
            ).encode("utf-8")
            with (staging_path / "manifest.json").open("xb") as stream:
                stream.write(manifest_bytes)
                stream.flush()
                os.fsync(stream.fileno())

            os.rename(staging_path, final_path)
        except BaseException:
            # Retain uncertain staging evidence; never delete or overwrite it.
            raise
        return final_path

    def close(self) -> None:
        if self._owns_hook:
            config_manager.configure_prepare_commit_hook(None)
            self._owns_hook = False
            _release_owner(self._owner_token)
        if self._roots is not None:
            self._roots.dispose()
        self._roots = None
        self._current = None
        self._state = None


__all__ = [
    "AUTHORITATIVE_STORE_DIRECTORY_NAME",
    "ROLLBACK_EXPORT_DIRECTORY_NAME",
    "AuthoritativeConfigurationError",
    "AuthoritativeConfigurationRuntime",
    "AuthoritativeRuntimeOwnershipError",
    "AuthoritativeRuntimeState",
    "LegacySnapshotDecodeError",
    "RollbackExportError",
    "ensure_authoritative_path_budget",
    "load_legacy_original_roots",
]
