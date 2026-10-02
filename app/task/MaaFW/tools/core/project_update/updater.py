from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Mapping, Sequence
from urllib.parse import quote

import httpx
from packaging import version

from app.utils.constants import MIRROR_ERROR_INFO

from ..interface.models import MaaFWInterface
from ..log_redact import mask_home_path
from .apply import (
    UpdateApplyError,
    _check_disk_space,
    _find_package_root,
    _read_interface_version,
    _safe_extract_zip,
    zip_entry_stats,
)
from .contracts import normalise_sha256
from .payloads import (
    ORIGIN_PACKAGE,
    PROJECTION_CHECK_FIELD,
    PayloadCancelled,
    PayloadError,
    PayloadTarget,
    RegisterResult,
    build_from_package,
    finalize,
    inherited_projection_revision,
    manifest_files,
    projection_revision_of,
    read_lineage,
    register,
    remove_tree,
    version_newer,
)
from .projection import PROJECTION_REVISION, abandoned_native_runtime_files
from .projection_heal import format_size
from .range_delta import (
    FORCE_FULL_PACKAGE_ENV,
    RangeDeltaCancelled,
    RangeDeltaUnavailable,
    RangeSpeedGuard,
    fetch_range_delta,
    force_full_package,
    is_github_download,
    open_range_delta,
)
from .state import (
    DEFAULT_CACHE_ROOT,
    DEFAULT_OPERATION_ROOT,
    UpdateOperationStore,
    redact_text,
)
from .timing import StageTimer, format_duration, format_megabytes
from .transport import (
    CANCELLED_MESSAGE,
    UpdateDownloadCancelled,
    download_resumable,
)

if TYPE_CHECKING:  # 导入 runtime_pool 会连带整个运行池包，选包时才导入
    from ..runtime_pool.architecture import ArchitectureTarget

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
    # 这次登记出来的新载荷，以及登记后该组（谱系 + 渠道）的 latest；视图切换按后者。
    payload_id: str | None = None
    latest_id: str | None = None

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
    预检）拒绝，新版本已丢弃、视图没动，原因在 ``str(exc)`` 里。
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


def _stale_projection_message(manifest: Mapping[str, Any]) -> str:
    """按旧投影规则建的载荷改要全量包时的日志：如实说明是否核对过、缺多少（``projectionCheck``）。"""

    record = manifest.get(PROJECTION_CHECK_FIELD)
    record = record if isinstance(record, Mapping) else {}
    reason = str(record.get("reason") or "").strip()
    suffix = f"（上次检查：{reason}）" if reason else ""
    missing = int(record.get("missingCount") or 0)
    if missing:
        return (
            f"当前版本按旧规则安装，查出漏装 {missing} 个文件但没补上{suffix}，"
            "改为请求全量包"
        )
    if record:
        return f"当前版本按旧规则安装，是否漏装文件还没核对成{suffix}，改为请求全量包"
    return "当前版本按旧规则安装，还没核对过是否漏装文件，改为请求全量包"


def _range_delta_blocker(payload: PayloadTarget) -> str:
    """当前载荷不走区间差量的原因（空串 = 可以走）。

    与「改要全量包」的三种情况同一判据（damaged、旧投影规则、旧布局原生库残留），但不分
    载荷来源：区间比的是实际字节，本地导入的载荷也能走；这三种首个版本先保守，照旧下整包。
    """

    try:
        manifest = payload.manifest()
    except PayloadError as exc:
        return f"当前版本的清单读不了（{exc}）"
    if projection_revision_of(manifest) < PROJECTION_REVISION:
        return "当前版本按旧投影规则安装"
    try:
        damaged = payload.payload_id in {
            str(item) for item in read_lineage(payload.root, payload.lineage)["damaged"]
        }
    except (OSError, PayloadError):
        damaged = False
    if damaged:
        return "当前版本有共用文件被改写过"
    files = manifest_files(manifest)
    if abandoned_native_runtime_files(
        [rel for rel, entry in files.items() if entry["origin"] != ORIGIN_PACKAGE],
        [rel for rel, entry in files.items() if entry["origin"] == ORIGIN_PACKAGE],
    ):
        return "当前版本里留着新包不再使用的旧布局原生库"
    return ""


def _host_update_target() -> ArchitectureTarget:
    """本机选包用的架构参数（Mirror 酱 os/arch、GitHub 资产架构段）。

    只从 ``runtime_pool.architecture.host_architecture()`` 取；不是 x64 时按「只支持 x64」
    报错，不悄悄按 x64 去下包。
    """

    from ..runtime_pool.architecture import (
        MaaFWUnsupportedArchitectureError,
        supported_architecture_target,
    )

    try:
        return supported_architecture_target()
    except MaaFWUnsupportedArchitectureError as exc:
        raise MaaFWProjectUpdateError(str(exc)) from None


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
    projection: bool = False,
    cancel_event: threading.Event | None = None,
    github_mirror_urls: Callable[[str], Sequence[tuple[str, str]]] | None = None,
    payload: PayloadTarget | None = None,
    after_register: Callable[[RegisterResult], Awaitable[Any]] | None = None,
) -> MaaFWProjectUpdateResult:
    """检查并按需更新项目：发现 → 下载一次 → 在 staging 里从当前载荷 + 包建新载荷 →
    预检 → 并入共用库 → 登记。项目视图在这里一个字节都不动。

    ``payload``：触发脚本当前挂的载荷（谱系、渠道、staging 与共用库，宿主按视图标记
    组装）。差量 / 全量只看它：当前载荷是更新得来的（``source.kind=update``）才要
    差量包，本地导入的一律要全量包。
    ``post_validate``：新载荷在 staging 里建好后被调（工作线程），收 staging 路径，
    返回 False 或抛异常都让这次更新作废、staging 丢弃（运行环境预检挂在这里）。
    ``after_register``：登记之后、发 ``completed`` 之前 await 一次，收登记结果——宿主
    在这里把触发脚本的视图切过去、把同组空闲脚本同步过去。
    ``precheck_gate``：确认有新版本之后、去要下载地址之前被 await 一次，收目标
    版本号，返回非空字符串就按「有更新但不可安装」跳过（原因即该串）——给
    运行前自动更新读上次预检备忘用；手动更新不传，也就忽略备忘。
    ``cancel_event``：用户停止任务时置位。下载会在一个 chunk 内停下；下载完成之后
    到登记之前，构建 / 预检 / 入库在步骤之间检查令牌，停下时丢掉 staging（没有要
    回滚的东西）；**登记之后不再响应取消**，切换做完再返回。一律抛
    ``cancelled=True`` 的 :class:`MaaFWProjectUpdateError`。
    ``github_mirror_urls``：下载地址 → ``(名字, 加速地址)`` 列表，只对 GitHub
    源生效。镜像清单与开关都在宿主侧（``tools/embedded/update_mirrors.py``），
    核心包只管按顺序试。``projection`` / ``project_lock_*`` 只为签名兼容留着：
    新载荷恒按投影白名单落地，互斥由宿主的谱系锁负责。
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

    if payload is not None:
        # 比较基准 = max(视图版本, 构建基准载荷的版本)。宿主在视图没能同步到组 latest
        # （被占用）时会把基准换成 latest：再拿视图的旧版本去比，会把组里已有的版本
        # 重新下一遍。
        try:
            base_version = str(payload.manifest().get("version") or "").strip()
        except PayloadError:
            base_version = ""
        if base_version and version_newer(base_version, current_version):
            send_update_log(f"本项目已登记 {base_version}，以它为基准检查更新")
            current_version = base_version
    send_update_log("start checking MaaFW project update")
    send_update_log(f"current version: {current_version}")
    send_update_log(f"update channel: {update_channel}")
    del project_lock_already_held, project_lock_timeout, projection

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
        # 差量包只能套在「更新器装的那一版」上：当前载荷是更新得来的（清单逐文件
        # 记着包内哈希、指纹就是它现在的指纹——载荷不可变）才要差量包；本地导入的
        # 载荷没有发布方基线，一律要全量包。
        prefer_full = True
        damaged = False
        stale_projection = False
        native_residue = False
        if payload is not None:
            try:
                base_manifest = payload.manifest()
            except PayloadError:
                base_manifest = {}
            source_kind = str((base_manifest.get("source") or {}).get("kind") or "")
            prefer_full = source_kind != "update"
            # 按旧投影规则建、漏装的文件又没补上的载荷：差量包只动包里那几个文件，套上去
            # 新版本照样缺；全量包的条目全部按当前规则投影。
            stale_projection = (
                not prefer_full
                and projection_revision_of(base_manifest) < PROJECTION_REVISION
            )
            if stale_projection:
                prefer_full = True
                send_update_log(_stale_projection_message(base_manifest))
            # 写穿巡检标过 damaged 的载荷：差量基线（清单）已与盘上内容不符，套差量会把
            # 被改写的文件原样带进新版本，只能整版重建。
            if not prefer_full:
                try:
                    damaged = payload.payload_id in {
                        str(item)
                        for item in read_lineage(payload.root, payload.lineage)[
                            "damaged"
                        ]
                    }
                except (OSError, PayloadError):
                    damaged = False
            if damaged:
                prefer_full = True
                send_update_log("当前版本有共用文件被改写过，改为请求全量包")
            # 换过外壳的导入目录留下的旧布局原生库（本修复之前的全量包会把它原样带进
            # 新载荷）：差量包不会删它，只有全量包按新包清单清得掉。用上一个包自己的清单
            # 当「下一个全量包」来判，清完之后同样的判断不再成立，不会每次都要全量包。
            if not prefer_full:
                base_files = manifest_files(base_manifest)
                native_residue = bool(
                    abandoned_native_runtime_files(
                        [
                            rel
                            for rel, entry in base_files.items()
                            if entry["origin"] != ORIGIN_PACKAGE
                        ],
                        [
                            rel
                            for rel, entry in base_files.items()
                            if entry["origin"] == ORIGIN_PACKAGE
                        ],
                    )
                )
                if native_residue:
                    prefer_full = True
                    send_update_log(
                        "当前版本里留着新包不再使用的旧布局原生库，改为请求全量包以清掉它"
                    )
        if prefer_full and not damaged and not stale_projection and not native_residue:
            send_update_log("当前版本是本地导入的，改为请求全量包")
        force_full = force_full_package()
        if force_full:
            prefer_full = True
            send_update_log(
                f"已设环境变量 {FORCE_FULL_PACKAGE_ENV}=1：一律请求全量包、不按区间差量"
            )

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
    if not candidate.plan_id:
        candidate.plan_id = uuid.uuid4().hex
    # GitHub 源的全量包先试按区间只取变化的文件（#1118）：当前载荷被迫要全量包的三种
    # 情况（damaged、旧投影规则、旧布局原生库残留）首个版本先保守，照旧下整包。
    range_delta = False
    if (
        payload is not None
        and not force_full
        and str(candidate.source or "").strip().casefold().startswith("github")
        and candidate.package_type in {None, "", "full"}
    ):
        blocker = await asyncio.to_thread(_range_delta_blocker, payload)
        if blocker:
            send_update_log(f"{blocker}，不按区间差量，下载全量包")
        else:
            range_delta = True
    try:
        apply_result = await apply_maafw_project_update(
            project_path.resolve(),
            candidate,
            proxy=proxy,
            send_log=send_update_log,
            progress=progress,
            post_validate=post_validate,
            cancel_event=cancel_event,
            github_mirror_urls=github_mirror_urls,
            payload=payload,
            after_register=after_register,
            range_delta=range_delta,
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
        payload_id=str(apply_result.get("payloadId") or "") or None,
        latest_id=str(apply_result.get("latestId") or "") or None,
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

    ``prefer_full_package``：调用方按当前载荷的来源定（本地导入的载荷没有发布方基线，
    只能要全量包）。

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
    target = _host_update_target()
    send_update_log(
        f"MirrorChyan platform: {target.mirrorchyan_os}/{target.mirrorchyan_arch}"
    )
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
    projection: bool = False,
    cancel_event: threading.Event | None = None,
    github_mirror_urls: Callable[[str], Sequence[tuple[str, str]]] | None = None,
    payload: PayloadTarget | None = None,
    after_register: Callable[[RegisterResult], Awaitable[Any]] | None = None,
    range_delta: bool = False,
) -> dict[str, Any]:
    """下载一次 → 在 staging 里建新载荷 → 预检 → 并入共用库 → 登记 → ``after_register``。

    staging 之外什么都不改：失败 / 预检不过 / 取消都只是丢掉 staging，当前载荷与
    所有视图原样不动，所以没有备份、回滚与中断恢复。登记之后不再响应取消。

    ``range_delta``：GitHub 发行包先试按区间只取变化的文件（``range_delta.py``），拼成
    虚拟全量包后照全量包建新载荷，结果与整包下载逐字节一致。区间这一路任何一步失败
    （停止除外）都丢掉这一批，接着照常下整包（整包可以走加速镜像，区间只直连）。
    """

    del project_lock_already_held, project_lock_timeout, projection
    send_update_log = send_log or (lambda _: None)
    download_url = str(candidate.download_url or "").strip()
    if not download_url:
        raise MaaFWProjectUpdateError("update provider did not return a download URL")
    if payload is None:
        raise MaaFWProjectUpdateError("项目还没有登记版本（视图没有标记），无法更新")

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

    def is_cancelled() -> bool:
        return cancel_event is not None and cancel_event.is_set()

    if is_cancelled():
        raise MaaFWProjectUpdateError(CANCELLED_MESSAGE, cancelled=True)
    effective_plan_id = str(candidate.plan_id or uuid.uuid4().hex)
    candidate.plan_id = effective_plan_id
    operation_id = uuid.uuid4().hex
    target_version = candidate.to_version or candidate.version
    operation = UpdateOperationStore.create(
        root=DEFAULT_OPERATION_ROOT,
        operation_id=operation_id,
        projectPath=str(project_path),
        planId=effective_plan_id,
        expectedFingerprint="",
        source=candidate.source,
        targetVersion=target_version,
        packageType=candidate.package_type or "",
        scriptId=str(script_id or payload.by or "").strip(),
    )
    # 各段用时：每段结束的日志带用时，收尾打一行汇总；失败 / 取消时说停在哪一段。
    # send_update_log 在两条路径上都既给用户看、又进 app.log（手动更新面板 / 任务日志）。
    timer = StageTimer()

    def log_stopped(exc: BaseException) -> None:
        # 段与段之间（找包根、读版本号）停下的，算在刚结束的那一段上。
        stage = timer.current or timer.last or "准备"
        verb = (
            "中止"
            if isinstance(exc, (PayloadCancelled, UpdateDownloadCancelled))
            or getattr(exc, "cancelled", False)
            else "失败"
        )
        send_update_log(
            f"更新已在「{stage}」阶段{verb}，本次已用时 {format_duration(timer.elapsed())}"
        )

    suffix = uuid.uuid4().hex[:8]
    staging_root = Path(payload.staging_root)
    extract_dir = staging_root / f"pkg-{payload.lineage}-{suffix}"
    # 区间差量拼虚拟全量包的目录，与整包解压目录分开：里面没变的文件是旧载荷 / 共用库同一
    # inode 的硬链接，区间失败后要是没删干净，整包解压往同名文件里 ``open("wb")`` 就是原地
    # 截断旧载荷。整包永远解压到 extract_dir 这个从没被区间用过的新目录。
    range_dir = staging_root / f"rpk-{payload.lineage}-{suffix}"
    staging = staging_root / f"payload-{payload.lineage}-{suffix}"
    expected_version = str(target_version or "").strip()

    # 区间差量：拼好的虚拟全量包（包内相对路径 → range_dir 下的文件）；None = 照常下整包。
    range_entries: dict[str, Path] | None = None
    range_transferred = 0
    range_takeover: frozenset[str] = frozenset()
    if range_delta:
        try:
            range_result = await _range_delta_package(
                download_url,
                candidate,
                payload,
                range_dir,
                target_version=str(target_version or ""),
                proxy=proxy,
                send_log=send_update_log,
                progress=progress,
                operation_id=operation.operation_id,
                timer=timer,
                cancelled=is_cancelled,
                mirrored=bool(alternates),
                mirror_fallback=bool(alternates)
                and normalise_sha256(candidate.sha256) is not None,
            )
        except RangeDeltaCancelled as exc:
            log_stopped(exc)
            await _discard_range_dir(range_dir, send_update_log)
            _finish_operation(operation, "cancelled")
            raise MaaFWProjectUpdateError(CANCELLED_MESSAGE, cancelled=True) from exc
        if range_result is not None:
            range_entries, range_transferred, range_takeover = range_result
            operation.update(
                "downloaded",
                mode="range",
                downloadedBytes=range_transferred,
                totalBytes=candidate.size,
            )

    downloaded = None
    if range_entries is None:
        timer.start("下载")
        try:
            downloaded = await download_resumable(
                source=candidate.source,
                version=target_version,
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
        except UpdateDownloadCancelled as exc:
            # 必须排在下面那个 ``except Exception`` 之前，否则「已中止」会被
            # 包成一条普通的更新失败。
            log_stopped(exc)
            _finish_operation(operation, "cancelled")
            raise MaaFWProjectUpdateError(str(exc), cancelled=True) from exc
        except MaaFWProjectUpdateError as exc:
            log_stopped(exc)
            _finish_operation(
                operation,
                "cancelled" if getattr(exc, "cancelled", False) else "failed",
                error=str(exc)[:500],
            )
            raise
        except Exception as exc:
            # 下载阶段失败也记终态：流水不停在 discovered，启动期清理一视同仁。
            log_stopped(exc)
            _finish_operation(operation, "failed", error=str(exc)[:500])
            raise MaaFWProjectUpdateError(str(exc)) from exc
        timer.finish()
    downloaded_bytes = downloaded.size if downloaded is not None else range_transferred
    if is_cancelled():
        send_update_log(
            f"更新已在「下载」之后中止，本次已用时 {format_duration(timer.elapsed())}"
        )
        await _remove_tree_in_thread(extract_dir)
        await _discard_range_dir(range_dir, send_update_log)
        _finish_operation(operation, "cancelled", downloadedBytes=downloaded_bytes)
        raise MaaFWProjectUpdateError(CANCELLED_MESSAGE, cancelled=True)

    def emit(stage: str, data: dict[str, Any]) -> None:
        _report_progress(progress, stage, operation_id=operation.operation_id, **data)

    def check_cancel() -> None:
        if is_cancelled():
            raise PayloadCancelled("update cancelled")

    def on_build_event(stage: str, data: dict[str, Any]) -> None:
        """``build_from_package`` 的阶段事件：照常转成进度，顺带收段、打带用时的日志。"""

        if stage == "plan_validated":
            elapsed = timer.finish()
            kind = "全量包" if data.get("packageType") == "full" else "差量包"
            if range_entries is not None:
                # 按全量包的语义建，对外仍报差量（前端显示「增量」）。
                kind = "区间差量（按全量包建新版本）"
                data = {**data, "packageType": "delta"}
            send_update_log(
                f"比对完成：{kind}，包内 {data.get('packageFiles', 0)} 个文件，"
                f"删除 {data.get('staleFiles', 0)} 个旧文件，用时 {format_duration(elapsed)}"
            )
            timer.start("复制旧版本")
            send_update_log("正在从当前版本复制出新版本骨架")
        elif stage == "staged":
            elapsed = timer.finish()
            send_update_log(
                f"新版本骨架已复制：{data.get('stagedFiles', 0)} 个文件，"
                f"用时 {format_duration(elapsed)}"
            )
            # 「正在套用更新包 x/y」由进度事件出（面板状态行 / 任务日志），这里不再单打一行。
            timer.start("套用更新包")
        emit(stage, data)

    def build_package(package_root: Path, unpacked: Path) -> Any:
        timer.start("比对")
        send_update_log("正在比对新旧版本文件")
        built = build_from_package(
            payload.manifest(),
            payload.directory(),
            package_root,
            unpacked,
            staging,
            blob_store=payload.blob_store,
            private=payload.private_paths,
            send_log=send_update_log,
            on_event=on_build_event,
            expected_package_type=(
                candidate.package_type
                if candidate.package_type in {"full", "delta"}
                else None
            ),
            target_version=target_version,
            cancelled=is_cancelled,
            package_entries=range_entries,
            takeover_dirs=range_takeover,
        )
        elapsed = timer.finish()
        send_update_log(
            f"套用更新包完成：{built.applied_files} 个文件，用时 {format_duration(elapsed)}"
        )
        actual = _read_interface_version(staging, strict=True).strip()
        if expected_version and actual.lstrip("vV") != expected_version.lstrip("vV"):
            raise PayloadError(
                "updated MaaFW interface version does not match the planned target"
            )
        return built, actual

    def build() -> Any:
        if range_entries is not None:
            # 区间差量已在 range_dir 里拼好了虚拟全量包，条目表就是整包的白名单。
            return build_package(range_dir, range_dir)
        timer.start("解压")
        staging_root.mkdir(parents=True, exist_ok=True)
        entry_files, expanded = zip_entry_stats(downloaded.path)
        # 解压一份、新载荷里包内条目再落一份（大文件多半进共用库，只占一次）。
        _check_disk_space(
            staging_root,
            staging_root,
            state_required=expanded,
            project_required=expanded,
        )
        extract_dir.mkdir(parents=True, exist_ok=True)
        send_update_log(
            f"正在解压更新包：{entry_files} 个文件，解压后约 {format_megabytes(expanded)}"
        )
        extracted = _safe_extract_zip(
            downloaded.path,
            extract_dir,
            progress=lambda data: emit("extracting", data),
            check_cancel=check_cancel,
            send_log=send_update_log,
        )
        elapsed = timer.finish()
        send_update_log(
            f"解压完成：{extracted.files} 个文件 / {format_megabytes(extracted.bytes)}，"
            f"用时 {format_duration(elapsed)}"
        )
        return build_package(_find_package_root(extract_dir), extract_dir)

    registered: RegisterResult | None = None
    try:
        built, actual_version = await asyncio.to_thread(build)
        # 解压目录里剩下的（没被挪进新载荷的）可能还有几百 MB：删在工作线程里，不在事件
        # 循环上同步删——那会冻住 WS 推送与界面，看起来又像卡死。用时只进汇总行。
        timer.start("清理解压目录")
        await asyncio.to_thread(
            remove_tree, range_dir if range_entries is not None else extract_dir
        )
        timer.finish()
        if is_cancelled():
            raise PayloadCancelled("update cancelled")
        emit("post_validating", {})
        if post_validate is not None:
            timer.start("预检")
            send_update_log("正在预检新版本的运行环境")
            # 回调（运行环境预检）失败的原因必须原样带出去：调用方要据此分
            # 「binding 拿不到」与其它失败、写备忘、给用户看文案。
            try:
                verdict = await asyncio.to_thread(post_validate, staging)
            except Exception as exc:
                if is_cancelled():
                    raise PayloadCancelled("update cancelled") from exc
                send_update_log(f"预检未通过，用时 {format_duration(timer.finish())}")
                raise MaaFWProjectUpdateError(
                    str(exc).strip() or type(exc).__name__,
                    post_validate_rejected=True,
                ) from exc
            if verdict is False:
                send_update_log(f"预检未通过，用时 {format_duration(timer.finish())}")
                raise MaaFWProjectUpdateError(
                    "MaaFW post-validation rejected the update",
                    post_validate_rejected=True,
                )
            send_update_log(f"预检通过，用时 {format_duration(timer.finish())}")
        if is_cancelled():
            raise PayloadCancelled("update cancelled")
        timer.start("并入共用库")
        send_update_log("正在把新版本的大文件并入共用库")
        finalized = await asyncio.to_thread(
            finalize,
            staging,
            blob_store=payload.blob_store,
            private=payload.private_paths,
            # 逐文件之间可停：每个文件的入库本身是原子的（硬链接 + os.replace），停在中间
            # 只会留下「已入库、staging 丢掉后只剩库里一个链接」的完整 blob，启动期回收收走。
            check_cancel=check_cancel,
        )
        send_update_log(
            f"并入共用库完成：新入库 {finalized.ingested_files} 个文件 / "
            f"{format_megabytes(finalized.ingested_bytes)}，"
            f"用时 {format_duration(timer.finish())}"
        )
        # 最后一个能干净停下的点：再往下就是登记，之后不再响应取消。
        if is_cancelled():
            raise PayloadCancelled("update cancelled")
        timer.start("生成清单")
        send_update_log("正在为新版本生成文件清单（大项目可能要一两分钟）")
        registered = await asyncio.to_thread(
            lambda: register(
                payload.root,
                staging,
                lineage=payload.lineage,
                channel=payload.channel,
                source={
                    "kind": "update",
                    "ref": _public_package_source(candidate.source)
                    or str(candidate.source or ""),
                    **({"mode": "range"} if range_entries is not None else {}),
                },
                by=payload.by,
                version=actual_version,
                lineage_info=payload.lineage_info,
                known_hashes=finalized.hashes,
                origins=built.origins,
                projection_revision=inherited_projection_revision(
                    payload.manifest(), built.plan.package_type
                ),
            )
        )
    except PayloadCancelled as exc:
        log_stopped(exc)
        await _remove_tree_in_thread(staging)
        _finish_operation(operation, "cancelled", downloadedBytes=downloaded_bytes)
        raise MaaFWProjectUpdateError(CANCELLED_MESSAGE, cancelled=True) from exc
    except MaaFWProjectUpdateError as exc:
        log_stopped(exc)
        await _remove_tree_in_thread(staging)
        _finish_operation(operation, "failed", error=str(exc)[:500])
        raise
    except (PayloadError, UpdateApplyError) as exc:
        log_stopped(exc)
        await _remove_tree_in_thread(staging)
        _finish_operation(operation, "failed", error=str(exc)[:500])
        raise MaaFWProjectUpdateError(str(exc)) from exc
    except Exception as exc:
        log_stopped(exc)
        await _remove_tree_in_thread(staging)
        _finish_operation(operation, "failed", error=str(exc)[:500])
        raise MaaFWProjectUpdateError(str(exc)) from exc
    finally:
        # 取消 / 失败时解压目录多半是整包大小；成功路径上面已经删过，这里是空操作。
        await _remove_tree_in_thread(extract_dir)
        await _discard_range_dir(range_dir, send_update_log)

    manifest_files = registered.manifest.get("files")
    send_update_log(
        f"文件清单已生成并登记：{len(manifest_files) if isinstance(manifest_files, Mapping) else 0}"
        f" 个文件，用时 {format_duration(timer.finish())}"
    )
    send_update_log(f"新版本构建总用时 {timer.summary()}")
    # 流水记到终态：启动期清理只收终态 / 本进程之前的记录，不让目录越攒越多。
    _finish_operation(operation, "registered", payloadId=registered.payload_id)
    emit("committed", {"payloadId": registered.payload_id})
    send_update_log(
        f"新版本已登记：{registered.payload_id}"
        + ("" if registered.created else "（与本机已有的同一版本内容相同，复用）")
    )
    if after_register is not None:
        # 登记之后不再响应取消：切换约 2 s，做完再返回。钩子自己的失败只记日志——
        # 载荷已在册，没切过去的视图下次运行前的组同步会补上，不算更新失败。
        try:
            await after_register(registered)
        except Exception:
            logger.warning("MaaFW 新版本登记后的切换失败", exc_info=True)
            send_update_log("新版本已登记，但切换脚本时出错；下次运行前会再同步")
    return {
        "operationId": operation.operation_id,
        "planId": effective_plan_id,
        "status": "committed",
        # 区间差量按全量包建（projectionRevision 照全量记），对外报差量。
        "packageType": (
            "delta" if range_entries is not None else built.plan.package_type
        ),
        "finalFingerprint": str(registered.manifest.get("fingerprint") or ""),
        "targetVersion": actual_version,
        "resumedFrom": downloaded.resumed_from if downloaded is not None else 0,
        "payloadId": registered.payload_id,
        "latestId": registered.target_id,
        "created": registered.created,
    }


async def _range_delta_package(
    download_url: str,
    candidate: MaaFWProjectUpdateCandidate,
    payload: PayloadTarget,
    package_dir: Path,
    *,
    target_version: str,
    proxy: httpx.Proxy | None,
    send_log: Callable[[str], None],
    progress: ProgressCallback | None,
    operation_id: str,
    timer: StageTimer,
    cancelled: Callable[[], bool],
    mirrored: bool = False,
    mirror_fallback: bool = False,
) -> tuple[dict[str, Path], int, frozenset[str]] | None:
    """GitHub 发行包按区间只取变化的文件，在 ``package_dir`` 里拼出虚拟全量包。

    返回 ``(条目表, 实际下载字节, 整体接管的目录)``；用不了（不在 github.com、服务端不认 Range、区间不符、
    CRC 错、超预算、超时……）丢掉 ``package_dir`` 返回 None，调用方照常下整包。用户停止
    抛 :class:`RangeDeltaCancelled`。``mirrored``：配置了 GitHub 加速镜像（区间不走镜像，
    要在日志里说一声，免得以为镜像没生效）。``mirror_fallback``：退回时整包真能走镜像（有镜像
    且资产有 sha256，与 ``transport.download_resumable`` 同一判据）——只有这时才设直连速度保护
    （:class:`RangeSpeedGuard`），没有更快的路可退时直连下整包只会更慢，不放弃区间。
    """

    if not is_github_download(download_url):
        send_log("发行包不在 github.com 上，不按区间差量，下载全量包")
        return None
    staging_root = package_dir.parent
    delta = None
    started = time.monotonic()
    speed_guard = RangeSpeedGuard() if mirror_fallback else None
    if speed_guard is not None:
        route_note = (
            "（区间只直连 github.com，不走加速镜像；没做成再按镜像下整包；直连按需下载预计"
            f"超过 {format_duration(speed_guard.budget)}"
            f"（或花在网络上的时间超过 {format_duration(speed_guard.hard_limit)}）就放弃区间）"
        )
    elif mirrored:
        route_note = (
            "（区间只直连 github.com；资产没有 sha256，整包也不走镜像，不按速度放弃区间"
            "（读取超时仍会退回整包））"
        )
    else:
        route_note = "（没有可用的加速镜像，不按速度放弃区间（读取超时仍会退回整包））"
    try:
        timer.start("区间比对")
        send_log(
            f"正在按区间读取 GitHub 发行包的文件目录，比对哪些文件变了{route_note}"
        )
        await asyncio.to_thread(staging_root.mkdir, parents=True, exist_ok=True)
        delta = await asyncio.to_thread(
            lambda: open_range_delta(
                download_url,
                int(candidate.size or 0),
                old_manifest=payload.manifest(),
                old_payload_dir=payload.directory(),
                lineage=payload.lineage,
                target_version=target_version,
                workdir=staging_root,
                proxy=proxy,
                cancelled=cancelled,
                send_log=send_log,
                speed_guard=speed_guard,
            )
        )
        send_log(
            f"按区间只取变化的 {len(delta.fetch)} 个文件（{format_size(delta.fetch_bytes)}，"
            f"计划传输 {format_size(delta.planned_bytes)}，含文件目录与合并的间隙），"
            f"其余 {len(delta.reuse)} 个沿用当前版本；读文件目录 "
            f"{format_size(delta.transferred)}，用时 {format_duration(timer.finish())}"
        )
        timer.start("区间下载")
        await asyncio.to_thread(
            _check_disk_space,
            staging_root,
            staging_root,
            state_required=delta.fetch_expanded,
            project_required=delta.fetch_expanded,
        )

        def report(done: int, total: int) -> None:
            _report_progress(
                progress,
                "downloading",
                status="running",
                downloaded_bytes=done,
                total_bytes=total,
                package_type="delta",
                operation_id=operation_id,
            )

        entries = await asyncio.to_thread(
            fetch_range_delta,
            delta,
            package_dir,
            cancelled=cancelled,
            progress=report,
        )
        send_log(
            f"区间下载完成：实际下载 {format_size(delta.transferred)}"
            f"（整包 {format_size(delta.size)}，{delta.reader.requests} 次请求），"
            f"用时 {format_duration(timer.finish())}"
        )
        # 只进 app.log 的一行汇总（与投影补齐同一写法）：日志包里据此认得出走了区间。
        logger.info(
            "MaaFW 区间差量：载荷 %s → %s，下载主机 %s，%d 次请求，读 %s / 整包 %s，"
            "复用 %d、取回 %d",
            payload.payload_id,
            target_version,
            delta.reader.final_host or "未知",
            delta.reader.requests,
            format_size(delta.transferred),
            format_size(delta.size),
            len(delta.reuse),
            len(delta.fetch),
        )
        return entries, delta.transferred, delta.takeover_dirs
    except RangeDeltaCancelled:
        raise
    except Exception as exc:  # noqa: BLE001 - 区间这一路任何失败都退回整包
        if not isinstance(exc, (RangeDeltaUnavailable, UpdateApplyError)):
            logger.warning("MaaFW 区间差量出错，改下全量包", exc_info=True)
        stage = timer.current or timer.last or "区间比对"
        timer.finish()
        where = f"停在「{stage}」，用时 {format_duration(time.monotonic() - started)}"
        if delta is not None:
            # 读中央目录就失败时 delta 还没建出来，只说得出阶段与用时。
            where += (
                f"，已从远端读 {format_size(delta.transferred)}、"
                f"{delta.reader.requests} 次请求"
            )
            await asyncio.to_thread(delta.close)
            delta = None
        await _discard_range_dir(package_dir, send_log)
        # 异常原文可能带路径（staging、旧载荷）或 URL：用户目录换成 <HOME>、URL 去掉查询串。
        reason = mask_home_path(
            redact_text(_sanitize_log_message(str(exc).strip() or type(exc).__name__))
        )
        send_log(f"按区间差量没做成（{reason}；{where}），改为下载全量包")
        # 前面的区间进度带着 package_type=delta，transport 的下载事件不带类型、宿主会沿用
        # 上一次的：先报一条全量，面板才不会把整包下载标成「增量」。
        _report_progress(
            progress,
            "downloading",
            status="running",
            downloaded_bytes=0,
            total_bytes=candidate.size,
            package_type="full",
            operation_id=operation_id,
        )
        return None
    finally:
        if delta is not None:
            await asyncio.to_thread(delta.close)


async def _discard_range_dir(path: Path, send_log: Callable[[str], None]) -> None:
    """删区间差量拼虚拟全量包的目录；删不掉（被占用）就说清楚，留给启动期清理。

    里面没变的文件是旧载荷 / 共用库的硬链接，只能摘目录项，绝不能再往里写：整包退回
    解压到另一个新目录（``pkg-*``），不碰这里。
    """

    await _remove_tree_in_thread(path)
    if await asyncio.to_thread(os.path.lexists, path):
        send_log(
            mask_home_path(
                f"区间差量的临时目录没删掉（{path}），留待下次启动时清理；"
                "整包会解压到另一个新目录，不受影响"
            )
        )


def _finish_operation(
    operation: UpdateOperationStore, status: str, **fields: Any
) -> None:
    """更新流水记终态；记不上只打日志（它只是流水，不影响这次更新的结果）。"""

    try:
        operation.update(status, **fields)
    except Exception:  # noqa: BLE001
        logger.warning("MaaFW 更新流水写终态失败: %s", status, exc_info=True)


async def _remove_tree_in_thread(path: Path) -> None:
    """在工作线程里删 staging / 解压目录（上万个文件要删好几秒，不能卡住事件循环）。

    ``to_thread`` 一调用就把删除交给了线程池：这里的 await 即使被取消，删除也会照常做完。
    """

    await asyncio.to_thread(remove_tree_quietly, path)


def remove_tree_quietly(path: Path) -> None:
    try:
        remove_tree(path)
    except OSError:
        logger.warning("MaaFW 更新 staging 清理失败，留待启动时清理: %s", path)


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
    target = _host_update_target()
    params["os"] = target.mirrorchyan_os
    params["arch"] = target.mirrorchyan_arch

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
    timeout: float = 30.0,
) -> MaaFWProjectUpdateDiscovery | None:
    """Fetch the exact MirrorChyan-selected version from GitHub Releases.

    ``timeout`` is per request; the projection heal check passes a shorter one
    because it runs synchronously before a task starts.

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
        proxy=proxy, follow_redirects=True, timeout=timeout
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
            _host_update_target().github_asset_pattern, re.IGNORECASE
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
