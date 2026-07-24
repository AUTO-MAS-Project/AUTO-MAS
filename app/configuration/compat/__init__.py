"""Safe opt-in bridge from legacy JSON files to Config v2 Wire documents.

The generic bridge intentionally has no schema knowledge.  Consequently it
must never copy an arbitrary legacy document into TOML.  A file-specific codec
has to be registered explicitly and attest that sensitive values are protected
before shadow/canary output is allowed.
"""

from __future__ import annotations

import copy
import tomllib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from .. import (
    CONFIG_V2_MODE,
    CONFIG_V2_MODE_AUTHORITATIVE,
    CONFIG_V2_MODE_CANARY,
    CONFIG_V2_MODE_OFF,
    CONFIG_V2_MODE_SHADOW,
    WireDict,
    serialize_wire_toml,
    write_wire_toml,
)
from ..v2.support.logger import get_logger
from .legacy_original_snapshot import (
    LEGACY_ROOT_FILE_NAMES,
    LegacyOriginalSnapshot,
    LegacyOriginalSnapshotError,
    ensure_legacy_original_snapshot,
)

logger = get_logger("compat")

SHADOW_SUFFIX = ".v2.shadow.toml"
V2_SUFFIX = ".v2.toml"

type PreflightStatus = Literal[
    "empty",
    "no_codec",
    "unsafe_codec",
    "round_trip_mismatch",
    "ready",
]


class LegacyCodec(Protocol):
    """A schema-specific, bidirectional legacy conversion contract."""

    def encode(self, legacy_data: dict[str, Any]) -> WireDict:
        """Convert one known legacy schema into Config v2 Wire data."""

    def decode(self, wire_data: WireDict) -> dict[str, Any]:
        """Convert Wire data back to the same legacy logical shape."""


@dataclass(frozen=True)
class LegacyPreflight:
    status: PreflightStatus
    wire: WireDict | None = None
    diff_paths: tuple[str, ...] = ()

    @property
    def can_write(self) -> bool:
        return self.status == "ready" and self.wire is not None


@dataclass(frozen=True)
class _CodecRegistration:
    codec: LegacyCodec
    secrets_protected: bool


class LegacyWireAdapter:
    """Run a non-destructive, codec-gated legacy migration preflight."""

    def __init__(self) -> None:
        self._codecs: dict[str, _CodecRegistration] = {}
        self._diff_log: list[dict[str, object]] = []

    @property
    def mode(self) -> str:
        return CONFIG_V2_MODE

    @property
    def is_shadow(self) -> bool:
        return self.mode == CONFIG_V2_MODE_SHADOW

    @property
    def is_authoritative(self) -> bool:
        return self.mode == CONFIG_V2_MODE_AUTHORITATIVE

    @property
    def is_canary(self) -> bool:
        return self.mode == CONFIG_V2_MODE_CANARY

    @property
    def is_off(self) -> bool:
        return self.mode == CONFIG_V2_MODE_OFF

    def register_codec(
        self,
        file_name: str,
        codec: LegacyCodec,
        *,
        secrets_protected: bool,
    ) -> None:
        """Register a real schema codec for one legacy file name.

        ``secrets_protected`` must be an explicit decision by the codec owner.
        Generic migration cannot infer which arbitrary strings are secrets.
        """
        key = file_name.strip().casefold()
        if not key or Path(file_name).name != file_name:
            raise ValueError("file_name must be a plain legacy file name")
        if key in self._codecs:
            raise ValueError(f"legacy codec already registered: {file_name}")
        self._codecs[key] = _CodecRegistration(codec, secrets_protected)

    def unregister_codec(self, file_name: str) -> None:
        self._codecs.pop(file_name.casefold(), None)

    def preflight(
        self,
        legacy_path: Path,
        legacy_data: dict[str, Any],
    ) -> LegacyPreflight:
        """Prove a shadow write is schema-aware and lossless before writing."""
        if not legacy_data:
            return LegacyPreflight("empty")

        registration = self._codecs.get(legacy_path.name.casefold())
        if registration is None:
            return LegacyPreflight("no_codec")
        if not registration.secrets_protected:
            return LegacyPreflight("unsafe_codec")

        wire = registration.codec.encode(copy.deepcopy(legacy_data))
        if not isinstance(wire, dict):
            raise TypeError("legacy codec encode() must return a dictionary")
        # Prove the codec against the representation that will actually be
        # read back from TOML.  The serializer intentionally removes ``None``
        # and normalizes Path/UUID values, so an in-memory-only comparison
        # would otherwise certify a lossy document.
        serialized_wire = tomllib.loads(serialize_wire_toml(wire))
        restored = registration.codec.decode(copy.deepcopy(serialized_wire))
        if not isinstance(restored, dict):
            raise TypeError("legacy codec decode() must return a dictionary")

        diff_paths = tuple(self._compute_diff_paths(legacy_data, restored))
        if diff_paths:
            return LegacyPreflight(
                "round_trip_mismatch",
                diff_paths=diff_paths,
            )
        return LegacyPreflight("ready", wire=copy.deepcopy(wire))

    def shadow_write(
        self,
        legacy_path: Path,
        legacy_data: dict[str, Any],
    ) -> Path | None:
        """Write only after safe preflight; otherwise leave every file intact.

        Atomic writer failures deliberately propagate.  In particular, this
        method never removes an existing generated file as error cleanup.
        """
        if self.is_off:
            return None

        result = self.preflight(legacy_path, legacy_data)
        if not result.can_write:
            if result.diff_paths:
                self._diff_log.append(
                    {
                        "timestamp": datetime.now().isoformat(),
                        "legacy_path": str(legacy_path),
                        "status": result.status,
                        "diff_paths": list(result.diff_paths),
                    }
                )
            logger.debug(
                "legacy v2 output skipped for %s: %s",
                legacy_path.name,
                result.status,
            )
            return None

        output_path = legacy_path.with_suffix(
            SHADOW_SUFFIX if self.is_shadow else V2_SUFFIX
        )
        assert result.wire is not None
        write_wire_toml(output_path, result.wire)
        logger.debug("legacy v2 output written: %s", output_path)
        return output_path

    @classmethod
    def _compute_diff_paths(
        cls,
        expected: object,
        actual: object,
        prefix: str = "$",
    ) -> list[str]:
        """Return structural/value mismatch paths without retaining values."""
        if isinstance(expected, dict) and isinstance(actual, dict):
            paths: list[str] = []
            for key in sorted(set(expected) | set(actual), key=str):
                path = f"{prefix}.{key}"
                if key not in expected or key not in actual:
                    paths.append(path)
                else:
                    paths.extend(
                        cls._compute_diff_paths(expected[key], actual[key], path)
                    )
            return paths
        if isinstance(expected, list) and isinstance(actual, list):
            paths = []
            for index in range(max(len(expected), len(actual))):
                path = f"{prefix}[{index}]"
                if index >= len(expected) or index >= len(actual):
                    paths.append(path)
                else:
                    paths.extend(
                        cls._compute_diff_paths(expected[index], actual[index], path)
                    )
            return paths
        if type(expected) is not type(actual) or expected != actual:
            return [prefix]
        return []

    @property
    def diff_log(self) -> list[dict[str, object]]:
        return copy.deepcopy(self._diff_log)

    def clear_diff_log(self) -> None:
        self._diff_log.clear()


# No codecs are registered by default. Shadow mode is therefore a safe
# preflight-only mode until each real legacy schema gets a reviewed adapter.
legacy_adapter = LegacyWireAdapter()


__all__ = [
    "LEGACY_ROOT_FILE_NAMES",
    "LegacyCodec",
    "LegacyOriginalSnapshot",
    "LegacyOriginalSnapshotError",
    "LegacyPreflight",
    "LegacyWireAdapter",
    "ensure_legacy_original_snapshot",
    "legacy_adapter",
]
