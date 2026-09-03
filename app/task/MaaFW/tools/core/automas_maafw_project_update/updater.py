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
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import quote, urljoin, urlsplit

import aiofiles
import httpx
from packaging import version

from app.utils.constants import MIRROR_ERROR_INFO

from ..automas_maafw_interface.models import MaaFWInterface
from .apply import (
    UpdateApplyError,
    apply_package_transaction,
    has_trusted_update_baseline,
)
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

# 错误码文案只维护一份：``app/utils/constants.py`` 的中文 ``MIRROR_ERROR_INFO``。
#
# 7001-7005 是 CDK 业务错误（HTTP 403）。实测服务端此时仍返回
# ``data.version_name``，版本检查照常成功，只是拿不到下载地址；这些码不当
# 致命错误，而是记录状态后改从 GitHub Release 下载。
MIRROR_CDK_STATUS_BY_CODE: dict[int, str] = {
    7001: "expired",
    7002: "invalid",
    7003: "quota",
    7004: "mismatched",
    7005: "blocked",
}
CDK_STATUS_OK = "ok"
CDK_STATUS_ABSENT = "absent"
CDK_ABSENT_REASON = "未配置 Mirror酱 CDK"


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
    # 与 MaaFWProjectUpdateResult 共享的结果字段（子任务契约 §8）。
    # ``source`` 在本对象上仍是版本元数据来源（恒为 ``mirrorchyan``）；
    # 实际下载来源看 ``package_source``。
    previous_version: str | None = None
    cdk_status: str = CDK_STATUS_ABSENT
    cdk_message: str = ""
    cdk_expired_time: int | None = None
    provider_error_code: int | None = None
    message: str = ""
    skipped_reason: str | None = None

    @property
    def installable(self) -> bool:
        return self.candidate is not None and self.candidate.installable

    @property
    def updated(self) -> bool:
        """A discovery never installs anything."""

        return False

    @property
    def version_name(self) -> str | None:
        return self.version or None

    @property
    def package_source(self) -> str | None:
        """Public download source name (``mirrorchyan`` / ``github``) or None."""

        return _public_package_source(
            self.candidate.source if self.candidate is not None else None
        )

    def get(self, key: str, default: Any = None) -> Any:
        """Mapping-style access so callers may use ``r.get(x)`` or ``getattr``."""

        return getattr(self, key, default)


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
    # 子任务契约 §8 字段。``previous_version`` / ``version_name`` 与既有的
    # ``current_version`` / ``latest_version`` 同义，构造时自动补齐。
    previous_version: str | None = None
    version_name: str | None = None
    cdk_status: str = CDK_STATUS_ABSENT
    cdk_message: str = ""
    cdk_expired_time: int | None = None
    skipped_reason: str | None = None

    def __post_init__(self) -> None:
        if self.previous_version is None and self.current_version:
            self.previous_version = self.current_version
        if self.version_name is None and self.latest_version:
            self.version_name = self.latest_version

    def get(self, key: str, default: Any = None) -> Any:
        """Mapping-style access so callers may use ``r.get(x)`` or ``getattr``."""

        return getattr(self, key, default)


@dataclass
class MaaFWMirrorChyanVersionCheck:
    """One MirrorChyan ``/latest`` query outcome, before the newer-than compare.

    A CDK business error (7001-7005) is *not* a failed check: the server still
    returns ``data.version_name`` (with HTTP 403), so the version can be
    compared and the package fetched from GitHub instead.  Only responses that
    carry no usable version raise :class:`MaaFWProjectUpdateError`.
    """

    version_name: str
    data: dict[str, Any] = field(default_factory=dict)
    download_url: str | None = None
    sha256: str | None = None
    cdk_status: str = CDK_STATUS_ABSENT
    cdk_message: str = ""
    cdk_expired_time: int | None = None
    provider_error_code: int | None = None

    @property
    def fallback_reason(self) -> str:
        """Why the package cannot come from MirrorChyan (for logs/reasons)."""

        if self.cdk_status == CDK_STATUS_ABSENT:
            return CDK_ABSENT_REASON
        if self.cdk_message:
            return self.cdk_message
        return "Mirror酱 未提供下载地址"


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
    """Normalize a package source name to the internal identifier.

    Version metadata always comes from MirrorChyan (it answers without a CDK).
    This value decides only where the **package** is downloaded from, and it is
    the user's explicit choice — there is no automatic fallback between sources.
    """

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


def _requested_package_source(config: dict[str, Any]) -> str:
    """用户选定的下载源，归一为核心包内部名。

    缺省 ``github_release``：与 ``MaaFWConfig.Update_Source`` 的默认值一致，
    也是唯一零配置可用的源（Mirror 酱必须有 CDK）。
    """

    raw = (
        config.get("package_source")
        or config.get("packageSource")
        or config.get("source")
    )
    if not str(raw or "").strip():
        return "github_release"
    return _normalise_package_source(raw)


def _public_package_source(raw_value: Any) -> str | None:
    """Map an internal candidate source to the public ``source`` field value."""

    value = str(raw_value or "").strip().casefold()
    if not value:
        return None
    if value.startswith("github"):
        return "github"
    return "mirrorchyan"


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
            skipped_reason=message,
        )

    send_update_log("start checking MaaFW project update")
    send_update_log(f"current version: {current_version}")
    send_update_log(f"update channel: {update_channel}")

    merged_source_config = dict(source_config or {})
    configured_cdk = str(
        merged_source_config.get("mirror_cdk") or merged_source_config.get("cdk") or ""
    ).strip()
    inherited_cdk = str(mirror_cdk or "").strip()
    if not configured_cdk and inherited_cdk:
        # 调用方既可以用 ``mirror_cdk=`` 参数给 CDK，也可以塞进 source_config；
        # 前者为准只在后者为空时生效。不能用 ``setdefault``：schema 会把未填的
        # CDK 序列化成空串而不是缺键。（这里说的不是全局兜底——凭据只看脚本级，
        # 合并发生在调用方，见 tools/embedded/update_credentials.py。）
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
    _report_progress(progress, "checking", message="checking for project updates")
    try:
        # 没有可信基线就直接要全量包：差量包在 apply 阶段必须能对上
        # projectFingerprint，而从未经 MAS 更新过的项目根本没有那份 manifest，
        # 于是「首次更新」必然被拒——这就是自举死锁。探测是只读的，不建目录。
        prefer_full = not has_trusted_update_baseline(project_path)
        discovery, version_check, skipped_reason = (
            await _discover_project_update_detailed(
                interface_model,
                current_version=current_version,
                source_config=merged_source_config,
                proxy=proxy,
                send_log=send_update_log,
                prefer_full_package=prefer_full,
            )
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

    cdk_fields = _cdk_result_fields(version_check)

    if discovery is None:
        if version_check is not None:
            message = f"MaaFW 项目已是最新版本: {current_version}"
            status = "no_update"
        else:
            message = skipped_reason or "MaaFW 项目未配置可用更新源，跳过更新"
            status = "skipped"
        send_update_log(message)
        _report_progress(
            progress,
            "completed",
            status=status,
            message=message,
            final=True,
        )
        return MaaFWProjectUpdateResult(
            checked=version_check is not None,
            updated=False,
            current_version=current_version,
            latest_version=(
                version_check.version_name if version_check is not None else None
            ),
            message=message,
            skipped_reason=skipped_reason or message,
            **cdk_fields,
        )

    _report_progress(
        progress,
        "checking",
        status="version_discovered",
        version=discovery.version,
        metadata_source=discovery.source,
        package_source=discovery.package_source,
    )

    if not discovery.installable:
        reason = (
            discovery.unavailable_reason
            or "更新源没有返回可安装的下载地址"
        )
        message = (
            f"发现 MaaFW 项目更新 {current_version} -> {discovery.version}，"
            f"但没有可安装的更新包: {reason}"
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
            source=None,
            message=message,
            skipped_reason=reason,
            **cdk_fields,
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

    message = (
        f"MaaFW 项目更新完成: {current_version} -> {candidate.version}"
        f"（来源: {_public_package_source(candidate.source)}）"
    )
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
        source=_public_package_source(candidate.source),
        message=message,
        **cdk_fields,
        operation_id=str(apply_result.get("operationId") or "") or None,
        plan_id=str(apply_result.get("planId") or candidate.plan_id or "") or None,
        project_fingerprint=str(apply_result.get("finalFingerprint") or "") or None,
        package_type=str(
            apply_result.get("packageType") or candidate.package_type or ""
        )
        or None,
        resumed_from=int(apply_result.get("resumedFrom") or 0),
    )


async def discover_maafw_project_update(
    interface_model: MaaFWInterface,
    *,
    current_version: str | None = None,
    source_config: dict[str, Any] | None = None,
    proxy: httpx.Proxy | None = None,
    send_log: Callable[[str], None] | None = None,
    prefer_full_package: bool = False,
    version_only: bool = False,
) -> MaaFWProjectUpdateDiscovery | None:
    """Discover a newer project version and pick where to download it from.

    Version metadata always comes from MirrorChyan (it answers without a CDK;
    a CDK business error 7001-7005 still yields the version).  **Where the
    package is downloaded from is the user's explicit choice** — there is no
    automatic fallback between sources:

    - ``package_source="mirrorchyan"``: needs a download URL, i.e. a working
      CDK.  Missing or rejected CDK means "not installable" with a readable
      reason; it does **not** silently switch to GitHub.
    - ``package_source="github_release"`` (the default): fetches the same
      version from the release of ``interface.github``.  Without
      ``interface.github`` the version is reported but marked not installable.

    ``source_config`` keys ``repo`` / ``tag`` / ``asset_pattern`` / ``token``
    are deprecated and ignored; ``package_source``, ``mirror_cdk``, ``channel``
    and ``project_shell_hint`` are honoured.  Returns
    ``None`` when the project is already up to date or has no
    ``mirrorchyan_rid``; the returned discovery carries the §8 result fields
    (``cdk_status`` / ``cdk_message`` / ``cdk_expired_time`` / ``message`` /
    ``skipped_reason`` ...).
    """

    discovery, _version_check, _skipped_reason = (
        await _discover_project_update_detailed(
            interface_model,
            current_version=current_version,
            source_config=source_config,
            proxy=proxy,
            send_log=send_log,
            prefer_full_package=prefer_full_package,
            version_only=version_only,
        )
    )
    return discovery


async def _discover_project_update_detailed(
    interface_model: MaaFWInterface,
    *,
    current_version: str | None = None,
    source_config: dict[str, Any] | None = None,
    proxy: httpx.Proxy | None = None,
    send_log: Callable[[str], None] | None = None,
    prefer_full_package: bool = False,
    version_only: bool = False,
) -> tuple[
    MaaFWProjectUpdateDiscovery | None,
    MaaFWMirrorChyanVersionCheck | None,
    str | None,
]:
    """Return ``(discovery, mirror_version_check, skipped_reason)``.

    ``discovery`` is ``None`` when nothing newer exists; ``mirror_version_check``
    is ``None`` only when MirrorChyan was never queried (no rid), so callers can
    still surface the CDK status for an up-to-date project.
    """

    config = dict(source_config or {})
    current = (
        current_version
        if current_version is not None
        else (interface_model.version or "")
    )
    send_update_log = send_log or (lambda _: None)

    rid = str(interface_model.mirrorchyan_rid or "").strip()
    if not rid:
        reason = "interface.json 未声明 mirrorchyan_rid，跳过更新检查"
        send_update_log(reason)
        return None, None, reason

    mirror_cdk = str(config.get("mirror_cdk") or config.get("cdk") or "").strip()
    channel = str(config.get("channel") or "stable").strip() or "stable"
    send_update_log(f"MirrorChyan RID: {rid}")
    if interface_model.mirrorchyan_multiplatform:
        send_update_log("MirrorChyan platform: win/x86_64")
    # 日志里绝不出现 CDK 明文，连前几位都不打。
    if mirror_cdk:
        send_update_log("MirrorChyan CDK: 已配置")
    else:
        send_update_log(
            "MirrorChyan CDK 未配置：仍可通过 Mirror酱 查版本，但拿不到下载地址"
        )

    # **查版本一律不带 CDK。** Mirror 酱在有更新且 CDK 有效时会签发一个一次性
    # 下载地址，而它能计数的就是这一下签发——带着 CDK 查一次版本就可能扣掉一次
    # 今日下载额度。运行前自动更新意味着每跑一次脚本查一次，编辑页那个「检查
    # 更新」按钮也随手就点，这些都不该烧额度。真要下载时再带 CDK 查第二次。
    version_check = await _query_mirrorchyan_latest(
        interface_model,
        current_version=current,
        mirror_cdk="",
        channel=channel,
        proxy=proxy,
        prefer_full=prefer_full_package,
        send_log=send_update_log,
    )
    latest = version_check.version_name
    send_update_log(f"version metadata source: MirrorChyan; latest={latest}")

    if not _is_remote_newer(latest, current):
        reason = f"已是最新版本: {current or latest}"
        return None, version_check, reason

    # 下载源由用户在脚本配置里显式选定，**不做自动分流**。选 Mirror 酱就必须
    # 自己填 CDK；CDK 缺失或不可用时明确报出原因，不悄悄换成 GitHub——用户得
    # 知道自己在从哪下载，出问题才查得动。
    requested = _requested_package_source(config)

    def unavailable(reason: str):
        send_update_log(reason)
        discovery = MaaFWProjectUpdateDiscovery(
            source="mirrorchyan",
            version=latest,
            unavailable_reason=reason,
        )
        return (
            _attach_version_check(discovery, version_check, current),
            version_check,
            None,
        )

    if requested == "mirrorchyan":
        if not mirror_cdk:
            return unavailable(
                "未配置 Mirror酱 CDK；"
                "更新源选的是 Mirror 酱，请填写 CDK 或改用 GitHub 源"
            )
        if version_only:
            # 只问「有没有新版本」的场景（编辑页那个检查更新按钮）到此为止：
            # 再往下就要带 CDK 换下载地址，而那一下会扣今日额度。用户点
            # 「更新」时才走完整流程。这里按「可安装」返回——填了 CDK 就
            # 确实能装，只是还没去取地址；CDK 本身有没有问题留到真更新时
            # 才会知道，这是不烧额度换来的代价。
            send_update_log("仅检查版本：不获取 Mirror酱 下载地址，避免占用 CDK 额度")
            discovery = MaaFWProjectUpdateDiscovery(
                source="mirrorchyan",
                version=latest,
                candidate=MaaFWProjectUpdateCandidate(
                    source="mirrorchyan", version=latest, to_version=latest
                ),
            )
            return (
                _attach_version_check(discovery, version_check, current),
                version_check,
                None,
            )

        # 确认要从 Mirror 酱下载了，才带 CDK 查第二次拿一次性下载地址。
        # 这一次才可能扣今日下载额度，而它对应一次真实下载。
        send_update_log("已确认有新版本，携带 CDK 获取 Mirror酱 下载地址")
        authorized = await _query_mirrorchyan_latest(
            interface_model,
            current_version=current,
            mirror_cdk=mirror_cdk,
            channel=channel,
            proxy=proxy,
            prefer_full=prefer_full_package,
            send_log=send_update_log,
        )
        # CDK 状态以带 CDK 的这次为准：不带 CDK 那次只知道有没有新版本。
        version_check = authorized
        if authorized.download_url is None:
            return unavailable(
                f"{authorized.fallback_reason}；"
                "更新源选的是 Mirror 酱，请检查 CDK 或改用 GitHub 源"
            )
        discovery = _discovery_from_mirror_check(authorized)
        send_update_log(f"install package source: MirrorChyan; version={latest}")
        return (
            _attach_version_check(discovery, authorized, current),
            authorized,
            None,
        )

    repo = _normalize_github_repo(str(interface_model.github or ""))
    if not repo:
        return unavailable(
            "更新源选的是 GitHub，但 interface.json 未声明 github 仓库，无法下载更新包"
        )

    send_update_log(f"install package source: GitHub Release; repo={repo}")
    try:
        github_discovery = await _check_github_release_update(
            interface_model,
            current_version=current,
            source_config=config,
            proxy=proxy,
            target_version=latest,
        )
    except (MaaFWProjectUpdateError, httpx.HTTPError) as exc:
        # 查询失败不阻断任务：报为「有更新但不可安装」，原因留在
        # unavailable_reason / skipped_reason 里，让上层照常继续运行脚本。
        return unavailable(
            f"GitHub Release 查询失败: {_sanitize_log_message(str(exc))}"
        )

    if github_discovery is None:
        return unavailable(
            f"GitHub 仓库 {repo} 没有与 Mirror酱 版本 {latest} 匹配的 Release"
        )

    if github_discovery.candidate is not None:
        # Keep the target identity from MirrorChyan even when GitHub spells
        # the matching tag with a conventional leading ``v``.
        github_discovery.candidate.version = latest
        github_discovery.candidate.to_version = latest
        send_update_log(f"install package source: GitHub Release; version={latest}")

    discovery = MaaFWProjectUpdateDiscovery(
        source="mirrorchyan",
        version=latest,
        candidate=github_discovery.candidate,
        unavailable_reason=github_discovery.unavailable_reason,
    )
    return _attach_version_check(discovery, version_check, current), version_check, None


def _attach_version_check(
    discovery: MaaFWProjectUpdateDiscovery,
    version_check: MaaFWMirrorChyanVersionCheck,
    current_version: str,
) -> MaaFWProjectUpdateDiscovery:
    """Copy CDK/version context onto a discovery and fill its summary."""

    discovery.previous_version = current_version or None
    discovery.cdk_status = version_check.cdk_status
    discovery.cdk_message = version_check.cdk_message
    discovery.cdk_expired_time = version_check.cdk_expired_time
    discovery.provider_error_code = version_check.provider_error_code
    if discovery.installable:
        label = (
            "Mirror酱" if discovery.package_source == "mirrorchyan" else "GitHub Release"
        )
        discovery.message = (
            f"发现新版本 {current_version} -> {discovery.version}，将从 {label} 下载"
        )
        discovery.skipped_reason = None
    else:
        reason = discovery.unavailable_reason or "更新源没有返回可安装的下载地址"
        discovery.message = (
            f"发现新版本 {current_version} -> {discovery.version}，"
            f"但没有可安装的更新包: {reason}"
        )
        discovery.skipped_reason = reason
    return discovery


def _cdk_result_fields(
    version_check: MaaFWMirrorChyanVersionCheck | None,
) -> dict[str, Any]:
    if version_check is None:
        return {
            "cdk_status": CDK_STATUS_ABSENT,
            "cdk_message": "",
            "cdk_expired_time": None,
        }
    return {
        "cdk_status": version_check.cdk_status,
        "cdk_message": version_check.cdk_message,
        "cdk_expired_time": version_check.cdk_expired_time,
    }



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
        raise MaaFWProjectUpdateError(
            "cannot create a plan without an installable candidate"
        )
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
        raise MaaFWProjectUpdateError(
            "update plan interface/provider descriptor is invalid"
        ) from exc
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
    if (
        discovery is not None
        and discovery.candidate is None
        and discovery.cdk_status != CDK_STATUS_OK
    ):
        raise MaaFWProjectUpdateError(
            f"MirrorChyan: {discovery.cdk_message or CDK_ABSENT_REASON}，无法下载已计划的更新包",
            provider_error_code=discovery.provider_error_code,
        )
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
    if (
        planned_type
        and candidate.package_type
        and candidate.package_type != planned_type
    ):
        raise MaaFWProjectUpdateError("planned package type changed")
    candidate.artifact_id = planned_artifact or actual_artifact
    candidate.plan_id = plan_id
    candidate.project_fingerprint = (
        str(state.get("projectFingerprint") or "").strip() or None
    )
    candidate.package_type = planned_type or candidate.package_type
    candidate.from_version = (
        str(state.get("fromVersion") or candidate.from_version or "").strip() or None
    )
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
        raise MaaFWProjectUpdateError("update candidate is missing source or version")
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
            expectedFingerprint=str(
                expected_fingerprint or candidate.project_fingerprint or ""
            ),
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
    prefer_full: bool = False,
    send_log: Callable[[str], None] | None = None,
) -> MaaFWProjectUpdateDiscovery | None:
    """Return a MirrorChyan discovery when a newer version exists.

    A CDK business error (7001-7005) still returns the discovery — carrying
    ``version`` plus ``cdk_status`` / ``cdk_message`` / ``provider_error_code``
    — just without an installable candidate.  Only version lookups that fail
    outright (8001-8004, 1001, unknown or negative codes, transport errors)
    raise.
    """

    if not str(interface_model.mirrorchyan_rid or "").strip():
        return None
    version_check = await _query_mirrorchyan_latest(
        interface_model,
        current_version=current_version,
        mirror_cdk=mirror_cdk,
        channel=channel,
        proxy=proxy,
        prefer_full=prefer_full,
        send_log=send_log,
    )
    if not _is_remote_newer(version_check.version_name, current_version):
        return None
    return _attach_version_check(
        _discovery_from_mirror_check(version_check),
        version_check,
        current_version,
    )


async def _query_mirrorchyan_latest(
    interface_model: MaaFWInterface,
    *,
    current_version: str,
    mirror_cdk: str,
    channel: str,
    proxy: httpx.Proxy | None,
    prefer_full: bool = False,
    send_log: Callable[[str], None] | None = None,
) -> MaaFWMirrorChyanVersionCheck:
    """Query ``/api/resources/{rid}/latest`` and classify the CDK outcome."""

    send_update_log = send_log or (lambda _: None)
    rid = str(interface_model.mirrorchyan_rid or "").strip()
    if not rid:
        raise MaaFWProjectUpdateError("interface.json 未声明 mirrorchyan_rid")

    params: dict[str, str] = {
        "user_agent": "AutoMasGui",
        "channel": channel or "stable",
    }
    if mirror_cdk:
        params["cdk"] = mirror_cdk
    if prefer_full:
        # 不带 current_version：MirrorChyan 的 current_version 是差量包的计算基准
        # （文档标为「推荐」而非必填），不给它就没法算差量，返回的是全量包。
        # 项目还没有可信基线时必须走这条路——差量包在 _validate_plan_base 里
        # 对不上 projectFingerprint 会被拒，导致「首次更新永远装不上」。
        send_update_log("本地无可信更新基线，改为请求全量包")
    else:
        params["current_version"] = current_version
    if interface_model.mirrorchyan_multiplatform:
        # 实测 os=win&arch=x86_64 与 windows/x64 都被服务端接受并归一；
        # 这里沿用 GitHub 资产命名的那套写法。
        params["os"] = "win"
        params["arch"] = "x86_64"

    url = f"https://mirrorchyan.com/api/resources/{rid}/latest"
    try:
        async with httpx.AsyncClient(
            proxy=proxy, follow_redirects=True, timeout=30.0
        ) as client:
            response = await client.get(url, params=params, headers=HTTP_HEADERS)
    except httpx.HTTPError as exc:
        raise MaaFWProjectUpdateError(
            f"MirrorChyan update check failed: {_sanitize_log_message(str(exc))}"
        ) from None

    result = _load_response_json(response)
    raw_error_code = result.get("code", 0)
    try:
        error_code: int | None = int(raw_error_code)
    except (TypeError, ValueError):
        error_code = None
    server_message = _sanitize_log_message(
        str(result.get("msg") or result.get("message") or "").strip()
    )
    raw_data = result.get("data")
    data: dict[str, Any] = dict(raw_data) if isinstance(raw_data, dict) else {}
    latest_version = str(
        data.get("version_name") or data.get("version") or data.get("name") or ""
    ).strip()

    if error_code in MIRROR_CDK_STATUS_BY_CODE:
        cdk_message = MIRROR_ERROR_INFO.get(error_code, MIRROR_ERROR_INFO[1])
        if not latest_version:
            raise MaaFWProjectUpdateError(
                f"MirrorChyan [{error_code}]: {cdk_message}",
                provider_error_code=error_code,
            )
        send_update_log(
            f"MirrorChyan CDK 状态 [{error_code}]: {cdk_message}；本次仅用 Mirror酱 查版本"
        )
        return MaaFWMirrorChyanVersionCheck(
            version_name=latest_version,
            data=data,
            cdk_status=MIRROR_CDK_STATUS_BY_CODE[error_code],
            cdk_message=cdk_message,
            provider_error_code=error_code,
        )

    if response.status_code != 200 or error_code != 0:
        if error_code not in (None, 0):
            error_message = MIRROR_ERROR_INFO.get(error_code)
            if error_message is None:
                error_message = MIRROR_ERROR_INFO[1]
                if server_message:
                    error_message = f"{error_message}: {server_message}"
            raise MaaFWProjectUpdateError(
                f"MirrorChyan [{error_code}]: {error_message}",
                provider_error_code=error_code,
            )
        raise MaaFWProjectUpdateError(
            f"MirrorChyan returned HTTP {response.status_code}"
        )

    if not data:
        raise MaaFWProjectUpdateError("MirrorChyan did not return version data")
    if not latest_version:
        raise MaaFWProjectUpdateError("MirrorChyan did not return version")

    return MaaFWMirrorChyanVersionCheck(
        version_name=latest_version,
        data=data,
        download_url=str(data.get("url") or "").strip() or None,
        sha256=str(data.get("sha256") or "").strip() or None,
        cdk_status=CDK_STATUS_OK if mirror_cdk else CDK_STATUS_ABSENT,
        cdk_expired_time=_metadata_int(data, "cdk_expired_time", "cdkExpiredTime"),
    )


def _discovery_from_mirror_check(
    version_check: MaaFWMirrorChyanVersionCheck,
) -> MaaFWProjectUpdateDiscovery:
    data = version_check.data
    latest_version = version_check.version_name
    return _build_update_discovery(
        source="mirrorchyan",
        version=latest_version,
        download_url=version_check.download_url,
        sha256=version_check.sha256,
        artifact_id=str(data.get("artifact_id") or data.get("artifactId") or "").strip()
        or None,
        package_type=_package_type_from_metadata(data),
        from_version=_metadata_text(
            data, "base_version", "baseVersion", "from_version", "fromVersion"
        ),
        to_version=_metadata_text(
            data, "target_version", "targetVersion", "to_version", "toVersion"
        )
        or latest_version,
        size=_metadata_int(data, "size", "file_size", "fileSize"),
        etag=_metadata_text(data, "etag", "ETag"),
        last_modified=_metadata_text(
            data, "last_modified", "lastModified", "Last-Modified"
        ),
        range_supported=_metadata_bool(
            data, "range", "range_supported", "rangeSupported"
        ),
        unavailable_reason=(
            f"{version_check.fallback_reason}，Mirror酱 未提供下载地址"
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
    """Fetch the exact MirrorChyan-selected version from GitHub Releases.

    The repository is always ``interface.github``, the tag is always the
    MirrorChyan ``version_name`` (``target_version``), and the asset is picked
    from the release's zip files by project name, Windows x86_64 platform and
    UI-shell variant (``project_shell_hint``, falling back to the
    ``mirrorchyan_rid`` suffix).  The historical ``source_config`` keys
    ``repo`` / ``github_repo`` / ``tag`` / ``github_tag`` / ``asset_pattern``
    / ``github_asset_pattern`` / ``token`` / ``github_token`` are deprecated
    and ignored.
    """

    repo = _normalize_github_repo(str(interface_model.github or ""))
    if not repo:
        return None

    target_version = str(target_version or "").strip()
    if not target_version:
        raise MaaFWProjectUpdateError(
            "GitHub release lookup requires an exact target version selected by MirrorChyan"
        )
    # Resolve that exact release instead of GitHub's stable-only ``latest``
    # endpoint so prereleases and an older same-version package stay
    # reachable.  Only the conventional optional leading ``v`` differs.
    api_urls = [
        f"https://api.github.com/repos/{repo}/releases/tags/{quote(candidate, safe='')}"
        for candidate in _github_tag_candidates(target_version)
    ]
    headers = dict(HTTP_HEADERS)
    headers["Accept"] = "application/vnd.github+json"

    response: httpx.Response | None = None
    async with httpx.AsyncClient(
        proxy=proxy, follow_redirects=True, timeout=30.0
    ) as client:
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

    shell_hint = str(source_config.get("project_shell_hint") or "").strip()
    if not shell_hint:
        shell_hint = _shell_from_rid_value(
            str(interface_model.mirrorchyan_rid or "")
        )
    download_url, selection_reason = _select_github_release_asset(
        data,
        r"\.zip$",
        project_name=interface_model.name,
        project_shell_hint=shell_hint,
        require_explicit_match=False,
        prefer_windows_x64=True,
    )
    asset = _github_asset_for_url(data, download_url)
    asset_digest = str(asset.get("digest") or "").strip() if asset else ""
    configured_sha256 = str(source_config.get("sha256") or "").strip() or None

    return _build_update_discovery(
        source="github_release",
        version=latest_version,
        download_url=download_url,
        sha256=configured_sha256 or asset_digest or None,
        artifact_id=(str(asset.get("id") or "").strip() or None if asset else None),
        package_type=_package_type_from_metadata(data),
        from_version=_metadata_text(
            data, "base_version", "baseVersion", "from_version", "fromVersion"
        ),
        to_version=_metadata_text(
            data, "target_version", "targetVersion", "to_version", "toVersion"
        )
        or latest_version,
        size=_metadata_int(asset or {}, "size"),
        etag=_metadata_text(asset or {}, "etag", "ETag"),
        last_modified=_metadata_text(
            asset or {}, "last_modified", "lastModified", "Last-Modified"
        ),
        range_supported=_metadata_bool(
            asset or {}, "range", "range_supported", "rangeSupported"
        ),
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
    value = (
        str(
            data.get("package_type")
            or data.get("packageType")
            or data.get("type")
            or ""
        )
        .strip()
        .lower()
    )
    return value if value in {"full", "delta"} else None


def _github_asset_for_url(
    data: Mapping[str, Any], url: str | None
) -> dict[str, Any] | None:
    if not url or not isinstance(data.get("assets"), list):
        return None
    for asset in data["assets"]:
        if (
            isinstance(asset, dict)
            and str(asset.get("browser_download_url") or "").strip() == url
        ):
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
                    current_url = _validate_download_url(urljoin(current_url, location))
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
                        f"download update package failed: HTTP {response.status_code}"
                    )

                _validate_download_url(str(response.url))
                content_length = _content_length(response)
                if content_length is not None and content_length > max_download_bytes:
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
        raise MaaFWProjectUpdateError("MaaFW remote package URL must use HTTPS")
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
        async for chunk in response.aiter_bytes(chunk_size=DOWNLOAD_ERROR_HINT_BYTES):
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
        raise MaaFWProjectUpdateError("download package release directory is invalid")
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
        loop.call_soon_threadsafe(partial(_report_progress, progress, stage, **payload))

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


def _apply_full_package(
    project_path: Path, package_root: Path, backup_dir: Path
) -> None:
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
            target = _resolve_project_relative_path(
                project_path, relative_path.as_posix()
            )
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
            raise MaaFWProjectUpdateError(
                f"changes.json {key} path is unsafe: {raw_path}"
            )
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
        for target in sorted(
            touched_paths, key=lambda item: len(item.parts), reverse=True
        ):
            _remove_path(target)

        if not backup_dir.exists():
            return
        for backup_child in sorted(
            backup_dir.rglob("*"), key=lambda item: len(item.parts)
        ):
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
        raise MaaFWProjectUpdateError(
            f"update package contains absolute path: {raw_path}"
        )
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise MaaFWProjectUpdateError(
            f"update package contains invalid path: {raw_path}"
        )
    if candidate.parts[0] == UPDATE_WORK_DIR:
        raise MaaFWProjectUpdateError(
            f"update package cannot write to {UPDATE_WORK_DIR}: {raw_path}"
        )

    target = (project_path / candidate).resolve()
    if not _is_within_path(target, project_path):
        raise MaaFWProjectUpdateError(
            f"update package path escapes project root: {raw_path}"
        )
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
            value = value[len(prefix) :]
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

    # Last-resort disambiguation: several assets can survive the project and
    # platform narrowing because the release ships one package per UI shell
    # family (e.g. M9A publishes ``*-MFAA.zip`` and ``*-MXU.zip`` for the same
    # version).  Only apply this once the more specific criteria above could
    # not settle on a single asset, so a stale shell hint never overrides an
    # otherwise unambiguous match.
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

    names = ", ".join(name for name, _ in narrowed[:5])
    return None, f"GitHub release package selection is ambiguous: {names}"


# rid 后缀 -> 外壳家族规范名。取值域与 _select_github_release_asset 的
# shell_aliases 保持一致。
_RID_SHELL_SUFFIXES = {
    "mfaa": "MFAAvalonia",
    "mfaavalonia": "MFAAvalonia",
    "mxu": "MXU",
    "cfa": "CFA",
    "mfw": "MFW",
}


def _shell_from_mirrorchyan_rid(project_path: Path) -> str:
    """按 interface.json 自己声明的 Mirror酱 资源 ID 判定外壳家族。

    这是项目作者声明的、而非猜的：同一项目发布多个外壳变体时 rid 必须逐个
    不同（M9A 的 MFAA 包是 ``M9A``、MXU 包是 ``M9A-MXU``），而那个后缀正是
    GitHub 分包名里用来区分的那一段。

    只在末段确实是已知外壳名时才采信，避免把 ``Foo-Bar`` 这类普通带横线的
    rid 误判。只发一个外壳的项目（MaaYYs / MaaEnd / 识宝）rid 没有后缀，
    自然落回下面的文件与目录特征。
    """

    try:
        raw = (project_path / "interface.json").read_text(encoding="utf-8-sig")
        rid = str(json.loads(raw).get("mirrorchyan_rid") or "").strip()
    except (OSError, ValueError):
        # 解析不了（比如 JSON5 写法）就当没有，交给下面的特征判定
        return ""
    return _shell_from_rid_value(rid)


def _shell_from_rid_value(rid: str) -> str:
    """Map a ``mirrorchyan_rid`` suffix such as ``M9A-MXU`` to its shell family."""

    rid = str(rid or "").strip()
    if "-" not in rid:
        return ""
    suffix = re.sub(r"[^a-z0-9]+", "", rid.rsplit("-", 1)[1].casefold())
    return _RID_SHELL_SUFFIXES.get(suffix, "")


def _shell_from_directory_name(directory_name: str) -> str:
    """Infer the shell variant from a release-style install directory name.

    GitHub packages unpack to ``{名}-{os}-{arch}-{版本}[-{变体}]`` (for
    example ``MaaYYs-win-x86_64-v3.14.8-MXU``); the trailing segment is the
    same variant token used to tell the release assets apart.
    """

    return _shell_from_rid_value(directory_name)


def detect_maafw_project_shell_hint(project_path: Path) -> str:
    """Identify a local UI shell from root-level markers.

    File-name markers come first. They only work when the shell names its
    executable after itself, which MXU does not always do: MaaYYs ships
    ``mxu.exe`` but M9A ships ``m9a.exe`` and MaaEnd ships ``MaaEnd.exe``,
    all three being MXU packages. Those fell through to "" and left the
    updater unable to choose between e.g. ``M9A-...-MFAA.zip`` and
    ``M9A-...-MXU.zip``.

    So when no file marker matches, fall back to structure: MXU ships the
    MaaFramework runtime in a root ``maafw/`` directory, and MFAAvalonia
    does not (it ships ``MaaAgentBinary/`` + ``libs/`` + ``runtimes/``
    alongside ``MFAAvalonia.dll``). The fallback runs **only** after the
    file markers came up empty, so MFW/CFA packages — which also carry
    ``maafw/`` but are already identified by ``MFW.exe`` / ``CFA.exe`` —
    keep their own answer.
    """

    declared = _shell_from_mirrorchyan_rid(project_path)
    if declared:
        return declared

    from_directory = _shell_from_directory_name(project_path.name)
    if from_directory:
        return from_directory

    try:
        entries = list(project_path.iterdir())
    except OSError:
        return ""

    file_names = {item.name.casefold() for item in entries if item.is_file()}

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
    if len(detected) == 1:
        return detected[0]
    if detected:
        return ""

    directory_names = {item.name.casefold() for item in entries if item.is_dir()}
    if "maafw" in directory_names:
        return "MXU"
    return ""


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
