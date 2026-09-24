"""版本发现：查最新版本并解析出下载地址。

Mirror 酱的免 CDK 接口是**所有下载源**的版本权威——自建站只能用 tag 拼 URL，
没有 latest 接口，靠这条口径补上。下载源只决定字节从哪来，不参与版本判断，
也**绝不自动分流**：选了 Mirror 酱而 CDK 不可用时报错跳过，不悄悄换成 GitHub。

唯一的例外是「用户选了 GitHub 而 Mirror 酱不可达」：此时回退查 GitHub 自己的
release 接口。字节仍来自用户选定的源，所以不违反上面那条。
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from packaging.version import InvalidVersion, Version

from app.utils.constants import MIRROR_ERROR_INFO
from app.utils.logger import get_logger

from .engines import EngineSpec, SourceId, select_asset_name

logger = get_logger("HSR 更新发现")

_MIRROR_API = "https://mirrorchyan.com/api/resources"
_GITHUB_API = "https://api.github.com"
_USER_AGENT = "AutoMasGui"
_TIMEOUT = 30.0

#: 这些码表示 CDK 本身有问题，但版本号仍然可用——照常上报「有新版」，
#: 只是标注不可安装，让用户知道该去续 CDK 而不是以为没更新。
_CDK_ERROR_CODES = frozenset({7001, 7002, 7003, 7004, 7005})


class HSRUpdateError(RuntimeError):
    """版本发现或下载准备阶段的可预期失败。"""


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
    #: 有更新但装不了时的原因（CDK 失效、源不给地址等），直接面向用户。
    blocked_reason: str | None = None

    @property
    def installable(self) -> bool:
        return self.candidate is not None


def is_newer(remote: str, current: str | None) -> bool:
    """比较版本。解析不了时保守地当作「没有新版」，不乱升级。"""

    if not current:
        return True
    try:
        return Version(str(remote).lstrip("v")) > Version(str(current).lstrip("v"))
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

    latest, note, mirror_url, mirror_sha = await _query_latest(
        spec,
        current_version=current_version,
        source=source,
        channel=channel,
        cdk=cdk,
        proxy=proxy,
    )

    if not is_newer(latest, current_version):
        return DiscoveryResult(
            engine=spec.engine,
            current_version=current_version,
            latest_version=latest,
            update_available=False,
        )

    base = {
        "engine": spec.engine,
        "current_version": current_version,
        "latest_version": latest,
        "update_available": True,
    }

    kind, asset = select_asset_name(spec, latest, can_extract_7z=seven_zip_available)

    if source == "MirrorChyan":
        if not mirror_url:
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
                latest_version=latest,
                source=source,
                asset_kind="zip",
                download_url=mirror_url,
                sha256=mirror_sha,
                release_note=note,
            ),
        )

    if source == "AutoSite":
        url = spec.station_url(latest)
        if not url:
            return DiscoveryResult(
                **base,
                blocked_reason=f"{spec.display_name} 未提供 AUTO-MAS 下载站渠道",
            )
        sha = await _fetch_station_sha256(url, proxy=proxy)
        return DiscoveryResult(
            **base,
            candidate=UpdateCandidate(
                engine=spec.engine,
                current_version=current_version,
                latest_version=latest,
                source=source,
                asset_kind="zip",
                download_url=url,
                sha256=sha,
                release_note=note,
            ),
        )

    url, sha = await _github_asset(spec, latest, asset, proxy=proxy)
    if not url:
        return DiscoveryResult(
            **base,
            blocked_reason=f"GitHub 发行版 {latest} 中未找到资产 {asset}",
        )
    return DiscoveryResult(
        **base,
        candidate=UpdateCandidate(
            engine=spec.engine,
            current_version=current_version,
            latest_version=latest,
            source=source,
            asset_kind=kind,
            download_url=url,
            sha256=sha,
            release_note=note,
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
) -> tuple[str, str, str, str]:
    """返回 ``(版本号, 更新说明, Mirror酱直链, Mirror酱sha256)``。"""

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
        if source != "GitHub":
            raise HSRUpdateError(
                f"查询 {spec.display_name} 最新版本失败：{exc}"
            ) from exc
        logger.warning(
            f"HSR 更新：Mirror 酱不可达（{exc}），"
            f"用户已选 GitHub 源，改查 GitHub release 接口"
        )
        version = await _github_latest_tag(spec, channel=channel, proxy=proxy)
        return version, "", "", ""


async def _query_mirrorchyan(
    spec: EngineSpec,
    *,
    current_version: str | None,
    channel: str,
    cdk: str,
    proxy: httpx.Proxy | None,
) -> tuple[str, str, str, str]:
    params: dict[str, str] = {"user_agent": _USER_AGENT, "channel": channel or "stable"}
    if current_version:
        params["current_version"] = current_version
    if cdk:
        params["cdk"] = cdk
    # 两个 rid 都是单平台：带 os/arch 会 404，实测确认，别加。

    async with httpx.AsyncClient(
        proxy=proxy, follow_redirects=True, timeout=_TIMEOUT
    ) as client:
        response = await client.get(
            f"{_MIRROR_API}/{spec.mirrorchyan_rid}/latest",
            params=params,
            headers={"User-Agent": _USER_AGENT},
        )
        response.raise_for_status()
        payload = response.json()

    code = int(payload.get("code", -1))
    data = payload.get("data") or {}
    version = str(data.get("version_name") or "").strip()

    if code in _CDK_ERROR_CODES:
        # CDK 有问题但版本号照给：保留版本，下载地址必然为空，由调用方
        # 转成 blocked_reason，用户才知道是 CDK 的事。
        logger.warning(
            f"HSR 更新：{spec.display_name} Mirror 酱 CDK 异常 {code}"
            f"（{MIRROR_ERROR_INFO.get(code, '未知错误')}）"
        )
        if not version:
            raise HSRUpdateError(MIRROR_ERROR_INFO.get(code, "Mirror 酱 CDK 不可用"))
        return version, str(data.get("release_note") or ""), "", ""

    if code != 0:
        raise HSRUpdateError(
            MIRROR_ERROR_INFO.get(code, MIRROR_ERROR_INFO[1])
            + f"（Mirror 酱返回 {code}）"
        )
    if not version:
        raise HSRUpdateError("Mirror 酱未返回版本号")

    return (
        version,
        str(data.get("release_note") or ""),
        str(data.get("url") or ""),
        str(data.get("sha256") or ""),
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
                raise HSRUpdateError(f"{spec.display_name} 没有可用的 GitHub 发行版")
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
        raise HSRUpdateError(f"GitHub 上没有 {spec.display_name} 的发行版 {tag}")

    for asset in payload.get("assets") or []:
        if str(asset.get("name")) != asset_name:
            continue
        digest = str(asset.get("digest") or "")
        return str(asset.get("browser_download_url") or ""), digest.rpartition(":")[2]
    return "", ""


async def _fetch_station_sha256(zip_url: str, *, proxy: httpx.Proxy | None) -> str:
    """自建站的 ``.sha256`` 旁文件。取不到就返回空串，退化为完整性校验。"""

    url = f"{zip_url.rsplit('.', 1)[0]}.sha256"
    try:
        async with httpx.AsyncClient(
            proxy=proxy, follow_redirects=True, timeout=_TIMEOUT
        ) as client:
            response = await client.get(url, headers={"User-Agent": _USER_AGENT})
            response.raise_for_status()
            return response.text.strip().split()[0]
    except Exception as exc:  # noqa: BLE001 - 旁文件缺失不该让更新失败
        logger.warning(f"HSR 更新：未取到自建站校验文件 {url}：{exc}")
        return ""


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
