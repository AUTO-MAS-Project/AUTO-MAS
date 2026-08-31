from __future__ import annotations

import asyncio
import fnmatch
import hashlib
import json
import os
import platform as host_platform
import re
import shutil
import stat
import sys
import time
import uuid
import zipfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Iterable, Mapping

import json5
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version


MANIFEST_FILE_NAME = ".auto_mas_maafw_project.json"
MANIFEST_SCHEMA_VERSION = 3
LEGACY_MANIFEST_SCHEMA_VERSION = 2
STORE_MARKER_NAME = ".auto_mas_maafw_project_store.json"
STORE_SCHEMA_VERSION = 1
STORE_KIND = "auto-mas-maafw-project-store"
DEFAULT_STORE_DIR = Path("data") / "maafw_project_store"
RUN_ROOT_MARKER_NAME = ".auto_mas_maafw_project_runs.json"
RUN_ROOT_SCHEMA_VERSION = 1
RUN_ROOT_KIND = "auto-mas-maafw-project-runs"
DEFAULT_RUN_DIR = Path("data") / "maafw_project_runs"
CHECKOUT_MARKER_NAME = ".auto_mas_maafw_checkout.json"
CHECKOUT_SCHEMA_VERSION = 1
CHECKOUT_KIND = "auto-mas-maafw-project-checkout"
_STORE_LOCKS_GUARD = RLock()
_STORE_LOCKS: dict[str, RLock] = {}

MAX_ZIP_FILE_COUNT = 200_000
MAX_ZIP_MEMBER_UNCOMPRESSED_BYTES = 8 * 1024 * 1024 * 1024
MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES = 16 * 1024 * 1024 * 1024
MAX_ZIP_COMPRESSION_RATIO = 500.0
_ZIP_COPY_CHUNK_SIZE = 1024 * 1024
MAX_SUMMARY_ITEM_NAMES = 128
_TREE_HASH_SCHEMA_VERSION = 2
_LEGACY_TREE_HASH_SCHEMA_VERSION = 1
_TREE_HASH_FRAMING = "domain-file-count-path-length-content-length-v2"
_LEGACY_TREE_HASH_FRAMING = "path-length-content-v1"
_PROJECTED_SOURCE_HASH_DOMAIN = b"AUTO-MAS:MaaFW:projected-source:v2\x00"
_STORE_PAYLOAD_HASH_DOMAIN = b"AUTO-MAS:MaaFW:store-payload:v2\x00"
_SOURCE_SNAPSHOT_HASH_DOMAIN = b"AUTO-MAS:MaaFW:source-snapshot:v2\x00"
_PROJECTED_SOURCE_HASH_DOMAIN_NAME = "AUTO-MAS:MaaFW:projected-source:v2"
_STORE_PAYLOAD_HASH_DOMAIN_NAME = "AUTO-MAS:MaaFW:store-payload:v2"
_PROJECTED_SOURCE_METADATA_DOMAIN = b"AUTO-MAS:MaaFW:projected-source-metadata\x00"
_PROJECTED_SOURCE_METADATA_SCHEMA_VERSION = 1

_COMPONENT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}

_DEPENDENCY_DIR_NAMES = {
    "agent",
    "agents",
    "lock",
    "locks",
    "plugins",
    "requirements",
}
_DEPENDENCY_FILE_PATTERNS = (
    "requirements*.txt",
    "constraints*.txt",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "uv.lock",
    "poetry.lock",
    "Pipfile",
    "Pipfile.lock",
    "environment.yml",
    "environment.yaml",
    "conda-lock.yml",
    "conda-lock.yaml",
    "*.lock",
)

_EXCLUDED_DIRECTORY_REASONS = {
    ".git": "source-control",
    ".github": "source-control",
    ".idea": "editor-state",
    ".vscode": "editor-state",
    "ui": "ui-shell",
    "gui": "ui-shell",
    "frontend": "ui-shell",
    "web": "ui-shell",
    "webui": "ui-shell",
    "electron": "ui-shell",
    "mfaavalonia": "ui-shell",
    "mxu": "ui-shell",
    "mfw": "ui-shell",
    "maapicli": "ui-shell",
    "node_modules": "ui-runtime",
    "runtime": "embedded-runtime",
    "runtimes": "embedded-runtime",
    "python": "embedded-python",
    "python-runtime": "embedded-python",
    "python_runtime": "embedded-python",
    "python-embed": "embedded-python",
    "python_embed": "embedded-python",
    ".venv": "embedded-python",
    "venv": "embedded-python",
    "__pycache__": "cache",
    ".cache": "cache",
    "cache": "cache",
    ".pytest_cache": "cache",
    ".mypy_cache": "cache",
    ".ruff_cache": "cache",
    ".tox": "cache",
    ".nox": "cache",
    ".mas-update": "updater-shell",
    "update": "updater-shell",
    "updates": "updater-shell",
    "updater": "updater-shell",
    "temp": "temporary",
    "tmp": "temporary",
    ".tmp": "temporary",
    "backup": "temporary",
    "backups": "temporary",
    "build": "build-output",
    "dist": "build-output",
}
_EXCLUDED_FILE_SUFFIXES = {".pyc", ".pyo", ".tmp", ".temp", ".log"}
_KNOWN_RUNTIME_FILE_NAMES = {
    "maaframework.dll",
    "maaframework.so",
    "maaframework.dylib",
    "maapicli",
    "maapicli.exe",
    "maatoolkit.dll",
    "python.exe",
    "pythonw.exe",
}
_KNOWN_RUNTIME_STEMS = {
    "maaframework",
    "maatoolkit",
    "maaadbcontrolunit",
    "maahttp",
}
_KNOWN_UI_SHELL_STEMS = {
    "mfaavalonia",
    "mxu",
    "mfw",
    "maapicli",
}
_SHELL_SUFFIXES = {".bat", ".cmd", ".exe", ".ps1", ".sh"}


class MaaFWProjectStoreError(RuntimeError):
    """Raised when an operation would violate the project-store contract."""


@dataclass
class _ProjectionPlan:
    source_root: Path
    interface_base: Path
    source_interface_path: Path
    interface_path: Path
    interface_data: dict[str, Any]
    rewritten_json: dict[Path, dict[str, Any]]
    copied_files: set[Path]
    copied_directories: set[Path]
    excluded_reasons: dict[str, str]
    agent_runtime: list[dict[str, Any]]
    required_python_abi: list[str]
    python_runtime: dict[str, Any] | None
    shared_agent_dependencies_complete: bool
    opaque_agent: bool
    conservative: bool
    warnings: list[str]


@dataclass(frozen=True)
class _ProjectionTargetMode:
    complete: bool
    allow_excluded_root: bool


@dataclass(frozen=True)
class _RequiredProjectionPath:
    path: Path
    label: str
    is_directory: bool
    agent_index: int | None = None
    agent_key: str | None = None
    python_entrypoint: bool = False
    allow_stripped_python_interpreter: bool = False
    source_missing: bool = False


@dataclass(frozen=True)
class _ImportSource:
    root: Path
    input_path: Path
    kind: str
    input_size_bytes: int
    archive_sha256: str | None = None
    cleanup_root: Path | None = None


class MaaFWProjectStoreService:
    """JSON-friendly implementation of ``maafw.project_store.v1``.

    Project payload files are immutable after import. The private manifest is
    management metadata and is updated atomically when runtime references,
    pins, bindings or last-used timestamps change.
    """

    def __init__(
        self,
        store_root: str | Path | None = None,
        *,
        run_root: str | Path | None = None,
    ) -> None:
        default_root = Path.cwd() / DEFAULT_STORE_DIR
        default_run_root = Path.cwd() / DEFAULT_RUN_DIR
        absolute_root = _configured_absolute_root(
            store_root,
            default_root,
            "project-store root",
        )
        absolute_run_root = _configured_absolute_root(
            run_root,
            default_run_root,
            "project run root",
        )
        _assert_existing_chain_has_no_reparse(absolute_root)
        _assert_existing_chain_has_no_reparse(absolute_run_root)
        if _path_trees_overlap(absolute_root, absolute_run_root):
            raise MaaFWProjectStoreError(
                "project-store root and project run root must use separate path trees"
            )
        if absolute_root.exists() and not absolute_root.is_dir():
            raise MaaFWProjectStoreError(
                f"project-store root must be a directory: {absolute_root}"
            )
        if absolute_run_root.exists() and not absolute_run_root.is_dir():
            raise MaaFWProjectStoreError(
                f"project run root must be a directory: {absolute_run_root}"
            )
        absolute_root.mkdir(parents=True, exist_ok=True)
        _assert_not_reparse(absolute_root)
        self.root = absolute_root.resolve(strict=True)
        self._is_default_root = _same_path(self.root, default_root)
        self._lock = _store_lock(self.root)
        self._resource_lifecycle_lock = asyncio.Lock()
        self._resource_lifecycle_task: ContextVar[asyncio.Task[Any] | None] = (
            ContextVar(
                f"maafw_project_resource_lifecycle_{id(self)}",
                default=None,
            )
        )
        with self._lock:
            self._root_identity = self._initialize_root_identity()
            _assert_existing_chain_has_no_reparse(self._projects_root)
            _assert_existing_chain_has_no_reparse(self._staging_root)
            self._projects_root.mkdir(parents=True, exist_ok=True)
            self._staging_root.mkdir(parents=True, exist_ok=True)
            _assert_not_reparse(self._projects_root)
            _assert_not_reparse(self._staging_root)
        absolute_run_root.mkdir(parents=True, exist_ok=True)
        _assert_not_reparse(absolute_run_root)
        self.run_root = absolute_run_root.resolve(strict=True)
        self._is_default_run_root = _same_path(self.run_root, default_run_root)
        self._run_lock = _store_lock(self.run_root)
        with self._run_lock:
            self._run_root_identity = self._initialize_run_root_identity()
            _assert_existing_chain_has_no_reparse(self._run_scripts_root)
            _assert_existing_chain_has_no_reparse(self._run_staging_root)
            self._run_scripts_root.mkdir(parents=True, exist_ok=True)
            self._run_staging_root.mkdir(parents=True, exist_ok=True)
            _assert_not_reparse(self._run_scripts_root)
            _assert_not_reparse(self._run_staging_root)

    @property
    def root_identity(self) -> dict[str, Any]:
        return _json_clone(self._root_identity)

    @property
    def rootIdentity(self) -> dict[str, Any]:  # noqa: N802 - public JSON contract
        return self.root_identity

    def storage_info(self) -> dict[str, Any]:
        """Return the immutable storage identity selected at service startup."""

        with self._lock, self._run_lock:
            self._assert_store_identity_unchanged()
            self._assert_run_identity_unchanged()
            return {
                "root": str(self.root),
                "storeId": self._root_identity["storeId"],
                "isDefault": self._is_default_root,
                "rootIdentity": self.root_identity,
                "runRoot": str(self.run_root),
                "runRootId": self._run_root_identity["runRootId"],
                "isDefaultRunRoot": self._is_default_run_root,
                "runRootIdentity": _json_clone(self._run_root_identity),
            }

    def _initialize_root_identity(self) -> dict[str, Any]:
        marker_path = self.root / STORE_MARKER_NAME
        if marker_path.exists() or marker_path.is_symlink():
            _assert_not_reparse(marker_path)
            if not marker_path.is_file():
                raise MaaFWProjectStoreError(
                    f"project-store marker must be a file: {marker_path}"
                )
            try:
                marker = json.loads(marker_path.read_text(encoding="utf-8"))
            except Exception as exc:
                raise MaaFWProjectStoreError(
                    f"project-store marker is invalid: {exc}"
                ) from exc
            return _validate_store_marker(marker)

        children = list(self.root.iterdir())
        if children:
            if not self._is_default_root or not _is_legacy_default_store(children):
                raise MaaFWProjectStoreError(
                    "refusing to initialize a non-empty directory without a valid "
                    f"project-store marker: {self.root}"
                )

        marker = {
            "schemaVersion": STORE_SCHEMA_VERSION,
            "kind": STORE_KIND,
            "storeId": str(uuid.uuid4()),
        }
        _write_json_atomic(marker_path, marker, self.root)
        return _validate_store_marker(marker)

    def _initialize_run_root_identity(self) -> dict[str, Any]:
        marker_path = self.run_root / RUN_ROOT_MARKER_NAME
        if marker_path.exists() or marker_path.is_symlink():
            _assert_not_reparse(marker_path)
            if not marker_path.is_file():
                raise MaaFWProjectStoreError(
                    f"project run-root marker must be a file: {marker_path}"
                )
            try:
                marker = json.loads(marker_path.read_text(encoding="utf-8"))
            except Exception as exc:
                raise MaaFWProjectStoreError(
                    f"project run-root marker is invalid: {exc}"
                ) from exc
            return _validate_run_root_marker(marker)
        if any(self.run_root.iterdir()):
            raise MaaFWProjectStoreError(
                "refusing to initialize a non-empty directory without a valid "
                f"project run-root marker: {self.run_root}"
            )
        marker = {
            "schemaVersion": RUN_ROOT_SCHEMA_VERSION,
            "kind": RUN_ROOT_KIND,
            "runRootId": str(uuid.uuid4()),
        }
        _write_json_atomic(marker_path, marker, self.run_root)
        return _validate_run_root_marker(marker)

    def _assert_store_identity_unchanged(self) -> None:
        marker_path = self.root / STORE_MARKER_NAME
        _assert_path_chain_within_root(marker_path, self.root)
        try:
            marker = _validate_store_marker(
                json.loads(marker_path.read_text(encoding="utf-8"))
            )
        except Exception as exc:
            raise MaaFWProjectStoreError(
                f"project-store identity marker changed or is invalid: {exc}"
            ) from exc
        if marker != self._root_identity:
            raise MaaFWProjectStoreError(
                "project-store identity changed during the service lifetime"
            )

    def _assert_run_identity_unchanged(self) -> None:
        marker_path = self.run_root / RUN_ROOT_MARKER_NAME
        _assert_path_chain_within_root(marker_path, self.run_root)
        try:
            marker = _validate_run_root_marker(
                json.loads(marker_path.read_text(encoding="utf-8"))
            )
        except Exception as exc:
            raise MaaFWProjectStoreError(
                f"project run-root identity marker changed or is invalid: {exc}"
            ) from exc
        if marker != self._run_root_identity:
            raise MaaFWProjectStoreError(
                "project run-root identity changed during the service lifetime"
            )

    @asynccontextmanager
    async def resource_lifecycle_transaction(self) -> AsyncIterator[None]:
        """Serialize reference reconciliation with project mutation and GC."""

        task = asyncio.current_task()
        if task is None:
            raise MaaFWProjectStoreError(
                "project resource transaction requires an asyncio task"
            )
        active_task = self._resource_lifecycle_task.get()
        if active_task is task:
            yield
            return
        if active_task is not None:
            raise MaaFWProjectStoreError(
                "project resource transaction cannot cross asyncio tasks"
            )

        async with self._resource_lifecycle_lock:
            token = self._resource_lifecycle_task.set(task)
            try:
                yield
            finally:
                self._resource_lifecycle_task.reset(token)

    @property
    def _projects_root(self) -> Path:
        return self.root / "projects"

    @property
    def _staging_root(self) -> Path:
        return self.root / ".staging"

    @property
    def _run_scripts_root(self) -> Path:
        return self.run_root / "scripts"

    @property
    def _run_staging_root(self) -> Path:
        return self.run_root / ".staging"

    def import_project(
        self,
        source_path: str | Path,
        project_id: str | None = None,
        version: str | None = None,
        *,
        runtime_constraint: str | None = None,
        platform: str | None = None,
        arch: str | None = None,
        runtime_binding: dict[str, Any] | None = None,
        remote_source: Mapping[str, Any] | None = None,
        reference: str | None = None,
        pinned: bool = False,
        activate: bool = True,
    ) -> dict[str, Any]:
        """Import a local directory or ZIP release as an immutable version."""

        imported_source = _materialize_import_source(
            source_path,
            store_root=self.root,
            staging_root=self._staging_root,
        )
        try:
            return self._import_materialized_project(
                imported_source,
                project_id,
                version,
                runtime_constraint=runtime_constraint,
                platform=platform,
                arch=arch,
                runtime_binding=runtime_binding,
                remote_source=remote_source,
                reference=reference,
                pinned=pinned,
                activate=activate,
            )
        finally:
            if (
                imported_source.cleanup_root is not None
                and imported_source.cleanup_root.exists()
            ):
                _safe_remove_tree(imported_source.cleanup_root, self.root)

    def _import_materialized_project(
        self,
        imported_source: _ImportSource,
        project_id: str | None,
        version: str | None,
        *,
        runtime_constraint: str | None,
        platform: str | None,
        arch: str | None,
        runtime_binding: dict[str, Any] | None,
        remote_source: Mapping[str, Any] | None,
        reference: str | None,
        pinned: bool,
        activate: bool,
    ) -> dict[str, Any]:
        source_root = imported_source.root
        interface_base, source_interface_path = _discover_project_interface(source_root)
        interface_data = _read_json_object(source_interface_path)
        plan = _build_projection_plan(
            source_root, source_interface_path, interface_data
        )
        normalized_project_id = _resolve_import_project_id(
            project_id,
            plan.interface_data,
            source_root,
        )
        interface_version = _optional_string(plan.interface_data.get("version"))
        normalized_version = _resolve_import_version(version, interface_version)
        normalized_remote_source = _merge_remote_source_metadata(
            remote_source,
            plan.interface_data,
        )
        source_hash_metadata = _projected_source_hash_metadata(plan.python_runtime)
        source_hash = _calculate_projected_source_hash(
            source_root,
            plan.copied_files,
            metadata=source_hash_metadata,
        )
        source_tree_bytes = _tree_size(source_root)

        with self._lock:
            final_dir = self._version_dir(normalized_project_id, normalized_version)
            if final_dir.exists():
                existing = self._load_manifest(
                    normalized_project_id, normalized_version
                )
                if (
                    normalized_remote_source is not None
                    and existing.get("remote") != normalized_remote_source
                ):
                    raise MaaFWProjectStoreError(
                        "immutable project version already exists with different "
                        "remote source identity: "
                        f"{normalized_project_id}@{normalized_version}"
                    )
                existing_hash = _manifest_source_hash(existing)
                existing_hash_schema = _manifest_hash_schema_version(
                    existing,
                    "source",
                )
                candidate_hash = source_hash
                if existing_hash_schema == _LEGACY_TREE_HASH_SCHEMA_VERSION:
                    existing_runtime = existing.get("runtime")
                    existing_runtime = (
                        existing_runtime
                        if isinstance(existing_runtime, Mapping)
                        else {}
                    )
                    existing_python = existing_runtime.get("python")
                    existing_python = (
                        existing_python
                        if isinstance(existing_python, Mapping)
                        else None
                    )
                    candidate_hash = _calculate_projected_source_hash_legacy(
                        source_root,
                        plan.copied_files,
                        metadata=_projected_source_hash_metadata(existing_python),
                    )
                if existing_hash != candidate_hash:
                    raise MaaFWProjectStoreError(
                        f"immutable project version already exists with different content: "
                        f"{normalized_project_id}@{normalized_version}"
                    )
                self._verify_store_payload(
                    existing,
                    final_dir / "data",
                )
                if activate:
                    self._write_current(normalized_project_id, normalized_version)
                return self.resolve_project(
                    normalized_project_id,
                    normalized_version,
                    touch=False,
                )

            final_dir.parent.mkdir(parents=True, exist_ok=True)
            _assert_path_chain_within_root(final_dir.parent, self.root)
            stage_dir = self._staging_root / (
                f"{normalized_project_id}.{normalized_version}.{uuid.uuid4().hex}"
            )
            data_dir = stage_dir / "data"
            imported_at = _format_timestamp()
            try:
                data_dir.mkdir(parents=True, exist_ok=False)
                cleared_hashes = _clear_native_resource_hashes(plan)
                _materialize_projection(plan, data_dir)
                if (
                    _calculate_projected_source_hash(
                        source_root,
                        plan.copied_files,
                        metadata=source_hash_metadata,
                    )
                    != source_hash
                ):
                    raise MaaFWProjectStoreError(
                        "staged import source changed while project payload was materialized"
                    )
                projected_payload_bytes = _tree_size(data_dir)
                payload_hash = _calculate_store_payload_hash(data_dir)
                warnings = list(plan.warnings)
                if cleared_hashes:
                    warnings.append(
                        "MaaFW native resource.hash values were cleared after projection; "
                        "recalculate hashes for the filtered tree before native hash validation."
                    )

                constraint = _resolve_runtime_constraint(
                    runtime_constraint,
                    plan.interface_data,
                    source_root,
                    interface_base,
                )
                if constraint is None:
                    warnings.append(
                        "No MaaFW runtime constraint was found in the ProjectInterface "
                        "or requirements files; managed routing must reject this version "
                        "until a constraint is supplied."
                    )
                agents = _build_agent_summary(plan.agent_runtime)
                capabilities = _build_capability_summary(plan)
                shells = _build_shell_summary(plan.excluded_reasons)
                size_summary = _build_size_summary(
                    source_tree_bytes=source_tree_bytes,
                    projected_payload_bytes=projected_payload_bytes,
                    input_size_bytes=imported_source.input_size_bytes,
                )
                manifest = {
                    "schemaVersion": MANIFEST_SCHEMA_VERSION,
                    "projectId": normalized_project_id,
                    "version": normalized_version,
                    "createdAt": imported_at,
                    "source": {
                        "kind": imported_source.kind,
                        "path": str(imported_source.input_path),
                        "projectPath": (
                            interface_base.relative_to(source_root).as_posix()
                            if interface_base != source_root
                            else "."
                        ),
                        "interfacePath": source_interface_path.relative_to(
                            source_root
                        ).as_posix(),
                        "interfaceVersion": interface_version,
                        # Compatibility alias retained for existing readers.
                        "version": interface_version,
                        "archiveSha256": imported_source.archive_sha256,
                        "inputSizeBytes": imported_source.input_size_bytes,
                        "treeSizeBytes": source_tree_bytes,
                        "hash": {
                            "algorithm": "sha256",
                            "scope": "projected-source",
                            "schemaVersion": _TREE_HASH_SCHEMA_VERSION,
                            "domain": _PROJECTED_SOURCE_HASH_DOMAIN_NAME,
                            "framing": _TREE_HASH_FRAMING,
                            "value": source_hash,
                        },
                    },
                    "payload": {
                        "hash": {
                            "algorithm": "sha256",
                            "scope": "store-payload",
                            "schemaVersion": _TREE_HASH_SCHEMA_VERSION,
                            "domain": _STORE_PAYLOAD_HASH_DOMAIN_NAME,
                            "framing": _TREE_HASH_FRAMING,
                            "value": payload_hash,
                        }
                    },
                    "projectInterface": {
                        "path": plan.interface_path.as_posix(),
                        "resourceHashCleared": bool(cleared_hashes),
                        "clearedResources": cleared_hashes,
                    },
                    "runtimeConstraint": constraint,
                    "requiredPythonAbi": plan.required_python_abi,
                    "agents": agents,
                    "capabilities": capabilities,
                    "shells": shells,
                    "size": size_summary,
                    "runtime": {
                        "constraint": constraint,
                        "platform": _optional_string(platform) or sys.platform,
                        "arch": _optional_string(arch)
                        or host_platform.machine()
                        or "unknown",
                        "python": _json_clone(plan.python_runtime),
                        "agent": agents,
                        "requiredPythonAbi": plan.required_python_abi,
                        "sharedAgentDependenciesComplete": (
                            plan.shared_agent_dependencies_complete
                        ),
                        "binding": _json_clone(runtime_binding),
                        "references": [reference.strip()]
                        if reference and reference.strip()
                        else [],
                        "leases": [],
                        "pinned": bool(pinned),
                        "lastUsedAt": imported_at if activate else None,
                    },
                    "projection": {
                        "copied": sorted(
                            _projection_output_path(plan, path).as_posix()
                            for path in plan.copied_files
                        ),
                        "copiedFromSource": sorted(
                            path.as_posix() for path in plan.copied_files
                        ),
                        "copiedDirectories": sorted(
                            {
                                _projection_output_path(plan, path).as_posix()
                                for path in plan.copied_directories
                                if path != Path(".")
                                and _projection_output_path(plan, path) != Path(".")
                            }
                        ),
                        "excluded": sorted(plan.excluded_reasons),
                        "excludedReasons": dict(sorted(plan.excluded_reasons.items())),
                        "sourceSizeBytes": source_tree_bytes,
                        "payloadSizeBytes": projected_payload_bytes,
                        "savedBytes": size_summary["savedBytes"],
                        "savedPercent": size_summary["savedPercent"],
                    },
                    "flags": {
                        "opaqueAgent": plan.opaque_agent,
                        "conservative": plan.conservative,
                    },
                    "warnings": warnings,
                }
                if normalized_remote_source is not None:
                    manifest["remote"] = normalized_remote_source
                _validate_project_manifest(
                    manifest,
                    expected_project_id=normalized_project_id,
                    expected_version=normalized_version,
                    data_path=data_dir,
                )
                _write_json(data_dir / MANIFEST_FILE_NAME, manifest)
                stage_dir.rename(final_dir)
            except FileExistsError as exc:
                if stage_dir.exists():
                    _safe_remove_tree(stage_dir, self.root)
                raise MaaFWProjectStoreError(
                    f"project version was created concurrently: "
                    f"{normalized_project_id}@{normalized_version}"
                ) from exc
            except Exception:
                if stage_dir.exists():
                    _safe_remove_tree(stage_dir, self.root)
                raise

            if activate:
                self._write_current(normalized_project_id, normalized_version)
            return self.resolve_project(
                normalized_project_id,
                normalized_version,
                touch=False,
            )

    def update_project(
        self,
        source_path: str | Path,
        project_id: str,
        version: str | None = None,
        *,
        runtime_constraint: str | None = None,
        platform: str | None = None,
        arch: str | None = None,
        runtime_binding: dict[str, Any] | None = None,
        remote_source: Mapping[str, Any] | None = None,
        reference: str | None = None,
        pinned: bool = False,
        activate: bool = True,
    ) -> dict[str, Any]:
        """Import an update as a new version; existing versions are never patched."""

        return self.import_project(
            source_path,
            project_id,
            version,
            runtime_constraint=runtime_constraint,
            platform=platform,
            arch=arch,
            runtime_binding=runtime_binding,
            remote_source=remote_source,
            reference=reference,
            pinned=pinned,
            activate=activate,
        )

    def resolve_project(
        self,
        project_id: str,
        version: str | None = None,
        *,
        touch: bool = True,
    ) -> dict[str, Any]:
        """Resolve a version to a runnable project directory.

        If ``version`` is omitted, the current pointer is preferred and the
        newest imported version is used as a tolerant fallback.
        """

        normalized_project_id = _validate_component(project_id, "project_id")
        with self._lock:
            resolved_version = self._resolve_version(normalized_project_id, version)
            manifest = self._load_manifest(normalized_project_id, resolved_version)
            if touch:
                manifest["runtime"]["lastUsedAt"] = _format_timestamp()
                self._write_manifest(normalized_project_id, resolved_version, manifest)
            return self._build_resolved_record(manifest)

    def checkout_project(
        self,
        project_id: str,
        version: str | None,
        script_id: str,
    ) -> dict[str, Any]:
        """Materialize an isolated, reusable writable copy for one script.

        Store payloads remain immutable. A checkout is copied in full into the
        run root, marked, and atomically published only after the copy succeeds.
        Existing matching checkouts are returned without touching their user
        output; malformed or conflicting directories are never overwritten.
        """

        normalized_project_id = _validate_component(project_id, "project_id")
        normalized_script_id = _validate_component(script_id, "script_id")
        with self._lock, self._run_lock:
            self._assert_store_identity_unchanged()
            self._assert_run_identity_unchanged()
            resolved_version = self._resolve_version(
                normalized_project_id,
                version,
            )
            manifest = self._load_manifest(
                normalized_project_id,
                resolved_version,
            )
            source_hash = _manifest_source_hash(manifest)
            source_dir = (
                self._version_dir(
                    normalized_project_id,
                    resolved_version,
                )
                / "data"
            )
            payload_hash = _manifest_payload_hash(manifest)
            identity = {
                "storeId": self._root_identity["storeId"],
                "projectId": normalized_project_id,
                "version": resolved_version,
                "sourceHash": source_hash,
                "payloadHash": payload_hash,
                "scriptId": normalized_script_id,
            }
            checkout_id = _checkout_id(identity)
            script_root = self._run_scripts_root / normalized_script_id
            final_dir = script_root / "checkouts" / checkout_id
            _assert_path_chain_within_root(final_dir, self.run_root)
            self._verify_store_payload(manifest, source_dir)
            if final_dir.exists() or final_dir.is_symlink():
                return self._load_checkout(final_dir, identity, manifest, reused=True)

            stage_dir = self._run_staging_root / f"{checkout_id}-{uuid.uuid4().hex}"
            _assert_path_chain_within_root(stage_dir, self.run_root)
            data_dir = stage_dir / "data"
            try:
                stage_dir.mkdir(parents=True, exist_ok=False)
                _copy_checkout_tree(source_dir, data_dir)
                copied_hash = _calculate_store_payload_hash(
                    data_dir,
                    hash_schema_version=_manifest_hash_schema_version(
                        manifest,
                        "payload",
                    ),
                )
                if copied_hash != payload_hash:
                    raise MaaFWProjectStoreError(
                        "project-store payload changed while preparing checkout; "
                        "refusing to publish an inconsistent run directory"
                    )
                marker = {
                    "schemaVersion": CHECKOUT_SCHEMA_VERSION,
                    "kind": CHECKOUT_KIND,
                    "checkoutId": checkout_id,
                    "runRootId": self._run_root_identity["runRootId"],
                    "identity": identity,
                    "createdAt": _format_timestamp(),
                    "lastUsedAt": _format_timestamp(),
                    "dataRelativePath": "data",
                    "leases": [],
                }
                _write_json(stage_dir / CHECKOUT_MARKER_NAME, marker)
                self._validate_checkout(stage_dir, identity, manifest)
                final_dir.parent.mkdir(parents=True, exist_ok=True)
                _assert_path_chain_within_root(final_dir.parent, self.run_root)
                stage_dir.replace(final_dir)
            except FileExistsError as exc:
                if stage_dir.exists():
                    _safe_remove_tree(stage_dir, self.run_root)
                if final_dir.exists() or final_dir.is_symlink():
                    return self._load_checkout(
                        final_dir,
                        identity,
                        manifest,
                        reused=True,
                    )
                raise MaaFWProjectStoreError(
                    f"project checkout path conflict: {final_dir}"
                ) from exc
            except Exception:
                if stage_dir.exists():
                    _safe_remove_tree(stage_dir, self.run_root)
                raise
            return self._load_checkout(final_dir, identity, manifest, reused=False)

    def _load_checkout(
        self,
        checkout_root: Path,
        expected_identity: dict[str, str],
        manifest: dict[str, Any],
        *,
        reused: bool,
    ) -> dict[str, Any]:
        marker = self._validate_checkout(checkout_root, expected_identity, manifest)
        if reused:
            if marker.get("leases") is None:
                marker["leases"] = []
            marker["lastUsedAt"] = _format_timestamp()
            _write_json_atomic(
                checkout_root / CHECKOUT_MARKER_NAME,
                marker,
                self.run_root,
            )
        data_path = (checkout_root / "data").resolve(strict=True)
        lease_values = marker.get("leases")
        lease_capable = isinstance(lease_values, list)
        return {
            "checkoutId": marker["checkoutId"],
            "dataPath": str(data_path),
            "projectId": expected_identity["projectId"],
            "version": expected_identity["version"],
            "scriptId": expected_identity["scriptId"],
            "sourceHash": expected_identity["sourceHash"],
            "payloadHash": expected_identity["payloadHash"],
            "storeId": expected_identity["storeId"],
            "runRootId": self._run_root_identity["runRootId"],
            "reused": bool(reused),
            "createdAt": marker.get("createdAt"),
            "lastUsedAt": marker.get("lastUsedAt"),
            "leaseProtectionAvailable": lease_capable,
            "activeLeaseIds": [
                str(item["leaseId"])
                for item in _active_leases(
                    lease_values,
                    time.time(),
                )
            ],
        }

    def acquire_checkout_lease(
        self,
        checkout_id: str,
        script_id: str,
        lease_id: str,
        *,
        owner: str,
        ttl_seconds: float = 5 * 60,
    ) -> dict[str, Any]:
        if ttl_seconds <= 0:
            raise MaaFWProjectStoreError("checkout lease ttl_seconds must be positive")
        normalized_owner = str(owner or "").strip()
        normalized_lease_id = str(lease_id or "").strip()
        if not normalized_owner or not normalized_lease_id:
            raise MaaFWProjectStoreError(
                "checkout lease owner and lease_id are required"
            )
        with self._run_lock:
            marker_path, marker = self._load_checkout_marker_by_id(
                checkout_id,
                script_id,
            )
            if not isinstance(marker.get("leases"), list):
                raise MaaFWProjectStoreError(
                    "checkout marker does not support leases; refusing unsafe activation"
                )
            now_value = time.time()
            leases = [
                item
                for item in _active_leases(marker["leases"], now_value)
                if item.get("leaseId") != normalized_lease_id
            ]
            leases.append(
                {
                    "leaseId": normalized_lease_id,
                    "owner": normalized_owner,
                    "acquiredAt": _format_timestamp(now_value),
                    "expiresAt": _format_timestamp(now_value + float(ttl_seconds)),
                }
            )
            marker["leases"] = leases
            marker["lastUsedAt"] = _format_timestamp(now_value)
            _write_json_atomic(marker_path, marker, self.run_root)
            return self._checkout_marker_record(marker_path.parent, marker)

    def release_checkout_lease(
        self,
        checkout_id: str,
        script_id: str,
        lease_id: str,
    ) -> dict[str, Any]:
        normalized_lease_id = str(lease_id or "").strip()
        if not normalized_lease_id:
            raise MaaFWProjectStoreError("checkout lease_id is required")
        with self._run_lock:
            marker_path, marker = self._load_checkout_marker_by_id(
                checkout_id,
                script_id,
            )
            leases = marker.get("leases")
            if not isinstance(leases, list):
                raise MaaFWProjectStoreError("checkout marker does not support leases")
            marker["leases"] = [
                item
                for item in _active_leases(leases, time.time())
                if item.get("leaseId") != normalized_lease_id
            ]
            _write_json_atomic(marker_path, marker, self.run_root)
            return self._checkout_marker_record(marker_path.parent, marker)

    def _load_checkout_marker_by_id(
        self,
        checkout_id: str,
        script_id: str,
    ) -> tuple[Path, dict[str, Any]]:
        normalized_checkout_id = str(checkout_id or "").strip()
        if not re.fullmatch(r"maafw-checkout-[0-9a-f]{32}", normalized_checkout_id):
            raise MaaFWProjectStoreError("checkout_id is invalid")
        normalized_script_id = _validate_component(script_id, "script_id")
        checkout_root = (
            self._run_scripts_root
            / normalized_script_id
            / "checkouts"
            / normalized_checkout_id
        )
        _assert_path_chain_within_root(checkout_root, self.run_root)
        marker_path = checkout_root / CHECKOUT_MARKER_NAME
        _assert_not_reparse(marker_path)
        try:
            marker = _validate_checkout_marker(
                json.loads(marker_path.read_text(encoding="utf-8"))
            )
        except Exception as exc:
            raise MaaFWProjectStoreError(f"cannot read checkout marker: {exc}") from exc
        if (
            marker["checkoutId"] != normalized_checkout_id
            or marker["identity"]["scriptId"] != normalized_script_id
            or marker["runRootId"] != self._run_root_identity["runRootId"]
        ):
            raise MaaFWProjectStoreError("checkout marker identity mismatch")
        return marker_path, marker

    def _checkout_marker_record(
        self,
        checkout_root: Path,
        marker: Mapping[str, Any],
    ) -> dict[str, Any]:
        identity = dict(marker["identity"])
        leases = marker.get("leases")
        return {
            "checkoutId": marker["checkoutId"],
            "dataPath": str((checkout_root / "data").resolve(strict=True)),
            **identity,
            "runRootId": marker["runRootId"],
            "createdAt": marker.get("createdAt"),
            "lastUsedAt": marker.get("lastUsedAt"),
            "leaseProtectionAvailable": isinstance(leases, list),
            "activeLeaseIds": [
                str(item["leaseId"]) for item in _active_leases(leases, time.time())
            ],
        }

    def _validate_checkout(
        self,
        checkout_root: Path,
        expected_identity: dict[str, str],
        manifest: dict[str, Any],
    ) -> dict[str, Any]:
        _assert_path_chain_within_root(checkout_root, self.run_root)
        _assert_not_reparse(checkout_root)
        if not checkout_root.is_dir():
            raise MaaFWProjectStoreError(
                f"project checkout must be a directory: {checkout_root}"
            )
        marker_path = checkout_root / CHECKOUT_MARKER_NAME
        _assert_not_reparse(marker_path)
        if not marker_path.is_file():
            raise MaaFWProjectStoreError(
                f"project checkout marker is missing: {checkout_root}"
            )
        try:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise MaaFWProjectStoreError(
                f"project checkout marker is invalid: {exc}"
            ) from exc
        validated = _validate_checkout_marker(marker)
        expected_checkout_id = _checkout_id(expected_identity)
        if (
            validated["checkoutId"] != expected_checkout_id
            or validated["runRootId"] != self._run_root_identity["runRootId"]
            or validated["identity"] != expected_identity
        ):
            raise MaaFWProjectStoreError(
                f"project checkout identity mismatch: {checkout_root}"
            )
        data_path = checkout_root / "data"
        _assert_path_chain_within_root(data_path, self.run_root)
        _assert_not_reparse(data_path)
        if not data_path.is_dir():
            raise MaaFWProjectStoreError(
                f"project checkout data is missing: {checkout_root}"
            )
        if (data_path / MANIFEST_FILE_NAME).exists():
            raise MaaFWProjectStoreError(
                "project checkout contains the private Project Store manifest"
            )
        interface_relative = _normalize_relative_path(
            manifest.get("projectInterface", {}).get("path"),
            "projectInterface.path",
        )
        interface_path = data_path / interface_relative
        _assert_path_chain_within_root(interface_path, self.run_root)
        _assert_not_reparse(interface_path)
        if not interface_path.is_file():
            raise MaaFWProjectStoreError(
                f"project checkout interface is missing: {interface_path}"
            )
        return validated

    @staticmethod
    def _verify_store_payload(
        manifest: Mapping[str, Any],
        data_path: Path,
    ) -> str:
        expected_hash = _manifest_payload_hash(manifest)
        actual_hash = _calculate_store_payload_hash(
            data_path,
            hash_schema_version=_manifest_hash_schema_version(
                manifest,
                "payload",
            ),
        )
        if actual_hash != expected_hash:
            raise MaaFWProjectStoreError(
                "immutable project-store payload integrity check failed; "
                "refusing to create or reuse a checkout"
            )
        return expected_hash

    def list_versions(self, project_id: str) -> list[dict[str, Any]]:
        normalized_project_id = _validate_component(project_id, "project_id")
        with self._lock:
            current = self._read_current(normalized_project_id)
            records: list[dict[str, Any]] = []
            for version in self._iter_versions(normalized_project_id):
                manifest = self._load_manifest(normalized_project_id, version)
                record = self._build_resolved_record(manifest)
                runtime = manifest.get("runtime", {})
                record.update(
                    {
                        "current": version == current,
                        "pinned": bool(runtime.get("pinned")),
                        "references": list(runtime.get("references") or []),
                        "lastUsedAt": runtime.get("lastUsedAt"),
                    }
                )
                records.append(record)
            records.sort(
                key=lambda item: (
                    str(item["manifest"].get("createdAt") or ""),
                    str(item["version"]),
                ),
                reverse=True,
            )
            return records

    def list_projects(self) -> list[dict[str, Any]]:
        with self._lock:
            result: list[dict[str, Any]] = []
            for project_id in self._iter_projects():
                versions = self.list_versions(project_id)
                result.append(
                    {
                        "projectId": project_id,
                        "currentVersion": self._read_current(project_id),
                        "versionCount": len(versions),
                        "versions": [item["version"] for item in versions],
                        "versionSummaries": [
                            {
                                "version": item["version"],
                                "current": item["current"],
                                "activeLeaseIds": list(item["activeLeaseIds"]),
                                "summary": _json_clone(item["summary"]),
                            }
                            for item in versions
                        ],
                        "summary": next(
                            (
                                _json_clone(item["summary"])
                                for item in versions
                                if item["current"]
                            ),
                            _json_clone(versions[0]["summary"]) if versions else None,
                        ),
                    }
                )
            return result

    def inventory(self) -> dict[str, Any]:
        """Return a fail-closed inventory instead of hiding corrupt entries."""

        with self._lock, self._run_lock:
            self._assert_store_identity_unchanged()
            self._assert_run_identity_unchanged()
            errors = self._inventory_project_structure()
            try:
                items = self.list_projects()
            except Exception as exc:
                items = []
                errors.append(
                    {
                        "scope": "project-store",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
            checkouts, checkout_errors = self._inventory_checkouts()
            errors.extend(checkout_errors)
            return {
                "complete": not errors,
                "items": items,
                "checkouts": checkouts,
                "errors": errors,
                "rootIdentity": self.root_identity,
                "runRootIdentity": _json_clone(self._run_root_identity),
            }

    def _inventory_project_structure(self) -> list[dict[str, Any]]:
        """Report Store-shaped entries that tolerant list APIs would skip."""

        errors: list[dict[str, Any]] = []
        for project_root in self._projects_root.iterdir():
            try:
                _assert_not_reparse(project_root)
                if not project_root.is_dir():
                    raise MaaFWProjectStoreError(
                        f"project-store entry must be a directory: {project_root}"
                    )
                project_id = _validate_component(project_root.name, "project_id")
                unknown = [
                    item
                    for item in project_root.iterdir()
                    if item.name not in {"current.json", "versions"}
                ]
                if unknown:
                    raise MaaFWProjectStoreError(
                        f"project directory contains unknown entries: {project_root}"
                    )
                current_path = project_root / "current.json"
                if current_path.exists() or current_path.is_symlink():
                    _assert_not_reparse(current_path)
                    self._read_current(project_id)
                versions_root = project_root / "versions"
                if not versions_root.exists():
                    raise MaaFWProjectStoreError(
                        f"project versions directory is missing: {project_root}"
                    )
                _assert_not_reparse(versions_root)
                if not versions_root.is_dir():
                    raise MaaFWProjectStoreError(
                        f"project versions path must be a directory: {versions_root}"
                    )
                for version_root in versions_root.iterdir():
                    version_name = version_root.name
                    try:
                        _assert_not_reparse(version_root)
                        if not version_root.is_dir():
                            raise MaaFWProjectStoreError(
                                "project version entry must be a directory: "
                                f"{version_root}"
                            )
                        version = _validate_component(version_name, "version")
                        manifest_path = self._manifest_path(project_id, version)
                        _assert_path_chain_within_root(manifest_path, self.root)
                        _assert_not_reparse(manifest_path)
                        if not manifest_path.is_file():
                            raise MaaFWProjectStoreError(
                                "project version manifest is missing: "
                                f"{project_id}@{version}"
                            )
                        manifest = self._load_manifest(project_id, version)
                        self._verify_store_payload(
                            manifest,
                            version_root / "data",
                        )
                    except Exception as exc:
                        errors.append(
                            {
                                "scope": "project-version",
                                "projectId": project_id,
                                "version": version_name,
                                "path": str(version_root),
                                "error": f"{type(exc).__name__}: {exc}",
                            }
                        )
            except Exception as exc:
                errors.append(
                    {
                        "scope": "project-store",
                        "path": str(project_root),
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
        return errors

    def _inventory_checkouts(
        self,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        items: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for script_root in self._run_scripts_root.iterdir():
            try:
                _assert_not_reparse(script_root)
                script_id = _validate_component(script_root.name, "script_id")
                if not script_root.is_dir():
                    raise MaaFWProjectStoreError(
                        f"project run script path must be a directory: {script_root}"
                    )
                children = list(script_root.iterdir())
                unknown = [child for child in children if child.name != "checkouts"]
                if unknown:
                    raise MaaFWProjectStoreError(
                        f"project run script directory contains unknown entries: {script_root}"
                    )
                checkouts_root = script_root / "checkouts"
                if not checkouts_root.exists():
                    continue
                _assert_not_reparse(checkouts_root)
                if not checkouts_root.is_dir():
                    raise MaaFWProjectStoreError(
                        f"project checkouts path must be a directory: {checkouts_root}"
                    )
                for checkout_root in checkouts_root.iterdir():
                    try:
                        _assert_not_reparse(checkout_root)
                        marker_path = checkout_root / CHECKOUT_MARKER_NAME
                        _assert_not_reparse(marker_path)
                        marker = _validate_checkout_marker(
                            json.loads(marker_path.read_text(encoding="utf-8"))
                        )
                        identity = marker["identity"]
                        if (
                            not checkout_root.is_dir()
                            or marker["checkoutId"] != checkout_root.name
                            or marker["runRootId"]
                            != self._run_root_identity["runRootId"]
                            or identity["scriptId"] != script_id
                            or _checkout_id(identity) != checkout_root.name
                        ):
                            raise MaaFWProjectStoreError(
                                f"project checkout identity mismatch: {checkout_root}"
                            )
                        data_path = checkout_root / "data"
                        _assert_not_reparse(data_path)
                        if not data_path.is_dir():
                            raise MaaFWProjectStoreError(
                                f"project checkout data is missing: {checkout_root}"
                            )
                        if (data_path / MANIFEST_FILE_NAME).exists():
                            raise MaaFWProjectStoreError(
                                "project checkout contains the private Project Store manifest"
                            )
                        store_available = True
                        try:
                            manifest = self._load_manifest(
                                identity["projectId"],
                                identity["version"],
                            )
                        except MaaFWProjectStoreError:
                            store_available = False
                        else:
                            self._validate_checkout(
                                checkout_root,
                                identity,
                                manifest,
                            )
                        items.append(
                            {
                                "checkoutId": marker["checkoutId"],
                                "dataPath": str(data_path.resolve(strict=True)),
                                **identity,
                                "runRootId": marker["runRootId"],
                                "storeAvailable": store_available,
                                "createdAt": marker.get("createdAt"),
                                "lastUsedAt": marker.get("lastUsedAt"),
                                "leaseProtectionAvailable": isinstance(
                                    marker.get("leases"),
                                    list,
                                ),
                                "activeLeaseIds": [
                                    str(item["leaseId"])
                                    for item in _active_leases(
                                        marker.get("leases"),
                                        time.time(),
                                    )
                                ],
                            }
                        )
                    except Exception as exc:
                        errors.append(
                            {
                                "scope": "project-checkout",
                                "scriptId": script_id,
                                "path": str(checkout_root),
                                "error": f"{type(exc).__name__}: {exc}",
                            }
                        )
            except Exception as exc:
                errors.append(
                    {
                        "scope": "project-run-script",
                        "path": str(script_root),
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
        return items, errors

    def switch_version(self, project_id: str, version: str) -> dict[str, Any]:
        normalized_project_id = _validate_component(project_id, "project_id")
        normalized_version = _validate_component(version, "version")
        with self._lock:
            self._load_manifest(normalized_project_id, normalized_version)
            self._write_current(normalized_project_id, normalized_version)
            return self.resolve_project(
                normalized_project_id,
                normalized_version,
                touch=True,
            )

    def bind_runtime(
        self,
        project_id: str,
        version: str | None = None,
        *,
        binding: dict[str, Any] | None = None,
        reference: str | None = None,
        pinned: bool | None = None,
        touch: bool = True,
    ) -> dict[str, Any]:
        normalized_project_id = _validate_component(project_id, "project_id")
        with self._lock:
            resolved_version = self._resolve_version(normalized_project_id, version)
            manifest = self._load_manifest(normalized_project_id, resolved_version)
            runtime = manifest.setdefault("runtime", {})
            if binding is not None:
                runtime["binding"] = _json_clone(binding)
            if reference is not None:
                normalized_reference = reference.strip()
                if not normalized_reference:
                    raise MaaFWProjectStoreError("reference cannot be empty")
                references = [
                    item
                    for item in runtime.get("references") or []
                    if isinstance(item, str)
                ]
                if normalized_reference not in references:
                    references.append(normalized_reference)
                runtime["references"] = references
            if pinned is not None:
                runtime["pinned"] = bool(pinned)
            if touch:
                runtime["lastUsedAt"] = _format_timestamp()
            self._write_manifest(normalized_project_id, resolved_version, manifest)
            return self._build_resolved_record(manifest)

    def release_runtime(
        self,
        project_id: str,
        version: str | None = None,
        *,
        reference: str | None = None,
        clear_binding: bool = False,
        unpin: bool = False,
    ) -> dict[str, Any]:
        normalized_project_id = _validate_component(project_id, "project_id")
        with self._lock:
            resolved_version = self._resolve_version(normalized_project_id, version)
            manifest = self._load_manifest(normalized_project_id, resolved_version)
            runtime = manifest.setdefault("runtime", {})
            if reference is not None:
                runtime["references"] = [
                    item
                    for item in runtime.get("references") or []
                    if isinstance(item, str) and item != reference
                ]
            if clear_binding:
                runtime["binding"] = None
            if unpin:
                runtime["pinned"] = False
            self._write_manifest(normalized_project_id, resolved_version, manifest)
            return self._build_resolved_record(manifest)

    def set_references(
        self,
        project_id: str,
        version: str | None,
        references: list[str],
        *,
        touch: bool = False,
    ) -> dict[str, Any]:
        """Replace the complete reference set during host reconciliation."""

        if not isinstance(references, list):
            raise MaaFWProjectStoreError("references must be a string array")
        normalized_references: list[str] = []
        for reference in references:
            if not isinstance(reference, str) or not reference.strip():
                raise MaaFWProjectStoreError(
                    "references must contain non-empty strings"
                )
            normalized = reference.strip()
            if normalized not in normalized_references:
                normalized_references.append(normalized)

        normalized_project_id = _validate_component(project_id, "project_id")
        with self._lock:
            resolved_version = self._resolve_version(normalized_project_id, version)
            manifest = self._load_manifest(normalized_project_id, resolved_version)
            runtime = manifest.setdefault("runtime", {})
            runtime["references"] = normalized_references
            if touch:
                runtime["lastUsedAt"] = _format_timestamp()
            self._write_manifest(normalized_project_id, resolved_version, manifest)
            return self._build_resolved_record(manifest)

    def acquire_lease(
        self,
        project_id: str,
        version: str | None = None,
        *,
        owner: str,
        ttl_seconds: float = 5 * 60,
        lease_id: str | None = None,
    ) -> dict[str, Any]:
        """Acquire a renewable lease protecting a resolved dataPath from GC."""

        normalized_owner = str(owner or "").strip()
        if not normalized_owner:
            raise MaaFWProjectStoreError("lease owner cannot be empty")
        if ttl_seconds <= 0:
            raise MaaFWProjectStoreError("lease ttl_seconds must be positive")
        normalized_lease_id = str(lease_id or uuid.uuid4().hex).strip()
        if not normalized_lease_id:
            raise MaaFWProjectStoreError("lease_id cannot be empty")

        normalized_project_id = _validate_component(project_id, "project_id")
        with self._lock:
            resolved_version = self._resolve_version(normalized_project_id, version)
            manifest = self._load_manifest(normalized_project_id, resolved_version)
            runtime = manifest.setdefault("runtime", {})
            now_value = time.time()
            leases = [
                item
                for item in _active_leases(runtime.get("leases"), now_value)
                if item.get("leaseId") != normalized_lease_id
            ]
            lease = {
                "leaseId": normalized_lease_id,
                "owner": normalized_owner,
                "acquiredAt": _format_timestamp(now_value),
                "expiresAt": _format_timestamp(now_value + float(ttl_seconds)),
            }
            leases.append(lease)
            runtime["leases"] = leases
            runtime["lastUsedAt"] = _format_timestamp(now_value)
            self._write_manifest(normalized_project_id, resolved_version, manifest)
            result = self._build_resolved_record(manifest)
            result["lease"] = lease
            return result

    def release_lease(
        self,
        project_id: str,
        version: str | None = None,
        *,
        lease_id: str,
    ) -> dict[str, Any]:
        normalized_lease_id = str(lease_id or "").strip()
        if not normalized_lease_id:
            raise MaaFWProjectStoreError("lease_id cannot be empty")
        normalized_project_id = _validate_component(project_id, "project_id")
        with self._lock:
            resolved_version = self._resolve_version(normalized_project_id, version)
            manifest = self._load_manifest(normalized_project_id, resolved_version)
            runtime = manifest.setdefault("runtime", {})
            runtime["leases"] = [
                item
                for item in _active_leases(runtime.get("leases"), time.time())
                if item.get("leaseId") != normalized_lease_id
            ]
            self._write_manifest(normalized_project_id, resolved_version, manifest)
            return self._build_resolved_record(manifest)

    def delete_version(self, project_id: str, version: str) -> dict[str, Any]:
        normalized_project_id = _validate_component(project_id, "project_id")
        normalized_version = _validate_component(version, "version")
        with self._lock:
            manifest = self._load_manifest(normalized_project_id, normalized_version)
            protection = self._protection_reasons(
                normalized_project_id,
                normalized_version,
                manifest,
            )
            if protection:
                raise MaaFWProjectStoreError(
                    f"project version is protected: {normalized_project_id}@{normalized_version} "
                    f"({', '.join(protection)})"
                )
            version_dir = self._version_dir(normalized_project_id, normalized_version)
            reclaimed_bytes = _tree_size(version_dir)
            _safe_remove_tree(version_dir, self.root)
            self._prune_empty_project_directories(normalized_project_id)
            return {
                "deleted": True,
                "projectId": normalized_project_id,
                "version": normalized_version,
                "reclaimedBytes": reclaimed_bytes,
            }

    def collect_garbage(
        self,
        *,
        project_id: str | None = None,
        dry_run: bool = True,
        grace_seconds: float = 24 * 60 * 60,
        keep_latest: int = 1,
        now: float | None = None,
        checkout_context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if grace_seconds < 0:
            raise MaaFWProjectStoreError("grace_seconds cannot be negative")
        if keep_latest < 0:
            raise MaaFWProjectStoreError("keep_latest cannot be negative")
        normalized_project_id = (
            _validate_component(project_id, "project_id")
            if project_id is not None
            else None
        )
        current_time = float(now if now is not None else time.time())

        with self._lock, self._run_lock:
            inventory = self.inventory()
            if not inventory["complete"]:
                if not dry_run:
                    raise MaaFWProjectStoreError(
                        "refusing project-store garbage collection because "
                        "resource inventory is incomplete"
                    )
                return {
                    "dryRun": True,
                    "complete": False,
                    "inventoryErrors": _json_clone(inventory["errors"]),
                    "graceSeconds": grace_seconds,
                    "keepLatest": keep_latest,
                    "candidates": [],
                    "deleted": [],
                    "kept": [],
                    "reclaimedBytes": 0,
                    "checkoutGarbageCollection": {
                        "candidates": [],
                        "deleted": [],
                        "kept": [],
                    },
                }
            checkout_gc = self._collect_checkout_garbage(
                inventory.get("checkouts") or [],
                dry_run=bool(dry_run),
                grace_seconds=float(grace_seconds),
                current_time=current_time,
                context=checkout_context,
            )
            project_ids = (
                [normalized_project_id]
                if normalized_project_id is not None
                else self._iter_projects()
            )
            candidates: list[dict[str, Any]] = []
            kept: list[dict[str, Any]] = []
            for candidate_project_id in project_ids:
                versions = self.list_versions(candidate_project_id)
                latest_versions = {item["version"] for item in versions[:keep_latest]}
                for item in versions:
                    manifest = item["manifest"]
                    version_value = str(item["version"])
                    reasons = self._protection_reasons(
                        candidate_project_id,
                        version_value,
                        manifest,
                        now=current_time,
                    )
                    if not dry_run:
                        runtime = manifest.setdefault("runtime", {})
                        active_leases = _active_leases(
                            runtime.get("leases"),
                            current_time,
                        )
                        if active_leases != runtime.get("leases"):
                            runtime["leases"] = active_leases
                            self._write_manifest(
                                candidate_project_id,
                                version_value,
                                manifest,
                            )
                    if version_value in latest_versions:
                        reasons.append("keep-latest")
                    age_anchor = manifest.get("runtime", {}).get(
                        "lastUsedAt"
                    ) or manifest.get("createdAt")
                    age_seconds = max(
                        0.0,
                        current_time - _parse_timestamp(age_anchor),
                    )
                    if age_seconds < grace_seconds:
                        reasons.append("grace-period")

                    summary = {
                        "projectId": candidate_project_id,
                        "version": version_value,
                        "dataPath": item["dataPath"],
                        "ageSeconds": age_seconds,
                    }
                    if reasons:
                        summary["reasons"] = sorted(set(reasons))
                        kept.append(summary)
                    else:
                        summary["bytes"] = _tree_size(
                            self._version_dir(candidate_project_id, version_value)
                        )
                        candidates.append(summary)

            deleted: list[dict[str, Any]] = []
            reclaimed_bytes = 0
            if not dry_run:
                for candidate in candidates:
                    version_dir = self._version_dir(
                        candidate["projectId"],
                        candidate["version"],
                    )
                    if (
                        self._read_current(candidate["projectId"])
                        == candidate["version"]
                    ):
                        self._clear_current(
                            candidate["projectId"],
                            candidate["version"],
                        )
                    _safe_remove_tree(version_dir, self.root)
                    reclaimed_bytes += int(candidate["bytes"])
                    deleted.append(dict(candidate))
                for candidate_project_id in project_ids:
                    self._prune_empty_project_directories(candidate_project_id)

            return {
                "dryRun": bool(dry_run),
                "complete": True,
                "inventoryErrors": [],
                "graceSeconds": grace_seconds,
                "keepLatest": keep_latest,
                "candidates": candidates,
                "deleted": deleted,
                "kept": kept,
                "reclaimedBytes": reclaimed_bytes,
                "checkoutGarbageCollection": checkout_gc,
            }

    def _collect_checkout_garbage(
        self,
        checkouts: Iterable[Mapping[str, Any]],
        *,
        dry_run: bool,
        grace_seconds: float,
        current_time: float,
        context: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        context_data = dict(context) if isinstance(context, Mapping) else {}
        bindings_value = context_data.get("managedBindings")
        bindings = dict(bindings_value) if isinstance(bindings_value, Mapping) else {}
        active_script_ids_value = context_data.get("activeScriptIds")
        if not isinstance(active_script_ids_value, (list, tuple, set, frozenset)):
            active_script_ids_value = []
        active_script_ids = {
            str(item).strip()
            for item in active_script_ids_value
            if isinstance(item, str) and item.strip()
        }
        confirmed = bool(context_data.get("confirmed"))
        candidates: list[dict[str, Any]] = []
        kept: list[dict[str, Any]] = []
        deleted: list[dict[str, Any]] = []
        reclaimed_bytes = 0
        for raw_checkout in checkouts:
            checkout = dict(raw_checkout)
            script_id = str(checkout.get("scriptId") or "")
            project_id = str(checkout.get("projectId") or "")
            version = str(checkout.get("version") or "")
            checkout_id = str(checkout.get("checkoutId") or "")
            binding_value = bindings.get(script_id)
            binding = (
                dict(binding_value) if isinstance(binding_value, Mapping) else None
            )
            binding_matches = bool(
                binding
                and str(binding.get("projectId") or "") == project_id
                and str(binding.get("version") or "") == version
            )
            orphan_reason = None
            if binding is None:
                orphan_reason = "managed-script-missing"
            elif not binding_matches:
                orphan_reason = "script-binding-moved"
            elif not checkout.get("storeAvailable"):
                orphan_reason = "store-version-missing"

            reasons: list[str] = []
            if not context_data:
                reasons.append("checkout-context-unavailable")
            if binding_matches:
                reasons.append("managed-script-binding")
            if script_id in active_script_ids:
                reasons.append("active-operation")
            if checkout.get("activeLeaseIds"):
                reasons.append("active-lease")
            if not checkout.get("leaseProtectionAvailable"):
                reasons.append("checkout-lease-unavailable")
            age_anchor = checkout.get("lastUsedAt") or checkout.get("createdAt")
            age_seconds = max(0.0, current_time - _parse_timestamp(age_anchor))
            if age_seconds < grace_seconds:
                reasons.append("grace-period")
            if orphan_reason is None and not binding_matches:
                reasons.append("orphan-state-unknown")
            if not dry_run and not confirmed:
                reasons.append("explicit-confirmation-required")

            summary = {
                "checkoutId": checkout_id,
                "scriptId": script_id,
                "projectId": project_id,
                "version": version,
                "dataPath": checkout.get("dataPath"),
                "ageSeconds": age_seconds,
                "orphanReason": orphan_reason,
            }
            if reasons:
                summary["reasons"] = sorted(set(reasons))
                kept.append(summary)
                continue
            checkout_root = (
                self._run_scripts_root
                / _validate_component(script_id, "script_id")
                / "checkouts"
                / checkout_id
            )
            summary["bytes"] = _tree_size(checkout_root)
            candidates.append(summary)
            if dry_run:
                continue
            marker_path, marker = self._load_checkout_marker_by_id(
                checkout_id,
                script_id,
            )
            marker_identity = marker["identity"]
            if (
                marker_identity["projectId"] != project_id
                or marker_identity["version"] != version
            ):
                raise MaaFWProjectStoreError(
                    f"checkout identity changed during garbage collection: {checkout_id}"
                )
            if not isinstance(marker.get("leases"), list):
                raise MaaFWProjectStoreError(
                    f"checkout lease protection became unavailable during garbage collection: {checkout_id}"
                )
            if _active_leases(marker.get("leases"), time.time()):
                raise MaaFWProjectStoreError(
                    f"checkout became active during garbage collection: {checkout_id}"
                )
            refreshed_age_anchor = marker.get("lastUsedAt") or marker.get("createdAt")
            if (
                max(0.0, time.time() - _parse_timestamp(refreshed_age_anchor))
                < grace_seconds
            ):
                raise MaaFWProjectStoreError(
                    f"checkout was reused during garbage collection: {checkout_id}"
                )
            _safe_remove_tree(marker_path.parent, self.run_root)
            reclaimed_bytes += int(summary["bytes"])
            deleted.append(dict(summary))
            checkouts_root = marker_path.parent.parent
            script_root = checkouts_root.parent
            if checkouts_root.is_dir() and not any(checkouts_root.iterdir()):
                checkouts_root.rmdir()
            if script_root.is_dir() and not any(script_root.iterdir()):
                script_root.rmdir()
        return {
            "candidates": candidates,
            "deleted": deleted,
            "kept": kept,
            "reclaimedBytes": reclaimed_bytes,
        }

    def _build_resolved_record(self, manifest: dict[str, Any]) -> dict[str, Any]:
        project_id = str(manifest["projectId"])
        version = str(manifest["version"])
        data_path = self._version_dir(project_id, version) / "data"
        interface_relative = Path(str(manifest["projectInterface"]["path"]))
        interface_path = (data_path / interface_relative).resolve(strict=True)
        _assert_within(interface_path, data_path)
        runtime = manifest.get("runtime")
        runtime = runtime if isinstance(runtime, dict) else {}
        active_lease_ids = [
            str(item["leaseId"])
            for item in _active_leases(runtime.get("leases"), time.time())
        ]
        return {
            "dataPath": str(data_path.resolve(strict=True)),
            "storeId": self._root_identity["storeId"],
            "projectId": project_id,
            "version": version,
            "runtimeConstraint": manifest.get("runtime", {}).get("constraint"),
            "activeLeaseIds": active_lease_ids,
            "manifestPath": str((data_path / MANIFEST_FILE_NAME).resolve(strict=True)),
            "projectInterfacePath": str(interface_path),
            "summary": _build_inventory_summary(manifest),
            "manifest": _json_clone(manifest),
        }

    def _project_dir(self, project_id: str) -> Path:
        return self._projects_root / _validate_component(project_id, "project_id")

    def _version_dir(self, project_id: str, version: str) -> Path:
        path = (
            self._project_dir(project_id)
            / "versions"
            / _validate_component(version, "version")
        )
        _assert_path_chain_within_root(path, self.root)
        return path

    def _manifest_path(self, project_id: str, version: str) -> Path:
        return self._version_dir(project_id, version) / "data" / MANIFEST_FILE_NAME

    def _load_manifest(self, project_id: str, version: str) -> dict[str, Any]:
        self._assert_store_identity_unchanged()
        manifest_path = self._manifest_path(project_id, version)
        if not manifest_path.is_file():
            raise MaaFWProjectStoreError(
                f"project version does not exist: {project_id}@{version}"
            )
        _assert_path_chain_within_root(manifest_path, self.root)
        _assert_not_reparse(manifest_path)
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise MaaFWProjectStoreError(
                f"cannot read project manifest: {project_id}@{version}: {exc}"
            ) from exc
        data_path = manifest_path.parent
        validated = _validate_project_manifest(
            payload,
            expected_project_id=project_id,
            expected_version=version,
            data_path=data_path,
            allow_legacy_schema=True,
        )
        if validated["schemaVersion"] == LEGACY_MANIFEST_SCHEMA_VERSION:
            validated = self._migrate_legacy_manifest(
                project_id,
                version,
                validated,
                data_path,
            )
        return _validate_project_manifest(
            validated,
            expected_project_id=project_id,
            expected_version=version,
            data_path=data_path,
        )

    def _migrate_legacy_manifest(
        self,
        project_id: str,
        version: str,
        manifest: dict[str, Any],
        data_path: Path,
    ) -> dict[str, Any]:
        """Annotate schema-2 hashes without changing their stable identities.

        Schema 2 used an ambiguous legacy tree framing. Existing checkout IDs
        contain those hash values, so rewriting them would strand writable
        per-script state. Verify the legacy payload first, then make the old
        framing explicit and upgrade only the private manifest metadata.
        """

        self._verify_store_payload(manifest, data_path)
        if "hashCompatibility" in manifest:
            raise MaaFWProjectStoreError(
                "legacy project manifest contains an unexpected hashCompatibility field"
            )
        migrated = _json_clone(manifest)
        migrated["schemaVersion"] = MANIFEST_SCHEMA_VERSION
        migrated["runtime"].setdefault("python", None)
        for section_name in ("source", "payload"):
            section = migrated[section_name]
            hash_value = section["hash"]
            hash_value["schemaVersion"] = _LEGACY_TREE_HASH_SCHEMA_VERSION
            hash_value["framing"] = _LEGACY_TREE_HASH_FRAMING
        migrated["hashCompatibility"] = {
            "migratedFromManifestSchemaVersion": LEGACY_MANIFEST_SCHEMA_VERSION,
            "sourceHashSchemaVersion": _LEGACY_TREE_HASH_SCHEMA_VERSION,
            "payloadHashSchemaVersion": _LEGACY_TREE_HASH_SCHEMA_VERSION,
            "migratedAt": _format_timestamp(),
        }
        _validate_project_manifest(
            migrated,
            expected_project_id=project_id,
            expected_version=version,
            data_path=data_path,
        )
        _write_json_atomic(
            self._manifest_path(project_id, version),
            migrated,
            self.root,
        )
        return migrated

    def _write_manifest(
        self,
        project_id: str,
        version: str,
        manifest: dict[str, Any],
    ) -> None:
        self._assert_store_identity_unchanged()
        _validate_project_manifest(
            manifest,
            expected_project_id=project_id,
            expected_version=version,
            data_path=self._version_dir(project_id, version) / "data",
        )
        _write_json_atomic(
            self._manifest_path(project_id, version),
            manifest,
            self.root,
        )

    def _resolve_version(self, project_id: str, version: str | None) -> str:
        if version is not None:
            normalized = _validate_component(version, "version")
            self._load_manifest(project_id, normalized)
            return normalized
        current = self._read_current(project_id)
        if current is not None:
            return current
        versions = self._iter_versions(project_id)
        if not versions:
            raise MaaFWProjectStoreError(f"project does not exist: {project_id}")
        manifests = [(item, self._load_manifest(project_id, item)) for item in versions]
        manifests.sort(
            key=lambda item: str(item[1].get("createdAt") or ""),
            reverse=True,
        )
        return manifests[0][0]

    def _current_path(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "current.json"

    def _read_current(self, project_id: str) -> str | None:
        current_path = self._current_path(project_id)
        if not current_path.is_file():
            return None
        _assert_path_chain_within_root(current_path, self.root)
        try:
            payload = json.loads(current_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise MaaFWProjectStoreError(
                f"cannot read current pointer for {project_id}: {exc}"
            ) from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("version"), str):
            raise MaaFWProjectStoreError(f"invalid current pointer for {project_id}")
        version = _validate_component(payload["version"], "version")
        if not self._manifest_path(project_id, version).is_file():
            raise MaaFWProjectStoreError(
                f"current pointer references missing version: {project_id}@{version}"
            )
        return version

    def _write_current(self, project_id: str, version: str) -> None:
        self._load_manifest(project_id, version)
        current_path = self._current_path(project_id)
        current_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json_atomic(
            current_path,
            {
                "projectId": project_id,
                "version": version,
                "updatedAt": _format_timestamp(),
            },
            self.root,
        )

    def _clear_current(self, project_id: str, expected_version: str) -> None:
        current_path = self._current_path(project_id)
        if not current_path.exists() and not current_path.is_symlink():
            return
        current = self._read_current(project_id)
        if current != expected_version:
            raise MaaFWProjectStoreError(
                "current pointer changed while collecting garbage: "
                f"{project_id}@{current or '<none>'}"
            )
        _assert_path_chain_within_root(current_path, self.root)
        current_path.unlink()

    def _iter_projects(self) -> list[str]:
        if not self._projects_root.exists():
            return []
        result: list[str] = []
        for child in self._projects_root.iterdir():
            _assert_not_reparse(child)
            if not child.is_dir():
                continue
            result.append(_validate_component(child.name, "project_id"))
        return sorted(result)

    def _iter_versions(self, project_id: str) -> list[str]:
        versions_root = self._project_dir(project_id) / "versions"
        if not versions_root.exists():
            return []
        _assert_path_chain_within_root(versions_root, self.root)
        result: list[str] = []
        for child in versions_root.iterdir():
            _assert_not_reparse(child)
            if not child.is_dir():
                continue
            version = _validate_component(child.name, "version")
            if self._manifest_path(project_id, version).is_file():
                result.append(version)
        return sorted(result)

    def _protection_reasons(
        self,
        project_id: str,
        version: str,
        manifest: dict[str, Any],
        *,
        now: float | None = None,
    ) -> list[str]:
        reasons: list[str] = []
        if self._read_current(project_id) == version:
            reasons.append("current")
        runtime = manifest.get("runtime", {})
        if runtime.get("pinned"):
            reasons.append("pinned")
        if runtime.get("references"):
            reasons.append("referenced")
        if _active_leases(
            runtime.get("leases"), now if now is not None else time.time()
        ):
            reasons.append("leased")
        return reasons

    def _prune_empty_project_directories(self, project_id: str) -> None:
        project_dir = self._project_dir(project_id)
        versions_dir = project_dir / "versions"
        if versions_dir.is_dir() and not any(versions_dir.iterdir()):
            versions_dir.rmdir()
        current_path = project_dir / "current.json"
        if (
            project_dir.is_dir()
            and not current_path.exists()
            and not any(project_dir.iterdir())
        ):
            project_dir.rmdir()


def _build_projection_plan(
    source_root: Path,
    source_interface_path: Path,
    interface_data: dict[str, Any],
) -> _ProjectionPlan:
    interface_base = source_interface_path.parent
    source_interface_relative = source_interface_path.relative_to(source_root)
    interface_path = _output_path_for_source(
        source_interface_relative,
        source_root,
        interface_base,
    )
    all_directories, all_files = _scan_safe_tree(source_root)
    target_modes: dict[Path, _ProjectionTargetMode] = {}
    required_paths: list[_RequiredProjectionPath] = []
    warnings: list[str] = []

    def add_target(
        relative_path: Path,
        *,
        complete: bool,
        required: bool,
        label: str,
        allow_excluded_root: bool = False,
        required_path: Path | None = None,
        agent_index: int | None = None,
        agent_key: str | None = None,
        python_entrypoint: bool = False,
        allow_stripped_python_interpreter: bool = False,
        allow_missing_python_interpreter: bool = False,
    ) -> None:
        normalized = _normalize_relative_path(
            relative_path.as_posix(),
            label,
            allow_root=True,
        )
        absolute = (source_root / normalized).resolve(strict=False)
        _assert_within(absolute, source_root)
        if not absolute.exists():
            if required and allow_missing_python_interpreter:
                exact_path = _normalize_relative_path(
                    (required_path or normalized).as_posix(),
                    f"required {label}",
                    allow_root=True,
                )
                exact_absolute = (source_root / exact_path).resolve(strict=False)
                _assert_within(exact_absolute, source_root)
                if exact_absolute.exists():
                    raise MaaFWProjectStoreError(
                        f"required {label} retention root does not exist: "
                        f"{relative_path.as_posix()}"
                    )
                required_paths.append(
                    _RequiredProjectionPath(
                        path=exact_path,
                        label=label,
                        is_directory=False,
                        agent_index=agent_index,
                        agent_key=agent_key,
                        python_entrypoint=python_entrypoint,
                        allow_stripped_python_interpreter=(
                            allow_stripped_python_interpreter
                        ),
                        source_missing=True,
                    )
                )
                return
            if required:
                raise MaaFWProjectStoreError(
                    f"required {label} path does not exist: {relative_path}"
                )
            warnings.append(
                f"optional {label} path was not found and was not copied: {relative_path}"
            )
            return
        previous = target_modes.get(
            normalized,
            _ProjectionTargetMode(complete=False, allow_excluded_root=False),
        )
        target_modes[normalized] = _ProjectionTargetMode(
            complete=bool(previous.complete or complete),
            allow_excluded_root=bool(
                previous.allow_excluded_root or allow_excluded_root
            ),
        )
        if required:
            exact_path = _normalize_relative_path(
                (required_path or normalized).as_posix(),
                f"required {label}",
                allow_root=True,
            )
            exact_absolute = (source_root / exact_path).resolve(strict=False)
            _assert_within(exact_absolute, source_root)
            if not exact_absolute.exists():
                raise MaaFWProjectStoreError(
                    f"required {label} path does not exist: {exact_path.as_posix()}"
                )
            required_paths.append(
                _RequiredProjectionPath(
                    path=exact_path,
                    label=label,
                    is_directory=exact_absolute.is_dir(),
                    agent_index=agent_index,
                    agent_key=agent_key,
                    python_entrypoint=python_entrypoint,
                    allow_stripped_python_interpreter=(
                        allow_stripped_python_interpreter
                    ),
                )
            )

    rewritten_json = _collect_and_rewrite_interfaces(
        source_root,
        interface_base,
        source_interface_path,
        interface_data,
        add_target,
    )

    for dependency_base in {source_root, interface_base}:
        for entry in dependency_base.iterdir():
            if entry.name.casefold() in _DEPENDENCY_DIR_NAMES and entry.is_dir():
                add_target(
                    entry.relative_to(source_root),
                    complete=False,
                    required=False,
                    label="agent dependency directory",
                )
            if entry.is_file() and any(
                fnmatch.fnmatchcase(entry.name, pattern)
                for pattern in _DEPENDENCY_FILE_PATTERNS
            ):
                add_target(
                    entry.relative_to(source_root),
                    complete=False,
                    required=False,
                    label="agent dependency file",
                )

    agent_runtime, agent_targets, opaque_agent = _inspect_agents(
        interface_data.get("agent"),
        interface_base,
        source_root,
        source_interface_relative.as_posix(),
    )
    for agent_target in agent_targets:
        add_target(
            agent_target,
            complete=False,
            required=False,
            label="agent dependency",
        )

    conservative = opaque_agent
    if conservative:
        target_modes[Path(".")] = _ProjectionTargetMode(
            complete=False,
            allow_excluded_root=False,
        )
        warnings.append(
            "Custom, Command or opaque agent detected; projection used conservative retention."
        )

    copied_files: set[Path] = set()
    copied_directories: set[Path] = {Path(".")}
    for target, mode in target_modes.items():
        target_absolute = source_root / target
        if target_absolute.is_file():
            if (
                _target_exclusion_reason(
                    target,
                    target=target,
                    mode=mode,
                    target_is_directory=False,
                )
                is None
            ):
                copied_files.add(target)
                copied_directories.update(_relative_parents(target))
            continue

        for directory in all_directories:
            if not _is_relative_to(directory, target):
                continue
            if (
                _target_exclusion_reason(
                    directory,
                    target=target,
                    mode=mode,
                    target_is_directory=True,
                    is_directory=True,
                )
                is None
            ):
                copied_directories.add(directory)
                copied_directories.update(_relative_parents(directory))
        for file_path in all_files:
            if not _is_relative_to(file_path, target):
                continue
            if (
                _target_exclusion_reason(
                    file_path,
                    target=target,
                    mode=mode,
                    target_is_directory=True,
                )
                is None
            ):
                copied_files.add(file_path)
                copied_directories.update(_relative_parents(file_path))

    _validate_required_projection_paths(
        required_paths,
        copied_files,
        copied_directories,
        agent_runtime,
        warnings,
    )
    for agent in agent_runtime:
        agent.pop("_projectionKey", None)

    excluded_reasons: dict[str, str] = {}
    for file_path in all_files - copied_files:
        excluded_reasons[file_path.as_posix()] = (
            _exclusion_reason(file_path) or "not-required-by-runtime-projection"
        )

    reserved_files = {
        path
        for path in copied_files
        if _projection_output_path_from_roots(
            path,
            source_root,
            interface_base,
        ).name
        == MANIFEST_FILE_NAME
    }
    for reserved in reserved_files:
        copied_files.remove(reserved)
        excluded_reasons[reserved.as_posix()] = "reserved-project-store-manifest"

    output_owners: dict[Path, Path] = {}
    for source_relative in copied_files:
        output_relative = _projection_output_path_from_roots(
            source_relative,
            source_root,
            interface_base,
        )
        owner = output_owners.setdefault(output_relative, source_relative)
        if owner != source_relative:
            raise MaaFWProjectStoreError(
                "projection path collision after promoting assets/: "
                f"{owner.as_posix()} and {source_relative.as_posix()} -> "
                f"{output_relative.as_posix()}"
            )

    required_python_abi = _detect_python_abi_tags(
        source_root,
        copied_files,
        agent_runtime,
    )
    for agent in agent_runtime:
        agent["abiTags"] = (
            list(required_python_abi) if agent.get("classification") == "python" else []
        )
    shared_agent_dependencies_complete = _shared_agent_dependencies_complete(
        source_root,
        interface_base,
        copied_files,
        agent_runtime,
    )
    python_runtime = _resolve_python_runtime_metadata(
        source_root,
        rewritten_json[source_interface_relative],
        agent_runtime,
    )
    _mark_declared_managed_python_agents(
        source_root=source_root,
        interface_base=interface_base,
        interface_data=interface_data,
        copied_files=copied_files,
        agent_runtime=agent_runtime,
        python_runtime=python_runtime,
    )
    python_agents = [
        agent for agent in agent_runtime if agent.get("classification") == "python"
    ]
    if python_agents and python_runtime is None:
        indexes = ", ".join(str(agent.get("index")) for agent in python_agents)
        raise MaaFWProjectStoreError(
            "Python Agent runtime ABI is unknown for indexes "
            f"{indexes}; declare ProjectInterface runtime.python or provide one "
            "unambiguous bundled python3XY._pth/python3XY.dll marker"
        )
    if python_agents and not shared_agent_dependencies_complete:
        indexes = ", ".join(str(agent.get("index")) for agent in python_agents)
        raise MaaFWProjectStoreError(
            "managed Python Agent dependencies are incomplete for indexes "
            f"{indexes}; declare one complete root requirements.txt without "
            "includes, local paths or remote URLs before importing as Managed"
        )

    return _ProjectionPlan(
        source_root=source_root,
        interface_base=interface_base,
        source_interface_path=source_interface_relative,
        interface_path=interface_path,
        interface_data=rewritten_json[source_interface_relative],
        rewritten_json=rewritten_json,
        copied_files=copied_files,
        copied_directories=copied_directories,
        excluded_reasons=excluded_reasons,
        agent_runtime=agent_runtime,
        required_python_abi=required_python_abi,
        python_runtime=python_runtime,
        shared_agent_dependencies_complete=shared_agent_dependencies_complete,
        opaque_agent=opaque_agent,
        conservative=conservative,
        warnings=warnings,
    )


def _target_exclusion_reason(
    path: Path,
    *,
    target: Path,
    mode: _ProjectionTargetMode,
    target_is_directory: bool,
    is_directory: bool = False,
) -> str | None:
    """Apply exclusions relative to an explicitly complete resource root.

    A ProjectInterface may legitimately name a resource directory ``runtime``,
    ``python`` or ``venv``.  Those names are unsafe as release-level defaults,
    but an explicit complete resource/attach-resource declaration is stronger
    evidence.  Only that target's prefix is ignored; exclusions inside it still
    remove known MaaFramework, Python and UI payloads.
    """

    if not mode.complete or not mode.allow_excluded_root or target == Path("."):
        return _exclusion_reason(path, is_directory=is_directory)
    if target_is_directory:
        scoped_path = path.relative_to(target)
        return _exclusion_reason(scoped_path, is_directory=is_directory)
    return _exclusion_reason(Path(path.name), is_directory=is_directory)


def _validate_required_projection_paths(
    required_paths: Iterable[_RequiredProjectionPath],
    copied_files: set[Path],
    copied_directories: set[Path],
    agent_runtime: list[dict[str, Any]],
    warnings: list[str],
) -> None:
    requirements = list(required_paths)
    python_entrypoints: dict[str, set[Path]] = {}
    for requirement in requirements:
        if (
            requirement.agent_key is not None
            and requirement.python_entrypoint
            and requirement.path in copied_files
        ):
            python_entrypoints.setdefault(requirement.agent_key, set()).add(
                requirement.path
            )

    runtime_agents = {
        str(agent.get("_projectionKey")): agent
        for agent in agent_runtime
        if agent.get("_projectionKey") is not None
    }

    for requirement in requirements:
        retained = (
            requirement.path in copied_directories
            if requirement.is_directory
            else requirement.path in copied_files
        )
        if retained:
            continue
        reason = (
            "missing-embedded-python"
            if requirement.source_missing
            else _exclusion_reason(
                requirement.path,
                is_directory=requirement.is_directory,
            )
        )
        if (
            requirement.allow_stripped_python_interpreter
            and not requirement.is_directory
            and _is_python_interpreter_path(requirement.path)
            and reason
            in {
                "embedded-python",
                "embedded-runtime",
                "missing-embedded-python",
            }
            and requirement.agent_index is not None
            and requirement.agent_key is not None
            and python_entrypoints.get(requirement.agent_key)
            and runtime_agents.get(requirement.agent_key, {}).get("classification")
            == "python"
        ):
            entrypoints = sorted(
                path.as_posix() for path in python_entrypoints[requirement.agent_key]
            )
            agent = runtime_agents[requirement.agent_key]
            agent["strippedInterpreter"] = {
                "sourcePath": requirement.path.as_posix(),
                "reason": reason,
                "retainedEntrypoints": entrypoints,
            }
            agent["interpreterRoute"] = "managed-python"
            agent["projectedChildExec"] = "python"
            action = (
                "was missing and was replaced"
                if requirement.source_missing
                else "was stripped"
            )
            warnings.append(
                f"{requirement.label} embedded Python interpreter {action} "
                f"({requirement.path.as_posix()}); retained Python entrypoint(s): "
                f"{', '.join(entrypoints)}."
            )
            continue
        raise MaaFWProjectStoreError(
            f"required {requirement.label} path was excluded by the "
            f"resource-only projection: {requirement.path.as_posix()} "
            f"({reason or 'not-retained'})"
        )


def _shared_agent_dependencies_complete(
    source_root: Path,
    interface_base: Path,
    copied_files: Iterable[Path],
    agent_runtime: Iterable[dict[str, Any]],
) -> bool:
    """Return true only for the runner's flat, root-requirements model."""

    if not any(agent.get("classification") == "python" for agent in agent_runtime):
        return False

    projected_files: dict[Path, Path] = {}
    for source_relative in copied_files:
        output_relative = _projection_output_path_from_roots(
            source_relative,
            source_root,
            interface_base,
        )
        projected_files[output_relative] = source_relative

    requirements_source = projected_files.get(Path("requirements.txt"))
    if requirements_source is None:
        return False

    for output_relative in projected_files:
        if output_relative == Path("requirements.txt"):
            continue
        name = output_relative.name.casefold()
        if any(
            fnmatch.fnmatchcase(name, pattern.casefold())
            for pattern in _DEPENDENCY_FILE_PATTERNS
        ):
            return False

    requirements_path = (source_root / requirements_source).resolve(strict=True)
    _assert_within(requirements_path, source_root)
    _assert_not_reparse(requirements_path)
    try:
        lines = requirements_path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError):
        return False
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if (
            line.startswith("-")
            or line.startswith((".", "/", "\\"))
            or line.endswith("\\")
            or re.search(r"\s--(?:hash|config-settings|global-option)\b", line)
            or re.search(r"@\s*(?:file:|https?://|git\+)", line, re.IGNORECASE)
            or line.casefold().startswith(("file:", "http://", "https://", "git+"))
            or Path(line.split(";", 1)[0].strip()).suffix.casefold()
            in {".whl", ".zip", ".gz", ".bz2"}
        ):
            return False
    return True


def _mark_declared_managed_python_agents(
    *,
    source_root: Path,
    interface_base: Path,
    interface_data: Mapping[str, Any],
    copied_files: set[Path],
    agent_runtime: list[dict[str, Any]],
    python_runtime: Mapping[str, Any] | None,
) -> None:
    """Bind safe bare-Python Agents to an explicit managed interpreter.

    Some modern ProjectInterface releases already declare ``child_exec`` as
    ``python`` instead of bundling an interpreter.  Once ``runtime.python`` is
    authoritative, leaving those plans as generic ``external`` commands would
    silently pick whichever Python happens to be on PATH.  Record the exact
    Store indexes only when a real project-local script entrypoint survived
    projection; unsafe module/command invocations fail closed at import time.
    """

    if python_runtime is None:
        return
    raw_agents = interface_data.get("agent")
    if isinstance(raw_agents, Mapping):
        agents: list[Any] = [raw_agents]
    elif isinstance(raw_agents, list):
        agents = raw_agents
    else:
        agents = []

    for runtime_agent in agent_runtime:
        if (
            runtime_agent.get("classification") != "python"
            or runtime_agent.get("interpreterRoute") is not None
        ):
            continue
        index = runtime_agent.get("index")
        if type(index) is not int or index < 0 or index >= len(agents):
            raise MaaFWProjectStoreError(
                "Python Agent runtime index does not match ProjectInterface"
            )
        source_agent = agents[index]
        if not isinstance(source_agent, Mapping):
            raise MaaFWProjectStoreError(f"agent[{index}] must be a JSON object")
        child_exec = (
            _optional_string(source_agent.get("child_exec"))
            or _optional_string(source_agent.get("childExec"))
            or ""
        )
        if not _is_python_interpreter_path(Path(child_exec.replace("\\", "/"))):
            continue
        raw_args = source_agent.get("child_args")
        if raw_args is None:
            raw_args = source_agent.get("childArgs")
        entrypoint = _safe_python_entrypoint_argument(raw_args)
        if entrypoint is None:
            raise MaaFWProjectStoreError(
                f"agent[{index}] uses managed Python without a safe project-local "
                ".py/.pyw entrypoint; -m, -c and opaque commands are not supported"
            )
        source_path, output_path = _resolve_and_project_local_path(
            entrypoint,
            interface_base,
            source_root,
            f"agent[{index}] Python entrypoint",
            required=True,
        )
        if source_path.suffix.casefold() not in {".py", ".pyw"}:
            raise MaaFWProjectStoreError(
                f"agent[{index}] managed Python entrypoint must be .py or .pyw"
            )
        if source_path.relative_to(source_root) not in copied_files:
            raise MaaFWProjectStoreError(
                f"agent[{index}] managed Python entrypoint was not retained by "
                "the resource projection"
            )
        runtime_agent["interpreterRoute"] = "managed-python"
        runtime_agent["projectedChildExec"] = "python"
        runtime_agent["managedEntrypoint"] = output_path.as_posix()


def _safe_python_entrypoint_argument(raw_args: Any) -> str | None:
    if not isinstance(raw_args, list):
        return None
    consume_next = False
    after_options = False
    for raw_arg in raw_args:
        if not isinstance(raw_arg, str) or not raw_arg:
            return None
        if consume_next:
            consume_next = False
            continue
        if after_options:
            return raw_arg
        if raw_arg == "--":
            after_options = True
            continue
        if raw_arg in {"-c", "-m"}:
            return None
        if raw_arg in {"--check-hash-based-pycs", "-W", "-X"}:
            consume_next = True
            continue
        if raw_arg.startswith("-"):
            continue
        return raw_arg
    return None


def _is_python_interpreter_path(path: Path) -> bool:
    return path.name.casefold() in {
        "python",
        "python.exe",
        "python3",
        "python3.exe",
        "pythonw",
        "pythonw.exe",
        "py",
        "py.exe",
    }


def _collect_and_rewrite_interfaces(
    source_root: Path,
    interface_base: Path,
    root_interface_path: Path,
    root_data: dict[str, Any],
    add_target: Any,
) -> dict[Path, dict[str, Any]]:
    rewritten: dict[Path, dict[str, Any]] = {}
    visiting: set[Path] = set()

    def visit(interface_file: Path, data: dict[str, Any]) -> None:
        source_relative = interface_file.relative_to(source_root)
        if source_relative in rewritten:
            return
        if source_relative in visiting:
            raise MaaFWProjectStoreError(
                f"cyclic ProjectInterface import: {source_relative.as_posix()}"
            )
        visiting.add(source_relative)
        add_target(
            source_relative,
            complete=True,
            required=True,
            label="ProjectInterface",
        )
        projected = _json_clone(data)

        raw_imports = data.get("import")
        if raw_imports is None:
            projected_imports: list[str] | None = None
        else:
            if not isinstance(raw_imports, list) or not all(
                isinstance(item, str) and item.strip() for item in raw_imports
            ):
                raise MaaFWProjectStoreError(
                    "ProjectInterface import must be a string array"
                )
            projected_imports = []
            for raw_import in raw_imports:
                imported_path, projected_path = _resolve_and_project_local_path(
                    raw_import,
                    interface_base,
                    source_root,
                    "ProjectInterface import",
                    required=True,
                )
                if not imported_path.is_file():
                    raise MaaFWProjectStoreError(
                        f"ProjectInterface import is not a file: {raw_import}"
                    )
                projected_imports.append(_format_project_path(projected_path))
                visit(imported_path, _read_json_object(imported_path))
            projected["import"] = projected_imports

        _rewrite_resource_paths(
            data,
            projected,
            interface_base,
            source_root,
            add_target,
        )
        _rewrite_controller_paths(
            data,
            projected,
            interface_base,
            source_root,
            add_target,
        )
        _rewrite_language_paths(
            data,
            projected,
            interface_base,
            source_root,
            add_target,
        )
        _rewrite_agent_paths(
            data,
            projected,
            interface_base,
            source_root,
            add_target,
            agent_scope=source_relative.as_posix(),
        )
        _rewrite_pretask_paths(
            data,
            projected,
            interface_base,
            source_root,
            add_target,
        )
        rewritten[source_relative] = projected
        visiting.remove(source_relative)

    visit(root_interface_path, root_data)
    return rewritten


def _rewrite_resource_paths(
    source: dict[str, Any],
    projected: dict[str, Any],
    interface_base: Path,
    source_root: Path,
    add_target: Any,
) -> None:
    source_resources = source.get("resource")
    projected_resources = projected.get("resource")
    if not isinstance(source_resources, list) or not isinstance(
        projected_resources, list
    ):
        return
    for index, source_resource in enumerate(source_resources):
        if not isinstance(source_resource, dict) or index >= len(projected_resources):
            continue
        projected_resource = projected_resources[index]
        if not isinstance(projected_resource, dict):
            continue
        resource_name = (
            _optional_string(source_resource.get("name")) or f"resource[{index}]"
        )
        raw_paths = source_resource.get("path")
        if isinstance(raw_paths, str):
            source_values = [raw_paths]
            preserve_scalar = True
        elif isinstance(raw_paths, list):
            source_values = raw_paths
            preserve_scalar = False
        else:
            continue
        rewritten_paths: list[str] = []
        for raw_path in source_values:
            if not isinstance(raw_path, str):
                raise MaaFWProjectStoreError(
                    f"resource {resource_name} path must contain strings"
                )
            source_path, output_path = _resolve_and_project_local_path(
                raw_path,
                interface_base,
                source_root,
                f"resource {resource_name}",
                required=True,
                allow_root=True,
            )
            add_target(
                source_path.relative_to(source_root),
                complete=True,
                required=True,
                label=f"resource {resource_name}",
                allow_excluded_root=True,
            )
            rewritten_paths.append(_format_project_path(output_path))
        projected_resource["path"] = (
            rewritten_paths[0] if preserve_scalar else rewritten_paths
        )


def _rewrite_controller_paths(
    source: dict[str, Any],
    projected: dict[str, Any],
    interface_base: Path,
    source_root: Path,
    add_target: Any,
) -> None:
    source_controllers = source.get("controller")
    projected_controllers = projected.get("controller")
    if not isinstance(source_controllers, list) or not isinstance(
        projected_controllers, list
    ):
        return
    for index, source_controller in enumerate(source_controllers):
        if not isinstance(source_controller, dict) or index >= len(
            projected_controllers
        ):
            continue
        projected_controller = projected_controllers[index]
        if not isinstance(projected_controller, dict):
            continue
        key = (
            "attach_resource_path"
            if "attach_resource_path" in source_controller
            else "attachResourcePath"
        )
        raw_value = source_controller.get(key)
        if raw_value is None:
            continue
        if isinstance(raw_value, str):
            values = [raw_value]
            preserve_scalar = True
        elif isinstance(raw_value, list):
            values = raw_value
            preserve_scalar = False
        else:
            raise MaaFWProjectStoreError(
                f"controller[{index}].{key} must be a string array"
            )
        rewritten_paths: list[str] = []
        for raw_path in values:
            if not isinstance(raw_path, str):
                raise MaaFWProjectStoreError(
                    f"controller[{index}].{key} must contain strings"
                )
            source_path, output_path = _resolve_and_project_local_path(
                raw_path,
                interface_base,
                source_root,
                f"controller[{index}].{key}",
                required=True,
                allow_root=True,
            )
            add_target(
                source_path.relative_to(source_root),
                complete=True,
                required=True,
                label=f"controller[{index}].{key}",
                allow_excluded_root=True,
            )
            rewritten_paths.append(_format_project_path(output_path))
        projected_controller[key] = (
            rewritten_paths[0] if preserve_scalar else rewritten_paths
        )


def _rewrite_language_paths(
    source: dict[str, Any],
    projected: dict[str, Any],
    interface_base: Path,
    source_root: Path,
    add_target: Any,
) -> None:
    languages = source.get("languages")
    projected_languages = projected.get("languages")
    if not isinstance(languages, dict) or not isinstance(projected_languages, dict):
        return
    for language, raw_path in languages.items():
        if not isinstance(raw_path, str):
            raise MaaFWProjectStoreError(f"languages.{language} must be a string path")
        source_path, output_path = _resolve_and_project_local_path(
            raw_path,
            interface_base,
            source_root,
            f"languages.{language}",
            required=True,
        )
        if not source_path.is_file():
            raise MaaFWProjectStoreError(f"languages.{language} is not a file")
        add_target(
            source_path.relative_to(source_root),
            complete=True,
            required=True,
            label=f"languages.{language}",
        )
        projected_languages[language] = _format_project_path(output_path)


def _rewrite_agent_paths(
    source: dict[str, Any],
    projected: dict[str, Any],
    interface_base: Path,
    source_root: Path,
    add_target: Any,
    *,
    agent_scope: str,
) -> None:
    source_agents = source.get("agent")
    projected_agents = projected.get("agent")
    if isinstance(source_agents, dict):
        source_values = [source_agents]
        projected_values = (
            [projected_agents] if isinstance(projected_agents, dict) else []
        )
    elif isinstance(source_agents, list):
        source_values = source_agents
        projected_values = (
            projected_agents if isinstance(projected_agents, list) else []
        )
    else:
        return
    for index, source_agent in enumerate(source_values):
        if not isinstance(source_agent, dict) or index >= len(projected_values):
            continue
        projected_agent = projected_values[index]
        if not isinstance(projected_agent, dict):
            continue
        raw_child_exec = (
            _optional_string(source_agent.get("child_exec"))
            or _optional_string(source_agent.get("childExec"))
            or ""
        )
        raw_child_args = source_agent.get("child_args")
        if raw_child_args is None:
            raw_child_args = source_agent.get("childArgs")
        child_args = (
            [item for item in raw_child_args if isinstance(item, str)]
            if isinstance(raw_child_args, list)
            else []
        )
        declared_type = (
            _optional_string(source_agent.get("type"))
            or _optional_string(source_agent.get("kind"))
            or ""
        )
        classification, _opaque = _classify_agent(
            declared_type,
            raw_child_exec,
            child_args,
        )
        agent_key = f"{agent_scope}#{index}"
        for key in ("child_exec", "childExec"):
            raw_exec = source_agent.get(key)
            if not isinstance(raw_exec, str) or not _looks_like_local_path(raw_exec):
                continue
            source_path, output_path = _resolve_and_project_executable_path(
                raw_exec,
                interface_base,
                source_root,
                f"agent[{index}].{key}",
                required=False,
            )
            managed_python_interpreter = (
                classification == "python" and _is_python_interpreter_path(source_path)
            )
            if not source_path.exists() and not managed_python_interpreter:
                raise MaaFWProjectStoreError(
                    f"agent[{index}].{key} path does not exist in the "
                    f"unpacked release: {raw_exec}"
                )
            add_target(
                _agent_retention_root(source_path, source_root),
                complete=False,
                required=True,
                label=f"agent[{index}].{key}",
                required_path=source_path.relative_to(source_root),
                agent_index=index,
                agent_key=agent_key,
                python_entrypoint=(
                    classification == "python"
                    and source_path.suffix.casefold() in {".py", ".pyw"}
                ),
                allow_stripped_python_interpreter=(managed_python_interpreter),
                allow_missing_python_interpreter=managed_python_interpreter,
            )
            projected_agent[key] = (
                "python"
                if managed_python_interpreter
                and (
                    not source_path.exists()
                    or _exclusion_reason(source_path.relative_to(source_root))
                    in {"embedded-python", "embedded-runtime"}
                )
                else _format_project_path(output_path)
            )
        for key in ("child_args", "childArgs"):
            raw_args = source_agent.get(key)
            projected_args = projected_agent.get(key)
            if not isinstance(raw_args, list) or not isinstance(projected_args, list):
                continue
            for argument_index, raw_arg in enumerate(raw_args):
                if not isinstance(raw_arg, str) or not _looks_like_local_path(raw_arg):
                    continue
                source_path, output_path = _resolve_and_project_local_path(
                    raw_arg,
                    interface_base,
                    source_root,
                    f"agent[{index}].{key}[{argument_index}]",
                    required=True,
                )
                add_target(
                    _agent_retention_root(source_path, source_root),
                    complete=False,
                    required=True,
                    label=f"agent[{index}].{key}[{argument_index}]",
                    required_path=source_path.relative_to(source_root),
                    agent_index=index,
                    agent_key=agent_key,
                    python_entrypoint=(
                        classification == "python"
                        and source_path.suffix.casefold() in {".py", ".pyw"}
                    ),
                )
                projected_args[argument_index] = _format_project_path(output_path)


def _rewrite_pretask_paths(
    source: dict[str, Any],
    projected: dict[str, Any],
    interface_base: Path,
    source_root: Path,
    add_target: Any,
) -> None:
    source_pretasks = source.get("pretask")
    projected_pretasks = projected.get("pretask")
    if isinstance(source_pretasks, dict):
        source_values = [source_pretasks]
        projected_values = (
            [projected_pretasks] if isinstance(projected_pretasks, dict) else []
        )
    elif isinstance(source_pretasks, list):
        source_values = source_pretasks
        projected_values = (
            projected_pretasks if isinstance(projected_pretasks, list) else []
        )
    else:
        return
    for index, source_pretask in enumerate(source_values):
        if not isinstance(source_pretask, dict) or index >= len(projected_values):
            continue
        raw_exec = source_pretask.get("exec")
        projected_pretask = projected_values[index]
        if (
            not isinstance(projected_pretask, dict)
            or not isinstance(raw_exec, str)
            or not _looks_like_local_path(raw_exec)
        ):
            continue
        source_path, output_path = _resolve_and_project_executable_path(
            raw_exec,
            interface_base,
            source_root,
            f"pretask[{index}].exec",
            required=True,
        )
        add_target(
            _agent_retention_root(source_path, source_root),
            complete=False,
            required=True,
            label=f"pretask[{index}].exec",
            required_path=source_path.relative_to(source_root),
        )
        projected_pretask["exec"] = _format_project_path(output_path)


def _inspect_agents(
    raw_agents: Any,
    interface_base: Path,
    source_root: Path,
    agent_scope: str,
) -> tuple[list[dict[str, Any]], set[Path], bool]:
    agents = (
        raw_agents
        if isinstance(raw_agents, list)
        else ([raw_agents] if isinstance(raw_agents, dict) else [])
    )
    runtime: list[dict[str, Any]] = []
    targets: set[Path] = set()
    opaque_found = False

    for index, agent in enumerate(agents):
        child_exec = (
            _optional_string(agent.get("child_exec"))
            or _optional_string(agent.get("childExec"))
            or ""
        )
        child_args = agent.get("child_args")
        if child_args is None:
            child_args = agent.get("childArgs")
        args = (
            [item for item in child_args or [] if isinstance(item, str)]
            if isinstance(child_args, list)
            else []
        )
        declared_type = (
            _optional_string(agent.get("type"))
            or _optional_string(agent.get("kind"))
            or ""
        )
        classification, opaque = _classify_agent(declared_type, child_exec, args)
        opaque_found = opaque_found or opaque
        discovered_paths: list[str] = []
        for raw_candidate in [child_exec, *args]:
            candidate = _resolve_agent_candidate(
                interface_base,
                source_root,
                raw_candidate,
            )
            if candidate is None:
                continue
            relative = candidate.relative_to(source_root)
            projected_relative = _output_path_for_source(
                relative,
                source_root,
                interface_base,
            )
            discovered_paths.append(projected_relative.as_posix())
            targets.add(_agent_retention_root(candidate, source_root))
            if candidate.is_file():
                parent = relative.parent
                if parent == Path(".") and candidate.suffix.casefold() in {
                    ".py",
                    ".pyw",
                }:
                    for sibling in source_root.glob("*.py*"):
                        if sibling.is_file():
                            targets.add(sibling.relative_to(source_root))
                    for folder_name in ("src", "lib", "modules", candidate.stem):
                        folder = source_root / folder_name
                        if folder.is_dir():
                            targets.add(folder.relative_to(source_root))

        runtime.append(
            {
                "index": index,
                "declaredType": declared_type or None,
                "childExec": child_exec or None,
                "classification": classification,
                "embeddedRequested": agent.get("embedded") is True,
                "opaque": opaque,
                "projectPaths": discovered_paths,
                "_projectionKey": f"{agent_scope}#{index}",
            }
        )

    return runtime, targets, opaque_found


def _classify_agent(
    declared_type: str,
    child_exec: str,
    child_args: list[str],
) -> tuple[str, bool]:
    kind = declared_type.casefold()
    executable = Path(child_exec.replace("\\", "/")).name.casefold()
    suffixes = {Path(item.replace("\\", "/")).suffix.casefold() for item in child_args}
    if kind in {"custom", "command", "shell", "opaque"}:
        return kind or "opaque", True
    if (
        _is_python_interpreter_path(Path(executable))
        or ".py" in suffixes
        or ".pyw" in suffixes
    ):
        return "python", False
    if (
        executable in {"node", "node.exe", "deno", "deno.exe", "bun", "bun.exe"}
        or ".js" in suffixes
        or ".mjs" in suffixes
    ):
        return "javascript", False
    if executable in {
        "cmd",
        "cmd.exe",
        "powershell",
        "powershell.exe",
        "pwsh",
        "pwsh.exe",
        "sh",
        "bash",
    }:
        return "command", True
    if child_exec and (
        "/" in child_exec or "\\" in child_exec or Path(child_exec).suffix
    ):
        return "native", False
    if child_exec:
        return "external", True
    return "opaque", True


def _resolve_agent_candidate(
    interface_base: Path,
    source_root: Path,
    raw_value: str,
) -> Path | None:
    if not _looks_like_local_path(raw_value):
        return None
    try:
        candidate, _ = _resolve_and_project_executable_path(
            raw_value,
            interface_base,
            source_root,
            "agent path",
            required=False,
        )
    except MaaFWProjectStoreError:
        return None
    return candidate if candidate.exists() else None


def _materialize_projection(plan: _ProjectionPlan, data_dir: Path) -> None:
    for relative_directory in sorted(
        plan.copied_directories,
        key=lambda path: (len(path.parts), path.as_posix()),
    ):
        if relative_directory == Path("."):
            continue
        output_directory = _projection_output_path(plan, relative_directory)
        if output_directory == Path("."):
            continue
        destination = (data_dir / output_directory).resolve(strict=False)
        _assert_within(destination, data_dir)
        destination.mkdir(parents=True, exist_ok=True)

    for relative_file in sorted(plan.copied_files, key=lambda path: path.as_posix()):
        source = (plan.source_root / relative_file).resolve(strict=True)
        _assert_within(source, plan.source_root)
        _assert_not_reparse(source)
        output_file = _projection_output_path(plan, relative_file)
        destination = (data_dir / output_file).resolve(strict=False)
        _assert_within(destination, data_dir)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    for source_relative, payload in plan.rewritten_json.items():
        output_file = _projection_output_path(plan, source_relative)
        if source_relative not in plan.copied_files:
            raise MaaFWProjectStoreError(
                f"rewritten ProjectInterface file was not projected: {source_relative}"
            )
        _write_json(data_dir / output_file, payload)


def _clear_native_resource_hashes(
    plan: _ProjectionPlan,
) -> list[dict[str, str]]:
    cleared: list[dict[str, str]] = []
    for source_relative, projected in plan.rewritten_json.items():
        resources = projected.get("resource")
        if not isinstance(resources, list):
            continue
        output_file = _projection_output_path(plan, source_relative).as_posix()
        for index, resource in enumerate(resources):
            if not isinstance(resource, dict) or "hash" not in resource:
                continue
            resource.pop("hash", None)
            cleared.append(
                {
                    "file": output_file,
                    "resource": (
                        _optional_string(resource.get("name")) or f"resource[{index}]"
                    ),
                }
            )
    return cleared


def _discover_project_interface(source_root: Path) -> tuple[Path, Path]:
    candidates = (
        (source_root, source_root / "interface.json"),
        (source_root, source_root / "interface.jsonc"),
        (source_root / "assets", source_root / "assets" / "interface.json"),
        (source_root / "assets", source_root / "assets" / "interface.jsonc"),
    )
    for project_root, interface_path in candidates:
        if interface_path.is_file():
            _assert_not_reparse(interface_path)
            _assert_within(interface_path.resolve(strict=True), source_root)
            return project_root.resolve(strict=True), interface_path.resolve(
                strict=True
            )
    raise MaaFWProjectStoreError(
        "interface.json or interface.jsonc was not found at the release root or assets/"
    )


def _scan_safe_tree(root: Path) -> tuple[set[Path], set[Path]]:
    directories: set[Path] = {Path(".")}
    files: set[Path] = set()
    for current_raw, directory_names, file_names in os.walk(
        root,
        topdown=True,
        followlinks=False,
    ):
        current = Path(current_raw)
        _assert_not_reparse(current)
        _assert_within(current.resolve(strict=True), root)
        for directory_name in list(directory_names):
            directory = current / directory_name
            _assert_not_reparse(directory)
            directories.add(directory.relative_to(root))
        for file_name in file_names:
            file_path = current / file_name
            _assert_not_reparse(file_path)
            if not file_path.is_file():
                raise MaaFWProjectStoreError(f"unsupported source entry: {file_path}")
            files.add(file_path.relative_to(root))
    return directories, files


def _calculate_projected_source_hash(
    root: Path,
    files: Iterable[Path],
    *,
    metadata: Mapping[str, Any] | None = None,
) -> str:
    return _calculate_tree_hash(
        root,
        files,
        domain=_PROJECTED_SOURCE_HASH_DOMAIN,
        metadata=metadata,
    )


def _calculate_tree_hash(
    root: Path,
    files: Iterable[Path],
    *,
    domain: bytes,
    metadata: Mapping[str, Any] | None = None,
) -> str:
    """Hash a file set with unambiguous domain-separated framing."""

    ordered_files = sorted(set(files), key=lambda path: path.as_posix())
    digest = hashlib.sha256()
    digest.update(domain)
    digest.update(len(ordered_files).to_bytes(8, "big"))
    for relative_path in ordered_files:
        source = (root / relative_path).resolve(strict=True)
        _assert_within(source, root)
        _assert_not_reparse(source)
        encoded_path = relative_path.as_posix().encode("utf-8")
        file_size = source.stat().st_size
        if file_size < 0:
            raise MaaFWProjectStoreError(f"project file size is invalid: {source}")
        digest.update(b"F")
        digest.update(len(encoded_path).to_bytes(8, "big"))
        digest.update(encoded_path)
        digest.update(file_size.to_bytes(8, "big"))
        consumed = 0
        with source.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                consumed += len(chunk)
                digest.update(chunk)
        _assert_not_reparse(source)
        if consumed != file_size or source.stat().st_size != file_size:
            raise MaaFWProjectStoreError(
                f"project file changed while its tree identity was calculated: {source}"
            )
    if metadata is not None:
        encoded_metadata = json.dumps(
            metadata,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        digest.update(b"M")
        digest.update(len(encoded_metadata).to_bytes(8, "big"))
        digest.update(encoded_metadata)
    else:
        digest.update(b"N")
    return digest.hexdigest()


def _calculate_projected_source_hash_legacy(
    root: Path,
    files: Iterable[Path],
    *,
    metadata: Mapping[str, Any] | None = None,
) -> str:
    """Reproduce schema-2 hashes solely for verified Store compatibility."""

    digest = hashlib.sha256()
    for relative_path in sorted(set(files), key=lambda path: path.as_posix()):
        source = (root / relative_path).resolve(strict=True)
        _assert_within(source, root)
        _assert_not_reparse(source)
        encoded_path = relative_path.as_posix().encode("utf-8")
        digest.update(len(encoded_path).to_bytes(8, "big"))
        digest.update(encoded_path)
        with source.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
    if metadata is not None:
        encoded_metadata = json.dumps(
            metadata,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        digest.update(_PROJECTED_SOURCE_METADATA_DOMAIN)
        digest.update(len(encoded_metadata).to_bytes(8, "big"))
        digest.update(encoded_metadata)
    return digest.hexdigest()


def _projected_source_hash_metadata(
    python_runtime: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if python_runtime is None:
        return None
    return {
        "schemaVersion": _PROJECTED_SOURCE_METADATA_SCHEMA_VERSION,
        "pythonRuntime": python_runtime,
    }


def _detect_python_abi_tags(
    root: Path,
    files: Iterable[Path],
    agent_runtime: Iterable[Mapping[str, Any]] = (),
) -> list[str]:
    tags: set[str] = set()
    compact_pattern = re.compile(
        r"(?<![A-Za-z0-9])(?P<tag>cp\d{2,3}(?:-[A-Za-z0-9_]+)?)",
        flags=re.IGNORECASE,
    )
    cpython_pattern = re.compile(
        r"(?<![A-Za-z0-9])(?P<tag>cpython-\d{2,3}(?:-[A-Za-z0-9_]+)+)",
        flags=re.IGNORECASE,
    )
    for relative_path in files:
        if relative_path.suffix.casefold() not in {".pyd", ".so"}:
            continue
        source = (root / relative_path).resolve(strict=True)
        _assert_within(source, root)
        for pattern in (compact_pattern, cpython_pattern):
            match = pattern.search(relative_path.name)
            if match is not None:
                tags.add(match.group("tag").casefold())
    bundled_versions, _ = _detect_bundled_python_version_evidence(
        root,
        agent_runtime,
    )
    tags.update(f"cp{major}{minor}" for major, minor in bundled_versions)
    return sorted(tags)


def _detect_bundled_python_version_evidence(
    source_root: Path,
    agent_runtime: Iterable[Mapping[str, Any]],
) -> tuple[set[tuple[int, int]], set[str]]:
    """Find unambiguous CPython minor markers without executing project code.

    Some Windows MFW releases omit the ``python/python.exe`` named by
    ProjectInterface while retaining the embeddable runtime DLL at the release
    root.  The exact ``python3XY.dll`` name is the same minor-family evidence as
    ``python3XY._pth`` and remains available before the shell is projected out.
    Only the release root and declared stripped-interpreter directories are
    inspected; similarly named files elsewhere in project resources are not
    treated as runtime metadata.
    """

    marker_roots: set[Path] = set()
    for agent in agent_runtime:
        stripped = agent.get("strippedInterpreter")
        if not isinstance(stripped, Mapping):
            continue
        raw_source_path = str(stripped.get("sourcePath") or "").strip()
        if not raw_source_path:
            continue
        marker_roots.add(source_root.resolve())
        marker_root = (source_root / Path(raw_source_path).parent).resolve()
        _assert_within(marker_root, source_root)
        if marker_root.is_dir():
            marker_roots.add(marker_root)

    versions: set[tuple[int, int]] = set()
    sources: set[str] = set()
    marker_patterns = (
        (
            re.compile(
                r"python(?P<major>\d)(?P<minor>\d{1,2})\._pth",
                flags=re.IGNORECASE,
            ),
            "embedded-python-marker",
        ),
        (
            re.compile(
                r"python(?P<major>\d)(?P<minor>\d{1,2})\.dll",
                flags=re.IGNORECASE,
            ),
            "bundled-python-runtime-library",
        ),
    )
    for marker_root in sorted(marker_roots, key=lambda path: str(path).casefold()):
        for marker in marker_root.iterdir():
            for pattern, source in marker_patterns:
                match = pattern.fullmatch(marker.name)
                if match is None:
                    continue
                _assert_not_reparse(marker)
                if not marker.is_file():
                    continue
                versions.add((int(match.group("major")), int(match.group("minor"))))
                sources.add(source)
                break

    if len(versions) > 1:
        rendered = ", ".join(f"{major}.{minor}" for major, minor in sorted(versions))
        raise MaaFWProjectStoreError(
            f"bundled Python metadata declares multiple interpreter minors: {rendered}"
        )
    return versions, sources


def _resolve_python_runtime_metadata(
    source_root: Path,
    interface_data: Mapping[str, Any],
    agent_runtime: Iterable[Mapping[str, Any]],
) -> dict[str, Any] | None:
    """Resolve a hard Python constraint without executing project code.

    A ProjectInterface declaration is authoritative when present. For older
    releases that bundle an interpreter and are projected onto managed Python,
    a unique ``python3XY._pth`` marker beside the stripped executable, or a
    ``python3XY.dll`` at that location/the release root, is stable evidence of
    the interpreter minor family shipped by that release.
    """

    explicit_constraint: str | None = None
    sources: list[str] = []
    runtime = interface_data.get("runtime")
    runtime_data = dict(runtime) if isinstance(runtime, Mapping) else {}
    python = runtime_data.get("python")
    if python is not None:
        if not isinstance(python, Mapping):
            raise MaaFWProjectStoreError(
                "ProjectInterface runtime.python must be a JSON object"
            )
        implementation = str(python.get("implementation") or "cpython").strip()
        if implementation.casefold() != "cpython":
            raise MaaFWProjectStoreError(
                "ProjectInterface runtime.python currently supports only cpython"
            )
        raw_constraint = str(
            python.get("requires") or python.get("constraint") or ""
        ).strip()
        if not raw_constraint:
            raise MaaFWProjectStoreError(
                "ProjectInterface runtime.python requires a non-empty constraint"
            )
        explicit_constraint = _normalize_python_constraint(raw_constraint)
        sources.append("project-interface")

    embedded_versions, embedded_sources = _detect_bundled_python_version_evidence(
        source_root,
        agent_runtime,
    )
    if embedded_versions:
        major, minor = next(iter(embedded_versions))
        if explicit_constraint is not None:
            if not _python_constraint_accepts_minor_family(
                explicit_constraint,
                major,
                minor,
            ):
                raise MaaFWProjectStoreError(
                    "ProjectInterface Python constraint does not match the bundled "
                    f"interpreter marker: {explicit_constraint} vs {major}.{minor}"
                )
        else:
            explicit_constraint = f"=={major}.{minor}.*"
        sources.extend(sorted(embedded_sources))

    if explicit_constraint is None:
        return None
    return {
        "implementation": "cpython",
        "constraint": explicit_constraint,
        "sources": sources,
    }


def _normalize_python_constraint(value: str) -> str:
    try:
        constraint = SpecifierSet(value)
    except InvalidSpecifier as exc:
        raise MaaFWProjectStoreError(
            f"invalid ProjectInterface Python constraint: {value}"
        ) from exc
    normalized = str(constraint)
    if not normalized:
        raise MaaFWProjectStoreError(
            "ProjectInterface Python constraint cannot be empty"
        )
    return normalized


def _python_constraint_accepts_minor_family(
    constraint: str,
    major: int,
    minor: int,
) -> bool:
    """Whether a minor-only bundled marker can satisfy a Python constraint.

    ``python313._pth`` proves the CPython 3.13 ABI family, not patch 3.13.0.
    The interpreter is removed from the managed projection, so an explicit
    patch constraint such as ``==3.13.14`` must be accepted and routed to the
    Pool instead of being compared against the synthetic version ``3.13``.
    CPython patch releases are small non-negative integers; probing a generous
    bounded family also handles normal ranges, exclusions and prefix pins.
    """

    specifier = SpecifierSet(constraint)
    return any(
        specifier.contains(
            Version(f"{major}.{minor}.{patch}"),
            prereleases=True,
        )
        for patch in range(1000)
    )


def _resolve_runtime_constraint(
    explicit: str | None,
    interface_data: dict[str, Any],
    source_root: Path,
    interface_base: Path,
) -> str | None:
    constraint = explicit.strip() if explicit is not None and explicit.strip() else None
    if constraint is None:
        for key in (
            "maafw_constraint",
            "maafwConstraint",
            "maafw_version",
            "maafwVersion",
            "maa_framework_version",
            "maaFrameworkVersion",
        ):
            value = _optional_string(interface_data.get(key))
            if value:
                constraint = value
                break
    if constraint is None:
        runtime = interface_data.get("runtime")
        if isinstance(runtime, dict):
            for key in ("maafw", "constraint", "version"):
                value = _optional_string(runtime.get(key))
                if value:
                    constraint = value
                    break
    if constraint is None:
        constraint = _read_maafw_requirement_constraint(
            source_root,
            interface_base,
        )

    bundled_version = _read_bundled_maafw_binary_version(source_root)
    if bundled_version is None:
        return constraint
    if constraint is not None and not _maafw_constraint_accepts_version(
        constraint,
        bundled_version,
    ):
        raise MaaFWProjectStoreError(
            "declared MaaFW constraint does not match bundled MaaFramework: "
            f"{constraint} vs {bundled_version}"
        )
    return constraint or f"=={bundled_version}"


def _read_maafw_requirement_constraint(
    source_root: Path,
    interface_base: Path,
) -> str | None:
    candidates: list[tuple[bool, str]] = []
    requirement_files = {
        path.resolve(strict=True)
        for base in {source_root, interface_base}
        for path in base.glob("requirements*.txt")
        if path.is_file()
    }
    requirement_pattern = re.compile(
        r"^\s*(?:maafw|maa[-_]framework)(?:\[[^\]]+\])?\s*"
        r"(?P<constraint>(?:===|==|~=|>=|<=|!=|>|<).+?)?\s*$",
        flags=re.IGNORECASE,
    )
    for requirement_file in sorted(requirement_files, key=str):
        _assert_not_reparse(requirement_file)
        try:
            lines = requirement_file.read_text(encoding="utf-8-sig").splitlines()
        except Exception as exc:
            raise MaaFWProjectStoreError(
                f"cannot read MaaFW requirements file {requirement_file}: {exc}"
            ) from exc
        for raw_line in lines:
            line = raw_line.split("#", 1)[0].split(";", 1)[0].strip()
            if not line or line.startswith(("-", "--")):
                continue
            match = requirement_pattern.fullmatch(line)
            if match is None:
                continue
            constraint = (match.group("constraint") or "").strip()
            if not constraint:
                continue
            exact = constraint.startswith(("===", "=="))
            candidates.append((exact, constraint))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], len(item[1])), reverse=True)
    return candidates[0][1]


def _read_bundled_maafw_binary_version(source_root: Path) -> str | None:
    """Read the authoritative project runtime version without loading binaries.

    MaaFW releases may ship both the Python client runtime in ``maafw`` and a
    separate Node/PiCLI bundle in ``runtimes/win-x64``.  They are distinct
    consumers and may legitimately be built from adjacent framework patches.
    """

    candidates = sorted(
        (
            path
            for path in source_root.rglob("*")
            if path.name.casefold() == "maaframework.dll"
            and not _is_stale_maafw_binary_candidate(path.relative_to(source_root))
        ),
        key=lambda path: path.as_posix().casefold(),
    )

    # Windows releases may carry a Python MaaFW runtime plus a separate
    # Node/PiCLI bundle under ``runtimes/win-*``. Only exclude the latter when
    # both consumers are positively identified; unrelated duplicate DLLs
    # remain conflict evidence and fail closed below.
    def is_python_runtime_candidate(path: Path) -> bool:
        relative = tuple(
            part.casefold() for part in path.relative_to(source_root).parts
        )
        if relative and relative[0] == "maafw":
            return True
        for index in range(len(relative) - 3):
            if relative[index : index + 4] == (
                "site-packages",
                "maa",
                "bin",
                "maaframework.dll",
            ):
                return True
        return False

    python_runtime_candidates = [
        path for path in candidates if is_python_runtime_candidate(path)
    ]
    if python_runtime_candidates:
        runtime_roots: set[Path] = set()
        for candidate in candidates:
            relative = candidate.relative_to(source_root)
            normalized = tuple(part.casefold() for part in relative.parts)
            if (
                len(normalized) >= 3
                and normalized[0] == "runtimes"
                and normalized[1].startswith("win-")
            ):
                runtime_roots.add(source_root.joinpath(*relative.parts[:2]))

        secondary_runtime_roots: set[Path] = set()
        for runtime_root in runtime_roots:
            for marker in runtime_root.rglob("*"):
                if marker.name.casefold() not in {"maanode.node", "maapicli.exe"}:
                    continue
                _assert_not_reparse(marker)
                if marker.is_file():
                    secondary_runtime_roots.add(runtime_root)
                    break

        candidates = [
            candidate
            for candidate in candidates
            if not any(
                candidate.is_relative_to(runtime_root)
                for runtime_root in secondary_runtime_roots
            )
        ]
    versions: dict[str, list[str]] = {}
    version_pattern = re.compile(
        rb"(?<![0-9A-Za-z])v(?P<version>\d+\.\d+\.\d+"
        rb"(?:[-+][0-9A-Za-z][0-9A-Za-z.-]*)?)(?![0-9A-Za-z.-])"
    )
    for candidate in candidates:
        resolved = candidate.resolve(strict=True)
        _assert_within(resolved, source_root)
        _assert_not_reparse(candidate)
        if not candidate.is_file():
            continue
        candidate_versions: set[str] = set()
        try:
            with candidate.open("rb") as handle:
                overlap = b""
                while True:
                    chunk = handle.read(1024 * 1024)
                    if not chunk:
                        break
                    searchable = overlap + chunk
                    for match in version_pattern.finditer(searchable):
                        raw_version = match.group("version").decode("ascii")
                        try:
                            candidate_versions.add(str(Version(raw_version)))
                        except InvalidVersion as exc:
                            raise MaaFWProjectStoreError(
                                "bundled MaaFramework contains an invalid "
                                f"version marker: {candidate} ({raw_version})"
                            ) from exc
                    overlap = searchable[-64:]
        except OSError as exc:
            raise MaaFWProjectStoreError(
                f"cannot inspect bundled MaaFramework version: {candidate}"
            ) from exc
        # A framework binary may retain historical version strings.  Such a
        # file is not an authoritative current-version marker; only a binary
        # containing exactly one semantic version contributes evidence.
        if len(candidate_versions) == 1:
            version = next(iter(candidate_versions))
            versions.setdefault(version, []).append(
                candidate.relative_to(source_root).as_posix()
            )

    if len(versions) > 1:
        # Some Windows releases include the same framework twice: the Python
        # package directory and the native runtime directory.  When both
        # copies carry a different marker, do not guess.  The project must be
        # cleaned or explicitly pinned by its author before it is managed.
        rendered = "; ".join(
            f"{version} ({', '.join(paths)})"
            for version, paths in sorted(versions.items())
        )
        raise MaaFWProjectStoreError(
            "bundled MaaFramework binaries declare different versions: "
            f"{rendered}. Remove stale or duplicate MaaFramework.dll files, "
            "or pin the project to one matching runtime before importing."
        )
    return next(iter(versions), None)


def _is_stale_maafw_binary_candidate(relative_path: Path) -> bool:
    ignored_directories = {
        "backup",
        "backups",
        "cache",
        "caches",
        "debug",
        "old",
        "staging",
        "temp",
        "temp_res",
        "tmp",
        "update",
        "updates",
        "updater",
    }
    for part in relative_path.parts[:-1]:
        normalized = part.casefold()
        if normalized.startswith("~") or normalized in ignored_directories:
            return True
    return False


def _maafw_constraint_accepts_version(
    constraint: str,
    bundled_version: str,
) -> bool:
    normalized = constraint.strip()
    if not normalized:
        return False
    if normalized[0].isdigit() or normalized[0].casefold() == "v":
        normalized = f"=={normalized}"
    try:
        return SpecifierSet(normalized).contains(
            Version(bundled_version),
            prereleases=True,
        )
    except InvalidSpecifier as exc:
        raise MaaFWProjectStoreError(
            f"invalid MaaFW runtime constraint: {constraint}"
        ) from exc


def _resolve_and_project_local_path(
    raw_path: str,
    interface_base: Path,
    source_root: Path,
    field_name: str,
    *,
    required: bool,
    allow_root: bool = False,
) -> tuple[Path, Path]:
    value = str(raw_path).strip().strip('"').strip("'").replace("\\", "/")
    value = value.replace("${PROJECT_DIR}", "{PROJECT_DIR}")
    if value.startswith("{PROJECT_DIR}"):
        value = value[len("{PROJECT_DIR}") :].lstrip("/")
    if not value and not allow_root:
        raise MaaFWProjectStoreError(f"{field_name} cannot be empty")
    candidate_path = Path(value or ".")
    if candidate_path.is_absolute() or candidate_path.drive or candidate_path.root:
        raise MaaFWProjectStoreError(
            f"{field_name} must stay inside the unpacked release: {raw_path}"
        )
    source_path = (interface_base / candidate_path).resolve(strict=False)
    _assert_within(source_path, source_root)
    if required and not source_path.exists():
        raise MaaFWProjectStoreError(
            f"{field_name} path does not exist in the unpacked release: {raw_path}"
        )
    if source_path.exists():
        _assert_existing_chain_has_no_reparse(source_path)
    source_relative = source_path.relative_to(source_root)
    output_path = _projection_output_path_from_roots(
        source_relative,
        source_root,
        interface_base,
    )
    return source_path, output_path


def _resolve_and_project_executable_path(
    raw_path: str,
    interface_base: Path,
    source_root: Path,
    field_name: str,
    *,
    required: bool,
) -> tuple[Path, Path]:
    """Resolve a local executable, including Windows' implicit ``.exe``."""

    source_path, output_path = _resolve_and_project_local_path(
        raw_path,
        interface_base,
        source_root,
        field_name,
        required=False,
    )
    if source_path.exists():
        return source_path, output_path

    value = str(raw_path).strip().strip('"').strip("'").replace("\\", "/")
    value = value.replace("${PROJECT_DIR}", "{PROJECT_DIR}")
    if value.startswith("{PROJECT_DIR}"):
        value = value[len("{PROJECT_DIR}") :].lstrip("/")
    if value and not Path(value).suffix:
        executable_path, executable_output = _resolve_and_project_local_path(
            f"{value}.exe",
            interface_base,
            source_root,
            field_name,
            required=False,
        )
        if executable_path.is_file():
            return executable_path, executable_output

    if required:
        raise MaaFWProjectStoreError(
            f"{field_name} path does not exist in the unpacked release: {raw_path}"
        )
    return source_path, output_path


def _output_path_for_source(
    source_relative: Path,
    source_root: Path,
    interface_base: Path,
) -> Path:
    return _projection_output_path_from_roots(
        source_relative,
        source_root,
        interface_base,
    )


def _projection_output_path(plan: _ProjectionPlan, source_relative: Path) -> Path:
    return _projection_output_path_from_roots(
        source_relative,
        plan.source_root,
        plan.interface_base,
    )


def _projection_output_path_from_roots(
    source_relative: Path,
    source_root: Path,
    interface_base: Path,
) -> Path:
    absolute_source = (source_root / source_relative).resolve(strict=False)
    _assert_within(absolute_source, source_root)
    try:
        relative_to_interface = absolute_source.relative_to(interface_base)
        return relative_to_interface if relative_to_interface.parts else Path(".")
    except ValueError:
        relative_to_release = absolute_source.relative_to(source_root)
        return relative_to_release if relative_to_release.parts else Path(".")


def _format_project_path(path: Path) -> str:
    if path == Path(".") or not path.parts:
        return "."
    return f"./{path.as_posix()}"


def _looks_like_local_path(value: str) -> bool:
    normalized = value.strip().strip('"').strip("'")
    if not normalized or normalized.startswith(("-", "http://", "https://")):
        return False
    if normalized.startswith(
        ("{PROJECT_DIR}", "${PROJECT_DIR}", "./", "../", ".\\", "..\\")
    ):
        return True
    if "/" in normalized or "\\" in normalized:
        return True
    return Path(normalized).suffix.casefold() in {
        ".py",
        ".pyw",
        ".js",
        ".mjs",
        ".cjs",
        ".exe",
        ".cmd",
        ".bat",
        ".ps1",
        ".sh",
    }


def _agent_retention_root(source_path: Path, source_root: Path) -> Path:
    source_relative = source_path.relative_to(source_root)
    if source_path.is_dir():
        return source_relative
    parent = source_relative.parent
    return parent if parent != Path(".") else source_relative


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as file:
            payload = json5.load(file)
    except Exception as exc:
        raise MaaFWProjectStoreError(
            f"cannot parse ProjectInterface file {path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise MaaFWProjectStoreError(
            f"ProjectInterface file must contain a JSON object: {path}"
        )
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_json_atomic(path: Path, payload: dict[str, Any], store_root: Path) -> None:
    _assert_path_chain_within_root(path, store_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    _assert_path_chain_within_root(path.parent, store_root)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        _write_json(temp_path, payload)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _materialize_import_source(
    source_path: str | Path,
    *,
    store_root: Path,
    staging_root: Path,
) -> _ImportSource:
    raw_path = Path(source_path)
    absolute_path = Path(os.path.abspath(raw_path))
    _assert_existing_chain_has_no_reparse(absolute_path)
    try:
        source = raw_path.resolve(strict=True)
    except OSError as exc:
        raise MaaFWProjectStoreError(
            f"source path does not exist: {source_path}"
        ) from exc
    _assert_not_reparse(source)

    if source.is_dir():
        root = _canonical_source_directory(source, store_root)
        # Directory snapshots can include a complete portable Python tree. On
        # Windows, spending another ``import-directory-.../source`` segment in
        # front of every copied entry is enough to hit the legacy directory
        # path limit even when both the source and final Store payload are
        # otherwise valid. The random staging directory is already the private
        # cleanup boundary, so use it directly as the immutable snapshot root.
        stage_dir = staging_root / uuid.uuid4().hex
        snapshot_root = stage_dir
        _assert_path_chain_within_root(stage_dir, store_root)
        try:
            input_size_bytes = _copy_stable_directory_snapshot(
                root,
                snapshot_root,
            )
            return _ImportSource(
                root=snapshot_root.resolve(strict=True),
                input_path=source,
                kind="directory",
                input_size_bytes=input_size_bytes,
                cleanup_root=stage_dir,
            )
        except Exception:
            if stage_dir.exists():
                _safe_remove_tree(stage_dir, store_root)
            raise

    if not source.is_file():
        raise MaaFWProjectStoreError(
            f"source path must be a directory or ZIP archive: {source_path}"
        )
    if _is_within(source, store_root):
        raise MaaFWProjectStoreError("source ZIP must be outside the project store")
    if source.suffix.casefold() != ".zip" or not zipfile.is_zipfile(source):
        raise MaaFWProjectStoreError(
            f"source file is not a valid ZIP archive: {source_path}"
        )

    stage_dir = staging_root / f"import-{uuid.uuid4().hex}"
    extract_root = stage_dir / "extract"
    _assert_path_chain_within_root(stage_dir, store_root)
    try:
        extract_root.mkdir(parents=True, exist_ok=False)
        archive_size = source.stat().st_size
        archive_sha256 = _sha256_file(source)
        _safe_extract_import_zip(source, extract_root)
        if (
            source.stat().st_size != archive_size
            or _sha256_file(source) != archive_sha256
        ):
            raise MaaFWProjectStoreError(
                "source ZIP changed while it was being imported"
            )
        _scan_safe_tree(extract_root)
        release_root = _select_zip_release_root(extract_root)
        return _ImportSource(
            root=release_root,
            input_path=source,
            kind="zip",
            input_size_bytes=archive_size,
            archive_sha256=archive_sha256,
            cleanup_root=stage_dir,
        )
    except Exception:
        if stage_dir.exists():
            _safe_remove_tree(stage_dir, store_root)
        raise


def _copy_stable_directory_snapshot(source_root: Path, snapshot_root: Path) -> int:
    """Copy one stable external directory state into private Store staging."""

    before_hash, before_size, directories, files = _calculate_source_tree_identity(
        source_root
    )
    snapshot_root.mkdir(parents=True, exist_ok=False)
    for relative_directory in sorted(
        directories,
        key=lambda path: (len(path.parts), path.as_posix()),
    ):
        if relative_directory == Path("."):
            continue
        (snapshot_root / relative_directory).mkdir(parents=True, exist_ok=False)

    for relative_file in sorted(files, key=lambda path: path.as_posix()):
        source_file = source_root / relative_file
        _assert_existing_chain_has_no_reparse(source_file)
        _assert_not_reparse(source_file)
        if not source_file.is_file():
            raise MaaFWProjectStoreError(
                f"source entry changed while it was being imported: {source_file}"
            )
        destination = snapshot_root / relative_file
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, destination)
        _assert_existing_chain_has_no_reparse(source_file)
        _assert_not_reparse(source_file)

    after_hash, after_size, _, _ = _calculate_source_tree_identity(source_root)
    snapshot_hash, snapshot_size, _, _ = _calculate_source_tree_identity(snapshot_root)
    if (
        before_hash != after_hash
        or before_hash != snapshot_hash
        or before_size != after_size
        or before_size != snapshot_size
    ):
        raise MaaFWProjectStoreError(
            "source directory changed while it was being imported"
        )
    return before_size


def _calculate_source_tree_identity(
    root: Path,
) -> tuple[str, int, set[Path], set[Path]]:
    directories, files = _scan_safe_tree(root)
    digest = hashlib.sha256()
    digest.update(_SOURCE_SNAPSHOT_HASH_DOMAIN)
    digest.update(len(directories).to_bytes(8, "big"))
    digest.update(len(files).to_bytes(8, "big"))
    total_size = 0
    for relative_directory in sorted(directories, key=lambda path: path.as_posix()):
        encoded = relative_directory.as_posix().encode("utf-8")
        digest.update(b"D")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    for relative_file in sorted(files, key=lambda path: path.as_posix()):
        source_file = root / relative_file
        _assert_existing_chain_has_no_reparse(source_file)
        _assert_not_reparse(source_file)
        if not source_file.is_file():
            raise MaaFWProjectStoreError(
                f"source entry changed while it was being imported: {source_file}"
            )
        encoded = relative_file.as_posix().encode("utf-8")
        file_size = source_file.stat().st_size
        digest.update(b"F")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(file_size.to_bytes(8, "big"))
        consumed = 0
        with source_file.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                consumed += len(chunk)
                total_size += len(chunk)
                digest.update(chunk)
        _assert_existing_chain_has_no_reparse(source_file)
        _assert_not_reparse(source_file)
        if consumed != file_size or source_file.stat().st_size != file_size:
            raise MaaFWProjectStoreError(
                f"source entry changed while it was being imported: {source_file}"
            )
    return digest.hexdigest(), total_size, directories, files


def _select_zip_release_root(extract_root: Path) -> Path:
    try:
        _discover_project_interface(extract_root)
        return extract_root
    except MaaFWProjectStoreError:
        pass

    candidates: list[Path] = []
    for child in sorted(extract_root.iterdir(), key=lambda item: item.name.casefold()):
        _assert_not_reparse(child)
        if not child.is_dir():
            continue
        try:
            _discover_project_interface(child)
        except MaaFWProjectStoreError:
            continue
        candidates.append(child.resolve(strict=True))
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise MaaFWProjectStoreError(
            "interface.json or interface.jsonc was not found at the ZIP root, "
            "assets/, or one direct wrapper directory"
        )
    raise MaaFWProjectStoreError(
        "ZIP contains multiple direct project roots; import one project per archive"
    )


def _safe_extract_import_zip(source: Path, extract_root: Path) -> None:
    try:
        archive = zipfile.ZipFile(source)
    except (OSError, zipfile.BadZipFile) as exc:
        raise MaaFWProjectStoreError(
            f"cannot open ZIP archive {source}: {exc}"
        ) from exc

    with archive:
        members = archive.infolist()
        if len(members) > MAX_ZIP_FILE_COUNT:
            raise MaaFWProjectStoreError(
                f"ZIP contains too many entries: {len(members)} > {MAX_ZIP_FILE_COUNT}"
            )

        checked: list[tuple[str, tuple[str, ...], zipfile.ZipInfo, bool]] = []
        total_declared = 0
        for member in members:
            normalized, parts = _validate_zip_member_name(member.filename)
            if member.flag_bits & 0x1:
                raise MaaFWProjectStoreError(
                    f"encrypted ZIP entries are not supported: {member.filename}"
                )

            unix_mode = (member.external_attr >> 16) & 0xFFFF
            unix_type = stat.S_IFMT(unix_mode)
            if unix_type and unix_type not in {stat.S_IFREG, stat.S_IFDIR}:
                raise MaaFWProjectStoreError(
                    f"ZIP links, devices and special files are not allowed: {member.filename}"
                )
            is_directory = member.is_dir() or unix_type == stat.S_IFDIR
            if is_directory and member.file_size:
                raise MaaFWProjectStoreError(
                    f"ZIP directory entry has file content: {member.filename}"
                )
            if member.file_size > MAX_ZIP_MEMBER_UNCOMPRESSED_BYTES:
                raise MaaFWProjectStoreError(
                    f"ZIP entry is too large after extraction: {member.filename}"
                )
            total_declared += member.file_size
            if total_declared > MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES:
                raise MaaFWProjectStoreError(
                    "ZIP declared uncompressed size exceeds the import limit"
                )
            if member.file_size:
                if member.compress_size <= 0:
                    raise MaaFWProjectStoreError(
                        f"ZIP entry has an unsafe compression ratio: {member.filename}"
                    )
                ratio = member.file_size / member.compress_size
                if ratio > MAX_ZIP_COMPRESSION_RATIO:
                    raise MaaFWProjectStoreError(
                        f"ZIP entry compression ratio exceeds the import limit: "
                        f"{member.filename}"
                    )
            checked.append((normalized.casefold(), parts, member, is_directory))

        checked.sort(key=lambda item: item[0])
        seen: dict[str, bool] = {}
        for folded, _parts, member, is_directory in checked:
            if folded in seen:
                raise MaaFWProjectStoreError(
                    f"ZIP contains duplicate or case-colliding paths: {member.filename}"
                )
            ancestors = folded.split("/")[:-1]
            for index in range(1, len(ancestors) + 1):
                ancestor = "/".join(ancestors[:index])
                if seen.get(ancestor) is False:
                    raise MaaFWProjectStoreError(
                        f"ZIP path crosses a file entry: {member.filename}"
                    )
            seen[folded] = is_directory

        total_actual = 0
        for _folded, parts, member, is_directory in checked:
            target = extract_root.joinpath(*parts)
            _assert_within(target.resolve(strict=False), extract_root)
            if is_directory:
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            member_actual = 0
            try:
                with (
                    archive.open(member, "r") as source_file,
                    target.open("xb") as output,
                ):
                    while True:
                        chunk = source_file.read(_ZIP_COPY_CHUNK_SIZE)
                        if not chunk:
                            break
                        member_actual += len(chunk)
                        total_actual += len(chunk)
                        if member_actual > MAX_ZIP_MEMBER_UNCOMPRESSED_BYTES:
                            raise MaaFWProjectStoreError(
                                f"ZIP entry exceeded the extraction limit: {member.filename}"
                            )
                        if total_actual > MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES:
                            raise MaaFWProjectStoreError(
                                "ZIP exceeded the total extraction limit"
                            )
                        output.write(chunk)
            except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                raise MaaFWProjectStoreError(
                    f"cannot safely extract ZIP entry {member.filename}: {exc}"
                ) from exc
            if member_actual != member.file_size:
                raise MaaFWProjectStoreError(
                    f"ZIP entry size changed while extracting: {member.filename}"
                )


def _validate_zip_member_name(raw_name: str) -> tuple[str, tuple[str, ...]]:
    if "\x00" in raw_name:
        raise MaaFWProjectStoreError("ZIP entry name contains a NUL byte")
    normalized = raw_name.replace("\\", "/")
    if (
        not normalized
        or normalized.startswith("/")
        or normalized.startswith("//")
        or re.match(r"^[A-Za-z]:", normalized)
    ):
        raise MaaFWProjectStoreError(f"ZIP entry uses an absolute path: {raw_name}")
    parts = tuple(part for part in normalized.split("/") if part)
    if not parts or any(part in {".", ".."} for part in parts):
        raise MaaFWProjectStoreError(
            f"ZIP entry escapes the extraction root: {raw_name}"
        )
    for part in parts:
        if ":" in part or part.endswith((".", " ")):
            raise MaaFWProjectStoreError(
                f"ZIP entry uses an unsafe Windows path component: {raw_name}"
            )
        if part.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES:
            raise MaaFWProjectStoreError(
                f"ZIP entry uses a reserved Windows path component: {raw_name}"
            )
    return "/".join(parts), parts


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_source_directory(source_path: str | Path, store_root: Path) -> Path:
    raw_path = Path(source_path)
    _assert_existing_chain_has_no_reparse(Path(os.path.abspath(raw_path)))
    try:
        source = raw_path.resolve(strict=True)
    except OSError as exc:
        raise MaaFWProjectStoreError(
            f"source directory does not exist: {source_path}"
        ) from exc
    if not source.is_dir():
        raise MaaFWProjectStoreError(f"source path is not a directory: {source_path}")
    _assert_not_reparse(source)
    if _is_within(source, store_root) or _is_within(store_root, source):
        raise MaaFWProjectStoreError(
            "source directory and project store must not contain each other"
        )
    return source


def _normalize_relative_path(
    raw_path: str,
    field_name: str,
    *,
    allow_root: bool = False,
) -> Path:
    value = str(raw_path).strip().replace("\\", "/")
    value = value.replace("${PROJECT_DIR}", "{PROJECT_DIR}")
    if value.startswith("{PROJECT_DIR}"):
        value = value[len("{PROJECT_DIR}") :].lstrip("/")
    candidate = Path(value)
    if candidate.is_absolute() or candidate.drive or candidate.root:
        raise MaaFWProjectStoreError(
            f"{field_name} must be project-relative: {raw_path}"
        )
    parts = [part for part in value.split("/") if part not in {"", "."}]
    if any(part == ".." for part in parts):
        raise MaaFWProjectStoreError(
            f"{field_name} escapes the project root: {raw_path}"
        )
    if not parts:
        if allow_root:
            return Path(".")
        raise MaaFWProjectStoreError(f"{field_name} cannot be empty")
    return Path(*parts)


def _validate_component(value: str, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not _COMPONENT_PATTERN.fullmatch(normalized):
        raise MaaFWProjectStoreError(
            f"{field_name} must use only letters, digits, '.', '_', '+', or '-'"
        )
    if normalized.endswith((".", " ")):
        raise MaaFWProjectStoreError(f"{field_name} has an unsafe trailing character")
    if normalized.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES:
        raise MaaFWProjectStoreError(f"{field_name} uses a reserved Windows name")
    return normalized


def _resolve_import_project_id(
    explicit_project_id: str | None,
    interface_data: Mapping[str, Any],
    source_root: Path,
) -> str:
    """Resolve the immutable project identity for a local import.

    ProjectInterface ``projectId``/``project_id`` is authoritative when
    present.  Without one, an explicit store ID remains a compatibility alias
    and is validated independently from display-only ``name``.  Name and the
    source directory are only fallbacks and still use component validation.
    """

    explicit = _optional_string(explicit_project_id)
    declared: str | None = None
    declared_key: str | None = None
    for key in ("projectId", "project_id"):
        candidate = _optional_string(interface_data.get(key))
        if candidate:
            if declared is not None and candidate != declared:
                raise MaaFWProjectStoreError(
                    "ProjectInterface projectId and project_id declarations "
                    "do not match"
                )
            declared = candidate
            declared_key = key

    if declared is not None:
        normalized_declared = _validate_component(declared, "project_id")
        if explicit is not None and explicit != normalized_declared:
            raise MaaFWProjectStoreError(
                "explicit project_id does not match ProjectInterface "
                f"authoritative ID ({declared_key}): "
                f"{explicit!r} != {normalized_declared!r}"
            )
        return normalized_declared
    if explicit:
        return _validate_component(explicit, "project_id")

    fallback = _optional_string(interface_data.get("name")) or source_root.name.strip()
    if fallback:
        return _validate_component(fallback, "project_id")
    raise MaaFWProjectStoreError(
        "ProjectInterface 未声明 name/projectId，且无法从项目目录自动识别 project_id"
    )


def _resolve_import_version(
    explicit_version: str | None,
    interface_version: str | None,
) -> str:
    explicit = _optional_string(explicit_version)
    declared = _optional_string(interface_version)
    if explicit and declared and not _versions_equivalent(explicit, declared):
        raise MaaFWProjectStoreError(
            "explicit version does not match ProjectInterface version: "
            f"{explicit!r} != {declared!r}"
        )
    # ProjectInterface is the authoritative resource identity.  If the caller
    # supplied an equivalent spelling (for example ``2.0.0`` vs ``v2.0.0``),
    # keep the declared spelling so repeated imports cannot create duplicate
    # logical versions under two directory names.
    selected = declared or explicit
    if selected is None:
        raise MaaFWProjectStoreError(
            "version is required when ProjectInterface does not declare one"
        )
    return _validate_component(selected, "version")


def _versions_equivalent(left: str, right: str) -> bool:
    def normalize(value: str) -> str:
        normalized = value.strip().casefold()
        if (
            len(normalized) > 1
            and normalized.startswith("v")
            and normalized[1].isdigit()
        ):
            normalized = normalized[1:]
        return normalized

    return normalize(left) == normalize(right)


def _exclusion_reason(path: Path, *, is_directory: bool = False) -> str | None:
    parts = path.parts if is_directory else path.parts[:-1]
    for part in parts:
        normalized_part = part.casefold()
        reason = _EXCLUDED_DIRECTORY_REASONS.get(normalized_part)
        if reason:
            return reason
        part_family = normalized_part.split(".", 1)[0]
        if part_family in _KNOWN_UI_SHELL_STEMS:
            return "ui-shell"
        if part_family in _KNOWN_RUNTIME_STEMS:
            return "embedded-runtime"
    name = path.name.casefold()
    if name == MANIFEST_FILE_NAME.casefold():
        return "reserved-project-store-manifest"
    if not is_directory:
        suffix = path.suffix.casefold()
        shell_family = name.split(".", 1)[0]
        if shell_family in _KNOWN_UI_SHELL_STEMS:
            return "ui-shell"
        if shell_family in _KNOWN_RUNTIME_STEMS:
            return "embedded-runtime"
        if suffix in _EXCLUDED_FILE_SUFFIXES:
            return "cache-or-temporary"
        if name in _KNOWN_RUNTIME_FILE_NAMES or (
            name.startswith("python") and suffix in {".dll", ".exe", ".so", ".dylib"}
        ):
            return "embedded-runtime"
        if suffix in _SHELL_SUFFIXES and (
            "update" in path.stem.casefold()
            or "updater" in path.stem.casefold()
            or path.stem.casefold().endswith(("gui", "ui", "launcher"))
        ):
            return "ui-or-updater-shell"
    return None


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


def _validate_store_marker(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MaaFWProjectStoreError("project-store marker must be a JSON object")
    if value.get("schemaVersion") != STORE_SCHEMA_VERSION:
        raise MaaFWProjectStoreError("project-store marker version is unsupported")
    if value.get("kind") != STORE_KIND:
        raise MaaFWProjectStoreError("project-store marker kind is invalid")
    store_id = value.get("storeId")
    try:
        normalized_store_id = str(uuid.UUID(str(store_id or "")))
    except ValueError as exc:
        raise MaaFWProjectStoreError("project-store marker storeId is invalid") from exc
    return {
        "schemaVersion": STORE_SCHEMA_VERSION,
        "kind": STORE_KIND,
        "storeId": normalized_store_id,
    }


def _validate_run_root_marker(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MaaFWProjectStoreError("project run-root marker must be a JSON object")
    if value.get("schemaVersion") != RUN_ROOT_SCHEMA_VERSION:
        raise MaaFWProjectStoreError("project run-root marker version is unsupported")
    if value.get("kind") != RUN_ROOT_KIND:
        raise MaaFWProjectStoreError("project run-root marker kind is invalid")
    try:
        run_root_id = str(uuid.UUID(str(value.get("runRootId") or "")))
    except ValueError as exc:
        raise MaaFWProjectStoreError(
            "project run-root marker runRootId is invalid"
        ) from exc
    return {
        "schemaVersion": RUN_ROOT_SCHEMA_VERSION,
        "kind": RUN_ROOT_KIND,
        "runRootId": run_root_id,
    }


def _validate_checkout_marker(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MaaFWProjectStoreError("project checkout marker must be a JSON object")
    if value.get("schemaVersion") != CHECKOUT_SCHEMA_VERSION:
        raise MaaFWProjectStoreError("project checkout marker version is unsupported")
    if value.get("kind") != CHECKOUT_KIND:
        raise MaaFWProjectStoreError("project checkout marker kind is invalid")
    checkout_id = str(value.get("checkoutId") or "")
    if not re.fullmatch(r"maafw-checkout-[0-9a-f]{32}", checkout_id):
        raise MaaFWProjectStoreError("project checkout marker checkoutId is invalid")
    try:
        run_root_id = str(uuid.UUID(str(value.get("runRootId") or "")))
    except ValueError as exc:
        raise MaaFWProjectStoreError(
            "project checkout marker runRootId is invalid"
        ) from exc
    identity = value.get("identity")
    if not isinstance(identity, dict):
        raise MaaFWProjectStoreError("project checkout marker identity is invalid")
    normalized_identity = {
        "storeId": str(identity.get("storeId") or ""),
        "projectId": str(identity.get("projectId") or ""),
        "version": str(identity.get("version") or ""),
        "sourceHash": str(identity.get("sourceHash") or ""),
        "payloadHash": str(identity.get("payloadHash") or ""),
        "scriptId": str(identity.get("scriptId") or ""),
    }
    if set(identity) != set(normalized_identity):
        raise MaaFWProjectStoreError("project checkout marker identity is invalid")
    try:
        normalized_identity["storeId"] = str(uuid.UUID(normalized_identity["storeId"]))
    except ValueError as exc:
        raise MaaFWProjectStoreError(
            "project checkout marker storeId is invalid"
        ) from exc
    _validate_component(normalized_identity["projectId"], "project_id")
    _validate_component(normalized_identity["version"], "version")
    _validate_component(normalized_identity["scriptId"], "script_id")
    if not re.fullmatch(r"[0-9a-f]{64}", normalized_identity["sourceHash"]):
        raise MaaFWProjectStoreError("project checkout marker sourceHash is invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", normalized_identity["payloadHash"]):
        raise MaaFWProjectStoreError("project checkout marker payloadHash is invalid")
    if value.get("dataRelativePath") != "data":
        raise MaaFWProjectStoreError(
            "project checkout marker dataRelativePath is invalid"
        )
    leases = value.get("leases")
    if leases is not None and not isinstance(leases, list):
        raise MaaFWProjectStoreError("project checkout marker leases are invalid")
    return {
        "schemaVersion": CHECKOUT_SCHEMA_VERSION,
        "kind": CHECKOUT_KIND,
        "checkoutId": checkout_id,
        "runRootId": run_root_id,
        "identity": normalized_identity,
        "createdAt": value.get("createdAt"),
        "lastUsedAt": value.get("lastUsedAt"),
        "dataRelativePath": "data",
        "leases": _json_clone(leases) if isinstance(leases, list) else None,
    }


def _configured_absolute_root(
    value: str | Path | None,
    default_root: Path,
    field_name: str,
) -> Path:
    normalized = str(value or "").strip()
    if not normalized:
        return Path(os.path.abspath(default_root))
    requested = Path(normalized)
    if not requested.is_absolute():
        raise MaaFWProjectStoreError(
            f"configured {field_name} must be an absolute path"
        )
    return Path(os.path.abspath(requested))


def _path_trees_overlap(left: Path, right: Path) -> bool:
    left_resolved = left.resolve(strict=False)
    right_resolved = right.resolve(strict=False)
    return _is_within(left_resolved, right_resolved) or _is_within(
        right_resolved,
        left_resolved,
    )


def _validate_project_manifest(
    value: Any,
    *,
    expected_project_id: str,
    expected_version: str,
    data_path: Path,
    allow_legacy_schema: bool = False,
) -> dict[str, Any]:
    """Validate every authoritative manifest field used by Store consumers."""

    if not isinstance(value, dict):
        raise MaaFWProjectStoreError("project manifest must be a JSON object")
    schema_version = value.get("schemaVersion")
    allowed_schemas = {MANIFEST_SCHEMA_VERSION}
    if allow_legacy_schema:
        allowed_schemas.add(LEGACY_MANIFEST_SCHEMA_VERSION)
    if type(schema_version) is not int or schema_version not in allowed_schemas:
        raise MaaFWProjectStoreError("project manifest schema version is unsupported")
    if (
        value.get("projectId") != expected_project_id
        or value.get("version") != expected_version
    ):
        raise MaaFWProjectStoreError(
            f"project manifest identity mismatch: "
            f"{expected_project_id}@{expected_version}"
        )
    _validate_component(expected_project_id, "project_id")
    _validate_component(expected_version, "version")
    _require_manifest_timestamp(value.get("createdAt"), "createdAt")
    if "remote" in value:
        normalized_remote = _normalize_remote_source_metadata(value.get("remote"))
        if normalized_remote is None or value.get("remote") != normalized_remote:
            raise MaaFWProjectStoreError(
                "project manifest remote source identity is not canonical"
            )

    source = _require_manifest_mapping(value, "source")
    source_kind = source.get("kind")
    if source_kind not in {"directory", "zip"}:
        raise MaaFWProjectStoreError("project manifest source.kind is invalid")
    _require_manifest_text(source.get("path"), "source.path")
    source_project_path = source.get("projectPath")
    if not isinstance(source_project_path, str):
        raise MaaFWProjectStoreError(
            "project manifest source.projectPath must be a string"
        )
    source_project_relative = _normalize_relative_path(
        source_project_path,
        "project manifest source.projectPath",
        allow_root=True,
    )
    source_interface_path = source.get("interfacePath")
    if not isinstance(source_interface_path, str):
        raise MaaFWProjectStoreError(
            "project manifest source.interfacePath must be a string"
        )
    source_interface_relative = _normalize_relative_path(
        source_interface_path,
        "project manifest source.interfacePath",
    )
    interface_version = source.get("interfaceVersion")
    if interface_version is not None:
        _require_manifest_text(interface_version, "source.interfaceVersion")
    if source.get("version") != interface_version:
        raise MaaFWProjectStoreError(
            "project manifest source.version does not match source.interfaceVersion"
        )
    for field_name in ("inputSizeBytes", "treeSizeBytes"):
        _require_non_negative_manifest_integer(
            source.get(field_name),
            f"source.{field_name}",
        )
    archive_hash = source.get("archiveSha256")
    if source_kind == "zip":
        if not isinstance(archive_hash, str) or not re.fullmatch(
            r"[0-9a-fA-F]{64}",
            archive_hash,
        ):
            raise MaaFWProjectStoreError(
                "project manifest source.archiveSha256 is invalid"
            )
    elif archive_hash is not None:
        raise MaaFWProjectStoreError(
            "directory project manifest must not declare source.archiveSha256"
        )

    source_hash_descriptor = _manifest_hash_descriptor(
        value,
        "source",
        expected_scope="projected-source",
    )
    _require_manifest_mapping(value, "payload")
    payload_hash_descriptor = _manifest_hash_descriptor(
        value,
        "payload",
        expected_scope="store-payload",
    )
    if schema_version == MANIFEST_SCHEMA_VERSION:
        legacy_hashes = {
            int(source_hash_descriptor["schemaVersion"])
            == _LEGACY_TREE_HASH_SCHEMA_VERSION,
            int(payload_hash_descriptor["schemaVersion"])
            == _LEGACY_TREE_HASH_SCHEMA_VERSION,
        }
        if len(legacy_hashes) != 1:
            raise MaaFWProjectStoreError(
                "project manifest source and payload hash schemas must migrate together"
            )
        uses_legacy_hashes = legacy_hashes == {True}
        if not uses_legacy_hashes and "hashCompatibility" in value:
            raise MaaFWProjectStoreError(
                "current project manifest must not declare legacy hash compatibility"
            )

    project_interface = _require_manifest_mapping(value, "projectInterface")
    interface_path_value = project_interface.get("path")
    if not isinstance(interface_path_value, str):
        raise MaaFWProjectStoreError(
            "project manifest projectInterface.path must be a string"
        )
    interface_relative = _normalize_relative_path(
        interface_path_value,
        "project manifest projectInterface.path",
    )
    try:
        expected_interface_relative = source_interface_relative.relative_to(
            source_project_relative
        )
    except ValueError as exc:
        raise MaaFWProjectStoreError(
            "project manifest source.interfacePath is outside source.projectPath"
        ) from exc
    if (
        interface_relative != expected_interface_relative
        or interface_relative.name.casefold()
        not in {"interface.json", "interface.jsonc"}
    ):
        raise MaaFWProjectStoreError(
            "project manifest ProjectInterface identity is inconsistent"
        )
    if type(project_interface.get("resourceHashCleared")) is not bool:
        raise MaaFWProjectStoreError(
            "project manifest projectInterface.resourceHashCleared must be boolean"
        )
    cleared_resources = project_interface.get("clearedResources")
    if not isinstance(cleared_resources, list) or any(
        not isinstance(item, Mapping) for item in cleared_resources
    ):
        raise MaaFWProjectStoreError(
            "project manifest projectInterface.clearedResources must be an object array"
        )
    for cleared_resource in cleared_resources:
        cleared_file = _require_manifest_text(
            cleared_resource.get("file"),
            "projectInterface.clearedResources.file",
        )
        _normalize_relative_path(
            cleared_file,
            "project manifest projectInterface.clearedResources.file",
        )
        _require_manifest_text(
            cleared_resource.get("resource"),
            "projectInterface.clearedResources.resource",
        )

    _assert_not_reparse(data_path)
    if not data_path.is_dir():
        raise MaaFWProjectStoreError(
            f"project manifest data directory is missing: {data_path}"
        )
    interface_path = data_path / interface_relative
    _assert_path_chain_within_root(interface_path, data_path)
    _assert_not_reparse(interface_path)
    if not interface_path.is_file():
        raise MaaFWProjectStoreError(
            f"project manifest ProjectInterface is missing: {interface_path}"
        )
    _, discovered_interface_path = _discover_project_interface(data_path)
    if not _same_path(discovered_interface_path, interface_path):
        raise MaaFWProjectStoreError(
            "project manifest ProjectInterface does not match the payload root"
        )
    stored_interface = _read_json_object(interface_path)
    if "remote" in value and _merge_remote_source_metadata(
        value.get("remote"),
        stored_interface,
    ) != value.get("remote"):
        raise MaaFWProjectStoreError(
            "project manifest remote source identity does not match ProjectInterface"
        )

    runtime = _require_manifest_mapping(value, "runtime")
    runtime_constraint = runtime.get("constraint")
    if runtime_constraint is not None:
        _require_manifest_text(runtime_constraint, "runtime.constraint")
    if value.get("runtimeConstraint") != runtime_constraint:
        raise MaaFWProjectStoreError(
            "project manifest runtimeConstraint does not match runtime.constraint"
        )
    _require_manifest_text(runtime.get("platform"), "runtime.platform")
    _require_manifest_text(runtime.get("arch"), "runtime.arch")

    if "python" not in runtime and schema_version != LEGACY_MANIFEST_SCHEMA_VERSION:
        raise MaaFWProjectStoreError("project manifest runtime.python is missing")
    python_runtime = runtime.get("python")
    if python_runtime is not None:
        if not isinstance(python_runtime, Mapping):
            raise MaaFWProjectStoreError(
                "project manifest runtime.python must be a JSON object or null"
            )
        if str(python_runtime.get("implementation") or "").casefold() != "cpython":
            raise MaaFWProjectStoreError(
                "project manifest runtime.python implementation is invalid"
            )
        python_constraint = _require_manifest_text(
            python_runtime.get("constraint"),
            "runtime.python.constraint",
        )
        try:
            SpecifierSet(python_constraint)
        except InvalidSpecifier as exc:
            raise MaaFWProjectStoreError(
                "project manifest runtime.python constraint is invalid"
            ) from exc
        _require_manifest_text_list(
            python_runtime.get("sources"),
            "runtime.python.sources",
            allow_empty=False,
            require_unique=True,
        )

    agents = value.get("agents")
    runtime_agents = runtime.get("agent")
    _require_manifest_object_list(agents, "agents")
    _require_manifest_object_list(runtime_agents, "runtime.agent")
    if agents != runtime_agents:
        raise MaaFWProjectStoreError(
            "project manifest agents do not match runtime.agent"
        )
    _validate_manifest_agents(agents)

    required_abi = _require_manifest_text_list(
        value.get("requiredPythonAbi"),
        "requiredPythonAbi",
        allow_empty=True,
        require_unique=True,
    )
    runtime_required_abi = _require_manifest_text_list(
        runtime.get("requiredPythonAbi"),
        "runtime.requiredPythonAbi",
        allow_empty=True,
        require_unique=True,
    )
    if required_abi != runtime_required_abi:
        raise MaaFWProjectStoreError(
            "project manifest requiredPythonAbi does not match runtime.requiredPythonAbi"
        )
    if type(runtime.get("sharedAgentDependenciesComplete")) is not bool:
        raise MaaFWProjectStoreError(
            "project manifest runtime.sharedAgentDependenciesComplete must be boolean"
        )

    binding = runtime.get("binding")
    if binding is not None:
        if not isinstance(binding, Mapping):
            raise MaaFWProjectStoreError(
                "project manifest runtime.binding must be a JSON object or null"
            )
        _require_manifest_text(binding.get("runtimeId"), "runtime.binding.runtimeId")
    _require_manifest_text_list(
        runtime.get("references"),
        "runtime.references",
        allow_empty=True,
        require_unique=True,
    )
    _active_leases(runtime.get("leases"), float("-inf"))
    if type(runtime.get("pinned")) is not bool:
        raise MaaFWProjectStoreError("project manifest runtime.pinned must be boolean")
    last_used_at = runtime.get("lastUsedAt")
    if last_used_at is not None:
        _require_manifest_timestamp(last_used_at, "runtime.lastUsedAt")

    projection = _require_manifest_mapping(value, "projection")
    copied = _require_manifest_relative_path_list(
        projection.get("copied"),
        "projection.copied",
    )
    if interface_relative.as_posix() not in copied:
        raise MaaFWProjectStoreError(
            "project manifest projection.copied does not contain ProjectInterface"
        )
    copied_from_source = _require_manifest_relative_path_list(
        projection.get("copiedFromSource"),
        "projection.copiedFromSource",
    )
    if len(copied_from_source) != len(copied):
        raise MaaFWProjectStoreError(
            "project manifest projected and source file lists are inconsistent"
        )
    _require_manifest_relative_path_list(
        projection.get("copiedDirectories"),
        "projection.copiedDirectories",
    )
    excluded = _require_manifest_relative_path_list(
        projection.get("excluded"),
        "projection.excluded",
    )
    excluded_reasons = projection.get("excludedReasons")
    if not isinstance(excluded_reasons, Mapping):
        raise MaaFWProjectStoreError(
            "project manifest projection.excludedReasons must be a JSON object"
        )
    if set(excluded_reasons) != set(excluded):
        raise MaaFWProjectStoreError(
            "project manifest projection.excludedReasons is inconsistent"
        )
    for excluded_path, reason in excluded_reasons.items():
        _require_manifest_text(excluded_path, "projection.excludedReasons key")
        _require_manifest_text(reason, f"projection.excludedReasons.{excluded_path}")
    for field_name in (
        "sourceSizeBytes",
        "payloadSizeBytes",
        "savedBytes",
    ):
        _require_non_negative_manifest_integer(
            projection.get(field_name),
            f"projection.{field_name}",
        )
    saved_percent = projection.get("savedPercent")
    if type(saved_percent) not in {int, float} or not 0 <= float(saved_percent) <= 100:
        raise MaaFWProjectStoreError(
            "project manifest projection.savedPercent is invalid"
        )
    source_size = int(projection["sourceSizeBytes"])
    payload_size = int(projection["payloadSizeBytes"])
    expected_saved_bytes = max(0, source_size - payload_size)
    expected_saved_percent = (
        round(expected_saved_bytes * 100 / source_size, 2) if source_size else 0.0
    )
    if (
        source_size != source.get("treeSizeBytes")
        or projection.get("savedBytes") != expected_saved_bytes
        or float(saved_percent) != expected_saved_percent
    ):
        raise MaaFWProjectStoreError(
            "project manifest projection size summary is inconsistent"
        )

    _validate_manifest_summaries(
        value,
        source=source,
        projection=projection,
        agent_count=len(agents),
    )
    warnings = value.get("warnings")
    if not isinstance(warnings, list) or any(
        not isinstance(item, str) for item in warnings
    ):
        raise MaaFWProjectStoreError("project manifest warnings must be a string array")
    return value


def _manifest_hash_descriptor(
    manifest: Mapping[str, Any],
    section_name: str,
    *,
    expected_scope: str,
) -> dict[str, Any]:
    section = manifest.get(section_name)
    if not isinstance(section, Mapping):
        raise MaaFWProjectStoreError(
            f"project manifest {section_name} must be a JSON object"
        )
    hash_value = section.get("hash")
    if not isinstance(hash_value, Mapping):
        raise MaaFWProjectStoreError(
            f"project manifest {section_name}.hash must be a JSON object"
        )
    if (
        str(hash_value.get("algorithm") or "").casefold() != "sha256"
        or hash_value.get("scope") != expected_scope
    ):
        raise MaaFWProjectStoreError(
            f"project manifest {section_name} hash identity is invalid"
        )
    digest_value = str(hash_value.get("value") or "").casefold()
    if not re.fullmatch(r"[0-9a-f]{64}", digest_value):
        raise MaaFWProjectStoreError(
            f"project manifest {section_name} hash value is invalid"
        )

    manifest_schema = manifest.get("schemaVersion")
    hash_schema = hash_value.get("schemaVersion")
    if manifest_schema == LEGACY_MANIFEST_SCHEMA_VERSION and hash_schema is None:
        if "domain" in hash_value or "framing" in hash_value:
            raise MaaFWProjectStoreError(
                f"legacy project manifest {section_name} hash framing is invalid"
            )
        return {
            **dict(hash_value),
            "value": digest_value,
            "schemaVersion": _LEGACY_TREE_HASH_SCHEMA_VERSION,
            "framing": _LEGACY_TREE_HASH_FRAMING,
        }

    if type(hash_schema) is not int:
        raise MaaFWProjectStoreError(
            f"project manifest {section_name} hash schema is invalid"
        )
    if hash_schema == _TREE_HASH_SCHEMA_VERSION:
        expected_domain = (
            _PROJECTED_SOURCE_HASH_DOMAIN_NAME
            if expected_scope == "projected-source"
            else _STORE_PAYLOAD_HASH_DOMAIN_NAME
        )
        if (
            hash_value.get("domain") != expected_domain
            or hash_value.get("framing") != _TREE_HASH_FRAMING
        ):
            raise MaaFWProjectStoreError(
                f"project manifest {section_name} hash framing is invalid"
            )
    elif hash_schema == _LEGACY_TREE_HASH_SCHEMA_VERSION:
        if (
            hash_value.get("framing") != _LEGACY_TREE_HASH_FRAMING
            or "domain" in hash_value
        ):
            raise MaaFWProjectStoreError(
                f"project manifest {section_name} legacy hash framing is invalid"
            )
        compatibility = manifest.get("hashCompatibility")
        if not isinstance(compatibility, Mapping):
            raise MaaFWProjectStoreError(
                "project manifest legacy hashes lack migration metadata"
            )
        if (
            compatibility.get("migratedFromManifestSchemaVersion")
            != LEGACY_MANIFEST_SCHEMA_VERSION
            or compatibility.get(f"{section_name}HashSchemaVersion")
            != _LEGACY_TREE_HASH_SCHEMA_VERSION
        ):
            raise MaaFWProjectStoreError(
                "project manifest legacy hash migration metadata is invalid"
            )
        _require_manifest_timestamp(
            compatibility.get("migratedAt"),
            "hashCompatibility.migratedAt",
        )
    else:
        raise MaaFWProjectStoreError(
            f"project manifest {section_name} hash schema is unsupported"
        )
    return {**dict(hash_value), "value": digest_value}


def _require_manifest_mapping(
    manifest: Mapping[str, Any],
    field_name: str,
) -> Mapping[str, Any]:
    value = manifest.get(field_name)
    if not isinstance(value, Mapping):
        raise MaaFWProjectStoreError(
            f"project manifest {field_name} must be a JSON object"
        )
    return value


def _require_manifest_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MaaFWProjectStoreError(
            f"project manifest {field_name} must be a non-empty string"
        )
    return value.strip()


def _require_manifest_timestamp(value: Any, field_name: str) -> str:
    normalized = _require_manifest_text(value, field_name)
    if _parse_timestamp(normalized) <= 0:
        raise MaaFWProjectStoreError(
            f"project manifest {field_name} is not a valid timestamp"
        )
    return normalized


def _require_non_negative_manifest_integer(value: Any, field_name: str) -> int:
    if type(value) is not int or value < 0:
        raise MaaFWProjectStoreError(
            f"project manifest {field_name} must be a non-negative integer"
        )
    return value


def _require_manifest_text_list(
    value: Any,
    field_name: str,
    *,
    allow_empty: bool,
    require_unique: bool,
) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise MaaFWProjectStoreError(
            f"project manifest {field_name} must be a string array"
        )
    if not allow_empty and not value:
        raise MaaFWProjectStoreError(f"project manifest {field_name} cannot be empty")
    if require_unique and len(value) != len(set(value)):
        raise MaaFWProjectStoreError(
            f"project manifest {field_name} contains duplicate values"
        )
    return value


def _require_manifest_object_list(value: Any, field_name: str) -> list[Any]:
    if not isinstance(value, list) or any(
        not isinstance(item, Mapping) for item in value
    ):
        raise MaaFWProjectStoreError(
            f"project manifest {field_name} must be an object array"
        )
    return value


def _validate_manifest_agents(value: list[Any]) -> None:
    indexes: list[int] = []
    for item in value:
        index = item.get("index")
        if type(index) is not int or index < 0:
            raise MaaFWProjectStoreError("project manifest agent index is invalid")
        indexes.append(index)
        _require_manifest_text(item.get("classification"), "agent.classification")
        if type(item.get("opaque")) is not bool:
            raise MaaFWProjectStoreError(
                "project manifest agent.opaque must be boolean"
            )
        _require_manifest_text_list(
            item.get("projectPaths"),
            "agent.projectPaths",
            allow_empty=True,
            require_unique=False,
        )
    if indexes != list(range(len(indexes))):
        raise MaaFWProjectStoreError(
            "project manifest agent indexes must be contiguous"
        )


def _validate_manifest_summaries(
    manifest: Mapping[str, Any],
    *,
    source: Mapping[str, Any],
    projection: Mapping[str, Any],
    agent_count: int,
) -> None:
    capabilities = _require_manifest_mapping(manifest, "capabilities")
    counts = capabilities.get("counts")
    if not isinstance(counts, Mapping):
        raise MaaFWProjectStoreError(
            "project manifest capabilities.counts must be a JSON object"
        )
    for field_name, count in counts.items():
        _require_manifest_text(field_name, "capabilities.counts key")
        _require_non_negative_manifest_integer(
            count,
            f"capabilities.counts.{field_name}",
        )
    if counts.get("agents") != agent_count:
        raise MaaFWProjectStoreError(
            "project manifest capabilities agent count is inconsistent"
        )
    _require_manifest_text_list(
        capabilities.get("features"),
        "capabilities.features",
        allow_empty=True,
        require_unique=True,
    )
    for field_name in (
        "controllerNames",
        "controllerTypes",
        "resourceNames",
        "taskNames",
        "optionTypes",
        "languageNames",
    ):
        _require_manifest_text_list(
            capabilities.get(field_name),
            f"capabilities.{field_name}",
            allow_empty=True,
            require_unique=True,
        )
    truncated = capabilities.get("truncated")
    if not isinstance(truncated, Mapping) or any(
        type(item) is not bool for item in truncated.values()
    ):
        raise MaaFWProjectStoreError(
            "project manifest capabilities.truncated is invalid"
        )

    shells = _require_manifest_mapping(manifest, "shells")
    _require_manifest_text_list(
        shells.get("families"),
        "shells.families",
        allow_empty=True,
        require_unique=True,
    )
    stripped_count = _require_non_negative_manifest_integer(
        shells.get("strippedCount"),
        "shells.strippedCount",
    )
    reason_counts = shells.get("reasonCounts")
    if not isinstance(reason_counts, Mapping):
        raise MaaFWProjectStoreError(
            "project manifest shells.reasonCounts must be a JSON object"
        )
    for reason, count in reason_counts.items():
        _require_manifest_text(reason, "shells.reasonCounts key")
        _require_non_negative_manifest_integer(
            count,
            f"shells.reasonCounts.{reason}",
        )
    shell_paths = shells.get("paths")
    if not isinstance(shell_paths, list) or any(
        not isinstance(item, Mapping) for item in shell_paths
    ):
        raise MaaFWProjectStoreError(
            "project manifest shells.paths must be an object array"
        )
    for item in shell_paths:
        shell_path = _require_manifest_text(item.get("path"), "shells.paths.path")
        _normalize_relative_path(shell_path, "project manifest shells.paths.path")
        _require_manifest_text(item.get("reason"), "shells.paths.reason")
    if stripped_count < len(shell_paths):
        raise MaaFWProjectStoreError(
            "project manifest shells.strippedCount is inconsistent"
        )
    if type(shells.get("pathsTruncated")) is not bool:
        raise MaaFWProjectStoreError(
            "project manifest shells.pathsTruncated must be boolean"
        )

    size = _require_manifest_mapping(manifest, "size")
    expected_sizes = {
        "inputBytes": source.get("inputSizeBytes"),
        "sourceTreeBytes": source.get("treeSizeBytes"),
        "projectedBytes": projection.get("payloadSizeBytes"),
        "savedBytes": projection.get("savedBytes"),
    }
    for field_name, expected in expected_sizes.items():
        actual = _require_non_negative_manifest_integer(
            size.get(field_name),
            f"size.{field_name}",
        )
        if actual != expected:
            raise MaaFWProjectStoreError(
                f"project manifest size.{field_name} is inconsistent"
            )
    size_percent = size.get("savedPercent")
    if type(size_percent) not in {int, float} or float(size_percent) != float(
        projection.get("savedPercent")
    ):
        raise MaaFWProjectStoreError(
            "project manifest size.savedPercent is inconsistent"
        )

    flags = _require_manifest_mapping(manifest, "flags")
    for field_name in ("opaqueAgent", "conservative"):
        if type(flags.get(field_name)) is not bool:
            raise MaaFWProjectStoreError(
                f"project manifest flags.{field_name} must be boolean"
            )


def _require_manifest_relative_path_list(value: Any, field_name: str) -> list[str]:
    paths = _require_manifest_text_list(
        value,
        field_name,
        allow_empty=True,
        require_unique=True,
    )
    for item in paths:
        _normalize_relative_path(
            item,
            f"project manifest {field_name}",
        )
    return paths


def _manifest_source_hash(manifest: Mapping[str, Any]) -> str:
    return str(
        _manifest_hash_descriptor(
            manifest,
            "source",
            expected_scope="projected-source",
        )["value"]
    )


def _manifest_payload_hash(manifest: Mapping[str, Any]) -> str:
    return str(
        _manifest_hash_descriptor(
            manifest,
            "payload",
            expected_scope="store-payload",
        )["value"]
    )


def _manifest_hash_schema_version(
    manifest: Mapping[str, Any],
    section_name: str,
) -> int:
    expected_scope = "projected-source" if section_name == "source" else "store-payload"
    return int(
        _manifest_hash_descriptor(
            manifest,
            section_name,
            expected_scope=expected_scope,
        )["schemaVersion"]
    )


def _calculate_store_payload_hash(
    data_path: Path,
    *,
    hash_schema_version: int = _TREE_HASH_SCHEMA_VERSION,
) -> str:
    _, files = _scan_safe_tree(data_path)
    files.discard(Path(MANIFEST_FILE_NAME))
    if hash_schema_version == _TREE_HASH_SCHEMA_VERSION:
        return _calculate_tree_hash(
            data_path,
            files,
            domain=_STORE_PAYLOAD_HASH_DOMAIN,
        )
    if hash_schema_version == _LEGACY_TREE_HASH_SCHEMA_VERSION:
        return _calculate_projected_source_hash_legacy(data_path, files)
    raise MaaFWProjectStoreError(
        f"unsupported Store payload hash schema: {hash_schema_version}"
    )


def _checkout_id(identity: Mapping[str, str]) -> str:
    encoded = json.dumps(
        dict(identity),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"maafw-checkout-{hashlib.sha256(encoded).hexdigest()[:32]}"


def _copy_checkout_tree(source_root: Path, target_root: Path) -> None:
    _assert_not_reparse(source_root)
    if not source_root.is_dir():
        raise MaaFWProjectStoreError(f"project-store payload is missing: {source_root}")
    target_root.mkdir(parents=True, exist_ok=False)
    for current_raw, directory_names, file_names in os.walk(
        source_root,
        followlinks=False,
    ):
        current = Path(current_raw)
        _assert_not_reparse(current)
        relative = current.relative_to(source_root)
        destination = target_root / relative
        destination.mkdir(parents=True, exist_ok=True)
        for directory_name in directory_names:
            child = current / directory_name
            _assert_not_reparse(child)
            if not child.is_dir():
                raise MaaFWProjectStoreError(
                    f"project-store payload contains a special directory: {child}"
                )
            (destination / directory_name).mkdir(parents=True, exist_ok=True)
        for file_name in file_names:
            child = current / file_name
            _assert_not_reparse(child)
            if not child.is_file():
                raise MaaFWProjectStoreError(
                    f"project-store payload contains a special file: {child}"
                )
            if relative == Path(".") and file_name == MANIFEST_FILE_NAME:
                continue
            shutil.copy2(child, destination / file_name)


def _store_lock(root: Path) -> RLock:
    key = os.path.normcase(str(root.resolve(strict=True)))
    with _STORE_LOCKS_GUARD:
        return _STORE_LOCKS.setdefault(key, RLock())


def _is_legacy_default_store(children: Iterable[Path]) -> bool:
    known_names = {"projects", ".staging"}
    for child in children:
        _assert_not_reparse(child)
        if child.name not in known_names or not child.is_dir():
            return False
    return True


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left.resolve(strict=False))) == os.path.normcase(
        str(Path(os.path.abspath(right)).resolve(strict=False))
    )


def _assert_not_reparse(path: Path) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    file_attributes = getattr(metadata, "st_file_attributes", 0)
    if path.is_symlink() or bool(file_attributes & reparse_flag):
        raise MaaFWProjectStoreError(f"reparse points are not allowed: {path}")


def _assert_path_chain_within_root(path: Path, root: Path) -> None:
    absolute = Path(os.path.abspath(path))
    root_absolute = root.resolve(strict=True)
    try:
        absolute.relative_to(root_absolute)
    except ValueError as exc:
        raise MaaFWProjectStoreError(f"path escapes project store: {path}") from exc
    current = root_absolute
    _assert_not_reparse(current)
    for part in absolute.relative_to(root_absolute).parts:
        current = current / part
        if current.exists() or current.is_symlink():
            _assert_not_reparse(current)


def _assert_within(path: Path, root: Path) -> None:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=True))
    except ValueError as exc:
        raise MaaFWProjectStoreError(f"path escapes allowed root: {path}") from exc


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


def _safe_remove_tree(path: Path, store_root: Path) -> None:
    _assert_path_chain_within_root(path, store_root)
    resolved_root = store_root.resolve(strict=True)
    resolved_path = path.resolve(strict=False)
    if resolved_path == resolved_root:
        raise MaaFWProjectStoreError("refusing to delete the project-store root")
    if not path.exists():
        return
    _assert_not_reparse(path)
    for current_raw, directory_names, file_names in os.walk(path, followlinks=False):
        current = Path(current_raw)
        _assert_not_reparse(current)
        for name in [*directory_names, *file_names]:
            _assert_not_reparse(current / name)
    shutil.rmtree(path)


def _build_agent_summary(agents: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for agent in agents:
        summaries.append(
            {
                key: _json_clone(value)
                for key, value in agent.items()
                if not str(key).startswith("_")
            }
        )
    return summaries


def _build_capability_summary(plan: _ProjectionPlan) -> dict[str, Any]:
    counters = {
        "controllers": 0,
        "resources": 0,
        "tasks": 0,
        "pretasks": 0,
        "presets": 0,
        "groups": 0,
        "settings": 0,
        "options": 0,
        "imports": 0,
        "languages": 0,
        "agents": len(plan.agent_runtime),
    }
    controller_names: set[str] = set()
    controller_types: set[str] = set()
    resource_names: set[str] = set()
    task_names: set[str] = set()
    option_types: set[str] = set()
    language_names: set[str] = set()
    features: set[str] = set()

    for payload in plan.rewritten_json.values():
        controllers = _interface_object_items(payload.get("controller"))
        resources = _interface_object_items(payload.get("resource"))
        tasks = _interface_object_items(payload.get("task"))
        pretasks = _interface_object_items(payload.get("pretask"))
        presets = _interface_object_items(payload.get("preset"))
        groups = _interface_object_items(payload.get("group"))
        settings = _interface_object_items(payload.get("setting"))
        options = _interface_object_items(
            payload.get("option")
            if payload.get("option") is not None
            else payload.get("options")
        )
        imports = _string_or_list(payload.get("import"))
        languages = payload.get("languages")

        counters["controllers"] += len(controllers)
        counters["resources"] += len(resources)
        counters["tasks"] += len(tasks)
        counters["pretasks"] += len(pretasks)
        counters["presets"] += len(presets)
        counters["groups"] += len(groups)
        counters["settings"] += len(settings)
        counters["options"] += len(options)
        counters["imports"] += len(imports)
        if isinstance(languages, dict):
            counters["languages"] += len(languages)
            language_names.update(str(key) for key in languages)

        _collect_field_values(controllers, "name", controller_names)
        _collect_field_values(controllers, "type", controller_types)
        _collect_field_values(resources, "name", resource_names)
        _collect_field_values(tasks, "name", task_names)
        _collect_field_values(options, "type", option_types)

        for key, feature in (
            ("agent", "agents"),
            ("pretask", "pretasks"),
            ("preset", "presets"),
            ("group", "groups"),
            ("setting", "settings"),
            ("option", "options"),
            ("hotkey", "hotkeys"),
            ("scan", "scan"),
            ("import", "imports"),
            ("languages", "i18n"),
        ):
            value = payload.get(key)
            if value not in (None, [], {}):
                features.add(feature)

    if any(
        path.parts and path.parts[0].casefold() == "plugins"
        for path in plan.copied_files
    ):
        features.add("native-plugins")
    if plan.required_python_abi:
        features.add("native-python-abi")
    if plan.opaque_agent:
        features.add("opaque-agent")

    return {
        "counts": counters,
        "features": sorted(features),
        "controllerNames": _bounded_summary_names(controller_names),
        "controllerTypes": _bounded_summary_names(controller_types),
        "resourceNames": _bounded_summary_names(resource_names),
        "taskNames": _bounded_summary_names(task_names),
        "optionTypes": _bounded_summary_names(option_types),
        "languageNames": _bounded_summary_names(language_names),
        "truncated": {
            "taskNames": len(task_names) > MAX_SUMMARY_ITEM_NAMES,
            "resourceNames": len(resource_names) > MAX_SUMMARY_ITEM_NAMES,
        },
    }


def _build_shell_summary(excluded_reasons: dict[str, str]) -> dict[str, Any]:
    relevant_reasons = {
        "ui-shell",
        "ui-runtime",
        "ui-or-updater-shell",
        "updater-shell",
    }
    family_names = {
        "mfaavalonia": "MFAAvalonia",
        "mxu": "MXU",
        "cfa": "CFA",
        "mfw": "MFW",
        "maapicli": "MaaPiCli",
    }
    paths: list[dict[str, str]] = []
    families: set[str] = set()
    reason_counts: dict[str, int] = {}
    for path, reason in sorted(excluded_reasons.items()):
        if reason not in relevant_reasons:
            continue
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
        for part in Path(path).parts:
            stem = part.casefold().split(".", 1)[0]
            if stem in family_names:
                families.add(family_names[stem])
        if len(paths) < MAX_SUMMARY_ITEM_NAMES:
            paths.append({"path": path, "reason": reason})
    stripped_count = sum(reason_counts.values())
    return {
        "families": sorted(families),
        "strippedCount": stripped_count,
        "reasonCounts": dict(sorted(reason_counts.items())),
        "paths": paths,
        "pathsTruncated": stripped_count > len(paths),
    }


def _build_size_summary(
    *,
    source_tree_bytes: int,
    projected_payload_bytes: int,
    input_size_bytes: int,
) -> dict[str, Any]:
    saved_bytes = max(0, source_tree_bytes - projected_payload_bytes)
    saved_percent = (
        round(saved_bytes * 100 / source_tree_bytes, 2) if source_tree_bytes else 0.0
    )
    return {
        "inputBytes": int(input_size_bytes),
        "sourceTreeBytes": int(source_tree_bytes),
        "projectedBytes": int(projected_payload_bytes),
        "savedBytes": int(saved_bytes),
        "savedPercent": saved_percent,
    }


def _build_inventory_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    source = manifest.get("source")
    source = source if isinstance(source, dict) else {}
    runtime = manifest.get("runtime")
    runtime = runtime if isinstance(runtime, dict) else {}
    agents = manifest.get("agents")
    if not isinstance(agents, list):
        agents = runtime.get("agent") if isinstance(runtime.get("agent"), list) else []
    capabilities = manifest.get("capabilities")
    if not isinstance(capabilities, dict):
        capabilities = {
            "counts": {"agents": len(agents)},
            "features": ["agents"] if agents else [],
        }
    shells = manifest.get("shells")
    if not isinstance(shells, dict):
        shells = {
            "families": [],
            "strippedCount": 0,
            "reasonCounts": {},
            "paths": [],
            "pathsTruncated": False,
        }
    size = manifest.get("size")
    if not isinstance(size, dict):
        projection = manifest.get("projection")
        projection = projection if isinstance(projection, dict) else {}
        source_tree_bytes = int(
            source.get("treeSizeBytes") or projection.get("sourceSizeBytes") or 0
        )
        projected_bytes = int(projection.get("payloadSizeBytes") or 0)
        size = _build_size_summary(
            source_tree_bytes=source_tree_bytes,
            projected_payload_bytes=projected_bytes,
            input_size_bytes=int(source.get("inputSizeBytes") or source_tree_bytes),
        )
    warnings = manifest.get("warnings")
    warning_count = len(warnings) if isinstance(warnings, list) else 0
    return {
        "projectId": manifest.get("projectId"),
        "version": manifest.get("version"),
        "remote": _json_clone(manifest.get("remote")),
        "interfaceVersion": (
            source.get("interfaceVersion")
            if source.get("interfaceVersion") is not None
            else source.get("version")
        ),
        "sourceKind": source.get("kind") or "directory",
        "runtimeConstraint": runtime.get("constraint"),
        "pythonConstraint": (
            runtime.get("python", {}).get("constraint")
            if isinstance(runtime.get("python"), Mapping)
            else None
        ),
        "pythonImplementation": (
            runtime.get("python", {}).get("implementation")
            if isinstance(runtime.get("python"), Mapping)
            else None
        ),
        "requiredPythonAbi": _json_clone(
            manifest.get("requiredPythonAbi")
            if isinstance(manifest.get("requiredPythonAbi"), list)
            else runtime.get("requiredPythonAbi") or []
        ),
        "agentCount": len(agents),
        "agents": _json_clone(agents),
        "capabilities": _json_clone(capabilities),
        "shells": _json_clone(shells),
        "size": _json_clone(size),
        "flags": _json_clone(manifest.get("flags") or {}),
        "warningCount": warning_count,
    }


def _interface_object_items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _collect_field_values(
    items: Iterable[dict[str, Any]],
    field: str,
    target: set[str],
) -> None:
    for item in items:
        value = _optional_string(item.get(field))
        if value:
            target.add(value)


def _bounded_summary_names(values: Iterable[str]) -> list[str]:
    return sorted(set(values), key=str.casefold)[:MAX_SUMMARY_ITEM_NAMES]


def _tree_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return total
    for current_raw, directory_names, file_names in os.walk(path, followlinks=False):
        current = Path(current_raw)
        _assert_not_reparse(current)
        for directory_name in directory_names:
            _assert_not_reparse(current / directory_name)
        for file_name in file_names:
            file_path = current / file_name
            _assert_not_reparse(file_path)
            total += file_path.stat().st_size
    return total


def _relative_parents(path: Path) -> set[Path]:
    parents: set[Path] = {Path(".")}
    current = path.parent
    while current != Path("."):
        parents.add(current)
        current = current.parent
    return parents


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _object_list(value: Any) -> list[dict[str, Any]]:
    return (
        [item for item in value or [] if isinstance(item, dict)]
        if isinstance(value, list)
        else []
    )


def _string_or_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str) and item.strip()]
    return []


def _normalize_remote_source_metadata(
    value: Any,
) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise MaaFWProjectStoreError("remote source identity must be a JSON object")
    source = str(value.get("source") or "").strip().casefold()
    if source in {"github", "github_release"}:
        allowed = {
            "source",
            "github",
            "github_tag",
            "github_asset_pattern",
        }
        if set(value) - allowed:
            raise MaaFWProjectStoreError(
                "GitHub remote source identity contains unsupported fields"
            )
        repo = _optional_string(value.get("github"))
        if repo is None:
            raise MaaFWProjectStoreError(
                "GitHub remote source identity is missing repository"
            )
        result = {"source": "GitHub", "github": repo}
        tag = _optional_string(value.get("github_tag"))
        asset_pattern = _optional_string(value.get("github_asset_pattern"))
        if tag is not None:
            result["github_tag"] = tag
        if asset_pattern is not None:
            result["github_asset_pattern"] = asset_pattern
        return result
    if source in {"mirrorchyan", "mirror_chyan", "mirror酱"}:
        allowed = {
            "source",
            "mirrorchyan_rid",
            "mirrorchyan_multiplatform",
        }
        if set(value) - allowed:
            raise MaaFWProjectStoreError(
                "MirrorChyan remote source identity contains unsupported fields"
            )
        rid = _optional_string(value.get("mirrorchyan_rid"))
        if rid is None:
            raise MaaFWProjectStoreError(
                "MirrorChyan remote source identity is missing RID"
            )
        multiplatform = value.get("mirrorchyan_multiplatform", True)
        if not isinstance(multiplatform, bool):
            raise MaaFWProjectStoreError(
                "MirrorChyan remote source multiplatform must be boolean"
            )
        return {
            "source": "MirrorChyan",
            "mirrorchyan_rid": rid,
            "mirrorchyan_multiplatform": multiplatform,
        }
    raise MaaFWProjectStoreError("remote source identity must be MirrorChyan or GitHub")


def _merge_remote_source_metadata(
    value: Any,
    interface: Mapping[str, Any],
) -> dict[str, Any] | None:
    remote = _normalize_remote_source_metadata(value)
    if remote is None:
        return None
    if remote["source"] == "GitHub":
        repo = _project_interface_remote_text(
            interface,
            ("github", "githubRepo", "github_repo", "GitHubRepo"),
        )
        tag = _project_interface_remote_text(
            interface,
            ("github_tag", "githubTag", "GitHubTag"),
        )
        asset_pattern = _project_interface_remote_text(
            interface,
            (
                "github_asset_pattern",
                "githubAssetPattern",
                "GitHubAssetPattern",
                "asset_pattern",
                "assetPattern",
            ),
        )
        if repo:
            remote["github"] = repo
        if tag:
            remote["github_tag"] = tag
        if asset_pattern:
            remote["github_asset_pattern"] = asset_pattern
        return remote

    rid = _project_interface_remote_text(
        interface,
        (
            "mirrorchyan_rid",
            "mirrorChyanRid",
            "mirrorchyanRid",
            "MirrorChyanRID",
        ),
    )
    multiplatform = _project_interface_remote_bool(
        interface,
        (
            "mirrorchyan_multiplatform",
            "mirrorChyanMultiplatform",
            "mirrorchyanMultiplatform",
        ),
    )
    if rid:
        remote["mirrorchyan_rid"] = rid
    if multiplatform is not None:
        remote["mirrorchyan_multiplatform"] = multiplatform
    return remote


def _project_interface_remote_sources(
    interface: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    sources: list[Mapping[str, Any]] = [interface]
    for key in (
        "project",
        "projectInterface",
        "project_interface",
        "remote",
        "sourceConfig",
        "source_config",
        "update",
    ):
        nested = interface.get(key)
        if isinstance(nested, Mapping):
            sources.append(nested)
    return sources


def _project_interface_remote_text(
    interface: Mapping[str, Any],
    keys: tuple[str, ...],
) -> str:
    for source in _project_interface_remote_sources(interface):
        for key in keys:
            value = _optional_string(source.get(key))
            if value is not None:
                return value
    return ""


def _project_interface_remote_bool(
    interface: Mapping[str, Any],
    keys: tuple[str, ...],
) -> bool | None:
    for source in _project_interface_remote_sources(interface):
        for key in keys:
            value = source.get(key)
            if isinstance(value, bool):
                return value
    return None


def _optional_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _json_clone(value: Any) -> Any:
    if value is None:
        return None
    try:
        return json.loads(json.dumps(value, ensure_ascii=False))
    except (TypeError, ValueError) as exc:
        raise MaaFWProjectStoreError("service values must be JSON-compatible") from exc


def _format_timestamp(timestamp: float | None = None) -> str:
    value = datetime.fromtimestamp(
        timestamp if timestamp is not None else time.time(),
        tz=timezone.utc,
    )
    return value.isoformat().replace("+00:00", "Z")


def _active_leases(value: Any, now: float) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise MaaFWProjectStoreError("project lease collection is invalid")
    active: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            raise MaaFWProjectStoreError("project lease entry is invalid")
        lease_id = item.get("leaseId")
        owner = item.get("owner")
        expires_at = item.get("expiresAt")
        if (
            not isinstance(lease_id, str)
            or not lease_id
            or not isinstance(owner, str)
            or not owner
        ):
            raise MaaFWProjectStoreError("project lease identity is invalid")
        expires_at_value = _parse_timestamp(expires_at)
        if expires_at_value <= 0:
            raise MaaFWProjectStoreError("project lease expiry is invalid")
        if expires_at_value <= now:
            continue
        active.append(_json_clone(item))
    return active


def _parse_timestamp(value: Any) -> float:
    if not isinstance(value, str) or not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0
