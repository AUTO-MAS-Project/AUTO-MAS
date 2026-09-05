"""Contracts shared by the resumable MaaFW project updater."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Literal

ArtifactType = Literal["full", "delta"]
UpdateStatus = Literal[
    "discovered",
    "plan_validated",
    "downloading",
    "paused",
    "downloaded",
    "verified",
    "staged",
    "applying",
    "post_validating",
    "committed",
    "cancelled",
    "failed",
    "rolled_back",
    "recovery_required",
]

RESERVED_PROJECT_DIRS = frozenset({".mas-update", ".mas-update-cache"})


def artifact_id_for(
    source: str,
    version: str,
    download_url: str,
    *,
    explicit: str | None = None,
    asset_name: str = "",
) -> str:
    """Build a stable identity that does not depend on signed URL queries."""

    value = str(explicit or "").strip().lower()
    if re.fullmatch(r"[0-9a-f]{24}", value):
        return value
    parsed_name = Path(download_url.split("?", 1)[0].split("#", 1)[0]).name
    identity = "\0".join(
        (
            str(source or "").strip().casefold(),
            str(version or "").strip(),
            str(asset_name or parsed_name).strip().casefold(),
        )
    )
    if value:
        identity += f"\0{value}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def normalise_sha256(value: Any) -> str | None:
    raw = str(value or "").strip().lower()
    if raw.startswith("sha256:"):
        raw = raw[7:].strip()
    if len(raw) != 64 or any(char not in "0123456789abcdef" for char in raw):
        return None
    return raw


def project_fingerprint(project_path: str | Path) -> str | None:
    """Hash project inputs while excluding updater-owned working files."""

    root = Path(project_path).expanduser().resolve(strict=False)
    if not root.is_dir():
        return None
    digest = hashlib.sha256()
    files: list[Path] = []
    for candidate in root.rglob("*"):
        try:
            relative = candidate.relative_to(root)
        except ValueError:
            continue
        if any(part in RESERVED_PROJECT_DIRS for part in relative.parts):
            continue
        if candidate.is_symlink():
            return None
        if candidate.is_file():
            files.append(candidate)
    for candidate in sorted(
        files, key=lambda item: item.relative_to(root).as_posix().casefold()
    ):
        relative = candidate.relative_to(root).as_posix()
        try:
            content = candidate.read_bytes()
        except OSError:
            return None
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


def safe_relative_path(raw_path: str) -> str:
    normalized = str(raw_path or "").strip().replace("\\", "/")
    candidate = Path(normalized)
    if (
        not normalized
        or candidate.is_absolute()
        or candidate.drive
        or candidate.root
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        raise ValueError(f"update package contains unsafe path: {raw_path}")
    if candidate.parts[0] in RESERVED_PROJECT_DIRS:
        raise ValueError(f"update package cannot write to reserved path: {raw_path}")
    return candidate.as_posix()


__all__ = [
    "ArtifactType",
    "RESERVED_PROJECT_DIRS",
    "UpdateStatus",
    "artifact_id_for",
    "canonical_json",
    "is_within",
    "normalise_sha256",
    "project_fingerprint",
    "safe_relative_path",
]
