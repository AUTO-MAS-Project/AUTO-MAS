from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping, Sequence
from urllib.parse import quote

import httpx
from packaging import version

from app.utils.constants import MIRROR_ERROR_INFO

from ..automas_maafw_interface.models import MaaFWInterface
from .apply import (
    UpdateApplyError,
    UpdatePostValidateRejected,
    UpdateProjectLockBusy,
    apply_package_transaction,
    has_trusted_update_baseline,
    recover_interrupted_update,
    update_baseline_matches_project,
)
from .contracts import normalise_sha256, project_fingerprint
from .state import (
    DEFAULT_CACHE_ROOT,
    DEFAULT_OPERATION_ROOT,
    UpdateOperationStore,
)
from .transport import (
    CANCELLED_MESSAGE,
    UpdateDownloadCancelled,
    download_resumable,
)

HTTP_HEADERS = {"User-Agent": "AutoMasGui"}

ProgressCallback = Callable[[dict[str, Any]], None]

logger = logging.getLogger("automas.maafw.project_update.updater")

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
    # 只查版本时为真：有新版本且来源可用，但尚未去换下载地址。
    url_deferred: bool = False

    @property
    def installable(self) -> bool:
        """这个候选包能不能装。

        ``url_deferred`` 是「只查版本」用的：确认了有新版本、来源也可用，
        只是**故意还没去换下载地址**——带 CDK 换地址会扣一次当日额度，
        而用户可能只是随手点了下检查更新。真更新时会重新走一遍拿到地址。
        """

        if self.url_deferred:
            return True
        return bool(str(self.download_url or "").strip())


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
    """Raised when a MaaFW project package cannot be checked or applied.

    ``post_validate_rejected``：更新事务被 ``post_validate`` 回调（运行环境
    预检）拒绝，文件已回滚到旧版本，原因在 ``str(exc)`` 里。
    ``project_lock_busy``：限时内没拿到项目锁（另一次更新 / 预检在跑）。
    ``cancelled``：调用方置位了 ``cancel_event``，本次更新是被用户停掉的，
    不是失败——调用方据此换文案，别把「已中止」说成「更新失败」。
    """

    def __init__(
        self,
        message: str,
        *,
        provider_error_code: int | None = None,
        unsafe_to_continue: bool = False,
        post_validate_rejected: bool = False,
        project_lock_busy: bool = False,
        cancelled: bool = False,
    ) -> None:
        super().__init__(message)
        self.provider_error_code = provider_error_code
        self.unsafe_to_continue = unsafe_to_continue
        self.post_validate_rejected = post_validate_rejected
        self.project_lock_busy = project_lock_busy
        self.cancelled = cancelled


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


def _format_package_size(size: int | None) -> str:
    """把包大小说成人话，接在 ``found …`` 那行后面；没有大小就什么都不加。

    359MB 全量包在直连 GitHub 下要几十分钟，用户看到「发现更新」之后那段
    静默里最该知道的就是「要下多大」。GitHub 资产元数据里必有 size，
    Mirror 酱有时也给。
    """

    if not size or size <= 0:
        return ""
    return f", {size / (1024 * 1024):.1f} MB"


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
        # abort a download/apply transaction. 但要留痕：这里吞掉过
        # ``no running event loop``，只剩一句「…失败」根本查不到。
        logger.warning("MaaFW 更新进度回调失败: stage=%s", stage, exc_info=True)


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
    precheck_gate: Callable[[str], Awaitable[str | None]] | None = None,
    project_lock_already_held: bool = False,
    project_lock_timeout: float | None = None,
    cancel_event: threading.Event | None = None,
    github_mirror_urls: Callable[[str], Sequence[tuple[str, str]]] | None = None,
) -> MaaFWProjectUpdateResult:
    """检查并按需应用项目更新。

    ``post_validate``：新文件落地后、清单写入前在 apply 工作线程里被调，返回
    False 或抛异常都让事务回滚（运行环境预检挂在这里）。
    ``precheck_gate``：确认有新版本之后、去要下载地址之前被 await 一次，收目标
    版本号，返回非空字符串就按「有更新但不可安装」跳过（原因即该串）——给
    运行前自动更新读上次预检备忘用；手动更新不传，也就忽略备忘。
    ``project_lock_timeout``：拿项目锁的限时；None 为不限时（自动路径）。
    ``cancel_event``：用户停止任务时置位，下载会在一个 chunk 内停下并抛
    ``cancelled=True`` 的 :class:`MaaFWProjectUpdateError`；apply 线程一旦起来
    就只能让它自己回滚完，所以取消只在下载与起线程之前生效。
    ``github_mirror_urls``：下载地址 → ``(名字, 加速地址)`` 列表，只对 GitHub
    源生效。镜像清单与开关都在宿主侧（``tools/embedded/update_mirrors.py``），
    核心包只管按顺序试。
    """

    send_update_log = send_log or (lambda _: None)
    current_version = interface_model.version or ""
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

    # 上次事务若在中间态被杀（预检把 post_validating 拉长到分钟级，进程随时
    # 可能没了），目录里是新文件、清单却没写：版本比对会判「已是最新」，从此
    # 既不更新也不回滚。进入发现之前先把它退回去。没有中间态记录时是空操作。
    try:
        await asyncio.to_thread(
            recover_interrupted_update,
            project_path,
            send_log=send_update_log,
            project_lock_already_held=project_lock_already_held,
            project_lock_timeout=project_lock_timeout,
        )
    except UpdateApplyError as exc:
        message = f"MaaFW project update failed: {_sanitize_log_message(str(exc))}"
        send_update_log(message)
        _report_progress(
            progress,
            "failed",
            status="recovery_failed",
            message=message,
            final=True,
        )
        raise MaaFWProjectUpdateError(
            str(exc),
            unsafe_to_continue=exc.unsafe_to_continue,
            project_lock_busy=isinstance(exc, UpdateProjectLockBusy),
        ) from exc

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
        if prefer_full:
            send_update_log("本地无可信更新基线，改为请求全量包")

        async def baseline_still_matches() -> bool:
            # 有清单也不等于项目没变：M9A 的 agent 每次启动都热更新
            # data/activity/*.json，指纹一变差量包同样会在 apply 阶段被拒。
            # 全项目哈希要 ~2s，所以不在这里算，而是交给发现流程在「确认有
            # 新版本、且要带 CDK 向 Mirror酱 要差量包」那一刻才算。
            matches = await asyncio.to_thread(
                update_baseline_matches_project, project_path
            )
            if not matches:
                send_update_log(
                    "项目内容与更新基线不一致（脚本自行热更新或手动改过文件），"
                    "差量包无法套用，改为请求全量包"
                )
            return matches

        (
            discovery,
            version_check,
            skipped_reason,
        ) = await _discover_project_update_detailed(
            interface_model,
            current_version=current_version,
            source_config=merged_source_config,
            proxy=proxy,
            send_log=send_update_log,
            prefer_full_package=prefer_full,
            baseline_matches=None if prefer_full else baseline_still_matches,
            precheck_gate=precheck_gate,
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
        # 全量 / 差量在这一步就定了（apply 的 plan_validated 只是再确认一遍），
        # 前端要在下载阶段就能标出包类型。
        package_type=(
            discovery.candidate.package_type
            if discovery.candidate is not None
            else None
        ),
    )

    if not discovery.installable:
        reason = discovery.unavailable_reason or "更新源没有返回可安装的下载地址"
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
        f"found MaaFW project update: {current_version} -> {candidate.version} "
        f"({candidate.source}{_format_package_size(candidate.size)})"
    )
    # 项目指纹要 rglob + sha256 整个项目（M9A 660MB 约 1s），只在真有候选
    # 更新时算，由 apply_maafw_project_update 算一次并绑定到 plan 上。
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
            project_lock_timeout=project_lock_timeout,
            cancel_event=cancel_event,
            github_mirror_urls=github_mirror_urls,
        )
    except Exception as exc:
        if getattr(exc, "cancelled", False):
            # 用户点的停止：断点留着、项目没动，说「失败」会让人以为坏了。
            message = "MaaFW project update cancelled"
            send_update_log(message)
            _report_progress(
                progress,
                "failed",
                status="cancelled",
                message=message,
                final=True,
            )
            raise
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

    (
        discovery,
        _version_check,
        _skipped_reason,
    ) = await _discover_project_update_detailed(
        interface_model,
        current_version=current_version,
        source_config=source_config,
        proxy=proxy,
        send_log=send_log,
        prefer_full_package=prefer_full_package,
        version_only=version_only,
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
    baseline_matches: Callable[[], Awaitable[bool]] | None = None,
    precheck_gate: Callable[[str], Awaitable[str | None]] | None = None,
) -> tuple[
    MaaFWProjectUpdateDiscovery | None,
    MaaFWMirrorChyanVersionCheck | None,
    str | None,
]:
    """Return ``(discovery, mirror_version_check, skipped_reason)``.

    ``discovery`` is ``None`` when nothing newer exists; ``mirror_version_check``
    is ``None`` only when MirrorChyan was never queried (no rid), so callers can
    still surface the CDK status for an up-to-date project.

    ``baseline_matches`` 只在「确认有新版本、要带 CDK 向 Mirror酱 拿差量包」之前
    被调用一次；返回 False 就改要全量包。它是懒的，因为算项目指纹要 ~2s，
    而绝大多数运行前检查的结果是「已是最新」。

    ``precheck_gate`` 在确认有新版本之后、分流下载源之前被 await 一次（收目标
    版本号）；返回非空字符串就以它为由按「有更新但不可安装」返回。放在这个
    位置是因为再往后 Mirror 酱那次带 CDK 的查询会扣额度、GitHub 会打 Release
    API——上次预检已经证明装不上的版本，不该再花这些。
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
    send_update_log("MirrorChyan platform: win/x86_64")
    # 日志里绝不出现 CDK 明文，连前几位都不打。
    if mirror_cdk:
        send_update_log("MirrorChyan CDK: 已配置")

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

    if precheck_gate is not None:
        gate_reason = str(await precheck_gate(latest) or "").strip()
        if gate_reason:
            return unavailable(gate_reason)

    # 下载源由用户在脚本配置里显式选定，**不做自动分流**。选 Mirror 酱就必须
    # 自己填 CDK；CDK 缺失或不可用时明确报出原因，不悄悄换成 GitHub——用户得
    # 知道自己在从哪下载，出问题才查得动。
    requested = _requested_package_source(config)

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
                    source="mirrorchyan",
                    version=latest,
                    to_version=latest,
                    url_deferred=True,
                ),
            )
            return (
                _attach_version_check(discovery, version_check, current),
                version_check,
                None,
            )

        # 确认要从 Mirror 酱下载了，才带 CDK 查第二次拿一次性下载地址。
        # 这一次才可能扣今日下载额度，而它对应一次真实下载。
        prefer_full = prefer_full_package
        if not prefer_full and baseline_matches is not None:
            # 差量包只有在项目与基线指纹完全一致时才装得上，到这一步才值得
            # 花那 ~2s 去比。
            prefer_full = not await baseline_matches()
        send_update_log("已确认有新版本，携带 CDK 获取 Mirror酱 下载地址")
        authorized = await _query_mirrorchyan_latest(
            interface_model,
            current_version=current,
            mirror_cdk=mirror_cdk,
            channel=channel,
            proxy=proxy,
            prefer_full=prefer_full,
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
            "Mirror酱"
            if discovery.package_source == "mirrorchyan"
            else "GitHub Release"
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
    project_lock_timeout: float | None = None,
    cancel_event: threading.Event | None = None,
    github_mirror_urls: Callable[[str], Sequence[tuple[str, str]]] | None = None,
) -> dict[str, Any]:
    send_update_log = send_log or (lambda _: None)
    download_url = str(candidate.download_url or "").strip()
    if not download_url:
        raise MaaFWProjectUpdateError("update provider did not return a download URL")

    # 加速镜像只对 GitHub 源有意义：Mirror 酱发的是一次性签名地址，套前缀
    # 只会把签名打坏。拿不到清单不是错误，直连照跑。
    alternates: Sequence[tuple[str, str]] = ()
    if github_mirror_urls is not None and str(
        candidate.source or ""
    ).strip().casefold().startswith("github"):
        try:
            alternates = tuple(github_mirror_urls(download_url))
        except Exception:
            logger.warning("MaaFW 更新镜像清单获取失败，改为直连", exc_info=True)
            alternates = ()

    root = project_path.resolve()
    if cancel_event is not None and cancel_event.is_set():
        raise MaaFWProjectUpdateError(CANCELLED_MESSAGE, cancelled=True)
    # 这一步要 rglob + sha256 整个项目，大项目一两分钟且全程无输出——
    # 「发现更新」之后的静默有一半在这里，先说一声再算。
    send_update_log("正在计算项目指纹（大项目可能要一两分钟）")
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
            cancel_event=cancel_event,
            alternates=alternates,
            expected_size=candidate.size,
        )
        operation.update(
            "downloaded",
            packagePath=str(downloaded.path),
            sha256=downloaded.sha256,
            downloadedBytes=downloaded.size,
            totalBytes=downloaded.total_bytes,
            resumedFromBytes=downloaded.resumed_from,
        )
        if cancel_event is not None and cancel_event.is_set():
            # 最后一次能干净停下的机会：线程一起，回滚就必须跑完，
            # 半途放手留下的是新旧混杂的树。
            operation.update("cancelled", downloadedBytes=downloaded.size)
            raise MaaFWProjectUpdateError(CANCELLED_MESSAGE, cancelled=True)
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
            project_lock_timeout=project_lock_timeout,
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
    except UpdateDownloadCancelled as exc:
        # 必须排在下面那个 ``except Exception`` 之前，否则「已中止」会被
        # 包成一条普通的更新失败。
        raise MaaFWProjectUpdateError(str(exc), cancelled=True) from exc
    except UpdateApplyError as exc:
        # 预检拒绝与锁忙都要在宿主侧认得出来：前者只发一次 warning、后者回
        # 409；其它 apply 失败仍是 error。原因文本原样带在 message 里。
        raise MaaFWProjectUpdateError(
            str(exc),
            unsafe_to_continue=exc.unsafe_to_continue,
            post_validate_rejected=isinstance(exc, UpdatePostValidateRejected),
            project_lock_busy=isinstance(exc, UpdateProjectLockBusy),
        ) from exc
    except MaaFWProjectUpdateError:
        raise
    except Exception as exc:
        raise MaaFWProjectUpdateError(str(exc)) from exc


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
    if not prefer_full:
        # prefer_full 时不带 current_version：MirrorChyan 的 current_version 是差量包
        # 的计算基准（文档标为「推荐」而非必填），不给它就没法算差量，返回的是
        # 全量包。项目没有可信基线、或基线指纹已对不上时必须走这条路——差量包在
        # _validate_plan_base 里对不上 projectFingerprint 会被拒。为什么要全量由
        # 调用方在决定 prefer_full 时记日志，这里不重复。
        params["current_version"] = current_version
    # os / arch 一律带上，不看 interface.json 的 mirrorchyan_multiplatform：
    # 该字段只是发布方给打包器的提示，MAA_Punish 这类分平台发布的项目根本没写它，
    # 而 Mirror 酱对分平台 rid 不带 os/arch 直接回 8001「资源不存在」，运行前
    # 更新检查就整条失败。实测单平台 rid（AUTO_MAS）多带这两个参数照常回 200，
    # os=win&arch=x86_64 与 windows/x64 都被服务端接受并归一；这里沿用 GitHub
    # 资产命名的那套写法。
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
        shell_hint = _shell_from_rid_value(str(interface_model.mirrorchyan_rid or ""))
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
