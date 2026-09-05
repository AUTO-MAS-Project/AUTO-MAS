from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from .cache import prune_uv_cache
from .identity import build_runtime_id, canonicalize_requirements
from .installer import host_bootstrap_python_request, install_python_runtime
from .pool import (
    MaaFWRuntimePool,
    MaaFWRuntimePoolError,
    RuntimeCachePruner,
    RuntimeInstaller,
)


class MaaFWRuntimePoolService:
    """JSON-friendly `maafw.runtime_pool.v1` service."""

    def __init__(
        self,
        pool_root: str | Path | None = None,
        *,
        installer: RuntimeInstaller | None = install_python_runtime,
        cache_pruner: RuntimeCachePruner | None = prune_uv_cache,
    ) -> None:
        root = pool_root or (Path.cwd() / "config" / "maafw_runtime_pool")
        self.pool = MaaFWRuntimePool(
            root,
            installer=installer,
            cache_pruner=cache_pruner,
        )

    @property
    def root_identity(self) -> dict[str, Any]:
        return self.pool.root_identity

    @property
    def rootIdentity(self) -> dict[str, Any]:  # noqa: N802 - public JSON contract
        return self.root_identity

    def storage_info(self) -> dict[str, Any]:
        return self.pool.storage_info()

    def list(self) -> list[dict[str, Any]]:
        return self.pool.list()

    def list_runtimes(self) -> list[dict[str, Any]]:
        return self.list()

    def inventory(self) -> dict[str, Any]:
        return self.pool.inventory()

    def resolve(
        self,
        requirements: Iterable[str],
        *,
        touch: bool = False,
        python_identity: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        return self.pool.resolve(
            requirements,
            touch=touch,
            python_identity=python_identity,
        )

    def ensure(
        self,
        requirements: Iterable[str],
        *,
        metadata: Mapping[str, Any] | None = None,
        python_identity: Mapping[str, Any] | None = None,
        bootstrap_python: str | Path | None = None,
    ) -> dict[str, Any]:
        return self.pool.ensure(
            requirements,
            metadata=metadata,
            python_identity=python_identity,
            bootstrap_python=bootstrap_python,
        )

    def resolve_runtime(
        self,
        request: str | Mapping[str, Any],
    ) -> dict[str, Any] | None:
        if isinstance(request, Mapping):
            runtime_id = str(request.get("runtimeId") or "").strip()
            if runtime_id:
                resolved = self.pool.get(
                    runtime_id,
                    touch=False,
                )
                if resolved is None:
                    return None
                if _request_contains_selector(request):
                    requirements, _, _, python_request = _normalize_runtime_request(
                        request
                    )
                    if not _runtime_matches_request(
                        resolved,
                        requirements=(
                            requirements
                            if _request_contains_requirements(request)
                            else None
                        ),
                        python_request=python_request,
                    ):
                        return None
                if bool(request.get("touch", False)):
                    return self.pool.touch(runtime_id)
                return resolved
        requirements, _, touch, python_request = _normalize_runtime_request(request)
        if python_request is None:
            # 宿主是 embeddable 时不能拿它建 venv，改按同小版本走池内托管解释器。
            python_request = host_bootstrap_python_request()
        if python_request is None:
            return self.resolve(requirements, touch=touch)
        target = self.pool.resolve_python(python_request, allow_install=False)
        if target is None:
            return None
        return self.resolve(
            requirements,
            touch=touch,
            python_identity=target["identity"],
        )

    def ensure_runtime(
        self,
        request: str | Mapping[str, Any],
    ) -> dict[str, Any]:
        requested_runtime_id = ""
        if isinstance(request, Mapping):
            requested_runtime_id = str(request.get("runtimeId") or "").strip()
            if requested_runtime_id:
                existing = self.pool.get(
                    requested_runtime_id,
                    touch=False,
                )
                if existing is not None:
                    if _request_contains_selector(request):
                        requirements, _, _, python_request = _normalize_runtime_request(
                            request
                        )
                        if not _runtime_matches_request(
                            existing,
                            requirements=(
                                requirements
                                if _request_contains_requirements(request)
                                else None
                            ),
                            python_request=python_request,
                        ):
                            raise MaaFWRuntimePoolError(
                                "requested runtimeId does not match the runtime manifest"
                            )
                    if bool(request.get("touch", False)):
                        return self.pool.touch(requested_runtime_id)
                    return existing
                if not _request_contains_requirements(request):
                    raise MaaFWRuntimePoolError(
                        "cannot ensure an unknown runtimeId without requirements"
                    )
        requirements, metadata, _, python_request = _normalize_runtime_request(request)
        if python_request is None:
            python_request = host_bootstrap_python_request()
        if python_request is None:
            python_identity = None
            bootstrap_python = None
        else:
            target = self.pool.resolve_python(python_request, allow_install=True)
            if target is None:  # pragma: no cover - allow_install is fail-closed
                raise MaaFWRuntimePoolError(
                    "MaaFW runtime Python could not be prepared"
                )
            python_identity = target["identity"]
            bootstrap_python = target["executable"]
        computed_runtime_id = build_runtime_id(
            requirements,
            python_identity=python_identity,
        )
        if requested_runtime_id and computed_runtime_id != requested_runtime_id:
            raise MaaFWRuntimePoolError(
                "requested runtimeId does not match the requirement selector: "
                f"requested={requested_runtime_id}, "
                f"computed={computed_runtime_id}"
            )
        return self.ensure(
            requirements,
            metadata=metadata,
            python_identity=python_identity,
            bootstrap_python=bootstrap_python,
        )

    def touch(
        self,
        runtime_id: str,
        *,
        at: str | datetime | None = None,
    ) -> dict[str, Any]:
        return self.pool.touch(runtime_id, at=at)

    def pin(self, runtime_id: str, pinned: bool = True) -> dict[str, Any]:
        return self.pool.pin(runtime_id, pinned)

    def add_reference(self, runtime_id: str, reference: str) -> dict[str, Any]:
        return self.pool.add_reference(runtime_id, reference)

    def remove_reference(self, runtime_id: str, reference: str) -> dict[str, Any]:
        return self.pool.remove_reference(runtime_id, reference)

    def set_references(
        self,
        runtime_id: str,
        references: Iterable[str],
    ) -> dict[str, Any]:
        return self.pool.set_references(runtime_id, references)

    def reconcile_references(
        self,
        runtime_id: str,
        references: Iterable[str],
    ) -> dict[str, Any]:
        return self.set_references(runtime_id, references)

    def acquire_lease(
        self,
        runtime_id: str,
        lease_id: str,
        *,
        owner: str = "",
        ttl_seconds: float | None = None,
    ) -> dict[str, Any]:
        return self.pool.acquire_lease(
            runtime_id,
            lease_id,
            owner=owner,
            ttl_seconds=ttl_seconds,
        )

    def release_lease(self, runtime_id: str, lease_id: str) -> dict[str, Any]:
        return self.pool.release_lease(runtime_id, lease_id)

    def delete(self, runtime_id: str) -> dict[str, Any]:
        return self.pool.delete(runtime_id)

    def gc(
        self,
        *,
        dry_run: bool = True,
        grace_seconds: float = 7 * 24 * 60 * 60,
        keep_latest: int = 1,
        now: str | datetime | None = None,
    ) -> dict[str, Any]:
        return self.pool.gc(
            dry_run=dry_run,
            grace_seconds=grace_seconds,
            keep_latest=keep_latest,
            now=now,
        )

    def collect_garbage(
        self,
        *,
        dry_run: bool = True,
        grace_seconds: float = 7 * 24 * 60 * 60,
        keep_latest: int = 1,
        now: str | datetime | None = None,
    ) -> dict[str, Any]:
        return self.gc(
            dry_run=dry_run,
            grace_seconds=grace_seconds,
            keep_latest=keep_latest,
            now=now,
        )


def _normalize_runtime_request(
    request: str | Mapping[str, Any],
) -> tuple[list[str], dict[str, Any], bool, dict[str, str] | None]:
    if isinstance(request, str):
        value = request.strip()
        if not value:
            raise ValueError("runtime requirement cannot be empty")
        return [value], {}, False, None
    if not isinstance(request, Mapping):
        raise TypeError("runtime request must be a requirement string or mapping")

    raw_requirements = request.get("requirements", request.get("packages"))
    if raw_requirements is None:
        raw_requirement = request.get(
            "maafwRequirement",
            request.get("requirement"),
        )
        raw_requirements = [raw_requirement] if isinstance(raw_requirement, str) else []
    if isinstance(raw_requirements, str):
        requirements = [raw_requirements]
    elif isinstance(raw_requirements, Mapping):
        raise TypeError("runtime request requirements must be a string or list")
    elif isinstance(raw_requirements, Iterable) and not isinstance(
        raw_requirements,
        (bytes, bytearray),
    ):
        requirements = list(raw_requirements)
        if not all(isinstance(item, str) for item in requirements):
            raise TypeError("runtime request requirements must contain strings")
    else:
        raise TypeError("runtime request requirements must be a string or list")

    metadata_value = request.get("metadata")
    metadata = dict(metadata_value) if isinstance(metadata_value, Mapping) else {}
    return (
        requirements,
        metadata,
        bool(request.get("touch", False)),
        _normalize_python_request(request.get("python")),
    )


def _request_contains_requirements(request: Mapping[str, Any]) -> bool:
    return any(
        key in request
        for key in (
            "requirements",
            "packages",
            "maafwRequirement",
            "requirement",
        )
    )


def _request_contains_selector(request: Mapping[str, Any]) -> bool:
    return _request_contains_requirements(request) or "python" in request


def _normalize_python_request(value: Any) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise TypeError("runtime request python must be an object")
    implementation = str(value.get("implementation") or "cpython").strip().casefold()
    constraint = str(value.get("constraint") or "").strip()
    if not constraint:
        raise ValueError("runtime request python.constraint cannot be empty")
    if constraint.replace(".", "").isdigit() and constraint.count(".") == 1:
        constraint = f"=={constraint}.*"
    try:
        SpecifierSet(constraint)
    except InvalidSpecifier as exc:
        raise ValueError(
            f"runtime request python.constraint is invalid: {constraint}"
        ) from exc
    return {
        "implementation": implementation,
        "constraint": constraint,
    }


def _runtime_matches_request(
    runtime: Mapping[str, Any],
    *,
    requirements: Iterable[str] | None,
    python_request: Mapping[str, str] | None,
) -> bool:
    if requirements is not None:
        expected_requirements = list(canonicalize_requirements(requirements))
        actual_requirements = runtime.get(
            "selectorRequirements",
            runtime.get("requirements"),
        )
        if list(actual_requirements or []) != expected_requirements:
            return False
    if python_request is None:
        return True
    identity = runtime.get("identity")
    if not isinstance(identity, Mapping):
        return False
    implementation = str(identity.get("pythonAbi") or "").split(":", 1)[0]
    if implementation.casefold() != python_request["implementation"].casefold():
        return False
    try:
        version = Version(str(identity.get("pythonVersion") or ""))
    except InvalidVersion:
        return False
    return SpecifierSet(python_request["constraint"]).contains(
        version,
        prereleases=True,
    )
