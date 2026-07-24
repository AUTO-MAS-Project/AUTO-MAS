"""Config v2 persistence facade."""

from __future__ import annotations

from pathlib import Path

from ..v2.wire import WireDict, write_wire_toml
from .coordinator import (
    ConfigGenerationCoordinator,
    DecodedGenerationSnapshot,
    GenerationCoordinatorError,
    RootDecodeError,
    RootSchemaError,
    RootSnapshotError,
    SerializedRootSnapshot,
)
from .generation_store import (
    FAULT_POINTS,
    AtomicGenerationStore,
    GenerationConflictError,
    GenerationIntegrityError,
    GenerationPathLengthError,
    GenerationRecoveryRequiredError,
    GenerationSnapshot,
    GenerationStoreError,
    NoCommittedGenerationError,
    OrphanRecord,
    ensure_windows_path_budget,
)


def atomic_write_toml(
    path: Path,
    data: WireDict,
    *,
    backup: bool = True,
    fsync: bool = True,
) -> Path:
    """Atomically write TOML and propagate every write/restore failure."""
    resolved = Path(path)
    write_wire_toml(resolved, data, backup=backup, fsync=fsync)
    return resolved


__all__ = [
    "FAULT_POINTS",
    "AtomicGenerationStore",
    "ConfigGenerationCoordinator",
    "DecodedGenerationSnapshot",
    "GenerationConflictError",
    "GenerationCoordinatorError",
    "GenerationIntegrityError",
    "GenerationPathLengthError",
    "GenerationRecoveryRequiredError",
    "GenerationSnapshot",
    "GenerationStoreError",
    "NoCommittedGenerationError",
    "OrphanRecord",
    "RootDecodeError",
    "RootSchemaError",
    "RootSnapshotError",
    "SerializedRootSnapshot",
    "atomic_write_toml",
    "ensure_windows_path_budget",
]
