#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""魔改 AVD 更新器：查更新，「更新」一键下载、拼新版、核对、换上，启动恢复。

本模块是更新引擎，调用 ``status`` / ``update`` / ``startup`` 须显式传入 ``UpdateHost``；
MAS 应用入口统一使用 :mod:`app.core.emulator_manager.update`，由宿主装配配置、实例查询和进度发布。

流程（每个根目录各走各的）：

1. **查更新**：按 :func:`.update_source.update_sources` 的顺序问（先 Mirror 酱，查不到或出错再问
   GitHub；MAS 设置的「更新源」选了 GitHub 时只问 GitHub），一律不带 CDK，只拿版本和 release_note。
   界面上点「检查更新」时强制查一次；结果缓存 4 小时，更新源设置一改就作废。失败写在状态里，不弹窗。
2. **更新**（:func:`update`）：本根目录有实例开着或正在开机就直接拒绝、请用户先关掉，什么都不动；
   界面在用户确认「更新期间不会启动用到这个魔改 AVD 的脚本和实例」后才调。开始以后到结束（成功、
   失败都算）这个根目录一律不许开机（:func:`update_in_progress`，``manager._launch`` 据此拒绝），依次
   - 再查一次最新版本（不走缓存）；
   - 选包（:func:`_pick_package`），优先顺序：「更新源」不是 GitHub 又填了 Mirror 酱 CDK（MAS 全局的
     ``Update.MirrorChyanCDK``）→ Mirror 酱（本地正好是起点时要增量包）；否则 → GitHub 按区间增量；
     不行 → GitHub 整包。CDK 过期、无效、次数用完、不含此资源，或 Mirror 酱出错时给出提示、改走
     GitHub（同样先试按区间增量；8001「这个平台没有包」不提示）。「更新源」选 GitHub 时填了 CDK 也不用；
   - **Mirror 酱省 CDK**：消耗 CDK 的是「带 CDK 要下载链接」这一步，每次点「更新」最多要一次。要到的链接
     只在内存里记（:class:`_MirrorLink`，不写 state.json、日志、状态接口），25 分钟内同一根目录、同一
     目标版本的下一次「更新」直接复用、不再要；超时或 MAS 重启作废。下载失败（含 403/404/410）只算
     失败：同一链接从头重下最多 3 次，仍不行这次就结束，不另要链接；下到的包 sha256 不对、增量包拼出来
     核对不过，作废这个链接，这次改走 GitHub，也不再向 Mirror 酱要；
   - GitHub 按区间增量（:mod:`.update_range`）：读包的中央目录，和根目录逐文件比 CRC32 + 大小，只取回
     变了的条目、没变的从本地复制。服务器不认 Range、变了的太多（取回量超过整包 40% 或 3000 个文件）、
     拼好后核对不过或任何异常，都丢掉这一批改下整包（只退这一次）；已经有下了一半的整包时直接续传整包；
   - 整包 / Mirror 酱的包下到 ``<根>\\.update\\download``（同盘），按发布记录 / Mirror 酱给的 SHA-256
     核对。GitHub 断了下次续传；Mirror 酱不支持续传，断了在同一个链接上从头重下（最多 3 次）；
   - 整包解到 ``pkg``；增量包按本地清单抄现有文件、按 ``changes.json`` 删改加，拼成整包的样子。然后按
     清单逐文件核对（旧版包没有清单，靠包的 SHA-256 + zip CRC），``sdk\\emulator`` 改名进 ``stage``
     （:mod:`.update_stage`）。Mirror 酱的包核对不过就丢掉，改走 GitHub（只退这一次）；
   - 换上。换上前再按进程查一次（挡 MAS 之外手动开的模拟器），还有程序开着模拟器文件就不换，
     停在「已下载好」，下次再点直接换上，不重新下载。
   有 MAS 任务在跑不再挡更新：开着的实例一开始就拒绝，更新中开机一律被拒，跑着的任务也开不了这个
   根目录的实例（那一步会失败并写明原因），用别的模拟器的任务不受影响。
3. **启动恢复**：MAS 启动时（主定时器之前）按 ``state.json`` 补完或退回上次没做完的换上。

设了 ``sdkRoot``（开发用的本地 SDK）的根目录不更新。进度经主 WebSocket 推
（``id=EmulatorManager``、``type=emulator2.avd-update.progress``），界面另用 HTTP 快照兜底。

CDK 只放进 Mirror 酱的请求参数：日志、错误信息、``state.json``、状态快照里都没有它；Mirror 酱的下载地址
（一次性）也不写进 ``state.json``，日志里只记主机名。
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import time
import zipfile
import zlib
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.services.common.update import transport as _service_update_transport
from app.utils import get_logger
from app.utils import update_files as _utils_update_files

from . import update_range
from . import update_stage as stage
from .components import (
    MetadataUnreadable,
    local_sdk_root,
    read_metadata_strict,
    root_key,
)
from .constants import (
    MIN_MOD_AVD_BUILD,
    UPDATE_CHECK_CACHE_SECONDS,
    UPDATE_MIN_FREE_BYTES,
)
from .update_source import (
    GITHUB_SOURCE,
    MIRROR_NO_PACKAGE,
    MIRROR_SOURCE,
    GitHubReleaseSource,
    MirrorChyanError,
    MirrorChyanSource,
    ModAvdVersion,
    RemoteRelease,
    UpdateSourceError,
    automas_too_old,
    display_version,
    github_api_url,
    local_version,
    mirror_api_root,
    parse_version,
    update_sources,
)

logger = get_logger("魔改 AVD 更新")

#: 查更新失败后多久之内不再自动重试（用户点「更新」不受限）。
_CHECK_FAILURE_BACKOFF_SECONDS = 600.0
#: 一个下载地址最多试几次（含第一次）：GitHub 每次接着续传；Mirror 酱不支持续传，每次从头下，
#: 不管什么错（含 403/404/410）都不另要链接（要一次链接就消耗一次 CDK）。同 MAS 本体
#: ``services/update.py`` 的 ``_download_update_locked``：同一地址重试 3 次，中途不换地址。
_DOWNLOAD_ATTEMPTS = 3
_DOWNLOAD_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
#: 进度消息最密多久发一条。
_PUBLISH_INTERVAL_SECONDS = 0.5
#: 要到的 Mirror 酱下载链接复用多久（秒）：服务端留 30 分钟（resource-backend ``logic/version.go`` 的
#: ``GetDistributeURL``），留出余量。
_MIRROR_LINK_REUSE_SECONDS = 25 * 60


@dataclass
class UpdateProgress:
    """推给界面的进度：``stage`` 是当前在做的事，``status`` 是 running / success / failed / idle。"""

    stage: str = "idle"
    status: str = "idle"
    message: str = ""
    percent: float | None = None
    downloadedBytes: int | None = None
    totalBytes: int | None = None
    speedBytesPerSec: float | None = None


@dataclass(frozen=True)
class UpdateSettings:
    """宿主当前的更新策略；凭据不进入状态快照或对象表示。"""

    github_only: bool
    automas_version: str
    mirror_cdk: str = field(repr=False)


@dataclass(frozen=True)
class UpdateHost:
    """更新器所需的宿主能力，不持有配置总管、管理器或消息总线。"""

    settings: Callable[[], UpdateSettings]
    proxy: Callable[[], httpx.Proxy | None]
    managed_roots: Callable[[], list[Path]]
    running_instances: Callable[[Path], list[str]]
    opening_instances: Callable[[Path], list[str]]
    publish_progress: Callable[[Path, UpdateProgress], Awaitable[None]]


@dataclass
class _MirrorLink:
    """要到的 Mirror 酱下载链接：要来的那一版（链接、目标版本、增量 / 全量、大小、sha256 都在 ``release``
    里）和要到的时间。只在内存里，不写 state.json、日志和状态接口。"""

    release: RemoteRelease
    at: float


class _Runtime:
    """一个根目录在本进程里的更新状态：同一时刻只跑一次更新。"""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.lock = asyncio.Lock()
        self.job: asyncio.Task[None] | None = None
        self.progress = UpdateProgress()
        self.published_at = 0.0
        #: 上次没做完的换上已经按 ``state.json`` 收拾过（拿着 ``lock`` 做，见 :func:`_ensure_recovered`）
        self.recovered = False
        #: 这次更新没按首选来下的原因（CDK 过期、增量包核对不过……），显示在进度和结果里
        self.notice = ""
        #: 要到、还没用完的 Mirror 酱下载链接（25 分钟内同一目标版本复用，见 :func:`_reusable_link`）
        self.mirror_link: _MirrorLink | None = None

    @property
    def busy(self) -> bool:
        return self.job is not None and not self.job.done()


_runtimes: dict[str, _Runtime] = {}
#: 正在更新的根目录（从点「更新」开始到结束，成功失败都算）：这段时间不许开机，
#: 用到它的脚本也就不会在更新中途启动它。
_updating: set[str] = set()

_remote: RemoteRelease | None = None
_remote_at = 0.0
_remote_failed_at = 0.0
_remote_error = ""
#: 上面这份缓存是在哪种更新源设置下查的（宿主 ``settings().github_only`` 的值）；设置一改就作废。
_remote_github_only: bool | None = None
_check_lock = asyncio.Lock()


def _runtime(root: Path) -> _Runtime:
    key = root_key(root)
    runtime = _runtimes.get(key)
    if runtime is None:
        runtime = _runtimes[key] = _Runtime(root)
    return runtime


# ---- 进度 ------------------------------------------------------------------


def _set(
    runtime: _Runtime,
    stage_name: str,
    status: str = "running",
    message: str = "",
    **fields: Any,
) -> None:
    runtime.progress = UpdateProgress(
        stage=stage_name, status=status, message=message, **fields
    )


async def _publish(runtime: _Runtime, *, force: bool = True, host: UpdateHost) -> None:
    now = time.monotonic()
    if not force and now - runtime.published_at < _PUBLISH_INTERVAL_SECONDS:
        return
    runtime.published_at = now
    await host.publish_progress(runtime.root, runtime.progress)


def _thread_progress(
    runtime: _Runtime, stage_name: str, message: str, *, host: UpdateHost
) -> stage.Progress:
    """给线程里的解包 / 核对用的进度回调：改进度，并按节流把消息投回事件循环发出去。"""
    loop = asyncio.get_running_loop()

    def report(done: int, total: int) -> None:
        _set(
            runtime,
            stage_name,
            message=message,
            percent=round(done * 100 / total, 1) if total else None,
            downloadedBytes=done,
            totalBytes=total,
        )
        now = time.monotonic()
        if now - runtime.published_at >= _PUBLISH_INTERVAL_SECONDS:
            runtime.published_at = now
            asyncio.run_coroutine_threadsafe(_publish(runtime, host=host), loop)

    return report


# ---- 根目录 ----------------------------------------------------------------


async def _managed(root: str, *, host: UpdateHost) -> Path:
    """只认 Emulator 2.0 里已经加进来的魔改 AVD 根目录：更新会改名目录，不能对任意路径动手。"""
    text = str(root or "").strip()
    if not text or not Path(text).is_absolute():
        raise ValueError("请给出魔改 AVD 根目录的完整路径")
    key = root_key(text)
    for managed in await asyncio.to_thread(host.managed_roots):
        if root_key(managed) == key:
            return managed
    raise ValueError(f"{text} 还没有作为魔改 AVD 加进模拟器管理，不能更新")


def _not_updatable_reason(root: Path) -> str:
    try:
        # mas-avd.json 读不出时看不到 sdkRoot，换上最后还要改它：先修好再更新
        read_metadata_strict(root)
    except MetadataUnreadable as e:
        return f"{e}，先修好或删掉它再更新"
    if local_sdk_root(root) is not None:
        return "这个根目录在 mas-avd.json 里设了 sdkRoot（开发用的本地 SDK），不更新"
    if not os.path.isfile(
        _utils_update_files.native_path(stage.emulator_dir(root) / "emulator.exe")
    ):
        return "这个根目录里没有 sdk\\emulator，请先放好魔改 AVD"
    return ""


def _ensure_updatable(root: Path) -> None:
    reason = _not_updatable_reason(root)
    if reason:
        raise ValueError(reason)


def update_in_progress(root: str | Path) -> bool:
    """这个根目录正在更新（从点「更新」开始到结束）：开机一律拒绝（``manager._launch``）。"""
    return root_key(root) in _updating


# ---- 查更新 ----------------------------------------------------------------


async def _latest(
    *, force: bool, current: ModAvdVersion | None = None, host: UpdateHost
) -> RemoteRelease:
    """最新一版。4 小时内查过就用缓存；查失败后 10 分钟内不自动重试（``force`` 例外）。

    ``current`` 是发起查询的根目录装着的版本（Mirror 酱的 ``current_version``）。各源依次问，前一个查不到
    或出错就问下一个。一律不带 CDK：只拿版本和 release_note，不要下载链接、不消耗 CDK。
    """
    global _remote, _remote_at, _remote_failed_at, _remote_error, _remote_github_only
    async with _check_lock:
        now = time.monotonic()
        github_only = host.settings().github_only
        if github_only != _remote_github_only:
            _remote, _remote_failed_at, _remote_error = None, 0.0, ""
            _remote_github_only = github_only
        if not force:
            if _remote is not None and now - _remote_at < UPDATE_CHECK_CACHE_SECONDS:
                return _remote
            if (
                _remote_failed_at
                and now - _remote_failed_at < _CHECK_FAILURE_BACKOFF_SECONDS
            ):
                if _remote is not None:
                    return _remote
                raise UpdateSourceError(_remote_error)
        errors: list[str] = []
        for source in update_sources(github_only=github_only):
            try:
                release = await source.latest(proxy=host.proxy(), current=current)
            except Exception as e:  # noqa: BLE001 - 一个源不行换下一个，全不行才报
                errors.append(f"{source.name}: {e}")
                logger.info(f"从 {source.name} 查 ModAVD 最新版本没成: {e}")
                continue
            _remote, _remote_at, _remote_failed_at, _remote_error = (
                release,
                time.monotonic(),
                0.0,
                "",
            )
            package = release.asset.name if release.asset else "下载前现要地址"
            logger.info(
                f"ModAVD 最新版本 {release.version.display}（tag {release.tag}，"
                f"来源 {release.source}，包 {package}）"
            )
            return release
        _remote_failed_at, _remote_error = time.monotonic(), "；".join(errors)
        raise UpdateSourceError(_remote_error)


def _shown(version: ModAvdVersion | None) -> str:
    """版本给人看的写法 ``0.32.1``；读不到时写「未知」。"""
    return version.display if version is not None else "未知"


def _newer(release: RemoteRelease | None, local: ModAvdVersion | None) -> bool:
    return release is not None and (local is None or release.version > local)


def _automas_block(release: RemoteRelease | None, *, host: UpdateHost) -> str:
    """这一版要求的 MAS 版本比当前高时，返回那个版本号。"""
    if release is None:
        return ""
    return (
        release.min_automas
        if automas_too_old(release.min_automas, host.settings().automas_version)
        else ""
    )


def _automas_refusal(release: RemoteRelease, *, host: UpdateHost) -> str:
    """这一版要求的 MAS 比当前新时给用户的那句话；不要求时返回空串。"""
    required = _automas_block(release, host=host)
    if not required:
        return ""
    return f"{release.version.display} 需要 AUTO-MAS {required} 或更新的版本，请先更新 AUTO-MAS"


def _staged_version(root: Path) -> str:
    """已经下好、核对过、比装着的新、等着换上的版本；没有返回空串。"""
    state = stage.read_state(root)
    version = parse_version((state.get("target") or {}).get("version"))
    if (
        state.get("phase") != stage.PHASE_STAGED
        or version is None
        or not stage.stage_emulator_dir(root).is_dir()
    ):
        return ""
    local = local_version(root)
    return str(version) if local is None or version > local else ""


# ---- 状态快照 --------------------------------------------------------------


def _snapshot_sync(
    root: Path, runtime: _Runtime, *, host: UpdateHost
) -> dict[str, Any]:
    local = local_version(root)
    reason = _not_updatable_reason(root)
    state = stage.read_state(root)
    release = _remote
    newer = not reason and _newer(release, local)
    return {
        "root": str(root),
        "updatable": not reason,
        "notUpdatableReason": reason,
        "currentVersion": str(local) if local else "",
        "currentBuild": local.label if local else "",
        "belowMinimum": local is None or local.build < MIN_MOD_AVD_BUILD,
        "minimumBuild": f"mas-{MIN_MOD_AVD_BUILD}",
        "minimumVersion": str(ModAvdVersion.of_build(MIN_MOD_AVD_BUILD)),
        "checkError": _remote_error,
        "latestVersion": str(release.version) if release else "",
        "latestBuild": release.version.label if release else "",
        "updateAvailable": newer,
        "requiredAutoMas": _automas_block(release, host=host) if newer else "",
        # Mirror 酱没给下载地址（没填 CDK）时不知道大小
        "assetSize": release.asset.size if release and release.asset else 0,
        "phase": state.get("phase", stage.PHASE_IDLE),
        "preparedVersion": _staged_version(root) if not reason else "",
        # 开着或正在开机的实例：有就不能更新（界面据此先提示关掉，不弹确认）
        "runningInstances": len(
            set(host.running_instances(root)) | set(host.opening_instances(root))
        )
        if not reason
        else 0,
        "busy": runtime.busy,
        "progress": asdict(runtime.progress),
        "lastResult": state.get("lastResult") or None,
    }


async def status(root: str, *, check: bool = False, host: UpdateHost) -> dict[str, Any]:
    """一个根目录的更新现状。``check`` 为真时（界面上的「检查更新」）先强制查一次最新版本（不走缓存、
    不带 CDK；查不到写在 ``checkError``，不算接口失败）。"""
    path = await _managed(root, host=host)
    if check and not _not_updatable_reason(path):
        try:
            current = await asyncio.to_thread(local_version, path)
            await _latest(force=True, current=current, host=host)
        except Exception as e:  # noqa: BLE001 - 查不到不算接口失败
            logger.warning(f"检查魔改 AVD 更新失败: {e}")
    return await asyncio.to_thread(_snapshot_sync, path, _runtime(path), host=host)


# ---- 选包 ------------------------------------------------------------------


def _add_notice(runtime: _Runtime, text: str) -> None:
    runtime.notice = f"{runtime.notice}；{text}" if runtime.notice else text


def _with_notice(runtime: _Runtime, text: str) -> str:
    return f"{runtime.notice}；{text}" if runtime.notice else text


def _download_label(release: RemoteRelease) -> str:
    """进度里写的「从哪下、下什么」。"""
    asset = release.asset
    assert asset is not None
    if release.source == MIRROR_SOURCE:
        if asset.incremental:
            return (
                f"从 Mirror 酱下载增量包（{display_version(asset.base)} → "
                f"{release.version.display}）"
            )
        return f"从 Mirror 酱下载全量包 {release.version.display}"
    return f"从 GitHub 下载 {asset.name}"


def _reusable_link(
    runtime: _Runtime, target: ModAvdVersion, local: ModAvdVersion | None
) -> RemoteRelease | None:
    """25 分钟内、同一目标版本、还比装着的新（增量包的起点还是装着的版本）的 Mirror 酱链接；
    不满足就作废、返回 ``None``。"""
    link = runtime.mirror_link
    if link is None:
        return None
    asset = link.release.asset
    if (
        asset is not None
        and time.monotonic() - link.at < _MIRROR_LINK_REUSE_SECONDS
        and link.release.version == target
        and (not asset.incremental or asset.base == str(local))
        and _newer(link.release, local)
    ):
        return link.release
    runtime.mirror_link = None
    return None


async def _pick_package(
    runtime: _Runtime, release: RemoteRelease, *, mirror: bool = True, host: UpdateHost
) -> RemoteRelease:
    """这次下哪个包，返回带下载链接的那一版。

    「更新源」不是 GitHub 又填了 CDK（且 ``mirror``）时用 Mirror 酱：25 分钟内要到过同一目标版本的链接就
    直接复用（:func:`_reusable_link`），否则带 CDK 要一次（这一步消耗 CDK，每次点「更新」最多一次）。
    本地正好是增量包的起点（根上的清单就是装着的版本）时带 ``current_version`` 要，可能给增量包；否则
    不带，只要全量包。Mirror 酱给不了（CDK 过期、无效、次数用完、不含此资源，或出错）就用 GitHub，原因
    记进 ``runtime.notice``；8001（这个平台没有包）不提示。「更新源」选 GitHub 时不用 CDK、不问 Mirror 酱。
    """
    root = runtime.root
    local = await asyncio.to_thread(local_version, root)
    github_only = host.settings().github_only
    cdk = "" if github_only else host.settings().mirror_cdk
    if cdk and mirror:
        reused = _reusable_link(runtime, release.version, local)
        if reused is not None:
            assert runtime.mirror_link is not None
            minutes = (time.monotonic() - runtime.mirror_link.at) / 60
            logger.info(
                f"{root} 复用 {minutes:.0f} 分钟前要到的 Mirror 酱下载链接，不再带 CDK 去要"
            )
            return reused
        patchable = await asyncio.to_thread(stage.patch_base_ok, root, local)
        try:
            picked = await MirrorChyanSource(cdk, mirror_api_root()).package(
                proxy=host.proxy(), current=local if patchable else None
            )
            if picked.asset is not None and picked.asset.incremental and not patchable:
                raise MirrorChyanError("没给全量包")
            if picked.asset is not None and _newer(picked, local):
                refusal = _automas_refusal(picked, host=host)
                if refusal:
                    raise RuntimeError(refusal)
                runtime.mirror_link = _MirrorLink(picked, time.monotonic())
                return picked
            logger.info(
                f"Mirror 酱这次没给比 {_shown(local)} 新的包（最新 {picked.version.display}），"
                "改用 GitHub"
            )
        except MirrorChyanError as e:
            if e.code != MIRROR_NO_PACKAGE:
                _add_notice(
                    runtime, str(e) if "Mirror 酱" in str(e) else f"Mirror 酱：{e}"
                )
            logger.info(f"{root} 这次不从 Mirror 酱下载（{e}），改用 GitHub")
    if release.source == GITHUB_SOURCE and release.asset is not None:
        github = release
    else:
        try:
            github = await GitHubReleaseSource(github_api_url()).latest(
                proxy=host.proxy()
            )
        except UpdateSourceError as e:
            if github_only:
                hint = "（更新源选的是 GitHub）"
            else:
                hint = "" if cdk else "（没有填 Mirror 酱 CDK 时只能从 GitHub 下载）"
            raise UpdateSourceError(f"{e}{hint}") from e
    if not _newer(github, local):
        raise RuntimeError(
            f"GitHub 上的最新版本是 {github.version.display}，不比装着的 {_shown(local)} 新"
        )
    refusal = _automas_refusal(github, host=host)
    if refusal:
        raise RuntimeError(refusal)
    return github


# ---- 下载与拼新版 ----------------------------------------------------------


def _error_text(e: BaseException) -> str:
    """下载出错的说明。HTTP 状态错误只写状态码：httpx 的消息里带完整地址（Mirror 酱的是一次性下载地址）。"""
    if isinstance(e, httpx.HTTPStatusError):
        return f"HTTP {e.response.status_code}"
    return f"{type(e).__name__}: {e}" if str(e) else type(e).__name__


async def _download(
    runtime: _Runtime, release: RemoteRelease, *, host: UpdateHost
) -> Path:
    """下载 ``release`` 的包，按发布记录 / Mirror 酱给的 SHA-256 核对。

    - GitHub：断了续传（``.part`` 留着，下次点「更新」接着下）。请求带了 Range 而服务器回 200 时，
      :func:`~app.services.common.update.transport.download_resumable` 从 0 重写，不追加。
    - Mirror 酱不支持续传：不发 Range，之前留下的半截直接丢掉从头下；中途断了（含 401/403/404/410）在
      同一个链接上从头重试，一共最多 :data:`_DOWNLOAD_ATTEMPTS` 次，仍不行这次就结束，不另要链接（下次
      点「更新」时链接还在 25 分钟内就复用）。两个来源的包名不同（Mirror 酱的带 ``-mirrorchyan``），半截
      的不会被另一边拿去续传。
    """
    root, asset = runtime.root, release.asset
    assert asset is not None
    mirror = release.source == MIRROR_SOURCE
    label = _download_label(release)
    folder = stage.download_dir(root)
    folder.mkdir(parents=True, exist_ok=True)
    final = folder / asset.name
    part = folder / f"{asset.name}.part"
    # 别的版本留下的包不再要了
    for child in folder.iterdir():
        if child.name in (final.name, part.name):
            continue
        if child.is_dir():
            stage.remove_tree(child)
        else:
            child.unlink(missing_ok=True)
    if final.is_file():
        if final.stat().st_size == asset.size and (
            not asset.sha256
            or await asyncio.to_thread(stage.file_sha256, final) == asset.sha256
        ):
            return final
        final.unlink()

    if mirror:
        part.unlink(missing_ok=True)
    received = max(part.stat().st_size, 0) if part.is_file() else 0
    window_bytes, window_start = 0, time.monotonic()
    speed: float | None = None

    async def on_bytes(count: int) -> None:
        nonlocal received, window_bytes, window_start, speed
        received = max(received + count, 0)
        window_bytes += max(count, 0)
        elapsed = time.monotonic() - window_start
        if elapsed >= 1:
            speed, window_bytes, window_start = (
                window_bytes / elapsed,
                0,
                time.monotonic(),
            )
        _set(
            runtime,
            "downloading",
            message=_with_notice(runtime, label),
            percent=round(received * 100 / asset.size, 1),
            downloadedBytes=received,
            totalBytes=asset.size,
            speedBytesPerSec=speed,
        )
        await _publish(runtime, force=False, host=host)

    # 地址只记主机名：Mirror 酱的下载地址是一次性的
    logger.info(
        f"开始{label}（{urlsplit(asset.url).netloc or '?'}，{asset.size} 字节，"
        f"已有 {received} 字节）"
    )
    url = asset.url
    digest: Any = None
    attempt = 0
    async with httpx.AsyncClient(
        proxy=host.proxy(),
        follow_redirects=True,
        timeout=_DOWNLOAD_TIMEOUT,
        headers={"User-Agent": "AutoMasGui"},
    ) as client:
        while True:
            attempt += 1
            if mirror and part.exists():
                # 从头下：不留半截，download_resumable 也就不发 Range
                part.unlink()
                received = 0
            digest = hashlib.sha256() if asset.sha256 else None
            try:
                size = await _service_update_transport.download_resumable(
                    client,
                    url,
                    part,
                    expected_size=asset.size,
                    on_bytes=on_bytes,
                    digest=digest,
                )
            except (httpx.HTTPError, OSError, ValueError) as e:
                if attempt >= _DOWNLOAD_ATTEMPTS:
                    # 不串上 httpx 的状态错误：它的消息里有完整地址
                    cause = None if isinstance(e, httpx.HTTPStatusError) else e
                    if mirror:
                        part.unlink(missing_ok=True)
                        raise RuntimeError(
                            "下载中断，再点一次更新会重新下载"
                            f"（从 Mirror 酱下载 {attempt} 次都没成：{_error_text(e)}）"
                        ) from cause
                    raise RuntimeError(
                        f"下载 {asset.name} 失败: {_error_text(e)}"
                    ) from cause
                again = "从头重下" if mirror else "续传"
                logger.warning(
                    f"下载 {asset.name} 出错，{attempt} 秒后{again}: {_error_text(e)}"
                )
                await asyncio.sleep(attempt)
                continue
            break
    if size != asset.size:
        raise RuntimeError(
            f"下载的 {asset.name} 大小不对（{size} / {asset.size} 字节）"
        )
    if asset.sha256 and digest is not None and digest.hexdigest() != asset.sha256:
        part.unlink(missing_ok=True)
        where = "Mirror 酱给的" if release.source == MIRROR_SOURCE else "发布记录的"
        raise stage.PackageError(
            f"下载的 {asset.name} 和{where} SHA-256 对不上，已删除，没有安装。请重试"
        )
    if not asset.sha256:
        logger.warning(
            f"{asset.name} 的发布记录里没有 SHA-256，只靠 zip 自带的 CRC 和清单核对"
        )
    os.replace(part, final)
    logger.info(f"{asset.name} 下载完成，SHA-256 核对通过")
    return final


def _verify_and_stage(
    root: Path, target: dict[str, Any], verifying: stage.Progress
) -> dict[str, Any]:
    """核对拼好的 ``pkg``（新写法版本必须有清单、逐文件比；模拟器的构建号与自编版标志），再把
    ``sdk\\emulator`` 改名进 ``stage``。不写状态，由调用方核对通过后写。"""
    version = parse_version(target["version"])
    assert version is not None
    verified = stage.verify_package(
        stage.pkg_dir(root), version, tag=target["tag"], progress=verifying
    )
    stage.build_stage(root, version)
    return {"verified": verified}


def _stage_sync(
    runtime: _Runtime,
    archive: Path,
    target: dict[str, Any],
    extracting: stage.Progress,
    verifying: stage.Progress,
) -> dict[str, Any]:
    """整包解包 / 增量包拼成整包的样子，再核对、拼 ``stage``（:func:`_verify_and_stage`）。"""
    root = runtime.root
    asset = target["asset"]
    if asset.get("incremental"):
        files = stage.build_patched_package(
            root,
            archive,
            parse_version(asset.get("base")),
            progress=extracting,
        )
    else:
        files = stage.extract_package(
            archive,
            stage.pkg_dir(root),
            top_dir=asset["topDir"],
            progress=extracting,
        )
    staged = _verify_and_stage(root, target, verifying)
    mode = "incremental" if asset.get("incremental") else "full"
    return {**staged, "files": files, "mode": mode}


def _mb(size: int) -> str:
    return f"{size / 1024**2:.1f} MB"


def _range_allowed(root: Path, release: RemoteRelease) -> bool:
    """GitHub 的整包才按区间取；已经有下好或下了一半的整包时直接用它（接着续传）。"""
    asset = release.asset
    if release.source != GITHUB_SOURCE or asset is None:
        return False
    folder = stage.download_dir(root)
    return not (
        (folder / asset.name).is_file() or (folder / f"{asset.name}.part").is_file()
    )


async def _stage_by_range(
    runtime: _Runtime,
    release: RemoteRelease,
    target: dict[str, Any],
    *,
    host: UpdateHost,
) -> dict[str, Any] | None:
    """GitHub 的整包按区间只取变了的文件（:mod:`.update_range`），没变的从本地复制，拼出和整包解出来一样的
    ``pkg``，再照样按新版清单逐文件核对、拼 ``stage``。

    服务器不认 Range、变了的太多（取回量超过整包的 40% 或 3000 个文件）、取回的数据不对、拼好后核对不过，
    或任何意外，都丢掉这一批、返回 ``None``，调用方改下整包（只退这一次）。
    """
    root = runtime.root
    asset = release.asset
    assert asset is not None
    pkg = stage.pkg_dir(root)
    try:
        async with httpx.AsyncClient(
            proxy=host.proxy(),
            follow_redirects=True,
            timeout=_DOWNLOAD_TIMEOUT,
            headers={"User-Agent": "AutoMasGui"},
        ) as client:
            plan = await update_range.plan_range(client, asset, root)
            label = f"从 GitHub 按区间下载 {len(plan.fetch)} 个文件（{_mb(plan.fetch_bytes)}）"
            logger.info(
                f"{root} 更新到 {release.version.display}：{label}，没变的 "
                f"{len(plan.copy)} 个从本地复制（整包 {_mb(asset.size)}）"
            )

            async def on_bytes(done: int, total: int) -> None:
                # 计划里每个条目按文件头余量估的长度，实际取回的会略多一点
                _set(
                    runtime,
                    "downloading",
                    message=_with_notice(runtime, label),
                    percent=min(round(done * 100 / total, 1), 100.0) if total else None,
                    downloadedBytes=min(done, total),
                    totalBytes=total,
                )
                await _publish(runtime, force=done == 0, host=host)

            await on_bytes(0, plan.fetch_bytes)
            await update_range.fetch_changed(client, plan, pkg, on_bytes=on_bytes)
        copying = "正在拼新版（没变的文件从本地复制）"
        _set(runtime, "extracting", message=copying)
        await _publish(runtime, host=host)
        await asyncio.to_thread(
            update_range.copy_unchanged,
            root,
            plan,
            pkg,
            _thread_progress(runtime, "extracting", copying, host=host),
        )
        staged = await asyncio.to_thread(
            _verify_and_stage,
            root,
            target,
            _thread_progress(runtime, "verifying", "正在按清单核对每个文件", host=host),
        )
        return {**staged, "files": len(plan.fetch) + len(plan.copy), "mode": "range"}
    except update_range.RangeUnavailable as e:
        logger.info(f"{root} 这次不按区间取，改下整包：{e}")
    except stage.PackageError as e:
        logger.warning(f"{root} 按区间拼出来核对不过，改下整包：{e}")
        _add_notice(runtime, "按区间拼出来核对不过，改下整包")
    except Exception as e:  # noqa: BLE001 - 区间这一路任何意外都退回整包
        logger.opt(exception=True).warning(f"{root} 按区间取出错，改下整包：{e}")
    # 状态这时是「正在准备」，丢掉半成品不会留下可以安装的东西
    await asyncio.to_thread(stage.remove_tree, pkg)
    await asyncio.to_thread(stage.remove_tree, stage.stage_emulator_dir(root).parent)
    return None


class _NothingToDo(Exception):
    """拿到锁以后发现前提已经不成立（已经是最新、没有要装的）。"""


#: 下好的包本身不对（zip 坏了、CRC 对不上、清单或内容核对不过）：这份下载不能再用
_BAD_PACKAGE_ERRORS = (stage.PackageError, zipfile.BadZipFile, zlib.error, EOFError)


def _discard_download(archive: Path) -> None:
    """丢掉核对不过的包，下次点「更新」重新下载。

    发布记录里没有 SHA-256 时，缓存只按大小认，不丢就会每次都拿这份坏包重试。
    """
    try:
        archive.unlink(missing_ok=True)
    except OSError as e:
        logger.warning(f"删除核对不过的 {archive} 失败，下次会重新核对: {e}")


async def _stage_release(
    runtime: _Runtime, release: RemoteRelease, *, host: UpdateHost
) -> dict[str, Any]:
    """下载 ``release`` 的包、拼好核对过，``state`` 停在 ``staged``，返回写进状态的 ``staged``。
    GitHub 的整包先试按区间只取变了的文件（:func:`_stage_by_range`），不行再下整包。

    动 ``pkg`` / ``stage`` 之前先把状态改成「正在准备」，核对通过、``stage`` 拼好后才写 ``staged``；
    中途失败（含 MAS 退出）都丢掉暂存、回到空闲（下载的包留着，下次接着下；包本身核对不过的才丢）。
    """
    root = runtime.root
    assert release.asset is not None
    target = release.as_dict()
    label = _download_label(release)
    unpack = "正在按增量包拼新版" if release.asset.incremental else "正在解包"
    await asyncio.to_thread(stage.begin_staging, root, target)
    archive: Path | None = None
    try:
        staged = None
        if await asyncio.to_thread(_range_allowed, root, release):
            staged = await _stage_by_range(runtime, release, target, host=host)
        if staged is None:
            _set(
                runtime,
                "downloading",
                message=_with_notice(runtime, label),
                totalBytes=release.asset.size,
            )
            await _publish(runtime, host=host)
            archive = await _download(runtime, release, host=host)
            _set(runtime, "extracting", message=unpack)
            await _publish(runtime, host=host)
            staged = await asyncio.to_thread(
                _stage_sync,
                runtime,
                archive,
                target,
                _thread_progress(runtime, "extracting", unpack, host=host),
                _thread_progress(
                    runtime, "verifying", "正在按清单核对每个文件", host=host
                ),
            )
        return await asyncio.to_thread(stage.finish_staging, root, target, staged)
    except BaseException as e:
        reason = "MAS 退出，没做完" if isinstance(e, asyncio.CancelledError) else str(e)
        # 断网、MAS 退出留着下载（.part 下次续传）；包本身核对不过的才丢
        if archive is not None and isinstance(e, _BAD_PACKAGE_ERRORS):
            await asyncio.shield(asyncio.to_thread(_discard_download, archive))
        await asyncio.shield(asyncio.to_thread(stage.abort_staging, root, reason))
        raise


async def _prepare(
    runtime: _Runtime, release: RemoteRelease, *, host: UpdateHost
) -> None:
    """选包、下载并拼好新版，结束时 ``state`` 停在 ``staged``。调用方拿着这个根目录的锁。

    Mirror 酱的包不对（sha256 对不上、增量包拼出来核对不过、包坏了）：丢掉暂存、作废这个链接，这次改走
    GitHub（先按区间增量，不行再整包），不再向 Mirror 酱要，只退这一次。
    """
    root = runtime.root
    state = await asyncio.to_thread(stage.read_state, root)
    if state.get("phase") == stage.PHASE_SWAPPING:
        raise RuntimeError("上一次换上还没收尾，请重启 MAS 后再试")
    # 上次没删完的先删（trash 里都是已经不要的），再看剩余空间
    await asyncio.to_thread(stage.purge_trash, root)
    free = (await asyncio.to_thread(shutil.disk_usage, root)).free
    if free < UPDATE_MIN_FREE_BYTES:
        left = await asyncio.to_thread(stage.trash_bytes, root)
        left_text = (
            f"{left / 1024**3:.2f} GB"
            if left >= 1024**3
            else f"{left / 1024**2:.1f} MB"
        )
        hint = (
            f"。另外 {stage.update_dir(root) / 'trash'} 里还占着 {left_text}，"
            "是之前要删、但文件被占用没删掉的，关掉占用它的程序（或重启电脑）后 MAS 会再删"
            if left
            else ""
        )
        raise RuntimeError(
            f"{root.anchor or root} 剩余空间 {free / 1024**3:.1f} GB，更新要临时占用约 "
            f"{UPDATE_MIN_FREE_BYTES / 1024**3:.1f} GB，请先清理{hint}"
        )
    picked = await _pick_package(runtime, release, host=host)
    try:
        staged = await _stage_release(runtime, picked, host=host)
    except _BAD_PACKAGE_ERRORS as e:
        if picked.source != MIRROR_SOURCE or picked.asset is None:
            raise
        runtime.mirror_link = None  # 这个链接给的包不对，作废
        kind = "增量包" if picked.asset.incremental else "包"
        logger.warning(f"{root} 的 Mirror 酱{kind}不对（{e}），这次改从 GitHub 下载")
        _add_notice(runtime, f"Mirror 酱的{kind}核对不过，改从 GitHub 下载")
        picked = await _pick_package(runtime, release, mirror=False, host=host)
        staged = await _stage_release(runtime, picked, host=host)
    # 包已经下好、核对过：链接用不着了
    runtime.mirror_link = None
    if staged["verified"] == "manifest":
        checked = "按清单逐文件核对"
    elif staged.get("mode") == "range":
        checked = "旧版包没有清单，按每个文件的 zip CRC 核对"
    else:
        checked = "旧版包没有清单，按 zip CRC 并核对了整包的 SHA-256"
    how = (
        "从 GitHub 按区间只取变了的"
        if staged.get("mode") == "range"
        else _download_label(picked)
    )
    logger.info(
        f"{root} 的 {picked.version.display} 已拼好（{how}，{staged['files']} 个文件，{checked}）"
    )


# ---- 换上 ------------------------------------------------------------------


async def _swap(runtime: _Runtime, *, host: UpdateHost) -> str:
    """换上拼好的新版，返回版本号。现在不能换就抛 :class:`~.update_stage.SwapBlocked`，暂存原样留着。

    更新期间 MAS 不会开这个根目录的实例（:func:`update_in_progress`），这里再查一次进程，挡的是 MAS
    之外手动开的模拟器；``swap_in`` 改名前还会按可执行文件路径再查一遍。
    """
    root = runtime.root
    running = await asyncio.to_thread(host.running_instances, root)
    if running:
        raise stage.SwapBlocked(
            f"还有 {len(running)} 台实例开着（不是 MAS 开的），请先关掉"
        )
    _set(runtime, "installing", message="正在换上新版")
    await _publish(runtime, host=host)
    return await asyncio.to_thread(stage.swap_in, root)


async def _ensure_recovered(runtime: _Runtime) -> None:
    """按 ``state.json`` 收拾上次没做完的换上，每个根目录只做一次。调用方拿着 ``runtime.lock``。

    启动恢复和更新用同一把锁、谁先到谁做：恢复不会把正在进行的这次更新当成上次的半截清掉，
    而后台初始化还没轮到恢复时用户就点了「更新」，也会先恢复再动手。
    """
    if runtime.recovered:
        return
    done = await asyncio.to_thread(stage.recover, runtime.root)
    runtime.recovered = True
    if done:
        logger.warning(f"{runtime.root} 的魔改 AVD 更新：{done}")


async def _update_job(
    runtime: _Runtime, release: RemoteRelease | None, *, host: UpdateHost
) -> None:
    """一次更新。调用方（:func:`update`）已经把根目录登记成「正在更新」，这里结束时（成功、失败、
    MAS 退出都算）撤掉。"""
    root = runtime.root
    try:
        await _run_update(runtime, release, host=host)
    finally:
        _updating.discard(root_key(root))


async def _run_update(
    runtime: _Runtime, release: RemoteRelease | None, *, host: UpdateHost
) -> None:
    root = runtime.root
    async with runtime.lock:
        runtime.notice = ""
        version = ""
        try:
            await _ensure_recovered(runtime)
            # 拿到锁之后重新判断：排队期间可能已经装上了别的版本、拼好了别的版本
            local = await asyncio.to_thread(local_version, root)
            version = await asyncio.to_thread(_staged_version, root)
            if (
                release is not None
                and _newer(release, local)
                and version != str(release.version)
            ):
                await _prepare(runtime, release, host=host)
                version = await asyncio.to_thread(_staged_version, root)
            if not version:
                raise _NothingToDo(f"已经是最新版本（{_shown(local)}）")
            installed = await _swap(runtime, host=host)
            done = f"已更新到 {display_version(installed)}"
            _set(
                runtime,
                "installed",
                "success",
                f"{done}（{runtime.notice}）" if runtime.notice else done,
            )
        except _NothingToDo as e:
            _set(runtime, "idle", "idle", str(e))
        except stage.SwapBlocked as e:
            shown = display_version(version)
            logger.info(f"{root} 的 {shown} 已下载好，这次没换上: {e}")
            _set(
                runtime,
                "staged",
                "failed",
                f"{shown} 已下载并核对好，但现在不能换上：{e}。处理好后再点「更新」直接换上，"
                "不用重新下载",
            )
        except Exception as e:  # noqa: BLE001 - 失败如实交给界面
            logger.opt(exception=True).warning(f"{root} 更新魔改 AVD 失败: {e}")
            failed = f"更新失败：{e}"
            _set(
                runtime,
                "failed",
                "failed",
                f"{failed}（{runtime.notice}）" if runtime.notice else failed,
            )
        await _publish(runtime, host=host)


def _action(
    reason: str, message: str, *, ok: bool = False, running: int = 0
) -> dict[str, Any]:
    return {
        "ok": ok,
        "reason": reason,
        "message": message,
        "runningInstances": running,
    }


async def update(root: str, *, host: UpdateHost) -> dict[str, Any]:
    """「更新」：查最新版、选包下载（Mirror 酱或 GitHub，整包或增量包）、拼新版、按清单核对，然后换上。
    立刻返回，进度看 WebSocket / 状态快照。

    本根目录有实例开着或正在开机就什么都不动，返回 ``instances_running``，请用户先关掉。开始以后到
    结束（成功、失败都算），这个根目录一律不许开机（:func:`update_in_progress`），用到它的脚本也就不会
    在更新中途把它开起来。已经下好、核对过的新版不重新下载；查不到最新版本时也照样换上它。
    """
    path = await _managed(root, host=host)
    _ensure_updatable(path)
    runtime = _runtime(path)
    if runtime.busy:
        return _action("busy", "正在更新，请稍候")
    local = await asyncio.to_thread(local_version, path)
    release: RemoteRelease | None = None
    check_error = ""
    try:
        release = await _latest(force=True, current=local, host=host)
    except Exception as e:  # noqa: BLE001 - 查不到时看有没有已经下好的
        logger.warning(f"检查魔改 AVD 更新失败: {e}")
        check_error = str(e)
    staged = await asyncio.to_thread(_staged_version, path)
    if release is not None and _newer(release, local):
        refusal = _automas_refusal(release, host=host)
        if refusal:
            return _action("automas_too_old", refusal)
    elif not staged:
        if release is None:
            return _action("check_failed", f"查不到最新版本：{check_error}")
        return _action("up_to_date", f"已经是最新版本（{_shown(local)}）")
    else:
        release = None  # 只换上已经下好的那一版
    running = await asyncio.to_thread(host.running_instances, path)
    # 从这里到 create_task 之间没有 await：再看一次有没有并发的更新，登记「正在更新」（之后开机一律被拒），
    # 再看有没有正在开机的。和开机（open 先登记自己、_launch 再看「正在更新」）互斥，两边总有一边看得见
    # 另一边；开着的实例上面已经按进程查过，开机要几十秒，查完到这里不会冒出一台开好的。
    if runtime.busy:
        return _action("busy", "正在更新，请稍候")
    busy = sorted(set(running) | set(host.opening_instances(path)))
    if busy:
        return _action(
            "instances_running",
            f"这个魔改 AVD 还有 {len(busy)} 台实例开着，请先关闭再更新",
            running=len(busy),
        )
    _updating.add(root_key(path))
    runtime.job = asyncio.create_task(
        _update_job(runtime, release, host=host), name=f"avd-update:{path}"
    )
    return _action("started", "已开始", ok=True)


# ---- 启动 ------------------------------------------------------------------


async def startup(*, host: UpdateHost) -> None:
    """MAS 启动时收拾上次没做完的换上（要在定时器拉起实例之前）。查更新等用户打开「管理与更新」时再查。"""
    roots = await asyncio.to_thread(host.managed_roots)
    for root in roots:
        runtime = _runtime(root)
        try:
            # 用户可能已经在界面上点了「更新」：等这个根目录的锁，不和正在进行的更新同时动手
            async with runtime.lock:
                await _ensure_recovered(runtime)
        except Exception as e:  # noqa: BLE001 - 一个根目录恢复失败不影响别的
            logger.opt(exception=True).error(f"{root} 的魔改 AVD 更新恢复失败: {e}")


__all__ = [
    "UpdateHost",
    "UpdateProgress",
    "UpdateSettings",
    "startup",
    "status",
    "update",
    "update_in_progress",
]
