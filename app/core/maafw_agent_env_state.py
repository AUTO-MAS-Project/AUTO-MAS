"""Authoritative, file-backed state for MaaFW environment preparation.

The editor is intentionally not the owner of preparation state.  This small
sidecar lets the backend answer a repeated prepare request by ``scriptId`` and
the current project fingerprint, including Managed records whose public
configuration does not expose the checkout path.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_STATE_VERSION = 1
_STATE_FILE_NAME = "maafw_agent_env_state.json"
_PROJECT_INPUTS = (
    "interface.json",
    "interface.jsonc",
    ".auto_mas_maafw_project.json",
    "requirements.txt",
    "pyproject.toml",
    "uv.lock",
)
_STATE_LOCK = threading.RLock()
_MANAGED_BINDING_KEYS = (
    "projectId",
    "version",
    "storeId",
    "runRootId",
    "runtimeId",
    "poolId",
)


def _state_path() -> Path:
    return Path.cwd() / "config" / _STATE_FILE_NAME


def _normalise_path(value: str | Path) -> str:
    # ``Path.resolve`` preserves the caller's spelling on Windows.  Cache
    # lookups must still hit when an editor supplies the same directory with a
    # different drive/segment case, so apply the platform's normal case rule
    # after resolving symlinks and relative segments.
    return os.path.normcase(
        str(Path(value).expanduser().resolve(strict=False))
    )


def _normalise_binding_identity(value: Mapping[str, Any] | None) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        return None
    normalized: dict[str, str] = {}
    for key in _MANAGED_BINDING_KEYS:
        raw = value.get(key, "")
        if not isinstance(raw, str):
            return None
        normalized[key] = raw.strip()
    return normalized


def _is_complete_binding_identity(value: Mapping[str, str] | None) -> bool:
    return value is not None and all(value.get(key) for key in _MANAGED_BINDING_KEYS)


def _is_cached_data_bound_to_identity(
    data: Mapping[str, Any],
    binding_identity: Mapping[str, str],
) -> bool:
    for key in ("runtimeId", "poolId"):
        raw = data.get(key)
        if not isinstance(raw, str) or raw.strip() != binding_identity[key]:
            return False
    return True


def _read_state() -> dict[str, Any] | None:
    path = _state_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict) or raw.get("version") != _STATE_VERSION:
        return None
    scripts = raw.get("scripts")
    if not isinstance(scripts, dict):
        return None
    return raw


def _write_state(state: Mapping[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{_STATE_FILE_NAME}.",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def project_fingerprint(project_path: str | Path) -> str | None:
    """Hash the project inputs that determine the Runner route."""

    root = Path(project_path).expanduser().resolve(strict=False)
    if not root.is_dir():
        return None

    digest = hashlib.sha256()
    found_interface = False
    for relative_name in _PROJECT_INPUTS:
        candidate = root / relative_name
        if not candidate.is_file():
            digest.update(f"missing:{relative_name}\0".encode("utf-8"))
            continue
        if relative_name in {"interface.json", "interface.jsonc"}:
            found_interface = True
        try:
            content = candidate.read_bytes()
        except OSError:
            return None
        digest.update(relative_name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)

    return digest.hexdigest() if found_interface else None


def _is_cached_data_valid(data: Mapping[str, Any], project_path: Path) -> bool:
    agents = data.get("agents")
    if not isinstance(agents, list):
        return False
    if not isinstance(data.get("agentCount"), int) or data["agentCount"] != len(agents):
        return False
    if not isinstance(data.get("logs"), list) or not all(
        isinstance(item, str) for item in data["logs"]
    ):
        return False
    for agent in agents:
        if not isinstance(agent, Mapping):
            return False
        if not isinstance(agent.get("childExec"), str) or not isinstance(
            agent.get("executable"), str
        ):
            return False
        for key in ("executable", "isolatedVenvPath"):
            raw_path = agent.get(key)
            if not raw_path:
                continue
            candidate = Path(str(raw_path))
            if candidate.is_absolute():
                if key == "executable" and not candidate.is_file():
                    return False
                if key == "isolatedVenvPath" and not candidate.is_dir():
                    return False
    # Every prepared MaaFW plan is tied to an immutable Runtime Pool entry.
    # A project fingerprint alone cannot prove that entry still exists after
    # GC or a pool relocation, so every cache requires its identity and paths.
    runtime_keys = ("runtimeId", "poolId", "pythonExecutable", "venvPath")
    runtime_values = tuple(data.get(key) for key in runtime_keys)
    if not all(isinstance(value, str) and value.strip() for value in runtime_values):
        return False
    python_executable = Path(str(data["pythonExecutable"]))
    venv_path = Path(str(data["venvPath"]))
    if not python_executable.is_absolute() or not python_executable.is_file():
        return False
    if not venv_path.is_absolute() or not venv_path.is_dir():
        return False
    raw_data_path = str(data.get("path") or "").strip()
    return bool(raw_data_path) and _normalise_path(raw_data_path) == _normalise_path(
        project_path
    )


def load_maafw_agent_env_state(
    script_id: str,
    requested_path: str | Path | None = None,
    *,
    expected_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return a ready result when the backend-owned state is still valid."""

    normalized_script_id = str(script_id or "").strip()
    if not normalized_script_id:
        return None
    with _STATE_LOCK:
        state = _read_state()
        if state is None:
            return None
        entry = state["scripts"].get(normalized_script_id)
        if not isinstance(entry, Mapping):
            return None
        raw_path = str(entry.get("path") or "").strip()
        fingerprint = str(entry.get("fingerprint") or "").strip()
        data = entry.get("data")
        if not raw_path or not fingerprint or not isinstance(data, Mapping):
            return None
        project_path = Path(raw_path).resolve(strict=False)
        if requested_path and str(requested_path).strip():
            if _normalise_path(requested_path) != _normalise_path(project_path):
                return None
        normalized_expected_binding = _normalise_binding_identity(expected_binding)
        if normalized_expected_binding is None:
            # A Managed cache must never be reused after the caller loses the
            # ability to resolve its current binding (including a type switch).
            if "bindingIdentity" in entry:
                return None
        else:
            if not _is_complete_binding_identity(normalized_expected_binding):
                return None
            cached_binding = _normalise_binding_identity(
                entry.get("bindingIdentity")
            )
            if (
                cached_binding != normalized_expected_binding
                or not _is_complete_binding_identity(cached_binding)
                or not _is_cached_data_bound_to_identity(
                    data,
                    normalized_expected_binding,
                )
            ):
                return None
        if project_fingerprint(project_path) != fingerprint:
            return None
        if not _is_cached_data_valid(data, project_path):
            return None
        return dict(data)


def save_maafw_agent_env_state(
    script_id: str,
    project_path: str | Path,
    data: Mapping[str, Any],
    *,
    expected_fingerprint: str,
    binding_identity: Mapping[str, Any] | None = None,
) -> bool:
    """Atomically save one successful prepare result for a script."""

    normalized_script_id = str(script_id or "").strip()
    normalized_expected_fingerprint = (
        str(expected_fingerprint or "").strip().casefold()
    )
    root = Path(project_path).expanduser().resolve(strict=False)
    if not normalized_script_id or not isinstance(data, Mapping):
        return False
    if (
        len(normalized_expected_fingerprint) != 64
        or any(
            character not in "0123456789abcdef"
            for character in normalized_expected_fingerprint
        )
    ):
        return False
    if not _is_cached_data_valid(data, root):
        return False
    normalized_binding = _normalise_binding_identity(binding_identity)
    if binding_identity is not None and (
        not _is_complete_binding_identity(normalized_binding)
        or not _is_cached_data_bound_to_identity(data, normalized_binding)
    ):
        return False
    with _STATE_LOCK:
        fingerprint = project_fingerprint(root)
        if fingerprint != normalized_expected_fingerprint:
            return False
        state = _read_state() or {"version": _STATE_VERSION, "scripts": {}}
        scripts = state.setdefault("scripts", {})
        if not isinstance(scripts, dict):
            scripts = {}
            state["scripts"] = scripts
        entry: dict[str, Any] = {
            "path": str(root),
            "fingerprint": fingerprint,
            "data": dict(data),
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }
        if normalized_binding is not None:
            entry["bindingIdentity"] = normalized_binding
        scripts[normalized_script_id] = entry
        _write_state(state)
        return True


def invalidate_maafw_agent_env_state(script_id: str) -> None:
    """Drop a script's cached result after resource or script deletion."""

    normalized_script_id = str(script_id or "").strip()
    if not normalized_script_id:
        return
    with _STATE_LOCK:
        state = _read_state()
        if state is None or normalized_script_id not in state["scripts"]:
            return
        state["scripts"].pop(normalized_script_id, None)
        _write_state(state)


__all__ = [
    "invalidate_maafw_agent_env_state",
    "load_maafw_agent_env_state",
    "project_fingerprint",
    "save_maafw_agent_env_state",
]
