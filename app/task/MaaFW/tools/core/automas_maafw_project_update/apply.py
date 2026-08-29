"""Safe local-directory package planning and transactional application."""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import shutil
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .contracts import (
    ArtifactType,
    RESERVED_PROJECT_DIRS,
    is_within,
    project_fingerprint,
    safe_relative_path,
)
from .state import DEFAULT_OPERATION_ROOT, UpdateOperationStore, project_lock


ZIP_MAX_ENTRIES = 100_000
ZIP_MAX_EXPANDED_BYTES = 8 * 1024 * 1024 * 1024
MANIFEST_NAME = "resource-manifest.json"
PROJECT_STATE_DIR_NAME = "maafw_project_state"


def _resolve_project_state_dir(project_path: Path, operation_root: Path) -> Path:
    """纯路径推导：不碰文件系统，供创建路径与只读探测共用。"""

    normalized = str(project_path.resolve(strict=False)).casefold()
    project_key = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]
    state_root = (
        operation_root.resolve(strict=False).parent / PROJECT_STATE_DIR_NAME
    ).resolve(strict=False)
    return state_root / project_key


def _project_state_dir(
    project_path: Path,
    operation: UpdateOperationStore,
    *,
    create: bool = True,
) -> Path:
    state_root = (
        operation.root.resolve(strict=False).parent / PROJECT_STATE_DIR_NAME
    ).resolve(strict=False)
    raw_state_dir = _resolve_project_state_dir(project_path, operation.root)
    if raw_state_dir.is_symlink():
        raise UpdateApplyError("MaaFW project state path cannot be a symlink")
    state_dir = raw_state_dir.resolve(strict=False)
    if not state_dir.is_relative_to(state_root):
        raise UpdateApplyError("MaaFW project state path escapes host state root")
    if state_dir.is_symlink():
        raise UpdateApplyError("MaaFW project state path cannot be a symlink")
    if create:
        state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def has_trusted_update_baseline(
    project_path: Path,
    *,
    operation_root: Path | None = None,
) -> bool:
    """项目是否已有可信的更新基线（差量包能据以校验的那个指纹）。

    只读探测，不创建任何目录。返回 False 时调用方应当去要**全量包**：
    差量包在 ``_validate_plan_base`` 里必须能对上 ``projectFingerprint``，
    从未经 MAS 更新过的项目没有这份 manifest，差量包一定被拒——那正是
    「首次更新永远装不上」的自举死锁。
    """

    try:
        # 只做路径推导，绝不新建 operation 目录或项目状态目录——探测必须无副作用。
        state_dir = _resolve_project_state_dir(
            Path(project_path), operation_root or DEFAULT_OPERATION_ROOT
        )
        manifest_path = state_dir / MANIFEST_NAME
        if not manifest_path.is_file():
            return False
        manifest = _load_manifest(manifest_path)
        return bool(str(manifest.get("projectFingerprint") or "").strip())
    except Exception:  # noqa: BLE001
        # 探测失败一律按「没有基线」处理：要全量包最多是多下点数据，
        # 要差量包却没有基线则是必然失败。
        return False


def _owned_state_path(path: Path, state_dir: Path) -> Path:
    candidate = path.expanduser().resolve(strict=False)
    base = state_dir.expanduser().resolve(strict=False)
    if not candidate.is_absolute() or not candidate.is_relative_to(base):
        raise UpdateApplyError("MaaFW update state path is outside operation-owned state")
    return candidate


class UpdateApplyError(RuntimeError):
    """Raised when a local update plan cannot be safely committed."""

    def __init__(self, message: str, *, unsafe_to_continue: bool = False) -> None:
        super().__init__(message)
        self.unsafe_to_continue = unsafe_to_continue


@dataclass(frozen=True)
class PackagePlan:
    package_type: ArtifactType
    package_root: Path
    files: dict[str, Path]
    hashes: dict[str, str]
    deleted: tuple[str, ...]
    base_version: str | None = None
    base_fingerprint: str | None = None
    target_version: str | None = None


def apply_package_transaction(
    project_path: Path,
    package_path: Path,
    *,
    operation: UpdateOperationStore | None = None,
    operation_root: Path | None = None,
    plan_id: str | None = None,
    expected_fingerprint: str | None = None,
    expected_package_type: ArtifactType | None = None,
    from_version: str | None = None,
    target_version: str | None = None,
    post_validate: Callable[[Path], Any] | None = None,
    send_log: Callable[[str], None] | None = None,
    progress: Callable[[str, dict[str, Any]], None] | None = None,
    project_lock_already_held: bool = False,
) -> dict[str, Any]:
    """Apply a package using a durable stage/backup transaction.

    The function only removes files previously recorded in the updater-owned
    project manifest. Unknown user files remain untouched during full updates.
    """

    root = project_path.expanduser().resolve(strict=False)
    archive = package_path.expanduser().resolve(strict=False)
    if not root.is_dir():
        raise UpdateApplyError(f"MaaFW project directory does not exist: {root}")
    if not archive.is_file():
        raise UpdateApplyError(f"MaaFW update package does not exist: {archive}")
    before = project_fingerprint(root)
    if before is None:
        raise UpdateApplyError("cannot calculate MaaFW project fingerprint")
    expected = str(expected_fingerprint or "").strip().lower()
    if expected and before != expected:
        raise UpdateApplyError("MaaFW project changed after update plan; apply rejected")

    store = operation or UpdateOperationStore.create(
        root=operation_root or DEFAULT_OPERATION_ROOT,
        projectPath=str(root),
        expectedFingerprint=expected or before,
        planId=plan_id or uuid.uuid4().hex,
        targetVersion=target_version or "",
    )
    effective_plan_id = str(plan_id or store.read().get("planId") or uuid.uuid4().hex)
    state_dir = _project_state_dir(root, store)
    work_dir = _owned_state_path(
        state_dir / "operations" / store.operation_id,
        state_dir,
    )
    extract_dir = work_dir / "extract"
    backup_dir = work_dir / "backup"
    raw_manifest_path = state_dir / MANIFEST_NAME
    if raw_manifest_path.is_symlink():
        raise UpdateApplyError("MaaFW project manifest cannot be a symlink")
    manifest_path = _owned_state_path(raw_manifest_path, state_dir)
    send_update_log = send_log or (lambda _message: None)

    with project_lock(root, project_lock_already_held=project_lock_already_held):
        current = project_fingerprint(root)
        if current != before or (expected and current != expected):
            raise UpdateApplyError("MaaFW project changed before apply; apply rejected")
        expanded_size = _zip_expanded_size(archive)
        _check_disk_space(
            state_dir,
            root,
            state_required=expanded_size,
            project_required=0,
        )
        _remove_owned_path(work_dir, state_dir)
        extract_dir.mkdir(parents=True, exist_ok=True)
        try:
            _safe_extract_zip(archive, extract_dir)
            package_root = _find_package_root(extract_dir)
            old_manifest = _load_manifest(manifest_path)
            previous_manifest_path = _owned_state_path(
                work_dir / "previous-manifest.json",
                state_dir,
            )
            if manifest_path.is_file():
                _copy_path(manifest_path, previous_manifest_path)
            plan = build_package_plan(
                package_root,
                extract_dir,
                root,
                old_manifest=old_manifest,
                expected_package_type=expected_package_type,
                from_version=from_version,
                target_version=target_version,
            )
            _validate_plan_base(root, plan, old_manifest, current)
            if plan.package_type == "full":
                stale = set(old_manifest.get("files", {})) - set(plan.files)
            else:
                stale = set(plan.deleted)
            touched = sorted(set(plan.files) | stale)
            _verify_owned_files(root, old_manifest)
            backup_size = _owned_backup_size(root, touched)
            payload_size = sum(
                source.stat().st_size
                for source in plan.files.values()
                if source.is_file()
            )
            # 只要 backup_size：expanded_size 在上面 _safe_extract_zip 时就已经
            # 真实落到 state 卷上了，这里再加一遍等于要求两倍空间，会在空间刚好
            # 够用时报出虚假的 INSUFFICIENT_DISK。
            _check_disk_space(
                state_dir,
                root,
                state_required=backup_size,
                project_required=payload_size,
            )
            store.update(
                "plan_validated",
                projectPath=str(root),
                packagePath=str(archive),
                planId=effective_plan_id,
                expectedFingerprint=expected or current,
                currentFingerprint=current,
                packageType=plan.package_type,
                fromVersion=plan.base_version or from_version or "",
                targetVersion=plan.target_version or target_version or "",
                plannedFiles=list(plan.files),
                deletedFiles=sorted(stale),
                workDir=str(work_dir),
                stateRoot=str(state_dir),
                manifestPath=str(manifest_path),
                previousManifestPath=(
                    str(previous_manifest_path) if manifest_path.is_file() else ""
                ),
            )
            _emit(progress, "plan_validated", {"planId": effective_plan_id, "packageType": plan.package_type})

            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_entries: dict[str, bool] = {}
            for relative in touched:
                target = _project_target(root, relative)
                if target.exists() or target.is_symlink():
                    backup_entries[relative] = True
                    _copy_path(target, backup_dir / relative)
                else:
                    backup_entries[relative] = False
            _write_json(work_dir / "backup-manifest.json", {"files": backup_entries})
            store.update(
                "staged",
                stageDir=str(extract_dir),
                backupDir=str(backup_dir),
                touchedPaths=touched,
                backupEntries=backup_entries,
            )
            _emit(progress, "staged", {"planId": effective_plan_id})

            store.update("applying")
            _emit(progress, "applying", {"planId": effective_plan_id})
            for relative in sorted(stale, key=lambda item: len(Path(item).parts), reverse=True):
                _remove_path(_project_target(root, relative))
            for relative, source in plan.files.items():
                target = _project_target(root, relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)

            store.update("post_validating")
            _emit(progress, "post_validating", {"planId": effective_plan_id})
            _validate_project_interface(root)
            actual_version = _read_interface_version(root, strict=True).strip()
            expected_version = str(plan.target_version or target_version or "").strip()
            if (
                expected_version
                and actual_version.lstrip("vV") != expected_version.lstrip("vV")
            ):
                raise UpdateApplyError(
                    "updated MaaFW interface version does not match the planned target"
                )
            if post_validate is not None:
                result = post_validate(root)
                if inspect.isawaitable(result):
                    raise UpdateApplyError("post_validate callback must be synchronous")
                if result is False:
                    raise UpdateApplyError("MaaFW post-validation rejected the update")

            after = project_fingerprint(root)
            if after is None:
                raise UpdateApplyError("cannot calculate updated MaaFW project fingerprint")
            manifest = {
                "schemaVersion": 1,
                "version": plan.target_version or target_version or "",
                "projectFingerprint": after,
                # 不登记字节码：它会被解释器重写，登记了只会让下一次
                # _verify_owned_files 判定「受管文件被本地改写」而永久拒装。
                # 旧 manifest 里已有的 .pyc 条目也借这次重写自然清出。
                "files": {
                    relative: _sha256_file(_project_target(root, relative))
                    for relative in sorted(set(plan.files) | (set(old_manifest.get("files", {})) - stale))
                    if _project_target(root, relative).is_file()
                    and not _is_bytecode_artifact(relative)
                },
            }
            _write_json(manifest_path, manifest)
            store.update("committed", committed=True, finalFingerprint=after)
            _emit(progress, "committed", {"planId": effective_plan_id})
            send_update_log("MaaFW update package committed")
            cleanup_warning = ""
            try:
                _remove_owned_path(work_dir, state_dir)
            except Exception as cleanup_error:
                # Project and manifest are already durably committed.  A
                # locked backup/staging file must not relabel a successful
                # update as failed or trigger a second application attempt.
                cleanup_warning = str(cleanup_error)[:500]
                store.update("committed", cleanupPending=True, cleanupError=cleanup_warning)
                send_update_log("MaaFW update committed; deferred state cleanup is required")
            return {
                "operationId": store.operation_id,
                "planId": effective_plan_id,
                "status": "committed",
                "packageType": plan.package_type,
                "currentFingerprint": current,
                "finalFingerprint": after,
                "targetVersion": plan.target_version or target_version,
                "cleanupPending": bool(cleanup_warning),
            }
        except Exception as exc:
            try:
                state = store.read()
            except Exception:
                state = {}
            if state.get("status") in {"applying", "post_validating", "staged"}:
                try:
                    _rollback_from_state(root, state)
                except Exception as rollback_error:
                    store.update(
                        "recovery_required",
                        recoveryRequired=True,
                        rollbackError=str(rollback_error)[:500],
                    )
                    raise UpdateApplyError(
                        f"MaaFW update failed and rollback failed: {rollback_error}",
                        unsafe_to_continue=True,
                    ) from rollback_error
                store.update("rolled_back", rollbackReason=str(exc)[:500])
                _emit(progress, "rolled_back", {"planId": effective_plan_id})
                _remove_owned_path(work_dir, state_dir)
            else:
                store.update("failed", error=str(exc)[:500])
                _remove_owned_path(work_dir, state_dir)
            if isinstance(exc, UpdateApplyError):
                raise
            raise UpdateApplyError(str(exc)) from exc


def build_package_plan(
    package_root: Path,
    extract_dir: Path,
    project_path: Path,
    *,
    old_manifest: Mapping[str, Any] | None = None,
    expected_package_type: ArtifactType | None = None,
    from_version: str | None = None,
    target_version: str | None = None,
) -> PackagePlan:
    changes_path = _find_changes_file(package_root, extract_dir)
    changes = _load_json(changes_path) if changes_path else {}
    declared_type = str(
        changes.get("packageType") or changes.get("type") or changes.get("kind") or ""
    ).strip().lower()
    package_type: ArtifactType = "delta" if changes_path else "full"
    if declared_type in {"full", "delta"}:
        package_type = declared_type  # type: ignore[assignment]
    if expected_package_type and package_type != expected_package_type:
        raise UpdateApplyError(
            f"update package type mismatch: expected {expected_package_type}, got {package_type}"
        )

    base_version = _first_text(changes, "baseVersion", "fromVersion", "from", "sourceVersion")
    base_fingerprint = _first_text(
        changes,
        "baseFingerprint",
        "baseHash",
        "projectFingerprint",
        "sourceFingerprint",
    )
    declared_target = _first_text(changes, "targetVersion", "version", "toVersion")
    payload_root = _resolve_payload_root(package_root, changes_path, changes, extract_dir)
    files: dict[str, Path] = {}
    hashes: dict[str, str] = {}
    for source in payload_root.rglob("*"):
        if source.is_dir():
            continue
        if source.is_symlink():
            raise UpdateApplyError(f"update package contains symlink: {source}")
        if source.name == "changes.json":
            continue
        relative = safe_relative_path(source.relative_to(payload_root).as_posix())
        files[relative] = source

    raw_file_metadata = changes.get("files")
    if isinstance(raw_file_metadata, Mapping):
        for raw_path, raw_meta in raw_file_metadata.items():
            relative = safe_relative_path(str(raw_path))
            source = payload_root / relative
            if source.is_file():
                files[relative] = source
            if isinstance(raw_meta, Mapping):
                digest = str(raw_meta.get("sha256") or raw_meta.get("hash") or "").strip().lower()
            else:
                digest = str(raw_meta or "").strip().lower()
            if digest:
                hashes[relative] = digest.removeprefix("sha256:")
    deleted = tuple(_deleted_paths(changes))
    for relative in deleted:
        safe_relative_path(relative)
    if package_type == "full" and not _has_interface_file(package_root):
        raise UpdateApplyError("full update package must contain interface.json")
    return PackagePlan(
        package_type=package_type,
        package_root=package_root,
        files=files,
        hashes=hashes,
        deleted=deleted,
        base_version=base_version,
        base_fingerprint=base_fingerprint,
        target_version=declared_target or target_version,
    )


def recover_update_operation(
    operation: UpdateOperationStore,
    *,
    send_log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Recover a staged/applying operation after a process restart."""

    try:
        state = operation.read()
    except Exception as exc:
        try:
            operation.mark_recovery_required(str(exc))
        except Exception:
            pass
        raise UpdateApplyError(
            f"MaaFW update journal recovery is required: {exc}",
            unsafe_to_continue=True,
        ) from exc
    status = str(state.get("status") or "")
    if status not in {"staged", "applying", "post_validating"}:
        return state
    raw_project = str(state.get("projectPath") or "").strip()
    raw_state_root = str(state.get("stateRoot") or "").strip()
    raw_work_dir = str(state.get("workDir") or "").strip()
    if not raw_project or not raw_state_root or not raw_work_dir:
        operation.mark_recovery_required("update journal has incomplete owned paths")
        raise UpdateApplyError(
            "MaaFW update journal has incomplete owned paths",
            unsafe_to_continue=True,
        )
    root = Path(raw_project).expanduser().resolve(strict=False)
    state_dir = Path(raw_state_root).expanduser().resolve(strict=False)
    host_state_root = (operation.root.resolve(strict=False).parent / PROJECT_STATE_DIR_NAME).resolve(strict=False)
    expected_key = hashlib.sha256(str(root).casefold().encode("utf-8")).hexdigest()[:24]
    if (
        not state_dir.is_absolute()
        or not state_dir.is_relative_to(host_state_root)
        or state_dir.name != expected_key
    ):
        operation.mark_recovery_required("update journal state root is outside host state")
        raise UpdateApplyError(
            "MaaFW update journal state root is outside host state",
            unsafe_to_continue=True,
        )
    try:
        work_dir = _owned_state_path(Path(raw_work_dir), state_dir)
    except UpdateApplyError as exc:
        operation.mark_recovery_required(str(exc))
        raise UpdateApplyError(str(exc), unsafe_to_continue=True) from exc
    if not root.is_dir():
        return operation.update("recovery_required", recoveryRequired=True, error="project path is missing")
    try:
        _rollback_from_state(root, state, state_dir=state_dir)
    except Exception as exc:
        operation.update("recovery_required", recoveryRequired=True, rollbackError=str(exc)[:500])
        raise UpdateApplyError(str(exc), unsafe_to_continue=True) from exc
    if send_log:
        send_log(f"MaaFW update operation recovered: {operation.operation_id}")
    _remove_owned_path(work_dir, state_dir)
    return operation.update("rolled_back", recovered=True)


def _validate_plan_base(
    project_path: Path,
    plan: PackagePlan,
    old_manifest: Mapping[str, Any],
    current_fingerprint: str,
) -> None:
    if plan.package_type != "delta":
        return
    recorded = str(plan.base_fingerprint or "").strip().lower()
    manifest_fingerprint = str(old_manifest.get("projectFingerprint") or "").strip().lower()
    if recorded:
        if recorded != current_fingerprint:
            raise UpdateApplyError("delta baseFingerprint does not match project")
    elif manifest_fingerprint:
        if manifest_fingerprint != current_fingerprint:
            raise UpdateApplyError("delta base manifest does not match project")
    else:
        raise UpdateApplyError("legacy delta has no trusted base fingerprint; full package required")
    if plan.base_version:
        current_version = _read_interface_version(project_path)
        if current_version and plan.base_version.strip().lstrip("vV") != current_version.strip().lstrip("vV"):
            raise UpdateApplyError(
                f"delta baseVersion does not match project: {plan.base_version} != {current_version}"
            )
    for relative, expected in plan.hashes.items():
        source = plan.files.get(relative)
        if source is None or _sha256_file(source) != expected:
            raise UpdateApplyError(f"delta file hash mismatch: {relative}")


def _is_bytecode_artifact(relative: str) -> bool:
    """相对路径是否为 Python 字节码产物。

    这类文件由解释器在**导入时**自行写出/重写：全量包里自带的 .pyc 一旦解压到
    新路径，首次 import 就会因源码 mtime 与嵌入路径变化被重写。若把它们纳入
    受管文件校验，装过一次并跑过一次之后，_verify_owned_files 就会认定「受管文件
    被本地改写」而**永久拒绝后续所有更新**——这正是全局 fail-closed 的代价。
    """

    normalized = relative.replace("\\", "/")
    return normalized.endswith(".pyc") or "__pycache__/" in f"{normalized}/"


def _verify_owned_files(project_path: Path, manifest: Mapping[str, Any]) -> None:
    files = manifest.get("files")
    if not isinstance(files, Mapping):
        return
    for raw_path, raw_hash in files.items():
        relative = safe_relative_path(str(raw_path))
        if _is_bytecode_artifact(relative):
            # 字节码由解释器重写，不构成「用户改动了受管文件」。
            continue
        target = _project_target(project_path, relative)
        if not target.exists():
            continue
        expected = str(raw_hash or "").strip().lower().removeprefix("sha256:")
        if expected and target.is_file() and _sha256_file(target) != expected:
            raise UpdateApplyError(f"managed project file was modified locally: {relative}")


def _rollback_from_state(
    project_path: Path,
    state: Mapping[str, Any],
    *,
    state_dir: Path | None = None,
) -> None:
    raw_backup = str(state.get("backupDir") or "").strip()
    if not raw_backup:
        raise UpdateApplyError("update journal has no backup directory")
    if state_dir is None:
        raw_state = str(state.get("stateRoot") or "").strip()
        if not raw_state:
            raise UpdateApplyError("update journal has no owned state root")
        state_dir = Path(raw_state).expanduser().resolve(strict=False)
    backup_dir = _owned_state_path(Path(raw_backup), state_dir)
    touched = state.get("touchedPaths")
    if not isinstance(touched, list):
        touched = []
    for raw_path in sorted((str(item) for item in touched), key=lambda item: len(Path(item).parts), reverse=True):
        _remove_path(_project_target(project_path, raw_path))
    backup_entries = state.get("backupEntries")
    if not isinstance(backup_entries, Mapping):
        backup_entries = {}
    for raw_path, existed in backup_entries.items():
        if not existed:
            continue
        source = (backup_dir / safe_relative_path(str(raw_path))).resolve(strict=False)
        if not source.is_relative_to(backup_dir):
            raise UpdateApplyError("update backup path escapes operation-owned backup")
        if source.exists():
            _copy_path(source, _project_target(project_path, str(raw_path)))
    raw_manifest = str(state.get("manifestPath") or "").strip()
    raw_previous_manifest = str(state.get("previousManifestPath") or "").strip()
    if raw_manifest and raw_previous_manifest:
        manifest_path = _owned_state_path(Path(raw_manifest), state_dir)
        previous_path = _owned_state_path(Path(raw_previous_manifest), state_dir)
        if previous_path.is_file():
            _copy_path(previous_path, manifest_path)
    elif raw_manifest:
        manifest_path = _owned_state_path(Path(raw_manifest), state_dir)
        _remove_path(manifest_path)


def _find_package_root(extract_dir: Path) -> Path:
    candidates = [extract_dir, *[item for item in extract_dir.iterdir() if item.is_dir()]]
    for candidate in candidates:
        if _has_interface_file(candidate) or (candidate / "changes.json").is_file():
            return candidate
    for interface in extract_dir.rglob("interface.json*"):
        if interface.name in {"interface.json", "interface.jsonc"}:
            return interface.parent
    for changes in extract_dir.rglob("changes.json"):
        return changes.parent
    raise UpdateApplyError("update package does not contain interface.json or changes.json")


def _zip_expanded_size(package_path: Path) -> int:
    try:
        with zipfile.ZipFile(package_path, "r") as archive:
            members = archive.infolist()
            if len(members) > ZIP_MAX_ENTRIES:
                raise UpdateApplyError(
                    f"update package contains too many entries: {len(members)}"
                )
            expanded = sum(max(0, int(item.file_size)) for item in members)
    except zipfile.BadZipFile as exc:
        raise UpdateApplyError("update package is not a valid zip file") from exc
    if expanded > ZIP_MAX_EXPANDED_BYTES:
        raise UpdateApplyError("update package expanded size exceeds limit")
    return expanded


def _owned_backup_size(project_path: Path, touched: list[str]) -> int:
    total = 0
    for relative in touched:
        target = _project_target(project_path, relative)
        if target.is_file():
            total += target.stat().st_size
        elif target.is_dir():
            for child in target.rglob("*"):
                if child.is_symlink():
                    raise UpdateApplyError("project contains a symlink in a managed path")
                if child.is_file():
                    total += child.stat().st_size
    return total


def _check_disk_space(
    state_dir: Path,
    project_path: Path,
    *,
    state_required: int,
    project_required: int,
) -> None:
    reserve = 1024 * 1024
    try:
        state_free = shutil.disk_usage(state_dir).free
        project_free = shutil.disk_usage(project_path).free
    except OSError as exc:
        raise UpdateApplyError(
            "INSUFFICIENT_DISK: cannot determine free space"
        ) from exc
    if state_free < max(0, state_required) + reserve:
        raise UpdateApplyError(
            f"INSUFFICIENT_DISK: update staging needs {state_required} bytes, "
            f"state volume has {state_free} bytes free"
        )
    if project_free < max(0, project_required) + reserve:
        raise UpdateApplyError(
            f"INSUFFICIENT_DISK: project commit needs {project_required} bytes, "
            f"project volume has {project_free} bytes free"
        )


def _safe_extract_zip(package_path: Path, extract_dir: Path) -> None:
    try:
        with zipfile.ZipFile(package_path, "r") as archive:
            members = archive.infolist()
            if len(members) > ZIP_MAX_ENTRIES:
                raise UpdateApplyError(f"update package contains too many entries: {len(members)}")
            expanded = sum(max(0, int(item.file_size)) for item in members)
            if expanded > ZIP_MAX_EXPANDED_BYTES:
                raise UpdateApplyError("update package expanded size exceeds limit")
            for member in members:
                target = (extract_dir / member.filename).resolve()
                if not is_within(target, extract_dir):
                    raise UpdateApplyError(f"update package contains unsafe path: {member.filename}")
                mode = (member.external_attr >> 16) & 0o170000
                if mode == 0o120000:
                    raise UpdateApplyError(f"update package contains symlink: {member.filename}")
            archive.extractall(extract_dir)
    except zipfile.BadZipFile as exc:
        raise UpdateApplyError("update package is not a valid zip file") from exc


def _resolve_payload_root(
    package_root: Path,
    changes_path: Path | None,
    changes: Mapping[str, Any],
    extract_dir: Path,
) -> Path:
    if changes_path is not None:
        raw_files = changes.get("payload") or changes.get("root")
        if isinstance(raw_files, str) and raw_files.strip():
            candidate = (changes_path.parent / raw_files).resolve()
            if not is_within(candidate, extract_dir) or not candidate.is_dir():
                raise UpdateApplyError("changes.json payload path is unsafe")
            return candidate
    for name in ("payload", "files"):
        candidate = package_root / name
        if candidate.is_dir():
            return candidate
    return package_root


def _find_changes_file(package_root: Path, extract_dir: Path) -> Path | None:
    direct = package_root / "changes.json"
    if direct.is_file():
        return direct
    direct = extract_dir / "changes.json"
    return direct if direct.is_file() else None


def _deleted_paths(changes: Mapping[str, Any]) -> list[str]:
    result: list[str] = []
    for key in ("delete", "deleted", "deleted_dir", "remove", "removed", "unlink", "unlinks"):
        value = changes.get(key)
        if isinstance(value, list):
            result.extend(str(item) for item in value if isinstance(item, str))
        elif isinstance(value, Mapping):
            result.extend(str(item) for item in value if isinstance(item, str))
    return result


def _load_manifest(path: Path) -> dict[str, Any]:
    value = _load_json(path)
    files = value.get("files")
    if isinstance(files, list):
        value["files"] = {str(item): "" for item in files if isinstance(item, str)}
    elif not isinstance(files, Mapping):
        value["files"] = {}
    return value


def _load_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateApplyError(f"cannot parse update metadata: {path.name}") from exc
    if not isinstance(value, dict):
        raise UpdateApplyError(f"update metadata must be an object: {path.name}")
    return value


def _first_text(value: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        raw = str(value.get(key) or "").strip()
        if raw:
            return raw
    return None


def _has_interface_file(path: Path) -> bool:
    return (path / "interface.json").is_file() or (path / "interface.jsonc").is_file()


def _read_interface_version(project_path: Path, *, strict: bool = False) -> str:
    for name in ("interface.json", "interface.jsonc"):
        path = project_path / name
        if not path.is_file():
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            try:
                import json5

                value = json5.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                if strict:
                    raise UpdateApplyError("updated MaaFW interface is not valid JSON/JSONC") from exc
                return ""
        if not isinstance(value, Mapping):
            if strict:
                raise UpdateApplyError("updated MaaFW interface must be a JSON object")
            return ""
        return str(value.get("version") or "")
    return ""


def _validate_project_interface(project_path: Path) -> None:
    if not _has_interface_file(project_path):
        raise UpdateApplyError("updated MaaFW project has no interface.json")
    _read_interface_version(project_path, strict=True)


def _project_target(project_path: Path, relative: str) -> Path:
    normalized = safe_relative_path(relative)
    target = (project_path / normalized).resolve(strict=False)
    if not is_within(target, project_path):
        raise UpdateApplyError(f"update path escapes project root: {relative}")
    return target


def _copy_path(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir() and not source.is_symlink():
        shutil.copytree(source, target, dirs_exist_ok=True)
    else:
        shutil.copy2(source, target)


def _remove_path(path: Path) -> None:
    if not path or (not path.exists() and not path.is_symlink()):
        return
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def _remove_owned_path(path: Path, state_dir: Path) -> None:
    target = _owned_state_path(path, state_dir)
    if target == state_dir:
        raise UpdateApplyError("refusing to remove project state root")
    _remove_path(target)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{uuid.uuid4().hex[:8]}.tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        with temporary.open("r+b") as handle:
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _emit(progress: Callable[[str, dict[str, Any]], None] | None, stage: str, payload: dict[str, Any]) -> None:
    if progress is None:
        return
    try:
        progress(stage, payload)
    except Exception:
        return


__all__ = [
    "MANIFEST_NAME",
    "PackagePlan",
    "UpdateApplyError",
    "apply_package_transaction",
    "build_package_plan",
    "recover_update_operation",
]
