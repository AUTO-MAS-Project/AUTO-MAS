from __future__ import annotations

import copy
import functools
import inspect
import json
import os
import platform
import re
import shutil
import stat
import threading
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from packaging.version import InvalidVersion, Version

from .cache import prune_uv_cache

from .identity import (
    IDENTITY_SCHEMA_VERSION,
    RUNTIME_ID_PREFIX,
    build_runtime_identity,
    find_maafw_requirement,
    infer_exact_maafw_version,
    runtime_id_for_identity,
)
from .installer import probe_python_identity, resolve_python_interpreter


POOL_SCHEMA_VERSION = 2
LEGACY_POOL_SCHEMA_VERSION = 1
MANIFEST_SCHEMA_VERSION = 1
POOL_MARKER_NAME = ".auto_mas_maafw_runtime_pool.json"
RUNTIME_MANIFEST_NAME = "manifest.json"
RUNTIME_DIRECTORY_NAME = "runtimes"
STAGING_DIRECTORY_NAME = ".staging"
RUNTIME_ID_RE = re.compile(r"^maafw-runtime-[0-9a-f]{24}$")

RuntimeInstaller = Callable[
    [Path, Sequence[str], dict[str, Any]],
    Mapping[str, Any] | None,
]
RuntimeCachePruner = Callable[..., Mapping[str, Any]]

_LOCKS_GUARD = threading.Lock()
_POOL_LOCKS: dict[str, threading.RLock] = {}


class MaaFWRuntimePoolError(RuntimeError):
    """Raised when a managed MaaFW runtime pool operation is unsafe or invalid."""


class _MaaFWRuntimeEntryStaleError(MaaFWRuntimePoolError):
    """Raised for a recoverable runtime entry that no longer resolves."""


class MaaFWRuntimePool:
    def __init__(
        self,
        root: str | Path,
        *,
        installer: RuntimeInstaller | None = None,
        cache_pruner: RuntimeCachePruner | None = prune_uv_cache,
    ) -> None:
        default_root = Path.cwd() / "config" / "maafw_runtime_pool"
        requested_root = Path(root)
        if not requested_root.is_absolute():
            raise MaaFWRuntimePoolError(
                "configured runtime-pool root must be an absolute path"
            )
        absolute_root = Path(os.path.abspath(requested_root))
        _assert_existing_chain_has_no_reparse(absolute_root)
        if absolute_root.exists() and not absolute_root.is_dir():
            raise MaaFWRuntimePoolError(
                f"runtime-pool root must be a directory: {absolute_root}"
            )
        absolute_root.mkdir(parents=True, exist_ok=True)
        _assert_not_reparse(absolute_root)
        self.root = absolute_root.resolve(strict=True)
        self._is_default_root = _same_path(self.root, default_root)
        self.runtime_root = self.root / RUNTIME_DIRECTORY_NAME
        self.staging_root = self.root / STAGING_DIRECTORY_NAME
        self.python_root = self.root / "python"
        self.installer = installer
        self.cache_pruner = cache_pruner
        self._lock = _pool_lock(self.root)
        self._root_identity: dict[str, Any] = {}
        with self._lock:
            self._initialize()

    @property
    def root_identity(self) -> dict[str, Any]:
        with self._lock:
            self._initialize()
            return copy.deepcopy(self._root_identity)

    @property
    def rootIdentity(self) -> dict[str, Any]:  # noqa: N802 - public JSON contract
        return self.root_identity

    def storage_info(self) -> dict[str, Any]:
        identity = self.root_identity
        return {
            "root": str(self.root),
            "poolId": identity["poolId"],
            "isDefault": self._is_default_root,
            "rootIdentity": identity,
        }

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            self._initialize()
            items: list[dict[str, Any]] = []
            for path in self.runtime_root.glob(f"{RUNTIME_ID_PREFIX}*"):
                if not path.is_dir() or path.is_symlink():
                    continue
                try:
                    manifest = self._read_manifest(path.name)
                    item = self._augment_manifest(manifest)
                except MaaFWRuntimePoolError:
                    continue
                items.append(item)
            return sorted(
                items,
                key=lambda item: str(item.get("lastUsedAt") or ""),
                reverse=True,
            )

    def resolve(
        self,
        requirements: Iterable[str],
        *,
        touch: bool = False,
        python_identity: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        identity = build_runtime_identity(
            requirements,
            python_identity=python_identity,
        )
        runtime_id = runtime_id_for_identity(identity)
        with self._lock:
            self._initialize()
            runtime_dir = self._runtime_dir(runtime_id)
            if not runtime_dir.exists() and not runtime_dir.is_symlink():
                return None
            try:
                manifest = self._read_manifest(runtime_id, expected_identity=identity)
                payload = self._augment_manifest(manifest, verify_python=True)
            except _MaaFWRuntimeEntryStaleError:
                return None
            if touch:
                manifest["lastUsedAt"] = _format_time(_utc_now())
                self._write_manifest(runtime_id, manifest)
                payload["lastUsedAt"] = manifest["lastUsedAt"]
            return payload

    def get(
        self,
        runtime_id: str,
        *,
        touch: bool = False,
    ) -> dict[str, Any] | None:
        with self._lock:
            self._initialize()
            runtime_dir = self._runtime_dir(runtime_id)
            if not runtime_dir.exists() and not runtime_dir.is_symlink():
                return None
            try:
                manifest = self._read_manifest(runtime_id)
                payload = self._augment_manifest(manifest, verify_python=True)
            except _MaaFWRuntimeEntryStaleError:
                return None
            if touch:
                manifest["lastUsedAt"] = _format_time(_utc_now())
                self._write_manifest(runtime_id, manifest)
                payload["lastUsedAt"] = manifest["lastUsedAt"]
            return payload

    def ensure(
        self,
        requirements: Iterable[str],
        *,
        installer: RuntimeInstaller | None = None,
        metadata: Mapping[str, Any] | None = None,
        python_identity: Mapping[str, Any] | None = None,
        bootstrap_python: str | Path | None = None,
    ) -> dict[str, Any]:
        identity = build_runtime_identity(
            requirements,
            python_identity=python_identity,
        )
        canonical_requirements = tuple(identity["requirements"])
        runtime_id = runtime_id_for_identity(identity)
        install = installer or self.installer
        if install is None:
            raise MaaFWRuntimePoolError(
                "runtime does not exist and no installer was provided"
            )
        if bootstrap_python is not None:
            install = _bind_bootstrap_python(install, bootstrap_python)

        with self._lock:
            self._initialize()
            existing = self.resolve(
                canonical_requirements,
                touch=True,
                python_identity=python_identity,
            )
            if existing is not None:
                return existing

            recovery_metadata, quarantine_dir = self._quarantine_stale_runtime(
                runtime_id
            )
            stage_dir = self.staging_root / f"{runtime_id}-{uuid.uuid4().hex}"
            environment_path = stage_dir / "environment"
            stage_created = False
            try:
                self._validate_staging_path(stage_dir, runtime_id)
                stage_dir.mkdir(parents=True, exist_ok=False)
                stage_created = True
                raw_install_result = install(
                    environment_path,
                    canonical_requirements,
                    copy.deepcopy(identity),
                )
                install_result = dict(raw_install_result or {})
                python_relative = self._resolve_installed_python(
                    stage_dir,
                    environment_path,
                    install_result,
                )
                installed_python_identity = _verify_installed_python_identity(
                    stage_dir / python_relative,
                    identity,
                )
                now = _format_time(_utc_now())
                maafw_requirement = find_maafw_requirement(canonical_requirements)
                maafw_version = _optional_string(
                    install_result.pop("maafwVersion", None)
                    or install_result.pop("maafw_version", None)
                ) or infer_exact_maafw_version(maafw_requirement)
                python_patch_version = _optional_string(
                    (
                        installed_python_identity.get("version")
                        if installed_python_identity is not None
                        else None
                    )
                    or install_result.pop("pythonVersion", None)
                    or install_result.pop("python_version", None)
                ) or (
                    str(identity["pythonVersion"])
                    if python_identity is not None
                    else platform.python_version()
                )
                resolved_requirements = _normalize_string_list(
                    install_result.pop("resolvedRequirements", None)
                    or install_result.pop("resolved_requirements", None),
                    "resolvedRequirements",
                )
                manifest = {
                    "schemaVersion": MANIFEST_SCHEMA_VERSION,
                    "kind": "auto-mas-maafw-runtime",
                    "runtimeId": runtime_id,
                    "identity": identity,
                    "selectorRequirements": list(canonical_requirements),
                    # Compatibility alias retained for existing callers.
                    "requirements": list(canonical_requirements),
                    "resolvedRequirements": resolved_requirements,
                    "maafwRequirement": maafw_requirement,
                    "maafwVersion": maafw_version,
                    "pythonPatchVersion": python_patch_version,
                    "environmentRelativePath": "environment",
                    "pythonRelativePath": python_relative.as_posix(),
                    "createdAt": recovery_metadata.get("createdAt", now),
                    "lastUsedAt": now,
                    "pinned": recovery_metadata.get("pinned", False),
                    "references": list(recovery_metadata.get("references", [])),
                    "leases": copy.deepcopy(recovery_metadata.get("leases", {})),
                    "metadata": _json_compatible(
                        metadata
                        if metadata is not None
                        else recovery_metadata.get("metadata", {})
                    ),
                    "installerMetadata": _json_compatible(install_result),
                }
                _write_json_atomic(stage_dir / RUNTIME_MANIFEST_NAME, manifest)

                runtime_dir = self._runtime_dir(runtime_id)
                if runtime_dir.exists():
                    self._remove_staging_dir(stage_dir, runtime_id)
                    return self._augment_manifest(
                        self._read_manifest(runtime_id, expected_identity=identity),
                        verify_python=True,
                    )
                try:
                    stage_dir.replace(runtime_dir)
                except OSError:
                    if not runtime_dir.is_dir():
                        raise
                    self._remove_staging_dir(stage_dir, runtime_id)
                return self._augment_manifest(
                    self._read_manifest(runtime_id, expected_identity=identity),
                    verify_python=True,
                )
            except Exception as install_error:
                cleanup_error: Exception | None = None
                if stage_created and (stage_dir.exists() or stage_dir.is_symlink()):
                    try:
                        self._remove_staging_dir(stage_dir, runtime_id)
                        if stage_dir.exists() or stage_dir.is_symlink():
                            raise MaaFWRuntimePoolError(
                                f"runtime staging directory could not be removed: "
                                f"{stage_dir}"
                            )
                    except Exception as exc:
                        cleanup_error = exc

                recovery_error: Exception | None = None
                quarantine_remains = False
                if quarantine_dir is not None and (
                    quarantine_dir.exists() or quarantine_dir.is_symlink()
                ):
                    runtime_dir = self._runtime_dir(runtime_id)
                    if not runtime_dir.exists() and not runtime_dir.is_symlink():
                        try:
                            self._validate_staging_path(quarantine_dir, runtime_id)
                            quarantine_dir.replace(runtime_dir)
                        except Exception as exc:
                            recovery_error = exc
                    else:
                        quarantine_remains = True

                if recovery_error is not None:
                    raise MaaFWRuntimePoolError(
                        "runtime recovery failed; protected runtime remains "
                        f"quarantined at {quarantine_dir}: {recovery_error}"
                    ) from recovery_error
                if quarantine_remains:
                    raise MaaFWRuntimePoolError(
                        "runtime publish or validation failed while the protected "
                        "runtime remains quarantined; refusing fallback over the "
                        f"existing runtime: {quarantine_dir}; {install_error}"
                    ) from install_error
                if cleanup_error is not None:
                    raise MaaFWRuntimePoolError(
                        "runtime staging cleanup failed after installation error: "
                        f"{cleanup_error}; {install_error}"
                    ) from cleanup_error
                raise

    def resolve_python(
        self,
        python_request: Mapping[str, Any],
        *,
        allow_install: bool = False,
    ) -> dict[str, Any] | None:
        """Resolve an explicit interpreter under the pool's operation lock."""

        with self._lock:
            self._initialize()
            return resolve_python_interpreter(
                self.root,
                python_request,
                allow_install=allow_install,
            )

    def touch(
        self,
        runtime_id: str,
        *,
        at: str | datetime | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            manifest = self._read_manifest(runtime_id)
            self._augment_manifest(manifest, verify_python=True)
            manifest["lastUsedAt"] = _format_time(_parse_time(at) if at else _utc_now())
            self._prune_expired_leases(manifest, _utc_now())
            self._write_manifest(runtime_id, manifest)
            return self._augment_manifest(manifest)

    def pin(self, runtime_id: str, pinned: bool = True) -> dict[str, Any]:
        with self._lock:
            manifest = self._read_manifest(runtime_id)
            manifest["pinned"] = bool(pinned)
            self._write_manifest(runtime_id, manifest)
            return self._augment_manifest(manifest)

    def add_reference(self, runtime_id: str, reference: str) -> dict[str, Any]:
        normalized = _required_token(reference, "reference")
        with self._lock:
            manifest = self._read_manifest(runtime_id)
            references = {
                str(item) for item in manifest.get("references", []) if str(item)
            }
            references.add(normalized)
            manifest["references"] = sorted(references)
            self._write_manifest(runtime_id, manifest)
            return self._augment_manifest(manifest)

    def remove_reference(self, runtime_id: str, reference: str) -> dict[str, Any]:
        normalized = _required_token(reference, "reference")
        with self._lock:
            manifest = self._read_manifest(runtime_id)
            manifest["references"] = sorted(
                str(item)
                for item in manifest.get("references", [])
                if str(item) and str(item) != normalized
            )
            self._write_manifest(runtime_id, manifest)
            return self._augment_manifest(manifest)

    def set_references(
        self,
        runtime_id: str,
        references: Iterable[str],
    ) -> dict[str, Any]:
        """Replace the declared reference set for one runtime.

        References describe durable project/version ownership. Callers should
        periodically reconcile this complete set from their authoritative
        manifests so removed projects cannot leave stale GC blockers behind.
        Active processes belong in ``leases`` instead.
        """

        if isinstance(references, str):
            raw_references: Iterable[str] = (references,)
        else:
            raw_references = references
        normalized = sorted(
            {_required_token(reference, "reference") for reference in raw_references}
        )
        with self._lock:
            manifest = self._read_manifest(runtime_id)
            manifest["references"] = normalized
            self._write_manifest(runtime_id, manifest)
            return self._augment_manifest(manifest)

    def acquire_lease(
        self,
        runtime_id: str,
        lease_id: str,
        *,
        owner: str = "",
        ttl_seconds: float | None = None,
    ) -> dict[str, Any]:
        normalized = _required_token(lease_id, "lease_id")
        if ttl_seconds is not None and ttl_seconds <= 0:
            raise MaaFWRuntimePoolError("lease ttl_seconds must be positive")
        with self._lock:
            manifest = self._read_manifest(runtime_id)
            self._augment_manifest(manifest, verify_python=True)
            now = _utc_now()
            self._prune_expired_leases(manifest, now)
            leases = dict(manifest.get("leases") or {})
            leases[normalized] = {
                "owner": str(owner or ""),
                "acquiredAt": _format_time(now),
                "expiresAt": (
                    _format_time(now + timedelta(seconds=float(ttl_seconds)))
                    if ttl_seconds is not None
                    else None
                ),
            }
            manifest["leases"] = leases
            manifest["lastUsedAt"] = _format_time(now)
            self._write_manifest(runtime_id, manifest)
            return self._augment_manifest(manifest)

    def release_lease(self, runtime_id: str, lease_id: str) -> dict[str, Any]:
        normalized = _required_token(lease_id, "lease_id")
        with self._lock:
            manifest = self._read_manifest(runtime_id)
            leases = dict(manifest.get("leases") or {})
            leases.pop(normalized, None)
            manifest["leases"] = leases
            self._write_manifest(runtime_id, manifest)
            return self._augment_manifest(manifest)

    def delete(self, runtime_id: str) -> dict[str, Any]:
        with self._lock:
            manifest = self._read_manifest(runtime_id)
            now = _utc_now()
            self._prune_expired_leases(manifest, now)
            blocked = self._deletion_blockers(manifest, now)
            if blocked:
                self._write_manifest(runtime_id, manifest)
                return {
                    "runtimeId": runtime_id,
                    "deleted": False,
                    "blocked": blocked,
                }
            self._remove_runtime_dir(runtime_id)
            return {"runtimeId": runtime_id, "deleted": True, "blocked": []}

    def gc(
        self,
        *,
        dry_run: bool = True,
        grace_seconds: float = 7 * 24 * 60 * 60,
        keep_latest: int = 1,
        now: str | datetime | None = None,
    ) -> dict[str, Any]:
        if grace_seconds < 0:
            raise MaaFWRuntimePoolError("gc grace_seconds cannot be negative")
        if keep_latest < 0:
            raise MaaFWRuntimePoolError("gc keep_latest cannot be negative")
        reference_time = _parse_time(now) if now is not None else _utc_now()
        cutoff = reference_time - timedelta(seconds=float(grace_seconds))

        with self._lock:
            inventory = self.inventory()
            if not inventory["complete"]:
                if not dry_run:
                    raise MaaFWRuntimePoolError(
                        "refusing runtime-pool garbage collection because "
                        "resource inventory is incomplete"
                    )
                return {
                    "dryRun": True,
                    "complete": False,
                    "inventoryErrors": copy.deepcopy(inventory["errors"]),
                    "graceSeconds": float(grace_seconds),
                    "keepLatest": int(keep_latest),
                    "candidates": [],
                    "deleted": [],
                    "kept": [],
                    "errors": [],
                    "cachePrune": {
                        "kind": "uv",
                        "scope": "pool",
                        "dryRun": True,
                        "attempted": False,
                        "status": "skipped-incomplete-inventory",
                        "error": "resource inventory is incomplete",
                    },
                }
            runtimes = self.list()
            keep_ids = {str(item["runtimeId"]) for item in runtimes[:keep_latest]}
            candidates: list[dict[str, Any]] = []
            kept: list[dict[str, Any]] = []
            deleted: list[str] = []
            errors: list[dict[str, str]] = []
            for item in runtimes:
                runtime_id = str(item["runtimeId"])
                reasons: list[str] = []
                if runtime_id in keep_ids:
                    reasons.append("keep_latest")
                reasons.extend(self._deletion_blockers(item, reference_time))
                last_used = _parse_time(item.get("lastUsedAt"))
                if last_used > cutoff:
                    reasons.append("grace_period")
                if reasons:
                    kept.append(
                        {"runtimeId": runtime_id, "reasons": sorted(set(reasons))}
                    )
                    continue

                candidate = {
                    "runtimeId": runtime_id,
                    "path": item["path"],
                    "lastUsedAt": item.get("lastUsedAt"),
                    "sizeBytes": item.get("sizeBytes", 0),
                }
                candidates.append(candidate)
                if dry_run:
                    continue
                try:
                    self._remove_runtime_dir(runtime_id)
                    deleted.append(runtime_id)
                except Exception as exc:
                    errors.append({"runtimeId": runtime_id, "error": str(exc)})

            cache_prune = self._prune_cache(dry_run=bool(dry_run))
            return {
                "dryRun": bool(dry_run),
                "complete": True,
                "inventoryErrors": [],
                "graceSeconds": float(grace_seconds),
                "keepLatest": int(keep_latest),
                "candidates": candidates,
                "deleted": deleted,
                "kept": kept,
                "errors": errors,
                "cachePrune": cache_prune,
            }

    def _prune_cache(self, *, dry_run: bool) -> dict[str, Any]:
        if self.cache_pruner is None:
            return {
                "kind": "uv",
                "scope": "pool",
                "dryRun": dry_run,
                "attempted": False,
                "status": "disabled",
                "error": "runtime pool cache pruner is disabled",
            }
        try:
            return dict(self.cache_pruner(self.root, dry_run=dry_run))
        except Exception as exc:
            return {
                "kind": "uv",
                "scope": "pool",
                "dryRun": dry_run,
                "attempted": False,
                "status": "error",
                "error": f"runtime pool cache prune failed: {exc}",
            }

    def _initialize(self) -> None:
        # Validate every managed child before reading or upgrading the marker so
        # an unsafe legacy layout is rejected without modifying it first.
        for managed_path in (
            self.runtime_root,
            self.staging_root,
            self.root / "cache",
            self.python_root,
        ):
            _assert_existing_chain_has_no_reparse(managed_path)
        marker_path = self.root / POOL_MARKER_NAME
        if marker_path.exists() or marker_path.is_symlink():
            _assert_not_reparse(marker_path)
            if not marker_path.is_file():
                raise MaaFWRuntimePoolError(
                    f"runtime pool marker must be a file: {marker_path}"
                )
            try:
                marker = json.loads(marker_path.read_text(encoding="utf-8"))
            except Exception as exc:
                raise MaaFWRuntimePoolError(
                    f"runtime pool marker is invalid: {exc}"
                ) from exc
            if (
                isinstance(marker, dict)
                and marker.get("schemaVersion") == LEGACY_POOL_SCHEMA_VERSION
                and marker.get("kind") == "auto-mas-maafw-runtime-pool"
                and not marker.get("poolId")
            ):
                marker = {
                    "schemaVersion": POOL_SCHEMA_VERSION,
                    "kind": "auto-mas-maafw-runtime-pool",
                    "poolId": str(uuid.uuid4()),
                }
                _write_json_atomic(marker_path, marker)
            identity = _validate_pool_marker(marker)
        else:
            children = list(self.root.iterdir())
            if children:
                if not self._is_default_root or not _is_legacy_default_pool(children):
                    raise MaaFWRuntimePoolError(
                        "refusing to initialize a non-empty directory without a valid "
                        f"runtime-pool marker: {self.root}"
                    )
            marker = {
                "schemaVersion": POOL_SCHEMA_VERSION,
                "kind": "auto-mas-maafw-runtime-pool",
                "poolId": str(uuid.uuid4()),
            }
            _write_json_atomic(marker_path, marker)
            identity = _validate_pool_marker(marker)
        if self._root_identity and self._root_identity != identity:
            raise MaaFWRuntimePoolError(
                "runtime pool identity changed during the service lifetime"
            )
        self._root_identity = identity
        _assert_existing_chain_has_no_reparse(self.runtime_root)
        _assert_existing_chain_has_no_reparse(self.staging_root)
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self.staging_root.mkdir(parents=True, exist_ok=True)
        self.python_root.mkdir(parents=True, exist_ok=True)
        _assert_not_reparse(self.runtime_root)
        _assert_not_reparse(self.staging_root)
        _assert_not_reparse(self.python_root)

    def inventory(self) -> dict[str, Any]:
        """List every managed-looking runtime and report corruption explicitly."""

        with self._lock:
            self._initialize()
            items: list[dict[str, Any]] = []
            errors: list[dict[str, Any]] = []
            for path in self.runtime_root.iterdir():
                try:
                    _assert_not_reparse(path)
                    if not path.is_dir():
                        raise MaaFWRuntimePoolError(
                            f"managed runtime path must be a directory: {path}"
                        )
                    manifest = self._read_manifest(path.name)
                    items.append(self._augment_manifest(manifest, verify_python=True))
                except Exception as exc:
                    errors.append(
                        {
                            "runtimeId": path.name,
                            "path": str(path),
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
            items.sort(
                key=lambda item: str(item.get("lastUsedAt") or ""),
                reverse=True,
            )
            return {
                "complete": not errors,
                "items": items,
                "errors": errors,
                "rootIdentity": self.root_identity,
            }

    def _runtime_dir(self, runtime_id: str) -> Path:
        _validate_runtime_id(runtime_id)
        return self.runtime_root / runtime_id

    def _read_manifest(
        self,
        runtime_id: str,
        *,
        expected_identity: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._initialize()
        runtime_dir = self._runtime_dir(runtime_id)
        self._validate_managed_runtime_dir(
            runtime_dir, runtime_id, require_manifest=False
        )
        manifest_path = runtime_dir / RUNTIME_MANIFEST_NAME
        _assert_not_reparse(manifest_path)
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise _MaaFWRuntimeEntryStaleError(
                f"runtime manifest not found: {runtime_id}"
            ) from exc
        except Exception as exc:
            raise MaaFWRuntimePoolError(
                f"runtime manifest is invalid: {runtime_id}: {exc}"
            ) from exc
        if isinstance(manifest, dict):
            pinned = manifest.get("pinned", False)
            if not isinstance(pinned, bool):
                raise MaaFWRuntimePoolError(
                    f"runtime manifest pin state is invalid: {runtime_id}"
                )
            _normalize_string_list(manifest.get("references", []), "references")
            _validate_runtime_leases(manifest.get("leases", {}))
        try:
            if not isinstance(manifest, dict):
                raise MaaFWRuntimePoolError(
                    f"runtime manifest must be an object: {runtime_id}"
                )
            if manifest.get("schemaVersion") != MANIFEST_SCHEMA_VERSION:
                raise MaaFWRuntimePoolError(
                    f"runtime manifest version is unsupported: {runtime_id}"
                )
            if manifest.get("kind") != "auto-mas-maafw-runtime":
                raise MaaFWRuntimePoolError(
                    f"runtime manifest kind is invalid: {runtime_id}"
                )
            if manifest.get("runtimeId") != runtime_id:
                raise MaaFWRuntimePoolError(
                    f"runtime manifest identity mismatch: {runtime_id}"
                )
            identity = manifest.get("identity")
            if (
                not isinstance(identity, dict)
                or runtime_id_for_identity(identity) != runtime_id
            ):
                raise MaaFWRuntimePoolError(
                    f"runtime manifest selector identity is invalid: {runtime_id}"
                )
            if identity.get("schemaVersion") != IDENTITY_SCHEMA_VERSION:
                raise MaaFWRuntimePoolError(
                    f"runtime manifest selector schema is invalid: {runtime_id}"
                )
            for field_name in (
                "pythonAbi",
                "pythonVersion",
                "platform",
                "architecture",
            ):
                if (
                    not isinstance(identity.get(field_name), str)
                    or not str(identity[field_name]).strip()
                ):
                    raise MaaFWRuntimePoolError(
                        f"runtime manifest selector identity is incomplete: {runtime_id}"
                    )
            if len(str(identity["pythonAbi"]).split(":", 2)) != 3:
                raise MaaFWRuntimePoolError(
                    f"runtime manifest selector ABI is invalid: {runtime_id}"
                )
            if any(
                not part.strip() for part in str(identity["pythonAbi"]).split(":", 2)
            ):
                raise MaaFWRuntimePoolError(
                    f"runtime manifest selector ABI is incomplete: {runtime_id}"
                )
            try:
                Version(str(identity["pythonVersion"]))
            except InvalidVersion as exc:
                raise MaaFWRuntimePoolError(
                    f"runtime manifest selector Python version is invalid: {runtime_id}"
                ) from exc
            identity_requirements = _normalize_string_list(
                identity.get("requirements"),
                "identity.requirements",
            )
            selector_requirements = _normalize_string_list(
                manifest.get("selectorRequirements", manifest.get("requirements")),
                "selectorRequirements",
            )
            compatibility_requirements = _normalize_string_list(
                manifest.get("requirements"),
                "requirements",
            )
            if (
                selector_requirements != identity_requirements
                or compatibility_requirements != identity_requirements
            ):
                raise MaaFWRuntimePoolError(
                    f"runtime manifest selector requirements mismatch: {runtime_id}"
                )
            _normalize_string_list(
                manifest.get("resolvedRequirements", []),
                "resolvedRequirements",
            )
            if (
                expected_identity is not None
                and manifest.get("identity") != expected_identity
            ):
                raise MaaFWRuntimePoolError(
                    f"runtime requirement selector mismatch: {runtime_id}"
                )
        except Exception as exc:
            raise _MaaFWRuntimeEntryStaleError(
                f"runtime manifest selector is stale: {runtime_id}: {exc}"
            ) from exc
        self._validate_managed_runtime_dir(
            runtime_dir, runtime_id, require_manifest=True
        )
        return manifest

    def _write_manifest(self, runtime_id: str, manifest: dict[str, Any]) -> None:
        runtime_dir = self._runtime_dir(runtime_id)
        self._validate_managed_runtime_dir(
            runtime_dir, runtime_id, require_manifest=True
        )
        _write_json_atomic(runtime_dir / RUNTIME_MANIFEST_NAME, manifest)

    def _augment_manifest(
        self,
        manifest: dict[str, Any],
        *,
        verify_python: bool = False,
    ) -> dict[str, Any]:
        payload = copy.deepcopy(manifest)
        try:
            runtime_id = str(payload["runtimeId"])
            runtime_path = self._runtime_dir(runtime_id)
            _assert_not_reparse(runtime_path)
            runtime_dir = runtime_path.resolve()
            environment_relative = Path(str(payload["environmentRelativePath"]))
            python_relative = Path(str(payload["pythonRelativePath"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise _MaaFWRuntimeEntryStaleError(
                "runtime manifest is missing required environment paths"
            ) from exc
        environment_candidate = runtime_dir / environment_relative
        python_candidate = runtime_dir / python_relative
        _assert_existing_chain_has_no_reparse(environment_candidate)
        _assert_existing_chain_has_no_reparse(python_candidate)
        environment_path = environment_candidate.resolve()
        python_executable = python_candidate.resolve()
        if not _is_within(environment_path, runtime_dir) or not _is_within(
            python_executable,
            runtime_dir,
        ):
            raise MaaFWRuntimePoolError(
                f"runtime manifest contains unsafe paths: {runtime_id}"
            )
        if not environment_path.is_dir() or not python_executable.is_file():
            raise _MaaFWRuntimeEntryStaleError(
                f"runtime environment is incomplete: {runtime_id}"
            )
        identity = payload.get("identity")
        if verify_python:
            if not isinstance(identity, Mapping):  # pragma: no cover - manifest guard
                raise MaaFWRuntimePoolError(
                    f"runtime manifest identity is invalid: {runtime_id}"
                )
            # A missing executable is recoverable above, but a present Python
            # whose probed ABI disagrees with its selector is an identity
            # violation. Keep that fail-closed contract instead of silently
            # quarantining and rebuilding under an untrusted interpretation.
            _verify_installed_python_identity(python_executable, identity)
        now = _utc_now()
        payload["path"] = str(runtime_dir)
        payload["poolId"] = self._root_identity["poolId"]
        payload["environmentPath"] = str(environment_path)
        payload["venvPath"] = str(environment_path)
        payload["pythonExecutable"] = str(python_executable)
        selector_requirements = list(
            payload.get("selectorRequirements") or payload.get("requirements") or []
        )
        payload["selectorRequirements"] = selector_requirements
        payload["resolvedRequirements"] = list(
            payload.get("resolvedRequirements") or []
        )
        payload["packages"] = selector_requirements
        payload["sizeBytes"] = _directory_size(runtime_dir)
        payload["activeLeaseIds"] = self._active_lease_ids(payload, now)
        return payload

    def _resolve_installed_python(
        self,
        stage_dir: Path,
        environment_path: Path,
        install_result: dict[str, Any],
    ) -> Path:
        raw_value = install_result.pop("pythonExecutable", None) or install_result.pop(
            "python_executable", None
        )
        if raw_value:
            candidate = Path(str(raw_value))
            if not candidate.is_absolute():
                candidate = environment_path / candidate
        else:
            candidate = _venv_python(environment_path)
        _assert_existing_chain_has_no_reparse(candidate)
        resolved = candidate.resolve()
        if not _is_within(resolved, stage_dir.resolve()) or not resolved.is_file():
            raise MaaFWRuntimePoolError(
                f"runtime installer did not create a managed Python executable: {candidate}"
            )
        return resolved.relative_to(stage_dir.resolve())

    def _quarantine_stale_runtime(
        self,
        runtime_id: str,
    ) -> tuple[dict[str, Any], Path | None]:
        runtime_dir = self._runtime_dir(runtime_id)
        if not runtime_dir.exists() and not runtime_dir.is_symlink():
            return {}, None
        self._validate_managed_runtime_dir(
            runtime_dir,
            runtime_id,
            require_manifest=False,
        )
        recovery_metadata = self._read_recovery_metadata(runtime_dir)
        quarantine_dir = self.staging_root / (
            f"{runtime_id}-quarantine-{uuid.uuid4().hex}"
        )
        self._validate_staging_path(quarantine_dir, runtime_id)
        if quarantine_dir.exists() or quarantine_dir.is_symlink():
            raise MaaFWRuntimePoolError(
                f"runtime quarantine path already exists: {quarantine_dir}"
            )
        runtime_dir.replace(quarantine_dir)
        return recovery_metadata, quarantine_dir

    def _read_recovery_metadata(self, runtime_dir: Path) -> dict[str, Any]:
        manifest_path = runtime_dir / RUNTIME_MANIFEST_NAME
        _assert_not_reparse(manifest_path)
        try:
            value = json.loads(manifest_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except Exception as exc:
            raise MaaFWRuntimePoolError(
                f"runtime recovery metadata is invalid: {runtime_dir.name}: {exc}"
            ) from exc
        if not isinstance(value, Mapping):
            return {}

        pinned = value.get("pinned", False)
        if not isinstance(pinned, bool):
            raise MaaFWRuntimePoolError(
                f"runtime recovery pin state is invalid: {runtime_dir.name}"
            )
        recovery: dict[str, Any] = {
            "pinned": pinned,
            "references": _normalize_string_list(
                value.get("references", []),
                "references",
            ),
        }
        leases = value.get("leases", {})
        _validate_runtime_leases(leases)
        recovery["leases"] = copy.deepcopy(dict(leases))
        metadata = value.get("metadata")
        if isinstance(metadata, Mapping):
            recovery["metadata"] = _json_compatible(metadata)
        for field_name in ("createdAt",):
            field_value = value.get(field_name)
            if isinstance(field_value, str) and field_value.strip():
                recovery[field_name] = field_value
        return recovery

    def _deletion_blockers(
        self,
        manifest: Mapping[str, Any],
        now: datetime,
    ) -> list[str]:
        blockers: list[str] = []
        if bool(manifest.get("pinned")):
            blockers.append("pinned")
        if [item for item in manifest.get("references", []) if str(item)]:
            blockers.append("referenced")
        if self._active_lease_ids(manifest, now):
            blockers.append("leased")
        return blockers

    def _active_lease_ids(
        self,
        manifest: Mapping[str, Any],
        now: datetime,
    ) -> list[str]:
        leases = manifest.get("leases")
        if not isinstance(leases, Mapping):
            return []
        active: list[str] = []
        for lease_id, payload in leases.items():
            if not isinstance(payload, Mapping):
                continue
            expires_at = payload.get("expiresAt")
            if expires_at is None or _parse_time(expires_at) > now:
                active.append(str(lease_id))
        return sorted(active)

    def _prune_expired_leases(self, manifest: dict[str, Any], now: datetime) -> None:
        leases = manifest.get("leases")
        if not isinstance(leases, Mapping):
            manifest["leases"] = {}
            return
        manifest["leases"] = {
            str(lease_id): dict(payload)
            for lease_id, payload in leases.items()
            if isinstance(payload, Mapping)
            and (
                payload.get("expiresAt") is None
                or _parse_time(payload.get("expiresAt")) > now
            )
        }

    def _remove_runtime_dir(self, runtime_id: str) -> None:
        runtime_dir = self._runtime_dir(runtime_id)
        self._validate_managed_runtime_dir(
            runtime_dir, runtime_id, require_manifest=True
        )
        shutil.rmtree(runtime_dir)

    def _remove_staging_dir(self, path: Path, runtime_id: str) -> None:
        self._validate_staging_path(path, runtime_id)
        if path.is_symlink():
            raise MaaFWRuntimePoolError(f"refusing to delete staging symlink: {path}")
        shutil.rmtree(path, ignore_errors=True)

    def _validate_staging_path(self, path: Path, runtime_id: str) -> None:
        _validate_runtime_id(runtime_id)
        _assert_not_reparse(path)
        resolved = path.resolve()
        if resolved.parent != self.staging_root.resolve():
            raise MaaFWRuntimePoolError(f"staging path escapes runtime pool: {path}")
        if not resolved.name.startswith(f"{runtime_id}-"):
            raise MaaFWRuntimePoolError(f"staging path does not match runtime: {path}")

    def _validate_managed_runtime_dir(
        self,
        path: Path,
        runtime_id: str,
        *,
        require_manifest: bool,
    ) -> None:
        _validate_runtime_id(runtime_id)
        _assert_not_reparse(path)
        if not path.is_dir():
            raise MaaFWRuntimePoolError(f"managed runtime must be a directory: {path}")
        resolved = path.resolve()
        if (
            resolved.parent != self.runtime_root.resolve()
            or resolved.name != runtime_id
        ):
            raise MaaFWRuntimePoolError(f"runtime path escapes managed pool: {path}")
        manifest_path = resolved / RUNTIME_MANIFEST_NAME
        _assert_not_reparse(manifest_path)
        if require_manifest and not manifest_path.is_file():
            raise MaaFWRuntimePoolError(
                f"managed runtime has no manifest: {runtime_id}"
            )


def _pool_lock(root: Path) -> threading.RLock:
    key = os.path.normcase(str(root.resolve()))
    with _LOCKS_GUARD:
        return _POOL_LOCKS.setdefault(key, threading.RLock())


def _validate_pool_marker(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MaaFWRuntimePoolError("runtime pool marker must be a JSON object")
    if value.get("schemaVersion") != POOL_SCHEMA_VERSION:
        raise MaaFWRuntimePoolError("runtime pool marker version is unsupported")
    if value.get("kind") != "auto-mas-maafw-runtime-pool":
        raise MaaFWRuntimePoolError("runtime pool marker kind is invalid")
    pool_id = value.get("poolId")
    try:
        normalized_pool_id = str(uuid.UUID(str(pool_id or "")))
    except ValueError as exc:
        raise MaaFWRuntimePoolError("runtime pool marker poolId is invalid") from exc
    return {
        "schemaVersion": POOL_SCHEMA_VERSION,
        "kind": "auto-mas-maafw-runtime-pool",
        "poolId": normalized_pool_id,
    }


def _is_legacy_default_pool(children: Iterable[Path]) -> bool:
    known_names = {
        RUNTIME_DIRECTORY_NAME,
        STAGING_DIRECTORY_NAME,
        "cache",
        "python",
    }
    for child in children:
        _assert_not_reparse(child)
        if child.name not in known_names or not child.is_dir():
            return False
    return True


def _assert_existing_chain_has_no_reparse(path: Path) -> None:
    existing: list[Path] = []
    current = path
    while True:
        if current.exists() or current.is_symlink():
            existing.append(current)
        if current.parent == current:
            break
        current = current.parent
    for item in reversed(existing):
        _assert_not_reparse(item)


def _assert_not_reparse(path: Path) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    file_attributes = getattr(metadata, "st_file_attributes", 0)
    if path.is_symlink() or bool(file_attributes & reparse_flag):
        raise MaaFWRuntimePoolError(f"reparse points are not allowed: {path}")


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left.resolve(strict=False))) == os.path.normcase(
        str(Path(os.path.abspath(right)).resolve(strict=False))
    )


def _validate_runtime_id(runtime_id: str) -> None:
    if not RUNTIME_ID_RE.fullmatch(str(runtime_id or "")):
        raise MaaFWRuntimePoolError(f"invalid managed runtime id: {runtime_id}")


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp-{uuid.uuid4().hex}")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _json_compatible(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_compatible(item) for item in value]
    return str(value)


def _required_token(value: str, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise MaaFWRuntimePoolError(f"{field_name} cannot be empty")
    return normalized


def _bind_bootstrap_python(
    installer: RuntimeInstaller,
    bootstrap_python: str | Path,
) -> RuntimeInstaller:
    """Bind exact bootstrap support without breaking legacy test installers."""

    try:
        parameters = inspect.signature(installer).parameters
    except (TypeError, ValueError):
        return installer
    accepts_keyword = "bootstrap_python" in parameters or any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )
    if not accepts_keyword:
        return installer
    return functools.partial(
        installer,
        bootstrap_python=str(Path(bootstrap_python).resolve()),
    )


def _verify_installed_python_identity(
    python_executable: Path,
    expected_identity: Mapping[str, Any],
) -> dict[str, str]:
    """Fail closed when a custom installer returns the wrong Python ABI."""

    try:
        actual = probe_python_identity(python_executable)
    except Exception as exc:
        # 带上原因原文：ctypes 自检失败这类信息只有在这里传出去，用户
        # 才看得到「标准库不可用」，而不是一句无从下手的「无法校验」。
        raise MaaFWRuntimePoolError(
            "installed runtime Python identity could not be verified: "
            f"{python_executable}: {exc}"
        ) from exc

    required_probe_fields = (
        "implementation",
        "cacheTag",
        "soabi",
        "version",
        "shortVersion",
        "platform",
        "architecture",
    )
    missing = [
        field
        for field in required_probe_fields
        if not str(actual.get(field) or "").strip()
    ]
    if missing:
        raise MaaFWRuntimePoolError(
            "installed runtime Python identity is incomplete: " + ", ".join(missing)
        )

    expected_python_version = str(expected_identity.get("pythonVersion") or "").strip()
    try:
        expected_release = Version(expected_python_version).release
    except InvalidVersion as exc:
        raise MaaFWRuntimePoolError(
            "selected runtime Python identity has an invalid pythonVersion"
        ) from exc
    actual_values = {
        "pythonAbi": (
            f"{actual['implementation']}:{actual['cacheTag']}:{actual['soabi']}"
        ),
        "pythonVersion": str(
            actual["version"] if len(expected_release) >= 3 else actual["shortVersion"]
        ),
        "platform": str(actual["platform"]),
        "architecture": str(actual["architecture"]),
    }
    mismatches = [
        f"{field}: expected={expected_identity.get(field)!r}, actual={actual_value!r}"
        for field, actual_value in actual_values.items()
        if str(expected_identity.get(field) or "") != actual_value
    ]
    if mismatches:
        raise MaaFWRuntimePoolError(
            "installed runtime Python identity does not match the selected ABI: "
            + "; ".join(mismatches)
        )
    return {str(key): str(value) for key, value in actual.items()}


def _optional_string(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _normalize_string_list(value: Any, field_name: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items: Iterable[Any] = value.splitlines()
    elif isinstance(value, Mapping):
        raise MaaFWRuntimePoolError(f"{field_name} must be a string list")
    elif isinstance(value, Iterable):
        items = value
    else:
        raise MaaFWRuntimePoolError(f"{field_name} must be a string list")
    normalized: set[str] = set()
    for item in items:
        if not isinstance(item, str):
            raise MaaFWRuntimePoolError(f"{field_name} must contain strings")
        token = item.strip()
        if token:
            normalized.add(token)
    return sorted(normalized, key=str.casefold)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _validate_runtime_leases(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise MaaFWRuntimePoolError("runtime manifest leases must be an object")
    for lease_id, payload in value.items():
        if not isinstance(lease_id, str) or not lease_id.strip():
            raise MaaFWRuntimePoolError("runtime manifest lease id is invalid")
        if not isinstance(payload, Mapping):
            raise MaaFWRuntimePoolError("runtime manifest lease entry is invalid")
        owner = payload.get("owner")
        if not isinstance(owner, str):
            raise MaaFWRuntimePoolError("runtime manifest lease owner is invalid")
        expires_at = payload.get("expiresAt")
        if expires_at is None:
            continue
        if not isinstance(expires_at, str) or not expires_at.strip():
            raise MaaFWRuntimePoolError("runtime manifest lease expiry is invalid")
        try:
            _parse_time(expires_at)
        except ValueError as exc:
            raise MaaFWRuntimePoolError(
                "runtime manifest lease expiry is invalid"
            ) from exc


def _parse_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    else:
        return datetime.fromtimestamp(0, timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_time(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace(
            "+00:00",
            "Z",
        )
    )


def _venv_python(environment_path: Path) -> Path:
    if os.name == "nt":
        return environment_path / "Scripts" / "python.exe"
    return environment_path / "bin" / "python"


def _is_within(path: Path, base_dir: Path) -> bool:
    try:
        path.relative_to(base_dir)
        return True
    except ValueError:
        return False


def _directory_size(path: Path) -> int:
    total = 0
    for directory, directory_names, file_names in os.walk(path):
        directory_path = Path(directory)
        directory_names[:] = [
            name for name in directory_names if not (directory_path / name).is_symlink()
        ]
        for name in file_names:
            file_path = directory_path / name
            try:
                if not file_path.is_symlink():
                    total += file_path.stat().st_size
            except OSError:
                continue
    return total
