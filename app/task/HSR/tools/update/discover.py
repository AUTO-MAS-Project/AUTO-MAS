"""版本发现：查最新版本并解析出下载地址。

Mirror 酱的免 CDK 接口是**所有下载源**的版本权威。自建站根据发布记录核对
目标版本并固定下载包。下载源只决定字节从哪来，不参与版本判断，
也**绝不自动分流**：选了 Mirror 酱而 CDK 不可用时报错跳过，不悄悄换成 GitHub。

唯一的例外是「用户选了 GitHub 而 Mirror 酱不可达」：此时回退查 GitHub 自己的
release 接口。字节仍来自用户选定的源，所以不违反上面那条。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import httpx
from packaging.version import InvalidVersion, Version

from app.services.common.update.transport import (
    MirrorResourceError,
    request_mirror_resource,
)
from app.utils import MIRROR_ERROR_INFO, format_exception_reason, get_logger

from ...task_mapping import engine_label
from .engines import EngineSpec, SourceId, select_asset_name

logger = get_logger("HSR 更新发现")

_GITHUB_API = "https://api.github.com"
_USER_AGENT = "AutoMasGui"
_TIMEOUT = 30.0

#: 这些码表示 CDK 本身有问题，但版本号仍然可用——照常上报「有新版」，
#: 只是标注不可安装，让用户知道该去续 CDK 而不是以为没更新。
_CDK_ERROR_CODES = frozenset({7001, 7002, 7003, 7004, 7005})


class HSRUpdateError(RuntimeError):
    """版本发现或下载准备阶段的可预期失败。"""


@dataclass(frozen=True)
class _LatestVersion:
    """保留版本信息与下载受阻原因，避免 CDK 错误在版本比较后丢失。"""

    version: str
    release_note: str = ""
    download_url: str = ""
    sha256: str = ""
    blocked_reason: str | None = None


@dataclass(frozen=True)
class UpdateCandidate:
    """一次可执行的更新。"""

    engine: str
    current_version: str | None
    latest_version: str
    source: SourceId
    asset_kind: str  # "7z" | "zip"
    download_url: str
    sha256: str = ""
    release_note: str = ""


@dataclass(frozen=True)
class DiscoveryResult:
    """版本发现的结论。``candidate`` 为空表示无需或无法更新。"""

    engine: str
    current_version: str | None
    latest_version: str | None
    update_available: bool
    candidate: UpdateCandidate | None = None
    #: 下载受阻原因（CDK 失效、源不给地址等），不因本地已是最新版而丢弃。
    blocked_reason: str | None = None

    @property
    def installable(self) -> bool:
        return self.candidate is not None


def is_newer(remote: str, current: str | None) -> bool:
    """比较版本。解析不了时保守地当作「没有新版」，不乱升级。"""

    try:
        remote_version = Version(str(remote).lstrip("v"))
        if not current:
            return True
        return remote_version > Version(str(current).lstrip("v"))
    except InvalidVersion:
        logger.warning(f"HSR 更新：无法解析版本 {remote!r} / {current!r}，跳过本次更新")
        return False


async def discover(
    spec: EngineSpec,
    *,
    current_version: str | None,
    source: SourceId,
    channel: str = "stable",
    cdk: str = "",
    proxy: httpx.Proxy | None = None,
    seven_zip_available: bool = False,
) -> DiscoveryResult:
    """查出该引擎是否有新版，以及能不能从用户选的源装上。"""

    latest = await _query_latest(
        spec,
        current_version=current_version,
        source=source,
        channel=channel,
        cdk=cdk,
        proxy=proxy,
    )

    if not is_newer(latest.version, current_version):
        return DiscoveryResult(
            engine=spec.engine,
            current_version=current_version,
            latest_version=latest.version,
            update_available=False,
            blocked_reason=latest.blocked_reason,
        )

    base = {
        "engine": spec.engine,
        "current_version": current_version,
        "latest_version": latest.version,
        "update_available": True,
    }

    if latest.blocked_reason:
        return DiscoveryResult(**base, blocked_reason=latest.blocked_reason)

    kind, asset = select_asset_name(
        spec, latest.version, can_extract_7z=seven_zip_available
    )

    if source == "MirrorChyan":
        if not latest.download_url:
            return DiscoveryResult(
                **base,
                blocked_reason=(
                    "已选择 Mirror 酱作为下载源，但未取得下载地址；"
                    "请检查 CDK 是否填写且仍然有效"
                ),
            )
        # Mirror 酱只发全量包，它给的是一次性直链，资产名由服务端决定。
        return DiscoveryResult(
            **base,
            candidate=UpdateCandidate(
                engine=spec.engine,
                current_version=current_version,
                latest_version=latest.version,
                source=source,
                asset_kind="zip",
                download_url=latest.download_url,
                sha256=latest.sha256,
                release_note=latest.release_note,
            ),
        )

    if source == "AutoSite":
        url = spec.station_url()
        if not url:
            return DiscoveryResult(
                **base,
                blocked_reason=(
                    f"{engine_label(spec.engine, left=False)}未提供 AUTO-MAS 下载站渠道"
                ),
            )
        url, sha = await _station_asset(url, latest.version, proxy=proxy)
        return DiscoveryResult(
            **base,
            candidate=UpdateCandidate(
                engine=spec.engine,
                current_version=current_version,
                latest_version=latest.version,
                source=source,
                asset_kind="zip",
                download_url=url,
                sha256=sha,
                release_note=latest.release_note,
            ),
        )

    url, sha = await _github_asset(spec, latest.version, asset, proxy=proxy)
    if not url:
        return DiscoveryResult(
            **base,
            blocked_reason=f"GitHub 发行版 {latest.version} 中未找到资产 {asset}",
        )
    return DiscoveryResult(
        **base,
        candidate=UpdateCandidate(
            engine=spec.engine,
            current_version=current_version,
            latest_version=latest.version,
            source=source,
            asset_kind=kind,
            download_url=url,
            sha256=sha,
            release_note=latest.release_note,
        ),
    )


async def _query_latest(
    spec: EngineSpec,
    *,
    current_version: str | None,
    source: SourceId,
    channel: str,
    cdk: str,
    proxy: httpx.Proxy | None,
) -> _LatestVersion:
    """查询版本，按用户选择的源处理 CDK 错误和 GitHub 回退。"""

    try:
        return await _query_mirrorchyan(
            spec,
            current_version=current_version,
            channel=channel,
            cdk=cdk if source == "MirrorChyan" else "",
            proxy=proxy,
        )
    except HSRUpdateError:
        raise
    except Exception as exc:  # noqa: BLE001 - 网络层异常形态很多，统一降级
        if isinstance(exc, MirrorResourceError) and source != "GitHub":
            reason = MIRROR_ERROR_INFO.get(exc.code, MIRROR_ERROR_INFO[1])
            if exc.code in _CDK_ERROR_CODES:
                # CDK 失败响应可能仍带版本号，只查版本与允许下载分别判断。
                data = exc.data if isinstance(exc.data, dict) else {}
                version = str(data.get("version_name") or "").strip()
                if version:
                    return _LatestVersion(
                        version=version,
                        release_note=str(data.get("release_note") or ""),
                        blocked_reason=reason,
                    )
            else:
                reason += f"（Mirror 酱返回 {exc.code}）"
            raise HSRUpdateError(reason) from exc
        reason = format_exception_reason(
            exc, stage=f"查询{engine_label(spec.engine)}最新版本失败"
        )
        if source != "GitHub":
            raise HSRUpdateError(reason) from exc
        logger.warning(
            f"HSR 更新：Mirror 酱不可达（{reason}），"
            f"用户已选 GitHub 源，改查 GitHub release 接口"
        )
        version = await _github_latest_tag(spec, channel=channel, proxy=proxy)
        return _LatestVersion(version=version)


async def _query_mirrorchyan(
    spec: EngineSpec,
    *,
    current_version: str | None,
    channel: str,
    cdk: str,
    proxy: httpx.Proxy | None,
) -> _LatestVersion:
    params: dict[str, str] = {"user_agent": _USER_AGENT, "channel": channel or "stable"}
    if current_version:
        params["current_version"] = current_version
    if cdk:
        params["cdk"] = cdk
    # 两个 rid 都是单平台：带 os/arch 会 404，实测确认，别加。

    payload = await request_mirror_resource(
        spec.mirrorchyan_rid,
        params=params,
        proxy=proxy,
        timeout=_TIMEOUT,
    )

    data = payload.get("data") or {}
    version = str(data.get("version_name") or "").strip()

    if not version:
        raise HSRUpdateError("Mirror 酱未返回版本号")

    return _LatestVersion(
        version=version,
        release_note=str(data.get("release_note") or ""),
        download_url=str(data.get("url") or ""),
        sha256=str(data.get("sha256") or ""),
    )


async def _github_latest_tag(
    spec: EngineSpec, *, channel: str, proxy: httpx.Proxy | None
) -> str:
    """Mirror 酱不可达时的兜底，只服务已选 GitHub 源的用户。"""

    async with httpx.AsyncClient(
        proxy=proxy, follow_redirects=True, timeout=_TIMEOUT
    ) as client:
        if channel == "beta":
            response = await client.get(
                f"{_GITHUB_API}/repos/{spec.github_repo}/releases",
                params={"per_page": "5"},
                headers=_github_headers(),
            )
            response.raise_for_status()
            releases = response.json() or []
            if not releases:
                raise HSRUpdateError(
                    f"{engine_label(spec.engine, left=False)}没有可用的 GitHub 发行版"
                )
            return str(releases[0].get("tag_name") or "")
        response = await client.get(
            f"{_GITHUB_API}/repos/{spec.github_repo}/releases/latest",
            headers=_github_headers(),
        )
        response.raise_for_status()
        return str((response.json() or {}).get("tag_name") or "")


async def _github_asset(
    spec: EngineSpec,
    tag: str,
    asset_name: str,
    *,
    proxy: httpx.Proxy | None,
) -> tuple[str, str]:
    """按 tag 精确取资产直链与 sha256（GitHub 的 ``digest`` 字段）。"""

    async with httpx.AsyncClient(
        proxy=proxy, follow_redirects=True, timeout=_TIMEOUT
    ) as client:
        payload = None
        for candidate_tag in _tag_candidates(tag):
            response = await client.get(
                f"{_GITHUB_API}/repos/{spec.github_repo}/releases/tags/{candidate_tag}",
                headers=_github_headers(),
            )
            if response.status_code == 404:
                continue
            response.raise_for_status()
            payload = response.json()
            break

    if not payload:
        raise HSRUpdateError(f"GitHub 上没有{engine_label(spec.engine)}的发行版 {tag}")

    for asset in payload.get("assets") or []:
        if str(asset.get("name")) != asset_name:
            continue
        digest = str(asset.get("digest") or "")
        return str(asset.get("browser_download_url") or ""), digest.rpartition(":")[2]
    return "", ""


async def _station_asset(
    content_url: str, tag: str, *, proxy: httpx.Proxy | None
) -> tuple[str, str]:
    """读取数据站的已发布记录，固定版本后交给下载器做哈希校验。"""

    detail_url = content_url.removesuffix("/download/content")
    try:
        async with httpx.AsyncClient(
            proxy=proxy, follow_redirects=True, timeout=_TIMEOUT
        ) as client:
            response = await client.get(detail_url, headers={"User-Agent": _USER_AGENT})
            response.raise_for_status()
            payload = response.json()
        if payload["code"] != 0:
            raise ValueError("发布记录不可用")
        published = payload["data"]["published_version"]
        version_no = published["version_no"]
        filename = published["source_filename"]
        sha = published["sha256"]
        if type(version_no) is not int or version_no < 1:
            raise ValueError("缺少有效的发布记录编号")
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", sha):
            raise ValueError("缺少有效的安装包校验值")
        match = re.fullmatch(r"StarRailAssistant_(.+)\.zip", filename)
        if match is None or Version(match[1]) != Version(tag):
            raise ValueError(f"下载站安装包 {filename} 与目标版本 {tag} 不一致")
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise HSRUpdateError(f"读取 AUTO-MAS 下载站安装包失败：{exc}") from exc

    # beta 是可变的文件记录名；固定版本编号，防止下载时被后续发布替换。
    return f"{content_url}?version_no={version_no}", sha.lower()


def _tag_candidates(tag: str) -> tuple[str, ...]:
    stripped = tag.lstrip("v")
    return (tag, stripped) if tag != stripped else (tag, f"v{tag}")


def _github_headers() -> dict[str, str]:
    return {"User-Agent": _USER_AGENT, "Accept": "application/vnd.github+json"}


__all__ = [
    "DiscoveryResult",
    "HSRUpdateError",
    "UpdateCandidate",
    "discover",
    "is_newer",
]
