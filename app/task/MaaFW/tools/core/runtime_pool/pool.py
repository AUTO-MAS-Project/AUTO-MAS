from __future__ import annotations

import copy
import functools
import inspect
import json
import os
import platform
import re
import shutil
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from packaging.version import InvalidVersion, Version

from ._shared import (
    MaaFWRuntimePoolError,
    assert_existing_chain_has_no_reparse,
    assert_not_reparse,
    format_time,
    parse_time,
    pool_lock,
    remove_tree_best_effort,
    utc_now,
    write_json_atomic,
)
from .cache import clean_uv_cache
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
#: 旧身份 runtime 无引用后的宽限：重建只是重装一次依赖，不值得为它多留几天；
#: 24 小时只为兜住「算不出版本」的脚本一轮（见 reclaim_stale_runtimes）。
RECLAIM_GRACE_SECONDS = 24 * 60 * 60
POOL_MARKER_NAME = ".auto_mas_maafw_runtime_pool.json"
RUNTIME_MANIFEST_NAME = "manifest.json"
RUNTIME_DIRECTORY_NAME = "runtimes"
STAGING_DIRECTORY_NAME = ".staging"
RUNTIME_ID_RE = re.compile(r"^maafw-runtime-[0-9a-f]{24}$")
#: ``.staging`` 里归池管的条目前缀：runtime 安装 / 隔离、binding / native 换入、rename-first 的 trash。
_STAGING_PREFIXES = (RUNTIME_ID_PREFIX, "binding-", "native-", "trash-")

RuntimeInstaller = Callable[
    [Path, Sequence[str], dict[str, Any]],
    Mapping[str, Any] | None,
]
#: 往已发布 base 追加装包的安装器：``(venv 的 python, 要装的声明, 已装的 freeze 行)``
#: → 至少带 ``resolvedRequirements`` 的结果（见 ``installer.install_extra_packages``）。
ExtraPackagesInstaller = Callable[
    [Path, tuple[str, ...], tuple[str, ...]],
    Mapping[str, Any] | None,
]


class _MaaFWRuntimeEntryStaleError(MaaFWRuntimePoolError):
    """Raised for a recoverable runtime entry that no longer resolves."""


class MaaFWRuntimePoolBusyError(MaaFWRuntimePoolError):
    """runtime 正被别的租约用着，这一刻不能对它做改动（追加装包）。"""


class MaaFWRuntimePool:
    def __init__(
        self,
        root: str | Path,
        *,
        installer: RuntimeInstaller | None = None,
    ) -> None:
        default_root = Path.cwd() / "config" / "maafw_runtime_pool"
        requested_root = Path(root)
        if not requested_root.is_absolute():
            raise MaaFWRuntimePoolError(
                "configured runtime-pool root must be an absolute path"
            )
        absolute_root = Path(os.path.abspath(requested_root))
        assert_existing_chain_has_no_reparse(absolute_root)
        if absolute_root.exists() and not absolute_root.is_dir():
            raise MaaFWRuntimePoolError(
                f"runtime-pool root must be a directory: {absolute_root}"
            )
        absolute_root.mkdir(parents=True, exist_ok=True)
        assert_not_reparse(absolute_root)
        self.root = absolute_root.resolve(strict=True)
        self._is_default_root = _same_path(self.root, default_root)
        self.runtime_root = self.root / RUNTIME_DIRECTORY_NAME
        self.staging_root = self.root / STAGING_DIRECTORY_NAME
        self.python_root = self.root / "python"
        self.installer = installer
        self._lock = pool_lock(self.root)
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
                manifest["lastUsedAt"] = format_time(utc_now())
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
                manifest["lastUsedAt"] = format_time(utc_now())
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
                now = format_time(utc_now())
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
                write_json_atomic(stage_dir / RUNTIME_MANIFEST_NAME, manifest)

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
            manifest["lastUsedAt"] = format_time(parse_time(at) if at else utc_now())
            self._prune_expired_leases(manifest, utc_now())
            self._write_manifest(runtime_id, manifest)
            return self._augment_manifest(manifest)

    def install_extra_packages(
        self,
        runtime_id: str,
        requirements: Iterable[str],
        *,
        installer: ExtraPackagesInstaller,
    ) -> dict[str, Any]:
        """池锁内往已发布的 base 追加装包（D2 ``extraPackages``），身份不变。

        某个版本的 binding 多声明了 base 常量集合里没有的发行包时走这里：
        ``installer(python, 声明, 已装 freeze)`` 由调用方注入（正式路径是
        ``installer.install_extra_packages``，只新增不升级），返回的
        ``resolvedRequirements`` 覆盖 manifest 里的那份，声明记进
        ``installerMetadata.extraPackages``；runtime id 由常量集合算出，不变。

        有活租约（别的 worker 正用着这份 base）时拒绝，抛
        ``MaaFWRuntimePoolBusyError``，调用方等它们结束再来；持池锁全程，
        ``ensure`` / ``clean_cache`` / 回收不会插进来。
        """

        wanted = tuple(
            dict.fromkeys(
                str(item).strip() for item in requirements if str(item).strip()
            )
        )
        if not wanted:
            raise MaaFWRuntimePoolError("no extra packages were requested")
        with self._lock:
            self._initialize()
            manifest = self._read_manifest(runtime_id)
            payload = self._augment_manifest(
                manifest, verify_python=True, include_size=False
            )
            active = list(payload.get("activeLeaseIds") or [])
            if active:
                raise MaaFWRuntimePoolBusyError(
                    f"runtime {runtime_id} is leased by {len(active)} holder(s); "
                    "extra packages cannot be installed while it is in use"
                )
            python_executable = Path(str(payload["pythonExecutable"]))
            installed = tuple(
                str(item) for item in manifest.get("resolvedRequirements") or []
            )
            result = dict(installer(python_executable, wanted, installed) or {})
            resolved = _normalize_string_list(
                result.pop("resolvedRequirements", None)
                or result.pop("resolved_requirements", None),
                "resolvedRequirements",
            )
            if not resolved:
                raise MaaFWRuntimePoolError(
                    "extra packages installer did not report resolvedRequirements"
                )
            raw_metadata = manifest.get("installerMetadata")
            installer_metadata = (
                dict(raw_metadata) if isinstance(raw_metadata, Mapping) else {}
            )
            extras = [
                str(item)
                for item in installer_metadata.get("extraPackages") or []
                if str(item)
            ]
            extras.extend(item for item in wanted if item not in extras)
            installer_metadata["extraPackages"] = extras
            manifest["resolvedRequirements"] = resolved
            manifest["installerMetadata"] = _json_compatible(installer_metadata)
            manifest["lastUsedAt"] = format_time(utc_now())
            self._write_manifest(runtime_id, manifest)
            return self._augment_manifest(manifest, include_size=False)

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
            now = utc_now()
            self._prune_expired_leases(manifest, now)
            leases = dict(manifest.get("leases") or {})
            leases[normalized] = {
                "owner": str(owner or ""),
                "acquiredAt": format_time(now),
                "expiresAt": (
                    format_time(now + timedelta(seconds=float(ttl_seconds)))
                    if ttl_seconds is not None
                    else None
                ),
            }
            manifest["leases"] = leases
            manifest["lastUsedAt"] = format_time(now)
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
            now = utc_now()
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

    def reclaim_stale_runtimes(
        self,
        *,
        valid_runtime_ids: Iterable[str],
        binding_versions: Iterable[str] = (),
        native_versions: Iterable[str] = (),
        replaced_versions: Iterable[str] = (),
        retained_versions: Iterable[str] = (),
        grace_seconds: float = RECLAIM_GRACE_SECONDS,
        now: str | datetime | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """按引用对账回收池里过时的东西（取代按 lastUsedAt 宽限 + keep_latest 的 gc）。

        权威清单由宿主侧算好传进来（核心包不读 Config，见 ``tools/embedded/pool_reconcile``）：

        - ``valid_runtime_ids``：当前宿主身份下的 base runtime id（所有项目共用一个；
          宿主是 embeddable 且托管解释器未装时算不出，宿主侧整轮弃权不会调到这里）。
        - ``binding_versions``：权威集合里各项目钉定 / 已能定下来的 maafw 精确版本；
          ``native_versions`` 是其中没自带 DLL、还要池里官方原生库的。
        - ``replaced_versions``：本轮明确被替换掉的旧版本（项目更新提交时传），只
          豁免宽限，不越过租约 / 引用计数 / 权威集合。
        - ``retained_versions``：本进程里正被引用的 binding 版本（prepare 后未 release、
          预检进行中），无条件保留——binding 的 .py 读完即关句柄，rename 对在用目录
          会成功，而 maa 有运行期懒加载，删了会半程 ModuleNotFoundError。

        回收对象与判据：

        1. ``runtimes/<id>``（不在 valid 里的）：
           - ``layout=base`` 的旧身份 base → 无活租约即删（重建只是重装一次依赖）；
           - 旧布局（maafw 装在 venv 里，版本 X）→ 先**就地收割** binding（RECORD 校验，
             零网络，见 ``binding.harvest_binding``），然后：X 的 binding（及需要时的
             native）已就绪 → 无活租约即删；否则 X 仍在权威集合里就保留
             （``needed_without_replacement``），不在集合里过了宽限（或 X 被替换）才删。
        2. ``bindings/maafw-X`` / ``native/maafw-X``：被引用或在权威集合里 → 保留；否则
           ``lastUsedAt`` 过了宽限（或 X 被替换）才删。
        3. ``cache/binding-src/<tag>.zip``：版本不在集合且文件过了宽限 → 删；
           ``cache/binding-wheels/``（旧的源码 wheel 缓存）整目录作废。
        4. 坏 manifest / 坏清单：单条记进 ``errors``，跳过，不锁死整轮。
        5. 删除一律 rename-first（换到 ``.staging`` 再 rmtree）：被映射的 DLL 让 rename
           失败时原样留到下次；换出后 rmtree 半途而废的残留由末尾的 staging 扫描收。

        返回里的 ``remainingLegacy`` 是本轮之后仍留在池里的旧布局 runtime，调用方据此
        决定要不要清 uv 缓存（仍有旧布局在就别清，保住离线重建）。
        """

        from . import binding as binding_module

        if grace_seconds < 0:
            raise MaaFWRuntimePoolError("reclaim grace_seconds cannot be negative")
        reference_time = parse_time(now) if now is not None else utc_now()
        cutoff = reference_time - timedelta(seconds=float(grace_seconds))
        valid_ids = {
            str(item).strip() for item in valid_runtime_ids if str(item).strip()
        }
        needed_bindings = _version_set(binding_versions)
        needed_natives = _version_set(native_versions)
        replaced = _version_set(replaced_versions)
        retained = _version_set(retained_versions)

        with self._lock:
            self._initialize()
            deleted: list[str] = []
            quarantined: list[dict[str, str]] = []
            kept: list[dict[str, Any]] = []
            skipped: list[dict[str, str]] = []
            errors: list[dict[str, str]] = []
            harvested: list[dict[str, str]] = []
            remaining_legacy: list[str] = []
            # §2.7：回收日志要报释放了多少。独占字节删了就腾出来；与 uv 缓存硬链接
            # 共用的那部分要等清缓存，单独一笔。dry_run 时是「将释放」。
            freed_bytes = 0
            cache_shared_bytes = 0

            def account(
                footprint: tuple[int, int], residue: Path | None = None
            ) -> None:
                nonlocal freed_bytes, cache_shared_bytes
                exclusive, shared = footprint
                if residue is not None:
                    left_exclusive, left_shared = _directory_footprint(residue)
                    exclusive = max(0, exclusive - left_exclusive)
                    shared = max(0, shared - left_shared)
                freed_bytes += exclusive
                cache_shared_bytes += shared

            def binding_ready(version: str) -> bool:
                if not version:
                    return False
                if binding_module.verify_binding(self.root, version) is None:
                    return False
                if version in needed_natives:
                    return binding_module.verify_native(self.root, version) is not None
                return True

            for path in sorted(self.runtime_root.glob(f"{RUNTIME_ID_PREFIX}*")):
                if not path.is_dir() or path.is_symlink():
                    continue
                runtime_id = path.name
                if runtime_id in valid_ids:
                    continue
                try:
                    manifest = self._read_manifest(runtime_id)
                except MaaFWRuntimePoolError as exc:
                    # 坏条目单独记录、单独跳过；别让一条坏 manifest 锁死整轮回收
                    errors.append({"runtimeId": runtime_id, "error": str(exc)})
                    remaining_legacy.append(runtime_id)
                    continue

                installer_metadata = manifest.get("installerMetadata")
                is_base = (
                    isinstance(installer_metadata, Mapping)
                    and installer_metadata.get("layout") == "base"
                )
                version = _normalize_maafw_version(manifest.get("maafwVersion"))
                reasons: list[str] = []
                if bool(manifest.get("pinned")):
                    # 手动钉住的条目（manifest 契约里的 pinned）不进回收；今天没人写它，
                    # 但既然 delete() 认它，回收也认，别让同一个字段两套语义。
                    reasons.append("pinned")
                if self._active_lease_ids(manifest, reference_time):
                    reasons.append("leased")
                if not is_base:
                    # 旧布局：先把 binding 收割出来（零网络），有了它旧 venv 就没用了
                    if version and not dry_run and not binding_ready(version):
                        outcome = self._harvest_legacy_runtime(
                            path,
                            manifest,
                            version,
                            native_needed=version in needed_natives,
                        )
                        if outcome is not None:
                            harvested.append(
                                {"runtimeId": runtime_id, "version": version, **outcome}
                            )
                    ready = binding_ready(version)
                    if not ready:
                        if version in needed_bindings:
                            reasons.append("needed_without_replacement")
                        last_used = parse_time(manifest.get("lastUsedAt"))
                        if last_used > cutoff and version not in replaced:
                            reasons.append("grace_period")
                if reasons:
                    kept.append({"runtimeId": runtime_id, "reasons": sorted(reasons)})
                    if not is_base:
                        remaining_legacy.append(runtime_id)
                    continue
                footprint = _directory_footprint(path)
                if dry_run:
                    deleted.append(runtime_id)
                    account(footprint)
                    continue
                outcome, detail = self._reclaim_runtime_dir(runtime_id)
                if outcome == "deleted":
                    deleted.append(runtime_id)
                    account(footprint)
                elif outcome == "quarantined":
                    # 已经不在 runtimes/ 里、不再是可用的 runtime，但盘上还有残留
                    deleted.append(runtime_id)
                    quarantined.append({"runtimeId": runtime_id, "path": detail})
                    account(footprint, Path(detail))
                else:
                    skipped.append({"runtimeId": runtime_id, "error": detail})
                    if not is_base:
                        remaining_legacy.append(runtime_id)

            # binding / native 目录
            bindings_deleted: list[str] = []
            bindings_kept: list[dict[str, Any]] = []
            for kind, root_dir, needed in (
                (
                    "binding",
                    self.root / binding_module.BINDINGS_DIRECTORY_NAME,
                    needed_bindings,
                ),
                (
                    "native",
                    self.root / binding_module.NATIVE_DIRECTORY_NAME,
                    needed_natives,
                ),
            ):
                if not root_dir.is_dir():
                    continue
                for child in sorted(root_dir.iterdir()):
                    if child.is_symlink() or not child.is_dir():
                        continue
                    version = binding_module.directory_version(child.name)
                    if version is None:
                        continue
                    label = f"{kind}:{version}"
                    reasons = []
                    if version in retained:
                        reasons.append("retained")
                    if version in needed:
                        reasons.append("needed")
                    if not reasons:
                        last_used = binding_module.manifest_last_used(
                            self.root, version, native=(kind == "native")
                        )
                        if (
                            last_used is not None
                            and last_used > cutoff
                            and version not in replaced
                        ):
                            reasons.append("grace_period")
                    if reasons:
                        bindings_kept.append(
                            {"entry": label, "reasons": sorted(reasons)}
                        )
                        continue
                    footprint = _directory_footprint(child)
                    if dry_run:
                        bindings_deleted.append(label)
                        account(footprint)
                        continue
                    outcome, detail = self._reclaim_directory(child)
                    if outcome == "deleted":
                        bindings_deleted.append(label)
                        account(footprint)
                    elif outcome == "quarantined":
                        bindings_deleted.append(label)
                        quarantined.append({"entry": label, "path": detail})
                        account(footprint, Path(detail))
                    else:
                        skipped.append({"entry": label, "error": detail})

            # 源码包缓存与作废的 wheel 缓存
            cache_deleted: list[str] = []
            source_cache = self.root / binding_module.BINDING_SRC_CACHE_RELATIVE_PATH
            if source_cache.is_dir():
                for archive in sorted(source_cache.glob("*.zip")):
                    version = _tag_version(archive.stem)
                    if version and version in (needed_bindings | retained):
                        continue
                    try:
                        archive_stat = archive.stat()
                    except OSError:
                        continue
                    modified = datetime.fromtimestamp(
                        archive_stat.st_mtime, tz=timezone.utc
                    )
                    if modified > cutoff and version not in replaced:
                        continue
                    if not dry_run:
                        try:
                            archive.unlink()
                        except OSError as exc:
                            skipped.append(
                                {"entry": f"source:{archive.name}", "error": str(exc)}
                            )
                            continue
                    cache_deleted.append(f"source:{archive.name}")
                    account(
                        (0, archive_stat.st_size)
                        if archive_stat.st_nlink > 1
                        else (archive_stat.st_size, 0)
                    )
            wheel_cache = self.root / "cache" / "binding-wheels"
            if wheel_cache.is_dir() and not wheel_cache.is_symlink():
                footprint = _directory_footprint(wheel_cache)
                if not dry_run:
                    outcome, detail = self._reclaim_directory(wheel_cache)
                    if outcome == "skipped":
                        skipped.append(
                            {"entry": "cache:binding-wheels", "error": detail}
                        )
                    elif outcome == "quarantined":
                        cache_deleted.append("cache:binding-wheels")
                        quarantined.append(
                            {"entry": "cache:binding-wheels", "path": detail}
                        )
                        account(footprint, Path(detail))
                    else:
                        cache_deleted.append("cache:binding-wheels")
                        account(footprint)
                else:
                    cache_deleted.append("cache:binding-wheels")
                    account(footprint)

            staging_swept: list[str] = []
            staging_residue: list[str] = []
            if not dry_run:
                staging_swept, staging_residue, staging_footprint = (
                    self._sweep_staging()
                )
                account(staging_footprint)
            return {
                "dryRun": bool(dry_run),
                "graceSeconds": float(grace_seconds),
                "validRuntimeIds": sorted(valid_ids),
                "bindingVersions": sorted(needed_bindings),
                "nativeVersions": sorted(needed_natives),
                "replacedVersions": sorted(replaced),
                "retainedVersions": sorted(retained),
                "deleted": deleted,
                "quarantined": quarantined,
                "kept": kept,
                "skipped": skipped,
                "errors": errors,
                "harvested": harvested,
                "bindingsDeleted": bindings_deleted,
                "bindingsKept": bindings_kept,
                "cacheDeleted": cache_deleted,
                "remainingLegacy": sorted(remaining_legacy),
                "stagingSwept": staging_swept,
                "stagingResidue": staging_residue,
                # 独占文件删掉即释放；与 uv 缓存硬链接共用的那部分要等清缓存才释放
                "freedBytes": freed_bytes,
                "cacheSharedBytes": cache_shared_bytes,
            }

    def _harvest_legacy_runtime(
        self,
        runtime_dir: Path,
        manifest: Mapping[str, Any],
        version: str,
        *,
        native_needed: bool,
    ) -> dict[str, str] | None:
        """从一个旧布局 runtime 就地收割 binding；失败只记日志，返回 None。"""

        from . import binding as binding_module

        environment = runtime_dir / str(
            manifest.get("environmentRelativePath") or "environment"
        )
        candidates = [environment / "Lib" / "site-packages"]
        candidates.extend(sorted(environment.glob("lib/python*/site-packages")))
        site_packages = next((item for item in candidates if item.is_dir()), None)
        if site_packages is None:
            return None
        installer_metadata = manifest.get("installerMetadata")
        source_hint = ""
        if isinstance(installer_metadata, Mapping):
            source_hint = str(installer_metadata.get("bindingSource") or "").strip()
        if not source_hint:
            source_hint = f"harvest:{runtime_dir.name}"
        try:
            last_used = parse_time(manifest.get("lastUsedAt"))
        except ValueError:
            last_used = None
        try:
            info = binding_module.harvest_binding(
                self.root,
                site_packages,
                native_needed=native_needed,
                source_hint=source_hint,
                last_used_at=last_used,
            )
        except Exception as exc:  # noqa: BLE001 - 收割失败改走下载，不影响回收其它条目
            return {"status": "failed", "error": str(exc)}
        if info is None:
            return {"status": "rejected"}
        return {
            "status": "harvested",
            "bindingDir": str(info.directory),
            "nativeDir": str(info.native_directory) if info.native_directory else "",
        }

    def _reclaim_directory(self, path: Path) -> tuple[str, str]:
        """rename-first 删一个池内目录（binding / native / 作废缓存）。

        返回 ``("deleted", "")`` / ``("quarantined", <残留路径>)`` / ``("skipped", <原因>)``。
        """

        try:
            assert_not_reparse(path)
            trash = self.staging_root / f"trash-{path.name}-{uuid.uuid4().hex}"
            self.staging_root.mkdir(parents=True, exist_ok=True)
            path.replace(trash)
        except (OSError, MaaFWRuntimePoolError) as exc:
            return "skipped", str(exc)
        if remove_tree_best_effort(trash):
            return "deleted", ""
        return "quarantined", str(trash)

    def clean_cache(self) -> dict[str, Any]:
        """整个清掉池自己的 uv 缓存（见 ``cache.clean_uv_cache``）。

        持池锁：``ensure`` 的安装全程也持这把锁，缓存不会在 uv 正往里写的时候
        被清掉。什么时候该清由宿主侧的对账决定（池里已无旧身份 runtime）。
        """

        with self._lock:
            self._initialize()
            return clean_uv_cache(self.root)

    def _usable_runtime_payload(self, runtime_id: str) -> dict[str, Any] | None:
        """与 ``get`` 同一套判定（manifest 合法、环境齐全、解释器 ABI 对得上），
        但不统计目录大小；只想知道「能不能用」时用它。持锁调用。"""

        runtime_dir = self._runtime_dir(runtime_id)
        if not runtime_dir.exists() and not runtime_dir.is_symlink():
            return None
        try:
            manifest = self._read_manifest(runtime_id)
            return self._augment_manifest(
                manifest, verify_python=True, include_size=False
            )
        except MaaFWRuntimePoolError:
            return None

    def _reclaim_runtime_dir(self, runtime_id: str) -> tuple[str, str]:
        """rename-first 删除一个 runtime。

        返回 ``("deleted", "")``、``("quarantined", <残留路径>)``（已换出 runtimes/
        但 rmtree 没删干净——某个 .pyd/.dll 还被映射着或被杀软占着）或
        ``("skipped", <原因>)``（连 rename 都失败，条目原样留在池里）。
        """

        try:
            _, quarantine_dir = self._quarantine_stale_runtime(runtime_id)
        except (OSError, MaaFWRuntimePoolError) as exc:
            # 目录里有被 worker 映射着的 DLL 时 os.replace 会失败：原样留下，下次再试
            return "skipped", str(exc)
        if quarantine_dir is None:
            return "deleted", ""
        # 已经换到隔离目录，剩下的 rmtree 尽力而为；残留由 _sweep_staging 下次再收
        if remove_tree_best_effort(quarantine_dir):
            return "deleted", ""
        return "quarantined", str(quarantine_dir)

    def _sweep_staging(self) -> tuple[list[str], list[str], tuple[int, int]]:
        """清掉 ``.staging`` 里遗留的半成品 / 隔离目录。

        返回 ``(本轮清空的条目名, 仍有残留的条目名, (释放的独占字节, 与缓存共用的字节))``。
        只在持有池锁时调用：``ensure`` 的安装与 binding 的换入全程也持有同一把锁，所以
        这里看到的每个 ``maafw-runtime-*`` / ``binding-*`` / ``native-*`` / ``trash-*`` 条目
        都不再有人用（安装失败没删干净的、隔离后 rmtree 半途而废的、下载到一半的 wheel）。
        仍删不掉的（DLL 还被映射着）留到下次。
        """

        swept: list[str] = []
        residue: list[str] = []
        freed = 0
        shared = 0
        if not self.staging_root.is_dir():
            return swept, residue, (freed, shared)
        for path in sorted(self.staging_root.iterdir()):
            if path.is_symlink():
                continue
            if not path.name.startswith(_STAGING_PREFIXES):
                continue
            if path.is_file():
                # binding 下载到一半的 .whl
                try:
                    size = path.stat().st_size
                    path.unlink()
                    swept.append(path.name)
                    freed += size
                except OSError:
                    residue.append(path.name)
                continue
            exclusive, linked = _directory_footprint(path)
            if remove_tree_best_effort(path):
                swept.append(path.name)
                freed += exclusive
                shared += linked
            else:
                residue.append(path.name)
                left_exclusive, left_linked = _directory_footprint(path)
                freed += max(0, exclusive - left_exclusive)
                shared += max(0, linked - left_linked)
        return swept, residue, (freed, shared)

    def _initialize(self) -> None:
        # Validate every managed child before reading or upgrading the marker so
        # an unsafe legacy layout is rejected without modifying it first.
        for managed_path in (
            self.runtime_root,
            self.staging_root,
            self.root / "cache",
            self.python_root,
            self.root / "bindings",
            self.root / "native",
        ):
            assert_existing_chain_has_no_reparse(managed_path)
        marker_path = self.root / POOL_MARKER_NAME
        if marker_path.exists() or marker_path.is_symlink():
            assert_not_reparse(marker_path)
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
                write_json_atomic(marker_path, marker)
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
            write_json_atomic(marker_path, marker)
            identity = _validate_pool_marker(marker)
        if self._root_identity and self._root_identity != identity:
            raise MaaFWRuntimePoolError(
                "runtime pool identity changed during the service lifetime"
            )
        self._root_identity = identity
        assert_existing_chain_has_no_reparse(self.runtime_root)
        assert_existing_chain_has_no_reparse(self.staging_root)
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self.staging_root.mkdir(parents=True, exist_ok=True)
        self.python_root.mkdir(parents=True, exist_ok=True)
        assert_not_reparse(self.runtime_root)
        assert_not_reparse(self.staging_root)
        assert_not_reparse(self.python_root)

    def inventory(self) -> dict[str, Any]:
        """List every managed-looking runtime and report corruption explicitly."""

        with self._lock:
            self._initialize()
            items: list[dict[str, Any]] = []
            errors: list[dict[str, Any]] = []
            for path in self.runtime_root.iterdir():
                try:
                    assert_not_reparse(path)
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
        assert_not_reparse(manifest_path)
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
        write_json_atomic(runtime_dir / RUNTIME_MANIFEST_NAME, manifest)

    def _augment_manifest(
        self,
        manifest: dict[str, Any],
        *,
        verify_python: bool = False,
        include_size: bool = True,
    ) -> dict[str, Any]:
        payload = copy.deepcopy(manifest)
        try:
            runtime_id = str(payload["runtimeId"])
            runtime_path = self._runtime_dir(runtime_id)
            assert_not_reparse(runtime_path)
            runtime_dir = runtime_path.resolve()
            environment_relative = Path(str(payload["environmentRelativePath"]))
            python_relative = Path(str(payload["pythonRelativePath"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise _MaaFWRuntimeEntryStaleError(
                "runtime manifest is missing required environment paths"
            ) from exc
        environment_candidate = runtime_dir / environment_relative
        python_candidate = runtime_dir / python_relative
        assert_existing_chain_has_no_reparse(environment_candidate)
        assert_existing_chain_has_no_reparse(python_candidate)
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
        now = utc_now()
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
        if include_size:
            # 整棵目录 stat 一遍，几千个文件；只想知道「能不能用」的调用方跳过它。
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
        assert_existing_chain_has_no_reparse(candidate)
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
        assert_not_reparse(manifest_path)
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
            if expires_at is None or parse_time(expires_at) > now:
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
                or parse_time(payload.get("expiresAt")) > now
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
        assert_not_reparse(path)
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
        assert_not_reparse(path)
        if not path.is_dir():
            raise MaaFWRuntimePoolError(f"managed runtime must be a directory: {path}")
        resolved = path.resolve()
        if (
            resolved.parent != self.runtime_root.resolve()
            or resolved.name != runtime_id
        ):
            raise MaaFWRuntimePoolError(f"runtime path escapes managed pool: {path}")
        manifest_path = resolved / RUNTIME_MANIFEST_NAME
        assert_not_reparse(manifest_path)
        if require_manifest and not manifest_path.is_file():
            raise MaaFWRuntimePoolError(
                f"managed runtime has no manifest: {runtime_id}"
            )


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
        assert_not_reparse(child)
        if child.name not in known_names or not child.is_dir():
            return False
    return True


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left.resolve(strict=False))) == os.path.normcase(
        str(Path(os.path.abspath(right)).resolve(strict=False))
    )


def _validate_runtime_id(runtime_id: str) -> None:
    if not RUNTIME_ID_RE.fullmatch(str(runtime_id or "")):
        raise MaaFWRuntimePoolError(f"invalid managed runtime id: {runtime_id}")


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
            parse_time(expires_at)
        except ValueError as exc:
            raise MaaFWRuntimePoolError(
                "runtime manifest lease expiry is invalid"
            ) from exc


def _version_set(values: Iterable[str]) -> set[str]:
    return {key for key in (_normalize_maafw_version(item) for item in values) if key}


def _tag_version(tag: str) -> str | None:
    """``v5.14.0-beta.1`` → ``5.14.0b1``；不是 tag 形状返回 None。"""

    text = str(tag or "").strip()
    if not text.lower().startswith("v"):
        return None
    try:
        # packaging 认 ``5.14.0-beta.1`` 这种写法，直接给 ``5.14.0b1``
        return str(Version(text[1:]))
    except InvalidVersion:
        return None


def _maafw_requirement_key(value: Any) -> str:
    """把 maafw requirement 归成与 manifest ``maafwRequirement`` 相同的规范形式。

    manifest 里存的是 ``canonicalize_requirements`` 的产物；宿主传来的是
    ``_normalize_maafw_requirement`` 的产物（``str(Requirement)``，如
    ``maafw==5.13.0``）。两边都再过一次同一个规范化器才能比。不是 maafw 的、
    解析不了的给空串。
    """

    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return find_maafw_requirement([text]) or ""
    except Exception:  # noqa: BLE001 - 坏 requirement 只影响它自己那条
        return ""


def _normalize_maafw_version(value: Any) -> str:
    """把 manifest / 宿主传来的 maafw 版本规范成 PEP 440 字符串；空值给空串。

    manifest 里的 ``maafwVersion`` 来自 ``importlib.metadata``（已规范），宿主那边
    来自 DLL 探测（``5.14.0-beta.1`` → ``5.14.0b1``）；两边都过一遍 ``Version`` 才能
    比。解析不了的原样小写返回，至少同一坏值能互相对上。
    """

    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return str(Version(text))
    except InvalidVersion:
        return text.lower()


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


def _directory_footprint(path: Path) -> tuple[int, int]:
    """``(独占字节, 与别处共用的字节)``，按硬链接数分。

    池里的 venv 是 uv 从 ``cache/uv`` 硬链接出来的：删掉目录时只剩这一个链接
    （``st_nlink == 1``）的文件才真的腾出磁盘，还挂在缓存（或另一份旧 venv）上的
    要等 ``uv cache clean`` 才释放，回收日志里两笔要分开报。只有 ``os.stat`` 会填
    ``st_nlink``（Windows 上 ``DirEntry.stat()`` 恒为 0），别换成 scandir 的结果。
    """

    exclusive = 0
    shared = 0
    for directory, directory_names, file_names in os.walk(path):
        directory_path = Path(directory)
        directory_names[:] = [
            name for name in directory_names if not (directory_path / name).is_symlink()
        ]
        for name in file_names:
            file_path = directory_path / name
            try:
                if file_path.is_symlink():
                    continue
                stat = file_path.stat()
            except OSError:
                continue
            if stat.st_nlink > 1:
                shared += stat.st_size
            else:
                exclusive += stat.st_size
    return exclusive, shared


def _directory_size(path: Path) -> int:
    return sum(_directory_footprint(path))
