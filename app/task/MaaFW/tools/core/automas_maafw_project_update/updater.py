from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import os
import re
import shutil
import stat
import uuid
import zipfile
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import quote, urljoin, urlsplit

import aiofiles
import httpx
from ..automas_maafw_interface.models import MaaFWInterface
from packaging import version

from .apply import UpdateApplyError, apply_package_transaction
from .contracts import artifact_id_for, normalise_sha256, project_fingerprint
from .state import (
    DEFAULT_CACHE_ROOT,
    DEFAULT_OPERATION_ROOT,
    DEFAULT_PLAN_ROOT,
    UpdateOperationStore,
    UpdatePlanStore,
)
from .transport import (
    DownloadCancelled,
    DownloadPaused,
    download_resumable,
)


UPDATE_WORK_DIR = ".mas-update"
DOWNLOAD_FILE_NAME = "download.zip"
DOWNLOAD_TEMP_NAME = "download.tmp"
DOWNLOAD_RETRY_TIMES = 3
DOWNLOAD_RETRY_DELAY_SECONDS = 1.0
DOWNLOAD_TIMEOUT_SECONDS = 300
DOWNLOAD_MAX_BYTES = 4 * 1024 * 1024 * 1024
DOWNLOAD_REDIRECT_LIMIT = 10
DOWNLOAD_CHUNK_SIZE = 64 * 1024
DOWNLOAD_ERROR_HINT_BYTES = 4096
DOWNLOAD_PROGRESS_INTERVAL_SECONDS = 0.2
DOWNLOAD_PROGRESS_PERCENT_STEP = 1.0
DOWNLOAD_PROGRESS_UNKNOWN_INTERVAL_SECONDS = 0.25
DOWNLOAD_PROGRESS_UNKNOWN_BYTES_STEP = 1024 * 1024
HTTP_HEADERS = {"User-Agent": "AutoMasGui"}

ProgressCallback = Callable[[dict[str, Any]], None]

MIRROR_ERROR_INFO = {
    1001: "MirrorChyan URL parameters are invalid",
    7001: "MirrorChyan CDK is expired",
    7002: "MirrorChyan CDK is invalid",
    7003: "MirrorChyan CDK download limit reached today",
    7004: "MirrorChyan CDK type does not match the resource",
    7005: "MirrorChyan CDK has been banned",
    8001: "MirrorChyan resource is not available for this platform",
    8002: "MirrorChyan OS parameter is invalid",
    8003: "MirrorChyan arch parameter is invalid",
    8004: "MirrorChyan channel parameter is invalid",
    1: "MirrorChyan returned unknown error",
}


@dataclass
class MaaFWUpdateProviderInfo:
    name: str
    label: str
    description: str = ""


@dataclass
class MaaFWProjectUpdateCandidate:
    source: str
    version: str
    download_url: str | None = None
    sha256: str | None = None
    artifact_id: str | None = None
    package_type: str | None = None
    from_version: str | None = None
    to_version: str | None = None
    size: int | None = None
    etag: str | None = None
    last_modified: str | None = None
    range_supported: bool | None = None
    plan_id: str | None = None
    project_fingerprint: str | None = None

    @property
    def installable(self) -> bool:
        """Return whether this candidate has an actionable package URL."""

        return bool(str(self.download_url or "").strip())


@dataclass
class MaaFWDownloadedProjectPackage:
    """A validated project archive downloaded without applying it in place."""

    source: str
    version: str
    path: str
    size: int
    sha256: str
    artifact_id: str | None = None
    resumed_from: int = 0
    total_bytes: int | None = None
    etag: str | None = None
    last_modified: str | None = None
    range_supported: bool | None = None
    operation_id: str | None = None
    plan_id: str | None = None


@dataclass
class MaaFWProjectUpdateDiscovery:
    """A newer version discovered by a provider.

    ``source`` identifies the metadata authority.  When a different package
    transport is selected, ``candidate.source`` carries that package source.
    Version discovery and package installation are separate provider
    capabilities. ``candidate`` is populated only when the provider returned
    an actionable download URL; callers must not treat a discovery without a
    candidate as installable.
    """

    source: str
    version: str
    candidate: MaaFWProjectUpdateCandidate | None = None
    unavailable_reason: str = ""
    plan_id: str | None = None
    project_fingerprint: str | None = None

    @property
    def installable(self) -> bool:
        return self.candidate is not None and self.candidate.installable


@dataclass
class MaaFWProjectUpdateResult:
    checked: bool
    updated: bool
    current_version: str
    latest_version: str | None = None
    source: str | None = None
    message: str = ""
    update_available: bool = False
    installable: bool = False
    operation_id: str | None = None
    plan_id: str | None = None
    project_fingerprint: str | None = None
    package_type: str | None = None
    resumed_from: int = 0


class MaaFWProjectUpdateError(RuntimeError):
    """Raised when a MaaFW project package cannot be checked or applied."""

    def __init__(
        self,
        message: str,
        *,
        provider_error_code: int | None = None,
        unsafe_to_continue: bool = False,
    ) -> None:
        super().__init__(message)
        self.provider_error_code = provider_error_code
        self.unsafe_to_continue = unsafe_to_continue


class _MaaFWProjectDownloadError(MaaFWProjectUpdateError):
    """Carry a stable outer-workflow progress status without emitting a terminal."""

    def __init__(self, message: str, *, progress_status: str = "") -> None:
        super().__init__(message)
        self.progress_status = progress_status


def _normalise_package_source(raw_value: Any) -> str:
    """Normalize the user-selected package source without changing metadata ownership."""

    value = str(raw_value or "").strip().casefold().replace("_", " ")
    if not value:
        return "mirrorchyan"
    if value in {"mirrorchyan", "mirror chyan", "mirror酱"}:
        return "mirrorchyan"
    if value in {"github", "github release", "github releases"}:
        return "github_release"
    raise MaaFWProjectUpdateError(
        f"unsupported MaaFW update package source: {raw_value}"
    )


def list_update_providers() -> list[MaaFWUpdateProviderInfo]:
    return [
        MaaFWUpdateProviderInfo(
            name="mirrorchyan",
            label="MirrorChyan",
            description=(
                "Authoritative version/channel metadata; MirrorChyan package source."
            ),
        ),
        MaaFWUpdateProviderInfo(
            name="github_release",
            label="GitHub Release",
            description=(
                "Package source only; fetch the exact version selected by MirrorChyan."
            ),
        ),
    ]


def _report_progress(
    callback: ProgressCallback | None,
    stage: str,
    **payload: Any,
) -> None:
    """Publish best-effort JSON-friendly progress without affecting updates."""

    if callback is None:
        return
    event = {"stage": stage, **payload}
    try:
        callback(event)
    except Exception:
        # Progress is observational. A disconnected UI must never corrupt or
        # abort a download/apply transaction.
        return


@dataclass
class _DownloadProgressThrottle:
    callback: ProgressCallback | None
    total_bytes: int | None
    clock: Callable[[], float]
    last_time: float | None = None
    last_bytes: int = 0
    last_percent: float | None = None

    def report(self, downloaded_bytes: int, *, force: bool = False) -> None:
        now = self.clock()
        percent = (
            min(100.0, downloaded_bytes * 100.0 / self.total_bytes)
            if self.total_bytes
            else None
        )
        if force and self.last_time is not None and downloaded_bytes == self.last_bytes:
            return
        should_emit = force or self.last_time is None
        if not should_emit and self.last_time is not None:
            elapsed = now - self.last_time
            if self.total_bytes:
                percent_delta = percent - (self.last_percent or 0.0)
                should_emit = (
                    elapsed >= DOWNLOAD_PROGRESS_INTERVAL_SECONDS
                    or percent_delta >= DOWNLOAD_PROGRESS_PERCENT_STEP
                )
            else:
                should_emit = (
                    elapsed >= DOWNLOAD_PROGRESS_UNKNOWN_INTERVAL_SECONDS
                    or downloaded_bytes - self.last_bytes
                    >= DOWNLOAD_PROGRESS_UNKNOWN_BYTES_STEP
                )
        if not should_emit:
            return

        self.last_time = now
        self.last_bytes = downloaded_bytes
        self.last_percent = percent
        _report_progress(
            self.callback,
            "downloading",
            downloaded_bytes=downloaded_bytes,
            total_bytes=self.total_bytes,
            percent=percent,
        )


async def update_maafw_project_if_needed(
    project_path: Path,
    interface_model: MaaFWInterface,
    *,
    mirror_cdk: str = "",
    channel: str = "stable",
    proxy: httpx.Proxy | None = None,
    send_log: Callable[[str], None] | None = None,
    source_config: dict[str, Any] | None = None,
    progress: ProgressCallback | None = None,
    post_validate: Callable[[Path], Any] | None = None,
    project_lock_already_held: bool = False,
) -> MaaFWProjectUpdateResult:
    send_update_log = send_log or (lambda _: None)
    current_version = interface_model.version or ""
    current_fingerprint = await asyncio.to_thread(project_fingerprint, project_path)
    update_channel = channel or "stable"

    if not current_version:
        message = "interface does not declare version, skip MaaFW project update"
        send_update_log(message)
        _report_progress(
            progress,
            "completed",
            status="version_missing",
            message=message,
            final=True,
        )
        return MaaFWProjectUpdateResult(
            checked=False,
            updated=False,
            current_version=current_version,
            message=message,
        )

    send_update_log("start checking MaaFW project update")
    send_update_log(f"current version: {current_version}")
    send_update_log(f"update channel: {update_channel}")

    merged_source_config = dict(source_config or {})
    configured_cdk = str(
        merged_source_config.get("mirror_cdk")
        or merged_source_config.get("cdk")
        or ""
    ).strip()
    inherited_cdk = str(mirror_cdk or "").strip()
    if not configured_cdk and inherited_cdk:
        # Script-local blank means "inherit the host CDK".  ``setdefault``
        # cannot express this because the schema deliberately serializes an
        # empty local value.
        merged_source_config["mirror_cdk"] = inherited_cdk
    if not str(merged_source_config.get("channel") or "").strip():
        merged_source_config["channel"] = update_channel
    if not str(merged_source_config.get("project_shell_hint") or "").strip():
        project_shell_hint = await asyncio.to_thread(
            detect_maafw_project_shell_hint,
            project_path,
        )
        if project_shell_hint:
            merged_source_config["project_shell_hint"] = project_shell_hint
    package_source = _normalise_package_source(
        merged_source_config.get("package_source")
        or merged_source_config.get("packageSource")
        or merged_source_config.get("source")
    )
    _report_progress(progress, "checking", message="checking for project updates")
    try:
        discovery = await discover_maafw_project_update(
            interface_model,
            current_version=current_version,
            source_config=merged_source_config,
            proxy=proxy,
            send_log=send_update_log,
        )
    except Exception as exc:
        message = f"MaaFW project update failed: {_sanitize_log_message(str(exc))}"
        send_update_log(message)
        _report_progress(
            progress,
            "failed",
            status="check_failed",
            message=message,
            final=True,
        )
        raise

    if discovery is None:
        message = f"MaaFW project is up to date: {current_version}"
        send_update_log(message)
        _report_progress(
            progress,
            "completed",
            status="no_update",
            message=message,
            final=True,
        )
        return MaaFWProjectUpdateResult(
            checked=True,
            updated=False,
            current_version=current_version,
            message=message,
        )

    _report_progress(
        progress,
        "checking",
        status="version_discovered",
        version=discovery.version,
        metadata_source=discovery.source,
        package_source=(
            discovery.candidate.source
            if discovery.candidate is not None
            else package_source
        ),
    )

    if not discovery.installable:
        reason = (
            discovery.unavailable_reason
            or f"{discovery.source} did not return an installable download URL"
        )
        message = (
            f"found MaaFW project update {current_version} -> {discovery.version} "
            f"({package_source}), but it is not installable: {reason}"
        )
        send_update_log(message)
        _report_progress(
            progress,
            "completed",
            status="no_installable_candidate",
            message=message,
            final=True,
        )
        return MaaFWProjectUpdateResult(
            checked=True,
            updated=False,
            current_version=current_version,
            update_available=True,
            installable=False,
            latest_version=discovery.version,
            source=package_source,
            message=message,
        )

    candidate = discovery.candidate
    if candidate is None:
        message = "update discovery is marked installable but has no candidate"
        _report_progress(
            progress,
            "failed",
            status="invalid_candidate",
            message=message,
            final=True,
        )
        raise MaaFWProjectUpdateError(message)

    send_update_log(
        f"found MaaFW project update: {current_version} -> {candidate.version} ({candidate.source})"
    )
    if not candidate.project_fingerprint:
        candidate.project_fingerprint = current_fingerprint
    if not candidate.plan_id:
        candidate.plan_id = uuid.uuid4().hex
    try:
        apply_result = await apply_maafw_project_update(
            project_path.resolve(),
            candidate,
            proxy=proxy,
            send_log=send_update_log,
            progress=progress,
            post_validate=post_validate,
            project_lock_already_held=project_lock_already_held,
        )
    except Exception as exc:
        detail = _sanitize_log_message(str(exc))
        message = (
            detail
            if detail.startswith("MaaFW project update failed:")
            else f"MaaFW project update failed: {detail}"
        )
        if message != detail:
            send_update_log(message)
        status = (
            getattr(exc, "progress_status", "")
            if isinstance(exc, MaaFWProjectUpdateError)
            else "apply_failed"
        ) or "apply_failed"
        _report_progress(
            progress,
            "failed",
            status=status,
            message=message,
            final=True,
        )
        raise

    message = f"MaaFW project update applied: {candidate.version}"
    send_update_log(message)
    _report_progress(
        progress,
        "completed",
        status="updated",
        message=message,
        final=True,
    )
    return MaaFWProjectUpdateResult(
        checked=True,
        updated=True,
        current_version=current_version,
        update_available=True,
        installable=True,
        latest_version=candidate.version,
        source=candidate.source,
        message=message,
        operation_id=str(apply_result.get("operationId") or "") or None,
        plan_id=str(apply_result.get("planId") or candidate.plan_id or "") or None,
        project_fingerprint=str(apply_result.get("finalFingerprint") or "") or None,
        package_type=str(apply_result.get("packageType") or candidate.package_type or "") or None,
        resumed_from=int(apply_result.get("resumedFrom") or 0),
    )


async def discover_maafw_project_update(
    interface_model: MaaFWInterface,
    *,
    current_version: str | None = None,
    source_config: dict[str, Any] | None = None,
    proxy: httpx.Proxy | None = None,
    send_log: Callable[[str], None] | None = None,
) -> MaaFWProjectUpdateDiscovery | None:
    config = dict(source_config or {})
    package_source = _normalise_package_source(
        config.get("package_source")
        or config.get("packageSource")
        or config.get("source")
    )
    current = current_version if current_version is not None else (interface_model.version or "")
    send_update_log = send_log or (lambda _: None)

    # MirrorChyan is the single version/channel authority.  The selected
    # package source only decides where the exact MirrorChyan target is
    # downloaded from; it must never switch version discovery to GitHub's
    # moving ``latest`` endpoint.
    if not interface_model.mirrorchyan_rid:
        send_update_log("MirrorChyan RID is not configured, skip update")
        return None

    mirror_cdk = str(config.get("mirror_cdk") or config.get("cdk") or "").strip()
    send_update_log(f"MirrorChyan RID: {interface_model.mirrorchyan_rid}")
    if interface_model.mirrorchyan_multiplatform:
        send_update_log("MirrorChyan platform: win/x64")
    if package_source == "mirrorchyan" and not mirror_cdk:
        send_update_log(
            "MirrorChyan CDK 未配置，仅检查版本；安装更新需要项目或全局 CDK"
        )

    mirror_discovery = await _check_mirrorchyan_update(
        interface_model,
        current_version=current,
        mirror_cdk=mirror_cdk,
        channel=str(config.get("channel") or "stable"),
        proxy=proxy,
    )
    if mirror_discovery is None:
        return None

    send_update_log(
        "version metadata source: MirrorChyan; "
        f"latest={mirror_discovery.version}"
    )
    if package_source == "mirrorchyan":
        if not mirror_cdk and mirror_discovery.installable:
            # A provider response must never turn a metadata-only check into
            # an unauthenticated install.  Keep the discovered version
            # visible, but require a project or host CDK before exposing an
            # installable candidate.
            mirror_discovery = MaaFWProjectUpdateDiscovery(
                source=mirror_discovery.source,
                version=mirror_discovery.version,
                unavailable_reason="MirrorChyan CDK is required to install this update",
            )
        if mirror_discovery.installable:
            send_update_log(
                "install package source: MirrorChyan; "
                f"version={mirror_discovery.version}"
            )
        return mirror_discovery

    # GitHub is a package transport only.  Resolve the exact version selected
    # by MirrorChyan, ignoring a configured GitHub tag that could otherwise
    # override the authoritative target.
    github_discovery = await _check_github_release_update(
        interface_model,
        current_version=current,
        source_config=config,
        proxy=proxy,
        target_version=mirror_discovery.version,
    )
    if github_discovery is None:
        return MaaFWProjectUpdateDiscovery(
            source="mirrorchyan",
            version=mirror_discovery.version,
            unavailable_reason=(
                "GitHub has no release matching the MirrorChyan target version"
            ),
        )

    if github_discovery.candidate is not None:
        # Keep the target identity from MirrorChyan even when GitHub spells
        # the matching tag with a conventional leading ``v``.
        github_discovery.candidate.version = mirror_discovery.version
        github_discovery.candidate.to_version = mirror_discovery.version
        send_update_log(
            "install package source: GitHub Release; "
            f"version={mirror_discovery.version}"
        )

    return MaaFWProjectUpdateDiscovery(
        source="mirrorchyan",
        version=mirror_discovery.version,
        candidate=github_discovery.candidate,
        unavailable_reason=github_discovery.unavailable_reason,
    )


def persist_maafw_update_plan(
    project_path: Path,
    interface_model: MaaFWInterface,
    discovery: MaaFWProjectUpdateDiscovery,
    *,
    source_config: Mapping[str, Any] | None = None,
    expected_fingerprint: str | None = None,
    script_id: str | None = None,
) -> UpdatePlanStore:
    """Persist a URL-free exact update plan after discovery.

    The signed provider URL remains process-local.  Later execution refreshes
    the same release/asset descriptor and rejects a version or artifact
    identity change instead of silently selecting a newer package.
    """

    candidate = discovery.candidate
    if candidate is None or not candidate.installable:
        raise MaaFWProjectUpdateError("cannot create a plan without an installable candidate")
    plan_id = uuid.uuid4().hex
    artifact_id = candidate.artifact_id or artifact_id_for(
        candidate.source,
        candidate.to_version or candidate.version,
        candidate.download_url or "",
    )
    candidate.artifact_id = artifact_id
    candidate.plan_id = plan_id
    candidate.project_fingerprint = expected_fingerprint
    config = dict(source_config or {})
    provider = _normalise_package_source(
        config.get("package_source")
        or config.get("packageSource")
        or config.get("source")
        or candidate.source
    )
    interface_descriptor = {
        "interface_version": getattr(interface_model, "interface_version", 2),
        "name": getattr(interface_model, "name", ""),
        "github": getattr(interface_model, "github", None),
        "mirrorchyan_rid": getattr(interface_model, "mirrorchyan_rid", None),
        "mirrorchyan_multiplatform": getattr(
            interface_model,
            "mirrorchyan_multiplatform",
            False,
        ),
    }
    descriptor = {
        "source": provider,
        "repo": str(config.get("repo") or config.get("github_repo") or "").strip(),
        "tag": str(config.get("tag") or config.get("github_tag") or "").strip(),
        "asset_pattern": str(
            config.get("asset_pattern") or config.get("github_asset_pattern") or ""
        ).strip(),
        "channel": str(config.get("channel") or "stable").strip() or "stable",
        "project_shell_hint": str(config.get("project_shell_hint") or "").strip(),
        "has_mirror_cdk": bool(
            str(config.get("mirror_cdk") or config.get("cdk") or "").strip()
        ),
    }
    return UpdatePlanStore.create(
        root=DEFAULT_PLAN_ROOT,
        plan_id=plan_id,
        projectPath=str(project_path.resolve()),
        projectFingerprint=expected_fingerprint or "",
        scriptId=str(script_id or "").strip(),
        currentVersion=str(getattr(interface_model, "version", "") or ""),
        targetVersion=candidate.to_version or candidate.version,
        source=candidate.source,
        metadataSource="mirrorchyan",
        packageSource=candidate.source,
        channel=str(config.get("channel") or "stable").strip() or "stable",
        artifactId=artifact_id,
        packageType=candidate.package_type or "",
        fromVersion=candidate.from_version or "",
        toVersion=candidate.to_version or candidate.version,
        size=candidate.size,
        etag=candidate.etag,
        lastModified=candidate.last_modified,
        rangeSupported=candidate.range_supported,
        sha256=candidate.sha256,
        providerDescriptor=descriptor,
        interfaceDescriptor=interface_descriptor,
    )


async def resolve_maafw_update_plan_candidate(
    plan: UpdatePlanStore | Mapping[str, Any],
    *,
    mirror_cdk: str = "",
    proxy: httpx.Proxy | None = None,
) -> MaaFWProjectUpdateCandidate:
    """Refresh the exact planned release URL without rediscovering latest."""

    state = plan.read() if isinstance(plan, UpdatePlanStore) else dict(plan)
    plan_id = str(state.get("planId") or "").strip()
    if not plan_id:
        raise MaaFWProjectUpdateError("update plan is missing planId")
    try:
        descriptor = dict(state.get("providerDescriptor") or {})
        interface = MaaFWInterface.model_validate(
            dict(state.get("interfaceDescriptor") or {})
        )
    except Exception as exc:
        raise MaaFWProjectUpdateError("update plan interface/provider descriptor is invalid") from exc
    source = str(state.get("source") or descriptor.get("source") or "").strip().lower()
    target = str(state.get("targetVersion") or state.get("toVersion") or "").strip()
    if not target:
        raise MaaFWProjectUpdateError("update plan is missing target version")
    config: dict[str, Any] = {
        **descriptor,
        "source": source,
        "mirror_cdk": str(mirror_cdk or "").strip(),
    }
    if source == "mirrorchyan":
        discovery = await _check_mirrorchyan_update(
            interface,
            current_version="0.0.0",
            mirror_cdk=str(mirror_cdk or "").strip(),
            channel=str(descriptor.get("channel") or "stable"),
            proxy=proxy,
        )
    elif source in {"github", "github_release"}:
        config["source"] = "github_release"
        discovery = await _check_github_release_update(
            interface,
            current_version="0.0.0",
            source_config=config,
            proxy=proxy,
            target_version=target,
        )
    else:
        raise MaaFWProjectUpdateError(f"unsupported update plan provider: {source}")
    if discovery is None or discovery.candidate is None:
        raise MaaFWProjectUpdateError("planned release is no longer available")
    candidate = discovery.candidate
    if _normalize_version(candidate.version) != _normalize_version(target):
        raise MaaFWProjectUpdateError(
            "planned release changed; create a new update plan"
        )
    planned_artifact = str(state.get("artifactId") or "").strip().lower()
    actual_artifact = candidate.artifact_id or artifact_id_for(
        candidate.source,
        candidate.to_version or candidate.version,
        candidate.download_url or "",
    )
    if planned_artifact and actual_artifact.lower() != planned_artifact:
        raise MaaFWProjectUpdateError(
            "planned package artifact changed; create a new update plan"
        )
    planned_type = str(state.get("packageType") or "").strip().lower()
    if planned_type and candidate.package_type and candidate.package_type != planned_type:
        raise MaaFWProjectUpdateError("planned package type changed")
    candidate.artifact_id = planned_artifact or actual_artifact
    candidate.plan_id = plan_id
    candidate.project_fingerprint = str(state.get("projectFingerprint") or "").strip() or None
    candidate.package_type = planned_type or candidate.package_type
    candidate.from_version = str(state.get("fromVersion") or candidate.from_version or "").strip() or None
    candidate.to_version = str(state.get("toVersion") or target).strip() or target
    return candidate


async def check_maafw_project_update(
    interface_model: MaaFWInterface,
    *,
    current_version: str | None = None,
    source_config: dict[str, Any] | None = None,
    proxy: httpx.Proxy | None = None,
    send_log: Callable[[str], None] | None = None,
) -> MaaFWProjectUpdateCandidate | None:
    """Return only an installable candidate for the legacy check contract.

    Use :func:`discover_maafw_project_update` when the caller must distinguish
    "newer version exists" from "an installable package is available".
    """

    discovery = await discover_maafw_project_update(
        interface_model,
        current_version=current_version,
        source_config=source_config,
        proxy=proxy,
        send_log=send_log,
    )
    if discovery is None:
        return None
    if not discovery.installable or discovery.candidate is None:
        reason = (
            discovery.unavailable_reason
            or f"{discovery.source} did not return an installable download URL"
        )
        raise MaaFWProjectUpdateError(
            f"{discovery.source} discovered version {discovery.version}, "
            f"but no installable update candidate is available: {reason}"
        )
    return discovery.candidate


async def apply_maafw_project_update(
    project_path: Path,
    candidate: MaaFWProjectUpdateCandidate,
    *,
    proxy: httpx.Proxy | None = None,
    send_log: Callable[[str], None] | None = None,
    progress: ProgressCallback | None = None,
    post_validate: Callable[[Path], Any] | None = None,
    script_id: str | None = None,
    project_lock_already_held: bool = False,
) -> dict[str, Any]:
    send_update_log = send_log or (lambda _: None)
    download_url = str(candidate.download_url or "").strip()
    if not download_url:
        raise MaaFWProjectUpdateError("update provider did not return a download URL")

    root = project_path.resolve()
    current = await asyncio.to_thread(project_fingerprint, root)
    if candidate.project_fingerprint and current != candidate.project_fingerprint:
        raise MaaFWProjectUpdateError(
            "MaaFW project changed after update plan; apply rejected"
        )
    effective_plan_id = str(candidate.plan_id or uuid.uuid4().hex)
    candidate.plan_id = effective_plan_id
    operation_id = uuid.uuid4().hex
    operation = UpdateOperationStore.create(
        root=DEFAULT_OPERATION_ROOT,
        operation_id=operation_id,
        projectPath=str(root),
        planId=effective_plan_id,
        expectedFingerprint=candidate.project_fingerprint or current or "",
        source=candidate.source,
        targetVersion=candidate.to_version or candidate.version,
        packageType=candidate.package_type or "",
        scriptId=str(script_id or "").strip(),
    )
    try:
        downloaded = await download_resumable(
            source=candidate.source,
            version=candidate.to_version or candidate.version,
            download_url=download_url,
            expected_sha256=candidate.sha256,
            artifact_id=candidate.artifact_id,
            cache_root=DEFAULT_CACHE_ROOT,
            operation=operation,
            proxy=proxy,
            send_log=send_update_log,
            progress=progress,
        )
        operation.update(
            "downloaded",
            packagePath=str(downloaded.path),
            sha256=downloaded.sha256,
            downloadedBytes=downloaded.size,
            totalBytes=downloaded.total_bytes,
            resumedFromBytes=downloaded.resumed_from,
        )
        result = await asyncio.to_thread(
            apply_package_transaction,
            root,
            downloaded.path,
            operation=operation,
            plan_id=effective_plan_id,
            expected_fingerprint=candidate.project_fingerprint or current,
            expected_package_type=(
                candidate.package_type
                if candidate.package_type in {"full", "delta"}
                else None
            ),
            from_version=candidate.from_version,
            target_version=candidate.to_version or candidate.version,
            post_validate=post_validate,
            project_lock_already_held=project_lock_already_held,
            send_log=send_update_log,
            progress=lambda stage, payload: _report_progress(
                progress,
                stage,
                operation_id=operation.operation_id,
                **payload,
            ),
        )
        result["resumedFrom"] = downloaded.resumed_from
        return result
    except (DownloadPaused, DownloadCancelled):
        raise
    except UpdateApplyError as exc:
        raise MaaFWProjectUpdateError(
            str(exc),
            unsafe_to_continue=exc.unsafe_to_continue,
        ) from exc
    except MaaFWProjectUpdateError:
        raise
    except Exception as exc:
        raise MaaFWProjectUpdateError(str(exc)) from exc


async def download_maafw_project_package(
    download_root: Path,
    candidate: MaaFWProjectUpdateCandidate,
    *,
    proxy: httpx.Proxy | None = None,
    send_log: Callable[[str], None] | None = None,
    max_download_bytes: int = DOWNLOAD_MAX_BYTES,
    progress: ProgressCallback | None = None,
    plan_id: str | None = None,
    expected_fingerprint: str | None = None,
    script_id: str | None = None,
) -> MaaFWDownloadedProjectPackage:
    """Download and validate one candidate without mutating a project tree.

    The archive is published atomically below ``download_root``.  Managed
    consumers can pass the returned path to Project Store, which remains the
    authority for safe extraction and immutable project import.
    """

    source = str(candidate.source or "").strip()
    project_version = str(candidate.version or "").strip()
    download_url = str(candidate.download_url or "").strip()
    if not source or not project_version:
        raise MaaFWProjectUpdateError(
            "update candidate is missing source or version"
        )
    if not download_url:
        raise MaaFWProjectUpdateError("update candidate is missing download URL")
    if max_download_bytes <= 0:
        raise MaaFWProjectUpdateError("download size limit must be positive")

    send_update_log = send_log or (lambda _: None)
    try:
        operation = UpdateOperationStore.create(
            root=DEFAULT_OPERATION_ROOT,
            source=source,
            targetVersion=candidate.to_version or project_version,
            artifactId=candidate.artifact_id or "",
            planId=str(plan_id or candidate.plan_id or ""),
            expectedFingerprint=str(expected_fingerprint or candidate.project_fingerprint or ""),
            scriptId=str(script_id or "").strip(),
        )
        outcome = await download_resumable(
            source=source,
            version=candidate.to_version or project_version,
            download_url=download_url,
            expected_sha256=candidate.sha256,
            artifact_id=candidate.artifact_id,
            cache_root=Path(download_root).resolve(),
            operation=operation,
            proxy=proxy,
            send_log=send_update_log,
            max_bytes=max_download_bytes,
            progress=progress,
        )
        _report_progress(
            progress,
            "downloaded",
            status="downloaded",
            downloaded_bytes=outcome.size,
            total_bytes=outcome.total_bytes or outcome.size,
            resumed_from_bytes=outcome.resumed_from,
            operation_id=operation.operation_id,
            percent=100.0,
        )
    except (DownloadPaused, DownloadCancelled):
        raise
    except Exception as exc:
        if isinstance(exc, MaaFWProjectUpdateError):
            raise
        raise MaaFWProjectUpdateError(str(exc)) from exc
    return MaaFWDownloadedProjectPackage(
        source=source,
        version=project_version,
        path=str(outcome.path),
        size=outcome.size,
        sha256=outcome.sha256,
        artifact_id=outcome.artifact_id,
        resumed_from=outcome.resumed_from,
        total_bytes=outcome.total_bytes,
        etag=outcome.etag,
        last_modified=outcome.last_modified,
        range_supported=outcome.range_supported,
        operation_id=operation.operation_id,
        plan_id=plan_id or candidate.plan_id,
    )


async def release_maafw_project_package(
    download_root: Path,
    package_path: str | Path,
    package_sha256: str,
) -> dict[str, Any]:
    """Release one validated content-addressed download.

    This is deliberately narrower than the updater's internal cleanup helper:
    callers may release only the exact ``<24 hex>/<sha256>.zip`` shape emitted
    by :func:`download_maafw_project_package`.  The operation is idempotent for
    an already-missing package and never recursively removes caller data.
    """

    return await _run_worker_to_completion(
        _release_content_addressed_download,
        Path(download_root),
        Path(package_path),
        package_sha256,
    )


async def _check_mirrorchyan_update(
    interface_model: MaaFWInterface,
    *,
    current_version: str,
    mirror_cdk: str,
    channel: str,
    proxy: httpx.Proxy | None,
) -> MaaFWProjectUpdateDiscovery | None:
    rid = interface_model.mirrorchyan_rid
    if not rid:
        return None

    params: dict[str, str] = {
        "user_agent": "AutoMasGui",
        "current_version": current_version,
        "cdk": mirror_cdk or "",
        "channel": channel or "stable",
    }
    if interface_model.mirrorchyan_multiplatform:
        params["os"] = "win"
        params["arch"] = "x64"

    url = f"https://mirrorchyan.com/api/resources/{rid}/latest"
    try:
        async with httpx.AsyncClient(proxy=proxy, follow_redirects=True, timeout=30.0) as client:
            response = await client.get(url, params=params, headers=HTTP_HEADERS)
    except httpx.HTTPError as exc:
        raise MaaFWProjectUpdateError(
            f"MirrorChyan update check failed: {_sanitize_log_message(str(exc))}"
        ) from None

    result = _load_response_json(response)
    raw_error_code = result.get("code", 0)
    try:
        error_code = int(raw_error_code)
    except (TypeError, ValueError):
        error_code = None
    if response.status_code != 200 or error_code != 0:
        if error_code not in (None, 0):
            error_message = MIRROR_ERROR_INFO.get(
                error_code,
                "MirrorChyan returned an unknown error",
            )
            raise MaaFWProjectUpdateError(
                f"MirrorChyan [{error_code}]: {error_message}",
                provider_error_code=error_code,
            )
        raise MaaFWProjectUpdateError(f"MirrorChyan returned HTTP {response.status_code}")

    data = result.get("data")
    if not isinstance(data, dict):
        raise MaaFWProjectUpdateError("MirrorChyan did not return version data")

    latest_version = str(
        data.get("version_name") or data.get("version") or data.get("name") or ""
    ).strip()
    if not latest_version:
        raise MaaFWProjectUpdateError("MirrorChyan did not return version")
    if not _is_remote_newer(latest_version, current_version):
        return None

    return _build_update_discovery(
        source="mirrorchyan",
        version=latest_version,
        download_url=str(data.get("url") or "").strip() or None,
        sha256=str(data.get("sha256") or "").strip() or None,
        artifact_id=str(data.get("artifact_id") or data.get("artifactId") or "").strip() or None,
        package_type=_package_type_from_metadata(data),
        from_version=_metadata_text(data, "base_version", "baseVersion", "from_version", "fromVersion"),
        to_version=_metadata_text(data, "target_version", "targetVersion", "to_version", "toVersion") or latest_version,
        size=_metadata_int(data, "size", "file_size", "fileSize"),
        etag=_metadata_text(data, "etag", "ETag"),
        last_modified=_metadata_text(data, "last_modified", "lastModified", "Last-Modified"),
        range_supported=_metadata_bool(data, "range", "range_supported", "rangeSupported"),
        unavailable_reason=(
            "MirrorChyan returned newer version metadata without a download URL"
        ),
    )


async def _check_github_release_update(
    interface_model: MaaFWInterface,
    *,
    current_version: str,
    source_config: dict[str, Any],
    proxy: httpx.Proxy | None,
    target_version: str = "",
) -> MaaFWProjectUpdateDiscovery | None:
    repo = _normalize_github_repo(
        str(
            source_config.get("repo")
            or source_config.get("github_repo")
            or interface_model.github
            or ""
        )
    )
    if not repo:
        return None

    tag = str(
        source_config.get("tag") or source_config.get("github_tag") or ""
    ).strip()
    if target_version:
        # MirrorChyan remains the version/channel authority in automatic mode.
        # Resolve that exact release instead of GitHub's stable-only ``latest``
        # endpoint so prereleases and an older same-version package stay
        # reachable.  A stale GitHubTag from a previous explicit-GitHub setup
        # must not override the Mirror-selected version in automatic mode.
        # Only the conventional optional leading ``v`` differs.
        api_urls = [
            f"https://api.github.com/repos/{repo}/releases/tags/{quote(candidate, safe='')}"
            for candidate in _github_tag_candidates(target_version)
        ]
    elif tag:
        api_urls = [
            f"https://api.github.com/repos/{repo}/releases/tags/{quote(tag, safe='')}"
        ]
    else:
        raise MaaFWProjectUpdateError(
            "GitHub release lookup requires an exact target version selected by MirrorChyan"
        )
    token = str(
        source_config.get("token") or source_config.get("github_token") or ""
    ).strip()
    headers = dict(HTTP_HEADERS)
    headers["Accept"] = "application/vnd.github+json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    response: httpx.Response | None = None
    async with httpx.AsyncClient(proxy=proxy, follow_redirects=True, timeout=30.0) as client:
        for api_url in api_urls:
            candidate_response = await client.get(api_url, headers=headers)
            if candidate_response.status_code == 404:
                continue
            response = candidate_response
            break

    if response is None:
        return None
    data = _load_response_json(response)
    if response.status_code >= 400:
        message = str(data.get("message") or "").strip()
        raise MaaFWProjectUpdateError(
            f"GitHub release check failed: HTTP {response.status_code} {message}"
        )

    latest_version = str(data.get("tag_name") or data.get("name") or "").strip()
    if not latest_version:
        raise MaaFWProjectUpdateError("GitHub release did not return version")
    if target_version and _normalize_version(latest_version) != _normalize_version(
        target_version
    ):
        return _build_update_discovery(
            source="github_release",
            version=latest_version,
            download_url=None,
            sha256=None,
            unavailable_reason=(
                "GitHub tag lookup returned a different version: "
                f"github={latest_version}, target={target_version}"
            ),
        )
    if not _is_remote_newer(latest_version, current_version):
        return None
    if target_version and data.get("draft") is True:
        return _build_update_discovery(
            source="github_release",
            version=latest_version,
            download_url=None,
            sha256=None,
            unavailable_reason="GitHub matching release is a draft",
        )

    configured_asset_pattern = str(
        source_config.get("asset_pattern")
        or source_config.get("github_asset_pattern")
        or ""
    ).strip()
    asset_pattern = configured_asset_pattern or r"\.zip$"
    download_url, selection_reason = _select_github_release_asset(
        data,
        asset_pattern,
        project_name=interface_model.name,
        project_shell_hint=str(source_config.get("project_shell_hint") or ""),
        require_explicit_match=bool(configured_asset_pattern),
        prefer_windows_x64=interface_model.mirrorchyan_multiplatform,
    )
    asset = _github_asset_for_url(data, download_url)
    asset_digest = str(asset.get("digest") or "").strip() if asset else ""
    configured_sha256 = str(source_config.get("sha256") or "").strip() or None

    return _build_update_discovery(
        source="github_release",
        version=latest_version,
        download_url=download_url,
        sha256=configured_sha256 or asset_digest or None,
        artifact_id=(
            str(asset.get("id") or "").strip() or None
            if asset
            else None
        ),
        package_type=_package_type_from_metadata(data),
        from_version=_metadata_text(data, "base_version", "baseVersion", "from_version", "fromVersion"),
        to_version=_metadata_text(data, "target_version", "targetVersion", "to_version", "toVersion") or latest_version,
        size=_metadata_int(asset or {}, "size"),
        etag=_metadata_text(asset or {}, "etag", "ETag"),
        last_modified=_metadata_text(asset or {}, "last_modified", "lastModified", "Last-Modified"),
        range_supported=_metadata_bool(asset or {}, "range", "range_supported", "rangeSupported"),
        unavailable_reason=(
            selection_reason
            or "GitHub release has no unambiguous matching package asset"
        ),
    )


def _build_update_discovery(
    *,
    source: str,
    version: str,
    download_url: str | None,
    sha256: str | None,
    unavailable_reason: str,
    artifact_id: str | None = None,
    package_type: str | None = None,
    from_version: str | None = None,
    to_version: str | None = None,
    size: int | None = None,
    etag: str | None = None,
    last_modified: str | None = None,
    range_supported: bool | None = None,
) -> MaaFWProjectUpdateDiscovery:
    normalized_url = str(download_url or "").strip()
    candidate = (
        MaaFWProjectUpdateCandidate(
            source=source,
            version=version,
            download_url=normalized_url,
            sha256=normalise_sha256(sha256),
            artifact_id=artifact_id,
            package_type=package_type if package_type in {"full", "delta"} else None,
            from_version=from_version,
            to_version=to_version or version,
            size=size,
            etag=etag,
            last_modified=last_modified,
            range_supported=range_supported,
        )
        if normalized_url
        else None
    )
    return MaaFWProjectUpdateDiscovery(
        source=source,
        version=version,
        candidate=candidate,
        unavailable_reason="" if candidate is not None else unavailable_reason,
    )


def _metadata_text(data: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = str(data.get(key) or "").strip()
        if value:
            return value
    return None


def _metadata_int(data: Mapping[str, Any], *keys: str) -> int | None:
    for key in keys:
        try:
            value = int(data.get(key))
        except (TypeError, ValueError):
            continue
        if value >= 0:
            return value
    return None


def _metadata_bool(data: Mapping[str, Any], *keys: str) -> bool | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().casefold() in {"true", "yes", "1"}:
            return True
        if isinstance(value, str) and value.strip().casefold() in {"false", "no", "0"}:
            return False
    return None


def _package_type_from_metadata(data: Mapping[str, Any]) -> str | None:
    value = str(
        data.get("package_type")
        or data.get("packageType")
        or data.get("type")
        or ""
    ).strip().lower()
    return value if value in {"full", "delta"} else None


def _github_asset_for_url(data: Mapping[str, Any], url: str | None) -> dict[str, Any] | None:
    if not url or not isinstance(data.get("assets"), list):
        return None
    for asset in data["assets"]:
        if isinstance(asset, dict) and str(asset.get("browser_download_url") or "").strip() == url:
            return asset
    return None


async def _download_update_package(
    project_path: Path,
    download_url: str,
    *,
    expected_sha256: str | None = None,
    proxy: httpx.Proxy | None,
    send_log: Callable[[str], None],
    progress: ProgressCallback | None,
) -> Path:
    update_dir = project_path / UPDATE_WORK_DIR
    temp_path = update_dir / DOWNLOAD_TEMP_NAME
    package_path = update_dir / DOWNLOAD_FILE_NAME
    await asyncio.to_thread(
        _prepare_download_paths,
        update_dir,
        temp_path,
        package_path,
    )

    await _download_candidate_to_paths(
        temp_path,
        package_path,
        download_url,
        expected_sha256=expected_sha256,
        proxy=proxy,
        send_log=send_log,
        max_download_bytes=DOWNLOAD_MAX_BYTES,
        progress=progress,
    )
    return package_path


async def _download_candidate_to_paths(
    temp_path: Path,
    package_path: Path,
    download_url: str,
    *,
    expected_sha256: str | None,
    proxy: httpx.Proxy | None,
    send_log: Callable[[str], None],
    max_download_bytes: int,
    progress: ProgressCallback | None,
) -> int:
    validated_url = _validate_download_url(download_url)

    send_log(
        "start downloading MaaFW update package: "
        f"{_sanitize_log_message(validated_url)}"
    )
    _report_progress(
        progress,
        "downloading",
        downloaded_bytes=0,
        total_bytes=None,
        percent=None,
    )
    last_error: Exception | None = None
    loop = asyncio.get_running_loop()
    deadline = loop.time() + DOWNLOAD_TIMEOUT_SECONDS
    for attempt in range(1, DOWNLOAD_RETRY_TIMES + 1):
        await asyncio.to_thread(_remove_path, temp_path)
        try:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError
            downloaded_bytes, total_bytes = await asyncio.wait_for(
                _stream_update_package(
                    temp_path,
                    validated_url,
                    proxy=proxy,
                    max_download_bytes=max_download_bytes,
                    progress=progress,
                ),
                timeout=remaining,
            )
            _report_progress(
                progress,
                "validating",
                downloaded_bytes=downloaded_bytes,
                total_bytes=total_bytes,
                percent=100.0 if total_bytes else None,
            )
            package_size = await _run_worker_to_completion(
                _validate_and_publish_download,
                temp_path,
                package_path,
                expected_sha256,
            )
            send_log(f"MaaFW update package downloaded: {package_size} bytes")
            return package_size
        except TimeoutError:
            await asyncio.to_thread(_remove_path, temp_path)
            raise _download_timeout_failure(send_log) from None
        except Exception as exc:
            last_error = exc
            await asyncio.to_thread(_remove_path, temp_path)
            if attempt >= DOWNLOAD_RETRY_TIMES:
                break
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise _download_timeout_failure(send_log) from None
            send_log(
                "download failed, retrying "
                f"({attempt}/{DOWNLOAD_RETRY_TIMES}): {_sanitize_log_message(str(exc))}"
            )
            await asyncio.sleep(min(DOWNLOAD_RETRY_DELAY_SECONDS, remaining))
            if loop.time() >= deadline:
                raise _download_timeout_failure(send_log) from None

    detail = _sanitize_log_message(str(last_error))
    if isinstance(last_error, MaaFWProjectUpdateError):
        message = detail
    else:
        message = f"download MaaFW update package failed: {detail}"
    terminal_message = (
        message
        if message.startswith("MaaFW project update failed:")
        else f"MaaFW project update failed: {message}"
    )
    send_log(terminal_message)
    raise _MaaFWProjectDownloadError(
        terminal_message,
        progress_status="download_failed",
    )


def _download_timeout_failure(
    send_log: Callable[[str], None],
) -> MaaFWProjectUpdateError:
    message = (
        "MaaFW project update failed: download timed out after "
        f"{DOWNLOAD_TIMEOUT_SECONDS} seconds"
    )
    send_log(message)
    return _MaaFWProjectDownloadError(
        message,
        progress_status="download_timeout",
    )


def _prepare_download_paths(
    update_dir: Path,
    temp_path: Path,
    package_path: Path,
) -> None:
    update_dir.mkdir(parents=True, exist_ok=True)
    _remove_path(temp_path)
    _remove_path(package_path)


def _validate_and_publish_download(
    temp_path: Path,
    package_path: Path,
    expected_sha256: str | None,
) -> int:
    """Validate a complete archive and atomically publish it off the event loop."""

    _ensure_downloaded_zip(temp_path)
    _ensure_expected_sha256(temp_path, expected_sha256)
    temp_path.replace(package_path)
    return package_path.stat().st_size


async def _stream_update_package(
    temp_path: Path,
    download_url: str,
    *,
    proxy: httpx.Proxy | None,
    max_download_bytes: int = DOWNLOAD_MAX_BYTES,
    progress: ProgressCallback | None = None,
) -> tuple[int, int | None]:
    current_url = _validate_download_url(download_url)
    async with httpx.AsyncClient(
        proxy=proxy,
        follow_redirects=False,
        timeout=30.0,
    ) as client:
        for redirect_count in range(DOWNLOAD_REDIRECT_LIMIT + 1):
            async with client.stream(
                "GET",
                current_url,
                headers=HTTP_HEADERS,
            ) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    location = str(response.headers.get("location") or "").strip()
                    if not location:
                        raise MaaFWProjectUpdateError(
                            "download update package redirect is missing Location"
                        )
                    if redirect_count >= DOWNLOAD_REDIRECT_LIMIT:
                        raise MaaFWProjectUpdateError(
                            "download update package exceeded redirect limit"
                        )
                    current_url = _validate_download_url(
                        urljoin(current_url, location)
                    )
                    continue

                if response.status_code not in (200, 206):
                    error_hint, provider_error_code = await _read_download_error_hint(
                        response
                    )
                    if error_hint:
                        raise MaaFWProjectUpdateError(
                            "download update package failed: "
                            f"HTTP {response.status_code}, {error_hint}",
                            provider_error_code=provider_error_code,
                        )
                    raise MaaFWProjectUpdateError(
                        "download update package failed: "
                        f"HTTP {response.status_code}"
                    )

                _validate_download_url(str(response.url))
                content_length = _content_length(response)
                if (
                    content_length is not None
                    and content_length > max_download_bytes
                ):
                    raise MaaFWProjectUpdateError(
                        "download update package exceeds size limit: "
                        f"{content_length} > {max_download_bytes}"
                    )

                downloaded_bytes = 0
                progress_throttle = _DownloadProgressThrottle(
                    callback=progress,
                    total_bytes=content_length,
                    clock=asyncio.get_running_loop().time,
                )
                progress_throttle.report(0, force=True)
                async with aiofiles.open(temp_path, "wb") as file:
                    async for chunk in response.aiter_bytes(
                        chunk_size=DOWNLOAD_CHUNK_SIZE
                    ):
                        if not chunk:
                            continue
                        downloaded_bytes += len(chunk)
                        if downloaded_bytes > max_download_bytes:
                            raise MaaFWProjectUpdateError(
                                "download update package exceeds size limit: "
                                f"> {max_download_bytes}"
                            )
                        await file.write(chunk)
                        progress_throttle.report(downloaded_bytes)
                progress_throttle.report(downloaded_bytes, force=True)
                return downloaded_bytes, content_length

    raise MaaFWProjectUpdateError("download update package redirect failed")


def _validate_download_url(raw_url: str | None) -> str:
    url = str(raw_url or "").strip()
    parsed = urlsplit(url)
    if parsed.scheme.lower() != "https":
        raise MaaFWProjectUpdateError(
            "MaaFW remote package URL must use HTTPS"
        )
    if not parsed.hostname or parsed.username or parsed.password:
        raise MaaFWProjectUpdateError("MaaFW remote package URL is invalid")

    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise MaaFWProjectUpdateError(
            "MaaFW remote package URL cannot target a private address"
        )
    return url


def _content_length(response: httpx.Response) -> int | None:
    raw_value = str(response.headers.get("content-length") or "").strip()
    if not raw_value:
        return None
    try:
        value = int(raw_value)
    except ValueError:
        return None
    return value if value >= 0 else None


async def _read_download_error_hint(
    response: httpx.Response,
) -> tuple[str, int | None]:
    try:
        content = bytearray()
        async for chunk in response.aiter_bytes(
            chunk_size=DOWNLOAD_ERROR_HINT_BYTES
        ):
            remaining = DOWNLOAD_ERROR_HINT_BYTES - len(content)
            if remaining <= 0:
                break
            content.extend(chunk[:remaining])
            if len(content) >= DOWNLOAD_ERROR_HINT_BYTES:
                break
    except Exception:
        return "", None
    return _build_download_error_details(bytes(content))


def _ensure_downloaded_zip(package_path: Path) -> None:
    if not package_path.exists() or package_path.stat().st_size == 0:
        raise MaaFWProjectUpdateError("update source returned an empty file")
    if zipfile.is_zipfile(package_path):
        return

    error_hint, provider_error_code = _read_local_download_error_details(package_path)
    if error_hint:
        raise MaaFWProjectUpdateError(
            f"download update package failed: {error_hint}",
            provider_error_code=provider_error_code,
        )
    raise MaaFWProjectUpdateError("update source did not return a valid zip file")


def _ensure_expected_sha256(package_path: Path, expected_sha256: str | None) -> None:
    expected = (expected_sha256 or "").strip().lower()
    if not expected:
        return

    actual = _calculate_sha256(package_path)
    if actual == expected:
        return

    raise MaaFWProjectUpdateError(
        f"sha256 mismatch, expected {expected[:12]}..., actual {actual[:12]}..."
    )


def _calculate_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _publish_content_addressed_download(
    provisional_path: Path,
    download_dir: Path,
    package_sha256: str,
) -> Path:
    """Publish a validated archive without sharing mutable temp names."""

    normalized_sha256 = str(package_sha256 or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", normalized_sha256):
        raise MaaFWProjectUpdateError("download package has an invalid sha256")
    package_path = (download_dir / f"{normalized_sha256}.zip").resolve()
    if not _is_within_path(package_path, download_dir):
        raise MaaFWProjectUpdateError("download package path escapes managed root")

    try:
        os.link(provisional_path, package_path)
    except FileExistsError:
        pass
    except OSError:
        if not package_path.exists():
            provisional_path.replace(package_path)

    if not package_path.is_file():
        raise MaaFWProjectUpdateError("download package could not be published")
    _ensure_downloaded_zip(package_path)
    if _calculate_sha256(package_path) != normalized_sha256:
        raise MaaFWProjectUpdateError("download cache sha256 verification failed")
    _remove_path(provisional_path)
    return package_path


def _release_content_addressed_download(
    download_root: Path,
    package_path: Path,
    package_sha256: str,
) -> dict[str, Any]:
    """Unlink one downloader-owned archive after strict identity checks."""

    normalized_sha256 = str(package_sha256 or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", normalized_sha256):
        raise MaaFWProjectUpdateError(
            "download package release requires a valid sha256"
        )
    if not package_path.is_absolute():
        raise MaaFWProjectUpdateError(
            "download package release requires an absolute package path"
        )

    lexical_root = Path(os.path.abspath(os.fspath(download_root)))
    lexical_package = Path(os.path.abspath(os.fspath(package_path)))
    try:
        relative = lexical_package.relative_to(lexical_root)
    except ValueError as exc:
        raise MaaFWProjectUpdateError(
            "download package release path escapes managed root"
        ) from exc
    if len(relative.parts) != 2:
        raise MaaFWProjectUpdateError(
            "download package release path has an invalid managed shape"
        )
    archive_key, file_name = relative.parts
    if not re.fullmatch(r"[0-9a-f]{24}", archive_key):
        raise MaaFWProjectUpdateError(
            "download package release path has an invalid archive key"
        )
    if file_name != f"{normalized_sha256}.zip":
        raise MaaFWProjectUpdateError(
            "download package release path does not match its sha256"
        )

    archive_dir = lexical_root / archive_key
    if _is_reparse_path(lexical_root):
        raise MaaFWProjectUpdateError(
            "download package release root cannot be a reparse point"
        )
    if lexical_root.exists() and not lexical_root.is_dir():
        raise MaaFWProjectUpdateError(
            "download package release root is not a directory"
        )
    if _is_reparse_path(archive_dir):
        raise MaaFWProjectUpdateError(
            "download package release directory cannot be a reparse point"
        )
    if archive_dir.exists() and not archive_dir.is_dir():
        raise MaaFWProjectUpdateError(
            "download package release directory is invalid"
        )
    if _is_reparse_path(lexical_package):
        raise MaaFWProjectUpdateError(
            "download package release target cannot be a reparse point"
        )
    if not os.path.lexists(lexical_package):
        return {
            "released": False,
            "retained": False,
            "directoryRemoved": False,
        }

    resolved_root = lexical_root.resolve(strict=False)
    resolved_package = lexical_package.resolve(strict=True)
    if not _is_within_path(resolved_package, resolved_root):
        raise MaaFWProjectUpdateError(
            "download package release target escapes managed root"
        )
    before = lexical_package.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise MaaFWProjectUpdateError(
            "download package release target is not a regular file"
        )
    if _calculate_sha256(lexical_package) != normalized_sha256:
        raise MaaFWProjectUpdateError(
            "download package release sha256 verification failed"
        )
    after = lexical_package.lstat()
    if _file_identity(before) != _file_identity(after):
        raise MaaFWProjectUpdateError(
            "download package changed while release was being verified"
        )

    try:
        lexical_package.unlink()
    except FileNotFoundError:
        return {
            "released": False,
            "retained": False,
            "directoryRemoved": False,
        }
    if os.path.lexists(lexical_package):
        raise MaaFWProjectUpdateError("download package could not be released")

    directory_removed = _remove_empty_download_directory(
        lexical_root,
        archive_dir,
        archive_key,
    )
    return {
        "released": True,
        "retained": False,
        "directoryRemoved": directory_removed,
    }


def _is_reparse_path(path: Path) -> bool:
    """Recognize POSIX symlinks and Windows junction/reparse points."""

    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    attributes = int(getattr(metadata, "st_file_attributes", 0) or 0)
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & reparse_flag)


def _file_identity(metadata: os.stat_result) -> tuple[int, int, int, int]:
    return (
        int(metadata.st_dev),
        int(metadata.st_ino),
        int(metadata.st_size),
        int(metadata.st_mtime_ns),
    )


def _remove_empty_download_directory(
    download_root: Path,
    download_dir: Path,
    archive_key: str,
) -> bool:
    """Remove one validated empty archive-key directory, never recursively."""

    normalized_key = str(archive_key or "").strip()
    if not re.fullmatch(r"[0-9a-f]{24}", normalized_key):
        return False
    lexical_root = Path(os.path.abspath(os.fspath(download_root)))
    expected_dir = lexical_root / normalized_key
    lexical_dir = Path(os.path.abspath(os.fspath(download_dir)))
    if lexical_dir != expected_dir:
        return False
    if _is_reparse_path(lexical_root) or _is_reparse_path(lexical_dir):
        return False
    if not lexical_dir.exists() or not lexical_dir.is_dir():
        return False
    resolved_root = lexical_root.resolve(strict=False)
    resolved_dir = lexical_dir.resolve(strict=True)
    if resolved_dir.parent != resolved_root:
        return False
    try:
        lexical_dir.rmdir()
    except OSError:
        # A non-empty or concurrently used directory must be retained.
        return False
    return True


def _cleanup_failed_managed_download(
    download_root: Path,
    download_dir: Path,
    archive_key: str,
    temp_path: Path,
    provisional_path: Path,
) -> None:
    _remove_download_work_file(temp_path)
    _remove_download_work_file(provisional_path)
    _remove_empty_download_directory(download_root, download_dir, archive_key)


def _remove_download_work_file(path: Path) -> None:
    """Unlink only a regular downloader work file; never recurse into a dir."""

    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return
    if not stat.S_ISREG(metadata.st_mode):
        return
    try:
        path.unlink()
    except FileNotFoundError:
        pass


async def _run_worker_to_completion(function: Callable[..., Any], *args: Any) -> Any:
    """Do not abandon a filesystem worker when its awaiter is cancelled."""

    worker = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        while not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                continue
            except BaseException:
                break
        if worker.done() and not worker.cancelled():
            try:
                worker.result()
            except BaseException:
                pass
        raise


async def _run_cleanup_to_completion(
    function: Callable[..., Any],
    *args: Any,
) -> None:
    """Finish best-effort cleanup, then let the outer exception propagate."""

    worker = asyncio.create_task(asyncio.to_thread(function, *args))
    while not worker.done():
        try:
            await asyncio.shield(worker)
        except asyncio.CancelledError:
            continue
        except BaseException:
            break
    if worker.done() and not worker.cancelled():
        try:
            worker.result()
        except BaseException:
            pass


def _read_local_download_error_hint(path: Path) -> str:
    hint, _ = _read_local_download_error_details(path)
    return hint


def _read_local_download_error_details(path: Path) -> tuple[str, int | None]:
    try:
        content = path.read_bytes()[:DOWNLOAD_ERROR_HINT_BYTES]
    except Exception:
        return "", None
    return _build_download_error_details(content)


def _build_download_error_hint(content: bytes) -> str:
    hint, _ = _build_download_error_details(content)
    return hint


def _build_download_error_details(content: bytes) -> tuple[str, int | None]:
    if not content:
        return "update source returned empty response", None

    text = _decode_download_error_text(content)
    if not text:
        return "", None

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        if text.lstrip().startswith("<"):
            return "update source returned an HTML page instead of zip", None
        return "", None

    if not isinstance(data, dict):
        return "", None

    raw_error_code = data.get("code")
    try:
        error_code = int(raw_error_code)
    except (TypeError, ValueError):
        error_code = None
    if error_code is not None and error_code != 0:
        error_message = MIRROR_ERROR_INFO.get(
            error_code,
            "MirrorChyan returned an unknown error",
        )
        return f"MirrorChyan [{error_code}]: {error_message}", error_code

    message = str(data.get("msg") or data.get("message") or "").strip()
    if not message:
        return "", None
    return f"update source returned error: {_sanitize_log_message(message)}", None


def _decode_download_error_text(content: bytes) -> str:
    for encoding in ("utf-8", "gb18030"):
        try:
            return content.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return ""


async def _apply_update_package(
    project_path: Path,
    package_path: Path,
    send_log: Callable[[str], None],
    *,
    progress: ProgressCallback | None = None,
) -> None:
    loop = asyncio.get_running_loop()

    def send_thread_log(message: str) -> None:
        loop.call_soon_threadsafe(send_log, message)

    def send_thread_progress(stage: str, **payload: Any) -> None:
        loop.call_soon_threadsafe(
            partial(_report_progress, progress, stage, **payload)
        )

    try:
        await _run_worker_to_completion(
            _apply_update_package_sync,
            project_path,
            package_path,
            send_thread_log,
            send_thread_progress,
        )
    finally:
        # Flush progress callbacks queued by the worker before returning or
        # propagating an apply failure.
        await asyncio.sleep(0)


def _apply_update_package_sync(
    project_path: Path,
    package_path: Path,
    send_log: Callable[[str], None],
    send_progress: Callable[..., None] | None = None,
) -> None:
    update_dir = project_path / UPDATE_WORK_DIR
    extract_dir = update_dir / "extract"
    backup_dir = update_dir / "backup"

    _remove_path(extract_dir)
    _remove_path(backup_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)

    try:
        if send_progress is not None:
            send_progress("extracting", message="extracting MaaFW update package")
        _safe_extract_zip(package_path, extract_dir)
        package_root = _find_package_root(extract_dir)
        changes_path = _find_changes_file(package_root, extract_dir)

        if send_progress is not None:
            send_progress("switching", message="applying MaaFW update package")
        if changes_path is None:
            send_log("applying full MaaFW update package")
            _apply_full_package(project_path, package_root, backup_dir)
        else:
            send_log("applying incremental MaaFW update package")
            _apply_incremental_package(
                project_path,
                package_root,
                changes_path,
                backup_dir,
                extract_dir,
            )
        send_log("MaaFW update package applied")
    finally:
        _remove_path(extract_dir)
        _remove_path(package_path)


def _apply_full_package(project_path: Path, package_root: Path, backup_dir: Path) -> None:
    backup_dir.mkdir(parents=True, exist_ok=True)
    touched_paths: set[Path] = set()

    try:
        for child in package_root.iterdir():
            if child.name in {UPDATE_WORK_DIR, "changes.json"}:
                continue

            target = _resolve_project_relative_path(project_path, child.name)
            touched_paths.add(target)
            _backup_target(project_path, target, backup_dir)
            _copy_path(child, target)
    except Exception:
        _restore_incremental_backup(project_path, backup_dir, touched_paths)
        raise
    else:
        _remove_path(backup_dir)


def _apply_incremental_package(
    project_path: Path,
    package_root: Path,
    changes_path: Path,
    backup_dir: Path,
    extract_dir: Path,
) -> None:
    changes = _load_changes(changes_path)
    payload_root = _resolve_payload_root(
        package_root,
        changes_path,
        changes,
        extract_dir,
    )
    backup_dir.mkdir(parents=True, exist_ok=True)
    touched_paths: set[Path] = set()

    try:
        for raw_path in _iter_deleted_paths(changes):
            target = _resolve_project_relative_path(project_path, raw_path)
            touched_paths.add(target)
            _backup_target(project_path, target, backup_dir)
            _remove_path(target)

        for source in payload_root.rglob("*"):
            if source.is_dir():
                continue
            if source == changes_path:
                continue
            if source.name == "changes.json":
                continue

            relative_path = source.relative_to(payload_root)
            target = _resolve_project_relative_path(project_path, relative_path.as_posix())
            touched_paths.add(target)
            _backup_target(project_path, target, backup_dir)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    except Exception:
        _restore_incremental_backup(project_path, backup_dir, touched_paths)
        raise
    else:
        _remove_path(backup_dir)


def _load_response_json(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except Exception as exc:
        raise MaaFWProjectUpdateError("update source did not return JSON") from exc
    if not isinstance(data, dict):
        raise MaaFWProjectUpdateError("update source returned invalid JSON shape")
    return data


def _is_remote_newer(remote_version: str, current_version: str) -> bool:
    remote = remote_version.strip()
    current = current_version.strip()
    if not remote:
        return False
    if not current:
        return True

    try:
        return version.parse(_normalize_version(remote)) > version.parse(
            _normalize_version(current)
        )
    except version.InvalidVersion:
        return remote != current


def _normalize_version(raw_version: str) -> str:
    return raw_version.strip().lstrip("vV")


def _safe_extract_zip(package_path: Path, extract_dir: Path) -> None:
    try:
        with zipfile.ZipFile(package_path, "r") as zip_ref:
            for member in zip_ref.infolist():
                target = (extract_dir / member.filename).resolve()
                if not _is_within_path(target, extract_dir):
                    raise MaaFWProjectUpdateError(
                        f"update package contains unsafe path: {member.filename}"
                    )
            zip_ref.extractall(extract_dir)
    except zipfile.BadZipFile as exc:
        raise MaaFWProjectUpdateError("update package is not a valid zip file") from exc


def _find_package_root(extract_dir: Path) -> Path:
    for candidate in [extract_dir, *_direct_child_dirs(extract_dir)]:
        if _has_interface_file(candidate):
            return candidate

    for interface_file in extract_dir.rglob("interface.json*"):
        if interface_file.name in {"interface.json", "interface.jsonc"}:
            return interface_file.parent

    raise MaaFWProjectUpdateError("interface.json was not found in update package")


def _find_changes_file(package_root: Path, extract_dir: Path) -> Path | None:
    for candidate in (package_root / "changes.json", extract_dir / "changes.json"):
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _has_interface_file(path: Path) -> bool:
    return (path / "interface.json").is_file() or (path / "interface.jsonc").is_file()


def _direct_child_dirs(path: Path) -> list[Path]:
    return [child for child in path.iterdir() if child.is_dir()]


def _load_changes(changes_path: Path) -> dict[str, Any]:
    try:
        data = json.loads(changes_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise MaaFWProjectUpdateError(f"cannot parse changes.json: {exc}") from exc
    if not isinstance(data, dict):
        raise MaaFWProjectUpdateError("changes.json must be a JSON object")
    return data


def _resolve_payload_root(
    package_root: Path,
    changes_path: Path,
    changes: dict[str, Any],
    extract_dir: Path,
) -> Path:
    for key in ("payload", "files", "root"):
        raw_path = changes.get(key)
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        candidate = (changes_path.parent / raw_path).resolve()
        if not candidate.exists() or not candidate.is_dir():
            continue
        if not _is_within_path(candidate, extract_dir):
            raise MaaFWProjectUpdateError(f"changes.json {key} path is unsafe: {raw_path}")
        return candidate

    for folder_name in ("payload", "files"):
        candidate = package_root / folder_name
        if candidate.exists() and candidate.is_dir():
            return candidate

    return package_root


def _iter_deleted_paths(changes: dict[str, Any]) -> list[str]:
    deleted_paths: list[str] = []
    for key in (
        "delete",
        "deleted",
        "deleted_dir",
        "remove",
        "removed",
        "unlink",
        "unlinks",
    ):
        value = changes.get(key)
        if isinstance(value, list):
            deleted_paths.extend(item for item in value if isinstance(item, str))
        elif isinstance(value, dict):
            deleted_paths.extend(item for item in value if isinstance(item, str))
    return deleted_paths


def _backup_target(project_path: Path, target: Path, backup_dir: Path) -> None:
    if not target.exists():
        return

    relative_path = target.relative_to(project_path)
    backup_path = backup_dir / relative_path
    if backup_path.exists():
        return

    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(target), str(backup_path))


def _restore_incremental_backup(
    project_path: Path,
    backup_dir: Path,
    touched_paths: set[Path],
) -> None:
    try:
        for target in sorted(touched_paths, key=lambda item: len(item.parts), reverse=True):
            _remove_path(target)

        if not backup_dir.exists():
            return
        for backup_child in sorted(backup_dir.rglob("*"), key=lambda item: len(item.parts)):
            if backup_child.is_dir():
                continue
            relative_path = backup_child.relative_to(backup_dir)
            target = project_path / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(backup_child), str(target))
    finally:
        _remove_path(backup_dir)


def _resolve_project_relative_path(project_path: Path, raw_path: str) -> Path:
    normalized = raw_path.strip().replace("\\", "/")
    if not normalized:
        raise MaaFWProjectUpdateError("update package contains empty path")

    candidate = Path(normalized)
    if candidate.is_absolute() or candidate.drive or candidate.root:
        raise MaaFWProjectUpdateError(f"update package contains absolute path: {raw_path}")
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise MaaFWProjectUpdateError(f"update package contains invalid path: {raw_path}")
    if candidate.parts[0] == UPDATE_WORK_DIR:
        raise MaaFWProjectUpdateError(f"update package cannot write to {UPDATE_WORK_DIR}: {raw_path}")

    target = (project_path / candidate).resolve()
    if not _is_within_path(target, project_path):
        raise MaaFWProjectUpdateError(f"update package path escapes project root: {raw_path}")
    return target


def _copy_path(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, target, dirs_exist_ok=True)
    else:
        shutil.copy2(source, target)


def _remove_path(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


def _is_within_path(path: Path, base_dir: Path) -> bool:
    try:
        path.resolve().relative_to(base_dir.resolve())
        return True
    except ValueError:
        return False


def _normalize_github_repo(raw_value: str) -> str:
    value = raw_value.strip()
    if not value:
        return ""
    value = value.removesuffix(".git")
    for prefix in ("https://github.com/", "http://github.com/", "github.com/"):
        if value.startswith(prefix):
            value = value[len(prefix):]
            break
    value = value.strip("/")
    parts = value.split("/")
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return ""
    return f"{parts[0]}/{parts[1]}"


def _github_tag_candidates(raw_version: str) -> list[str]:
    """Return exact version tag spellings without broad release enumeration."""

    value = raw_version.strip()
    if not value:
        return []
    candidates = [value]
    if value.startswith(("v", "V")) and len(value) > 1:
        candidates.append(value[1:])
        if value.startswith("V"):
            candidates.append(f"v{value[1:]}")
    else:
        candidates.append(f"v{value}")
    return list(dict.fromkeys(candidates))


def _select_github_release_asset(
    data: dict[str, Any],
    asset_pattern: str,
    *,
    project_name: str = "",
    project_shell_hint: str = "",
    require_explicit_match: bool = False,
    prefer_windows_x64: bool = False,
) -> tuple[str | None, str]:
    assets = data.get("assets")
    if not isinstance(assets, list):
        return None, "GitHub release assets are missing"

    try:
        pattern = re.compile(asset_pattern)
    except re.error as exc:
        raise MaaFWProjectUpdateError(f"invalid GitHub asset pattern: {exc}") from exc

    matches: list[tuple[str, str]] = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "")
        if not pattern.search(name):
            continue
        url = str(asset.get("browser_download_url") or "").strip()
        if url:
            matches.append((name, url))

    if not matches:
        return None, f"GitHub release has no matching asset for {asset_pattern!r}"
    if len(matches) == 1:
        return matches[0][1], ""

    if require_explicit_match:
        names = ", ".join(name for name, _ in matches[:5])
        return None, f"GitHub asset pattern is ambiguous: {names}"

    narrowed = matches
    shell_token = re.sub(r"[^a-z0-9]+", "", project_shell_hint.casefold())
    shell_aliases = {
        "mfaavalonia": ("mfaavalonia", "mfavalonia", "mfaa"),
        "mxu": ("mxu",),
        "cfa": ("cfa",),
        "mfw": ("mfw",),
    }.get(shell_token, (shell_token,) if shell_token else ())
    if shell_aliases:
        shell_patterns = [
            re.compile(
                rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])",
                re.IGNORECASE,
            )
            for token in shell_aliases
        ]
        shell_matches = [
            item
            for item in narrowed
            if any(pattern.search(item[0]) for pattern in shell_patterns)
        ]
        if shell_matches:
            narrowed = shell_matches
            if len(narrowed) == 1:
                return narrowed[0][1], ""

    project_token = re.sub(r"[^a-z0-9]+", "", project_name.casefold())
    if project_token:
        token_pattern = re.compile(
            rf"(?<![a-z0-9]){re.escape(project_token)}(?![a-z0-9])",
            re.IGNORECASE,
        )
        project_matches = [item for item in narrowed if token_pattern.search(item[0])]
        if project_matches:
            narrowed = project_matches
            if len(narrowed) == 1:
                return narrowed[0][1], ""

    if prefer_windows_x64:
        windows_pattern = re.compile(
            r"(?<![a-z0-9])(?:win|windows)(?![a-z0-9])",
            re.IGNORECASE,
        )
        windows_matches = [item for item in narrowed if windows_pattern.search(item[0])]
        if windows_matches:
            narrowed = windows_matches
        arch_pattern = re.compile(
            r"(?<![a-z0-9])(?:x86[-_]?64|x64|amd64)(?![a-z0-9])",
            re.IGNORECASE,
        )
        arch_matches = [item for item in narrowed if arch_pattern.search(item[0])]
        if arch_matches:
            narrowed = arch_matches
        if len(narrowed) == 1:
            return narrowed[0][1], ""

    names = ", ".join(name for name, _ in narrowed[:5])
    return None, f"GitHub release package selection is ambiguous: {names}"


def detect_maafw_project_shell_hint(project_path: Path) -> str:
    """Identify a local UI shell only from strong root-level file markers."""

    try:
        file_names = {
            item.name.casefold()
            for item in project_path.iterdir()
            if item.is_file()
        }
    except OSError:
        return ""

    markers = {
        "MFAAvalonia": {
            "mfaavalonia.exe",
            "mfaavalonia.dll",
            "mfaavalonia.desktop",
            "mfaavalonia.runtimeconfig.json",
        },
        "MXU": {"mxu.exe", "mxu.dll", "mxu.py", "mxu.pyw"},
        "CFA": {"cfa.exe", "cfa.py", "cfa.pyw"},
        "MFW": {"mfw.exe", "mfw.py", "mfw.pyw"},
    }
    detected = [
        shell_name
        for shell_name, shell_markers in markers.items()
        if file_names.intersection(shell_markers)
    ]
    return detected[0] if len(detected) == 1 else ""


def _sanitize_log_message(message: str) -> str:
    sensitive_patterns = [
        (
            r"((?:https?://)?(?:www\.)?mirrorchyan\.com/api/resources/download/)"
            r"[^/?#\s\"']+",
            r"\1***",
        ),
        (r"(cdk=)[^&\s]+", r"\1***"),
        (r"(password=)[^&\s]+", r"\1***"),
        (r"(token=)[^&\s]+", r"\1***"),
        (r"(api_key=)[^&\s]+", r"\1***"),
        (r"(secret=)[^&\s]+", r"\1***"),
    ]
    sanitized_message = message
    for pattern, replacement in sensitive_patterns:
        sanitized_message = re.sub(
            pattern,
            replacement,
            sanitized_message,
            flags=re.IGNORECASE,
        )
    return sanitized_message
