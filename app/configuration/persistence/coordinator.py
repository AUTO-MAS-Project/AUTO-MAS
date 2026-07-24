"""Coordinate complete Config v2 roots with immutable generations.

This module is deliberately not connected to the production configuration
gate.  It provides the narrow bridge needed to serialize one complete set of
live Config v2 roots and publish it through :class:`AtomicGenerationStore`.
"""

from __future__ import annotations

import tomllib
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import cast
from uuid import UUID

from ..v2.manager import config_manager
from ..v2.node import ConfigNode
from ..v2.node_state import NodeState
from ..v2.wire import WireDict, serialize_wire_toml
from .generation_store import (
    AtomicGenerationStore,
    GenerationConflictError,
    GenerationSnapshot,
)


class GenerationCoordinatorError(RuntimeError):
    """Base error that never retains or renders configuration payloads."""

    error_code = "generation_coordinator_error"


class RootSchemaError(GenerationCoordinatorError):
    """The configured or supplied root set does not match the exact schema."""

    error_code = "generation_root_schema_error"


class RootSnapshotError(GenerationCoordinatorError):
    """One live root could not be exported as canonical persisted TOML."""

    error_code = "generation_root_snapshot_error"


class RootDecodeError(GenerationCoordinatorError):
    """One stored root is not a strict UTF-8 TOML object."""

    error_code = "generation_root_decode_error"


class TransactionGenerationCommitError(GenerationCoordinatorError):
    """A durable transaction generation could not be safely confirmed."""

    error_code = "transaction_generation_commit_error"


@dataclass(frozen=True)
class SerializedRootSnapshot:
    """A complete canonical TOML snapshot with payload-safe ``repr``."""

    required_roots: tuple[str, ...]
    roots: Mapping[str, bytes] = field(repr=False)


@dataclass(frozen=True)
class DecodedGenerationSnapshot:
    """A validated generation decoded into independent Wire dictionaries."""

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
    roots: Mapping[str, WireDict] = field(repr=False)


class ConfigGenerationCoordinator:
    """Serialize and atomically publish one exact Config v2 root schema."""

    def __init__(
        self,
        store: AtomicGenerationStore,
        *,
        required_roots: Collection[str],
        schema: Mapping[str, type[ConfigNode]],
    ) -> None:
        if isinstance(required_roots, (str, bytes)):
            raise TypeError("required_roots must be a collection of root names")
        requested_roots = tuple(required_roots)
        store_roots = tuple(store.required_roots)
        if (
            len(requested_roots) != len(store_roots)
            or set(requested_roots) != set(store_roots)
        ):
            raise RootSchemaError(
                "coordinator required roots do not match the generation store"
            )
        if not isinstance(schema, Mapping):
            raise TypeError("schema must map root names to ConfigNode types")
        if len(schema) != len(store_roots) or set(schema) != set(store_roots):
            raise RootSchemaError(
                "coordinator schema does not match the required root set"
            )

        checked_schema: dict[str, type[ConfigNode]] = {}
        for name in store_roots:
            node_type = schema[name]
            if not isinstance(node_type, type) or not issubclass(
                node_type,
                ConfigNode,
            ):
                raise RootSchemaError(
                    "coordinator schema values must be ConfigNode types"
                )
            checked_schema[name] = node_type

        self._store = store
        self._required_roots = store_roots
        self._schema = MappingProxyType(checked_schema)

    @property
    def required_roots(self) -> tuple[str, ...]:
        """Return the canonical root order owned by the generation store."""
        return self._required_roots

    @property
    def schema(self) -> Mapping[str, type[ConfigNode]]:
        """Return the immutable exact root schema."""
        return self._schema

    async def snapshot(
        self,
        roots: Mapping[str, ConfigNode],
    ) -> SerializedRootSnapshot:
        """Export every required active root before performing any store write."""
        async with config_manager.snapshot_barrier():
            return await self._snapshot_unlocked(roots)

    async def _snapshot_unlocked(
        self,
        roots: Mapping[str, ConfigNode],
        *,
        include_staged: bool = False,
    ) -> SerializedRootSnapshot:
        """Export roots while the caller owns the manager snapshot barrier."""
        live_roots = self._validate_live_roots(roots)
        serialized: dict[str, bytes] = {}

        for name in self._required_roots:
            root = live_roots[name]
            source = root.effective if include_staged else root
            if (
                source._activation_state != NodeState.ACTIVE
                or source._deleted
            ):
                raise RootSnapshotError(
                    f"configuration root is not persistable: root={name}"
                )
            snapshot_failed = False
            try:
                if include_staged:
                    payload = await root.to_dict(
                        if_decrypt=False,
                        include_reactive=False,
                        include_staged=True,
                    )
                else:
                    # Preserve compatibility with existing ConfigNode
                    # subclasses that override the historical two-keyword
                    # signature.  Staged export is a new explicit contract.
                    payload = await root.to_dict(
                        if_decrypt=False,
                        include_reactive=False,
                    )
                source = root.effective if include_staged else root
                if (
                    source._activation_state != NodeState.ACTIVE
                    or source._deleted
                    or not isinstance(payload, dict)
                ):
                    raise ValueError("root state changed during export")
                canonical = serialize_wire_toml(cast(WireDict, payload))
                restored = tomllib.loads(canonical)
                if not isinstance(restored, dict) or not _wire_equal(
                    payload,
                    restored,
                ):
                    raise ValueError("canonical TOML round-trip changed data")
                serialized[name] = canonical.encode("utf-8", errors="strict")
            except Exception:
                # Export and serializer exceptions can contain plaintext or
                # ciphertext.  Replace them with root identity only and do not
                # retain the original exception as __cause__/__context__.  The
                # replacement is raised after leaving the except block because
                # ``raise ... from None`` only hides, but still retains,
                # ``__context__``.
                snapshot_failed = True
            if snapshot_failed:
                raise RootSnapshotError(
                    f"configuration root snapshot failed: root={name}"
                )

        return SerializedRootSnapshot(
            required_roots=self._required_roots,
            roots=MappingProxyType(serialized),
        )

    async def commit(
        self,
        roots: Mapping[str, ConfigNode],
        *,
        expected_generation: str | None,
        expected_revision: int,
        transaction_id: UUID | str,
    ) -> GenerationSnapshot:
        """Publish one complete snapshot with an explicit strict CAS."""
        async with config_manager.snapshot_barrier():
            captured = await self._snapshot_unlocked(roots)
            return self._commit_store_with_confirmation(
                captured,
                expected_generation=expected_generation,
                expected_revision=expected_revision,
                transaction_id=transaction_id,
            )

    async def commit_transaction(
        self,
        roots: Mapping[str, ConfigNode],
        *,
        expected_generation: str | None,
        expected_revision: int,
    ) -> GenerationSnapshot:
        """Durably publish the current prepare-commit workspace generation."""
        context = config_manager.current
        if context is None or not context.preparing_commit:
            raise RuntimeError(
                "transaction generation commit requires the current owner "
                "prepare-commit hook"
            )
        captured = await self._snapshot_unlocked(
            roots,
            include_staged=True,
        )
        return self._commit_store_with_confirmation(
            captured,
            expected_generation=expected_generation,
            expected_revision=expected_revision,
            transaction_id=context.transaction_id,
        )

    def _commit_store_with_confirmation(
        self,
        captured: SerializedRootSnapshot,
        *,
        expected_generation: str | None,
        expected_revision: int,
        transaction_id: UUID | str,
    ) -> GenerationSnapshot:
        """Commit or confirm an after-CURRENT exception without replaying it."""
        try:
            transaction_hex = UUID(str(transaction_id)).hex
        except (AttributeError, TypeError, ValueError):
            raise ValueError("transaction_id must be a UUID") from None

        commit_failed = False
        commit_conflicted = False
        try:
            committed = self._store.commit(
                captured.roots,
                expected_generation=expected_generation,
                expected_revision=expected_revision,
                transaction_id=transaction_hex,
            )
        except GenerationConflictError:
            commit_failed = True
            commit_conflicted = True
        except Exception:
            # Fault hooks and integration exceptions are not trusted to be
            # payload-safe.  Inspect CURRENT after leaving the except block so
            # a replacement error never survives as exception context.
            commit_failed = True
        if not commit_failed:
            return committed

        read_failed = False
        try:
            current = self._store.read_current()
        except Exception:
            read_failed = True
        if (
            not read_failed
            and current.transaction_id == transaction_hex
            and current.parent_generation == expected_generation
            and current.parent_revision == expected_revision
            and current.rollback_of is None
            and dict(current.roots) == dict(captured.roots)
        ):
            return current

        if commit_conflicted:
            raise GenerationConflictError(
                "configuration generation compare-and-swap conflict"
            )
        raise TransactionGenerationCommitError(
            "transaction generation commit was not durably confirmed"
        )

    def load_current(self) -> DecodedGenerationSnapshot:
        """Load and decode CURRENT without mutating any supplied live root."""
        return self._decode_snapshot(self._store.read_current())

    def rollback(
        self,
        target_generation: str,
        *,
        expected_generation: str,
        expected_revision: int,
        transaction_id: UUID | str,
    ) -> DecodedGenerationSnapshot:
        """Delegate rollback to the store and decode its complete new snapshot."""
        snapshot = self._store.rollback(
            target_generation,
            expected_generation=expected_generation,
            expected_revision=expected_revision,
            transaction_id=transaction_id,
        )
        return self._decode_snapshot(snapshot)

    def _validate_live_roots(
        self,
        roots: Mapping[str, ConfigNode],
    ) -> dict[str, ConfigNode]:
        if not isinstance(roots, Mapping):
            raise TypeError("roots must map root names to ConfigNode instances")
        if len(roots) != len(self._required_roots) or set(roots) != set(
            self._required_roots
        ):
            raise RootSchemaError(
                "live root mapping does not match the required root set"
            )

        checked: dict[str, ConfigNode] = {}
        for name in self._required_roots:
            root = roots[name]
            if type(root) is not self._schema[name]:
                raise RootSchemaError(
                    f"live root does not match the exact schema: root={name}"
                )
            checked[name] = root
        return checked

    def _decode_snapshot(
        self,
        snapshot: GenerationSnapshot,
    ) -> DecodedGenerationSnapshot:
        raw_roots = snapshot.roots
        if len(raw_roots) != len(self._required_roots) or set(raw_roots) != set(
            self._required_roots
        ):
            raise RootDecodeError(
                "stored generation does not contain the required root set"
            )

        decoded: dict[str, WireDict] = {}
        for name in self._required_roots:
            raw = raw_roots[name]
            if not isinstance(raw, bytes):
                raise RootDecodeError(
                    f"stored generation root is not bytes: root={name}"
                )
            decode_failed = False
            try:
                text = raw.decode("utf-8", errors="strict")
                payload = tomllib.loads(text)
            except (UnicodeDecodeError, tomllib.TOMLDecodeError):
                decode_failed = True
            if decode_failed:
                raise RootDecodeError(
                    f"stored generation root is not valid UTF-8 TOML: root={name}"
                )
            if not isinstance(payload, dict):
                raise RootDecodeError(
                    f"stored generation root is not an object: root={name}"
                )
            decoded[name] = cast(WireDict, payload)

        return DecodedGenerationSnapshot(
            generation=snapshot.generation,
            revision=snapshot.revision,
            parent_generation=snapshot.parent_generation,
            parent_revision=snapshot.parent_revision,
            parent_manifest_sha256=snapshot.parent_manifest_sha256,
            transaction_id=snapshot.transaction_id,
            rollback_of=snapshot.rollback_of,
            root_set_sha256=snapshot.root_set_sha256,
            request_cas_sha256=snapshot.request_cas_sha256,
            manifest_sha256=snapshot.manifest_sha256,
            roots=MappingProxyType(decoded),
        )


def _wire_equal(expected: object, actual: object) -> bool:
    """Compare a Wire value with its TOML round-trip without rendering values."""
    if isinstance(expected, (UUID, Path)):
        expected = str(expected)

    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False
        normalized: dict[object, object] = {}
        for key, value in expected.items():
            normalized_key = str(key) if isinstance(key, UUID) else key
            if normalized_key in normalized:
                return False
            normalized[normalized_key] = value
        if set(normalized) != set(actual):
            return False
        return all(
            _wire_equal(value, actual[key])
            for key, value in normalized.items()
        )

    if isinstance(expected, list):
        if not isinstance(actual, list) or len(expected) != len(actual):
            return False
        return all(
            _wire_equal(expected_item, actual_item)
            for expected_item, actual_item in zip(
                expected,
                actual,
                strict=True,
            )
        )

    return type(expected) is type(actual) and expected == actual


__all__ = [
    "ConfigGenerationCoordinator",
    "DecodedGenerationSnapshot",
    "GenerationCoordinatorError",
    "RootDecodeError",
    "RootSchemaError",
    "RootSnapshotError",
    "SerializedRootSnapshot",
    "TransactionGenerationCommitError",
]
