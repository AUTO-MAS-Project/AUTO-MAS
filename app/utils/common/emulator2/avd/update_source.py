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

"""魔改 AVD 更新：版本号与下载源。

**版本号**（ModAVD 发版规则）：版本号和 tag 都写成 ``v0.<N>.<P>``。第一段 0 表示内测阶段（转正式后
是 1）；N 是构建号（与 ``Pkg.BuildId=mas-N`` 同一个数）；P 是不重编、只重新打包的次数。例如 mas32
换成新格式重新打包是 ``v0.32.1``，mas33 是 ``v0.33.0``。按三段数字比较；GitHub 上的旧 tag
``v37.2.10-masN`` 当作 ``(0, N, 0)``。本地版本有清单（``modavd-manifest.json``）读清单的 ``version``，
没有就把 ``Pkg.BuildId=mas-N`` 当作 ``v0.N.0``，所以装着旧 mas32 的根目录会把 ``v0.32.1`` 认成新版。

**Release 正文**只读第一行的机读行 ``<!-- modavd: {...} -->`` 里的 ``min_automas``：比当前 MAS 新就不装、
提示先更新 MAS。公告不在 MAS 里显示。

**下载源可插拔**：:class:`UpdateSource` 只回答「最新一版是什么、包在哪、多大、哈希多少」；
下载、拼新版、换上都和源无关（:mod:`.updater`、:mod:`.update_stage`）。按顺序问（:func:`update_sources`）：

- **Mirror 酱**（:class:`MirrorChyanSource`）：``GET https://mirrorchyan.com/api/resources/ModAVD/latest``，
  带 ``current_version``（本地版本 ``v0.N.P``）、``os=win``、``arch=x64``、``channel=stable``。查更新一律
  不带 CDK，只拿版本和 ``release_note``；只有真要下载时才带 ``cdk``（MAS 全局的 ``Update.MirrorChyanCDK``，
  不另设）要一次下载链接（这一步消耗 CDK），可能是从 ``current_version`` 到新版的增量包。``min_automas``
  从同步的 ``release_note`` 第一行读，和 GitHub 正文同一套解析。CDK 只在请求参数里，不进日志、错误信息和状态。
- **GitHub**（:class:`GitHubReleaseSource`）：Mirror 酱查不到、出错、没有 CDK 时用它的主包（先按区间只取
  变了的文件，见 :mod:`.update_range`，不行再下整包）。

**包**：从 0.32.1 起每版只发主包 ``ModAVD-<ver>-win-x64.zip``（没有顶层目录，包根就是 ModAVD 根目录，
根上有 ``modavd-manifest.json``）、源码包 ``ModAVD-<ver>-sources.zip`` 和 ``SHA256SUMS.txt``。主包的文件名
和清单的 ``platform`` 带平台（现在只有 ``win-x64``，见 ``constants.MODAVD_PLATFORM``），只认本机平台的
包（:func:`package_candidates`）。旧 tag 的主包 ``ModAVD-37.2.10-masN.zip`` 带同名顶层目录，解包时剥掉。
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx
from packaging import version as pep440

from app.services.common.update import transport as _service_update_transport
from app.utils import MIRROR_ERROR_INFO, get_logger

from .components import read_mod_build
from .constants import (
    MODAVD_MANIFEST_FILE,
    MODAVD_MIRROR_API_ENV,
    MODAVD_MIRROR_ARCH,
    MODAVD_MIRROR_CHANNEL,
    MODAVD_MIRROR_OS,
    MODAVD_MIRROR_RID,
    MODAVD_PLATFORM,
    MODAVD_RELEASE_API,
    MODAVD_RELEASE_API_ENV,
    UPDATE_API_TIMEOUT_SECONDS,
)

logger = get_logger("魔改 AVD 更新")

# ---- 版本号 ----------------------------------------------------------------

_NEW_TAG = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")
_LEGACY_TAG = re.compile(r"v?\d+\.\d+\.\d+-mas(\d+)")


@dataclass(frozen=True, order=True)
class ModAvdVersion:
    """ModAVD 的版本号 ``v<major>.<build>.<patch>``，按三段数字比较。

    ``major`` 0 是内测阶段（转正式后是 1）；``build`` 是第二段，就是构建号 N（``mas-N``）；``patch`` 是
    不重编、只重新打包的次数。
    """

    major: int
    build: int
    patch: int = 0

    @classmethod
    def of_build(cls, build: int) -> ModAvdVersion:
        """只知道构建号时（没有清单的旧包、旧 tag）：内测阶段的 ``v0.N.0``。"""
        return cls(0, build, 0)

    def __str__(self) -> str:
        """版本身份写法 ``v0.32.1``：和 tag、清单的 ``version`` 一字不差，存状态、比较、对外请求都用它。"""
        return f"v{self.major}.{self.build}.{self.patch}"

    @property
    def display(self) -> str:
        """给人看的写法 ``0.32.1``：界面、提示文字、日志都用它，不带 ``v``、不写 ``mas-N``。"""
        return f"{self.major}.{self.build}.{self.patch}"

    @property
    def label(self) -> str:
        """构建号写法：``mas-33``（和 ``Pkg.BuildId`` 一致）。"""
        return f"mas-{self.build}"


def display_version(text: object) -> str:
    """把版本身份字符串（``v0.32.1``、旧 tag ``v37.2.10-mas32``）换成给人看的 ``0.32.1``；认不出原样返回。"""
    parsed = parse_version(text)
    return parsed.display if parsed is not None else str(text or "")


def parse_version(text: object) -> ModAvdVersion | None:
    """``v0.32.1`` / ``0.33.0`` → 三段；旧 tag ``v37.2.10-mas32`` → ``(0, 32, 0)``；别的写法返回 ``None``。"""
    value = str(text or "").strip()
    if match := _NEW_TAG.fullmatch(value):
        return ModAvdVersion(*(int(part) for part in match.groups()))
    if match := _LEGACY_TAG.fullmatch(value):
        return ModAvdVersion.of_build(int(match.group(1)))
    return None


def requires_manifest(tag: object) -> bool:
    """新写法的版本（``vX.Y.Z``，第一个是 ``v0.32.1``）必须带 ``modavd-manifest.json``；
    只有旧 tag ``v37.2.10-masN`` 的包没有清单。"""
    return _NEW_TAG.fullmatch(str(tag or "").strip()) is not None


def read_manifest_file(path: Path) -> dict[str, Any] | None:
    """读一份 ``modavd-manifest.json``；不在、读不出、不是对象都返回 ``None``。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def local_version(root: str | Path) -> ModAvdVersion | None:
    """根目录里装着的 ModAVD 版本。

    有清单读清单的 ``version``；没有清单（mas32 及更早）按 ``Pkg.BuildId=mas-N`` 算成 ``v0.N.0``。
    清单里的构建号和 ``sdk\\emulator`` 实际的对不上时（用户按说明手动换过 ``sdk\\emulator``，
    清单还是旧的），以实际的模拟器为准。两样都读不到返回 ``None``。
    """
    build = read_mod_build(root)
    manifest = read_manifest_file(Path(root) / MODAVD_MANIFEST_FILE) or {}
    declared = parse_version(manifest.get("version"))
    if declared is not None and (build is None or declared.build == build):
        return declared
    if build is not None:
        return ModAvdVersion.of_build(build)
    return declared


def local_version_text(root: str | Path) -> str | None:
    """组件列表、电脑检查里显示的本地版本 ``0.32.1``，和 :func:`local_version` 同一规则。

    模拟器的 ``Pkg.BuildId`` 读不到时返回 ``None``：这份模拟器本身认不出版本，光凭清单写的不算。
    """
    if read_mod_build(root) is None:
        return None
    version = local_version(root)
    return version.display if version is not None else None


def automas_too_old(min_automas: object, current: str) -> bool:
    """``min_automas``（机读行）高于当前 MAS 版本时为真；没写或认不出都按不限制。"""
    if not isinstance(min_automas, str) or not min_automas.strip():
        return False
    try:
        return pep440.parse(current) < pep440.parse(min_automas.strip())
    except pep440.InvalidVersion:
        logger.warning(
            f"认不出 min_automas 或 MAS 版本号，按不限制: {min_automas!r} / {current!r}"
        )
        return False


_MACHINE_LINE = re.compile(r"<!--\s*modavd:\s*(\{.*\})\s*-->")


def parse_min_automas(body: object) -> str:
    """Release 正文第一行机读行里的 ``min_automas``；没有机读行（mas32 及更早）、没写、解析不了都返回空串。"""
    lines = str(body or "").replace("\r\n", "\n").split("\n")
    match = _MACHINE_LINE.fullmatch(lines[0].strip()) if lines else None
    if not match:
        return ""
    try:
        data = json.loads(match.group(1))
    except ValueError as e:
        logger.warning(f"ModAVD 公告的机读行解析失败，按不限制 AUTO-MAS 版本处理: {e}")
        return ""
    value = data.get("min_automas") if isinstance(data, dict) else None
    return value.strip() if isinstance(value, str) else ""


# ---- 下载源 ----------------------------------------------------------------


class UpdateSourceError(RuntimeError):
    """下载源查不到最新版本、或返回的东西用不了。"""


GITHUB_SOURCE = "github"
MIRROR_SOURCE = "mirrorchyan"


@dataclass(frozen=True)
class RemoteAsset:
    """要下载的那个包。``top_dir`` 是解包时要剥掉的顶层目录：只有旧 tag 的主包有（``ModAVD-37.2.10-masN``），
    新写法的主包没有顶层目录，为空串。``sha256`` 拿不到时为 ``None``（只靠 zip 自带的 CRC）。

    ``incremental`` 为真时是 Mirror 酱从 ``base``（版本身份 ``v0.N.P``）到新版的增量包（见
    :func:`.update_stage.build_patched_package`），否则是整包。
    """

    name: str
    url: str
    size: int
    sha256: str | None
    top_dir: str
    incremental: bool = False
    base: str = ""


@dataclass(frozen=True)
class RemoteRelease:
    """下载源报出的最新一版。``min_automas`` 是它要求的最低 AUTO-MAS 版本（没要求为空串）。
    ``asset`` 是能下的包；Mirror 酱没给下载地址（没有 CDK）时为 ``None``。"""

    source: str
    tag: str
    version: ModAvdVersion
    min_automas: str
    asset: RemoteAsset | None

    def as_dict(self) -> dict[str, Any]:
        """写进 ``state.json`` 的那一份：拼新版、记更新历史要用的字段。

        Mirror 酱的下载地址是一次性的（每次下载前现要），不写进去。
        """
        asset = self.asset
        if asset is None:
            raise UpdateSourceError(f"{self.version.display} 没有能下载的包")
        return {
            "source": self.source,
            "tag": self.tag,
            "version": str(self.version),
            "asset": {
                "name": asset.name,
                "url": asset.url if self.source != MIRROR_SOURCE else "",
                "size": asset.size,
                "sha256": asset.sha256,
                "topDir": asset.top_dir,
                "incremental": asset.incremental,
                "base": asset.base,
            },
        }


class UpdateSource(Protocol):
    """下载源：只负责报出最新一版和它的包。``current`` 是发请求的根目录装着的版本。"""

    name: str

    async def latest(
        self, *, proxy: httpx.Proxy | None, current: ModAvdVersion | None = None
    ) -> RemoteRelease: ...


_SHA256_DIGEST = re.compile(r"sha256:([0-9a-fA-F]{64})")
_SHA256_HEX = re.compile(r"[0-9a-f]{64}")


def _asset_from_github(item: dict[str, Any], top_dir: str) -> RemoteAsset:
    digest = _SHA256_DIGEST.fullmatch(str(item.get("digest") or ""))
    url = str(item.get("browser_download_url") or "")
    size = item.get("size")
    if not url or not isinstance(size, int) or size <= 0:
        raise UpdateSourceError(f"GitHub 返回的附件信息不完整: {item.get('name')}")
    return RemoteAsset(
        name=str(item["name"]),
        url=url,
        size=size,
        sha256=digest.group(1).lower() if digest else None,
        top_dir=top_dir,
    )


def package_candidates(tag: str) -> list[tuple[str, str]]:
    """``tag`` 这一版可以拿来装的包：``[(附件名, 解包时要剥掉的顶层目录)]``。

    - 新写法（``vX.Y.Z``）只认带平台的主包 ``ModAVD-<ver>-win-x64.zip``，没有顶层目录（包根就是 ModAVD
      根目录）。不带平台的 ``ModAVD-<ver>.zip``、``-update.zip`` 从没正式发布过，不认；别的平台的包也不认。
      有人把带顶层目录的新写法主包传上来时，解包后根上没有 ``sdk/emulator`` 和清单，按现有核对拒装。
    - 旧 tag ``v37.2.10-masN`` 只有主包 ``ModAVD-37.2.10-masN.zip``（顶层目录同名），照旧剥掉。
    """
    ver = tag.strip().removeprefix("v")
    if requires_manifest(tag):
        return [(f"ModAVD-{ver}-{MODAVD_PLATFORM}.zip", "")]
    return [(f"ModAVD-{ver}.zip", f"ModAVD-{ver}")]


def release_from_github(data: object) -> RemoteRelease:
    """GitHub ``releases/latest`` 的响应 → :class:`RemoteRelease`。包按 :func:`package_candidates` 挑，
    解压时剥掉它的顶层目录（只有旧 tag 的主包有）。"""
    if not isinstance(data, dict):
        raise UpdateSourceError("GitHub 返回的不是 Release 对象")
    tag = str(data.get("tag_name") or "")
    parsed = parse_version(tag)
    if parsed is None:
        raise UpdateSourceError(f"认不出最新版本的 tag: {tag!r}")
    assets = {
        str(item.get("name")): item
        for item in data.get("assets") or []
        if isinstance(item, dict)
    }
    candidates = package_candidates(tag)
    found = next(((name, top) for name, top in candidates if name in assets), None)
    if found is None:
        wanted = " 或 ".join(name for name, _ in candidates)
        raise UpdateSourceError(
            f"{tag} 里没有本机（{MODAVD_PLATFORM}）能用的包 {wanted}"
        )
    return RemoteRelease(
        source=GITHUB_SOURCE,
        tag=tag,
        version=parsed,
        min_automas=parse_min_automas(data.get("body")),
        asset=_asset_from_github(assets[found[0]], found[1]),
    )


class GitHubReleaseSource:
    """GitHub：``GET repos/ModAVD/ModAVD/releases/latest``，走 MAS 的代理设置。"""

    name = GITHUB_SOURCE

    def __init__(self, api_url: str = MODAVD_RELEASE_API) -> None:
        self.api_url = api_url

    async def latest(
        self, *, proxy: httpx.Proxy | None, current: ModAvdVersion | None = None
    ) -> RemoteRelease:
        try:
            async with httpx.AsyncClient(
                proxy=proxy,
                follow_redirects=True,
                timeout=UPDATE_API_TIMEOUT_SECONDS,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "AutoMasGui",
                },
            ) as client:
                response = await client.get(self.api_url)
        except httpx.HTTPError as e:
            detail = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
            raise UpdateSourceError(f"连不上 GitHub（{detail}）") from e
        if response.status_code != 200:
            hint = (
                "，可能是查询次数超过了 GitHub 的限制，稍后再试"
                if response.status_code in (403, 429)
                else ""
            )
            raise UpdateSourceError(f"GitHub 返回 HTTP {response.status_code}{hint}")
        try:
            data = response.json()
        except ValueError as e:
            raise UpdateSourceError("GitHub 返回的内容不是 JSON") from e
        return release_from_github(data)


#: CDK 本身有问题的 Mirror 酱业务码：过期、错误、当天下载次数用完、不含这个资源、被封禁。
MIRROR_CDK_ERRORS = frozenset({7001, 7002, 7003, 7004, 7005})
#: 这个系统和架构下没有包（不带 os/arch 时也是它）。
MIRROR_NO_PACKAGE = 8001


class MirrorChyanError(UpdateSourceError):
    """Mirror 酱给不了能用的结果。``code`` 是它的业务码；连不上、响应不对时为 ``None``。
    消息是给人看的中文，不含 CDK 和带 CDK 的地址。"""

    def __init__(self, message: str, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code

    @property
    def cdk_problem(self) -> bool:
        return self.code in MIRROR_CDK_ERRORS


def mirror_error_text(code: int) -> str:
    """Mirror 酱业务码的中文说明（和 MAS 别处同一份 ``MIRROR_ERROR_INFO``）。"""
    return MIRROR_ERROR_INFO.get(code, f"错误码 {code}")


def release_from_mirror(data: object, *, base: ModAvdVersion | None) -> RemoteRelease:
    """Mirror 酱 ``latest`` 响应的 ``data`` → :class:`RemoteRelease`。

    带了 CDK、又有比 ``current_version`` 新的版本时才有下载地址（``url``、``sha256``、``filesize``、
    ``update_type``）：``update_type`` 为 ``incremental`` 是从 ``base``（请求带的 ``current_version``）到新版的
    增量包，否则是全量包（同 GitHub 的主包，包根就是 ModAVD 根目录）。没有下载地址时 ``asset`` 为 ``None``。
    """
    if not isinstance(data, dict):
        raise MirrorChyanError("Mirror 酱返回的数据不完整")
    tag = str(data.get("version_name") or "").strip()
    version = parse_version(tag)
    if version is None:
        raise MirrorChyanError(f"认不出 Mirror 酱上最新版本的版本号: {tag!r}")
    asset: RemoteAsset | None = None
    url = data.get("url")
    if isinstance(url, str) and url.strip():
        size = data.get("filesize")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            raise MirrorChyanError("Mirror 酱给了下载地址，但没给包的大小")
        incremental = data.get("update_type") == "incremental"
        if incremental and base is None:
            raise MirrorChyanError("Mirror 酱给了增量包，但请求没带当前版本")
        digest = str(data.get("sha256") or "").strip().lower()
        stem = (
            f"ModAVD-{base.display}-to-{version.display}"
            if incremental and base is not None
            else f"ModAVD-{version.display}"
        )
        asset = RemoteAsset(
            name=f"{stem}-{MODAVD_PLATFORM}-mirrorchyan.zip",
            url=url.strip(),
            size=size,
            sha256=digest if _SHA256_HEX.fullmatch(digest) else None,
            top_dir="",
            incremental=incremental,
            base=str(base) if incremental else "",
        )
    return RemoteRelease(
        source=MIRROR_SOURCE,
        tag=tag,
        version=version,
        min_automas=parse_min_automas(data.get("release_note")),
        asset=asset,
    )


class MirrorChyanSource:
    """Mirror 酱：``GET <api>/ModAVD/latest``，走 MAS 的代理设置。

    ``cdk`` 是 MAS 全局的 ``Update.MirrorChyanCDK``，只放进请求参数：错误信息里不带它，也不带含它的地址
    （:func:`~app.services.common.update.transport.request_mirror_resource` 不用 ``raise_for_status``）。
    消耗 CDK 的是「带 CDK 要下载链接」（:meth:`package`）；查更新（:meth:`latest`）一律不带 CDK。
    """

    name = MIRROR_SOURCE

    def __init__(
        self,
        cdk: str = "",
        api_root: str = _service_update_transport.MIRROR_RESOURCE_API,
    ) -> None:
        self._cdk = cdk.strip()
        self.api_root = api_root

    @property
    def has_cdk(self) -> bool:
        return bool(self._cdk)

    def _scrub(self, text: str) -> str:
        return text.replace(self._cdk, "***") if self._cdk else text

    async def _query(
        self,
        *,
        proxy: httpx.Proxy | None,
        current: ModAvdVersion | None,
        with_cdk: bool,
    ) -> RemoteRelease:
        params = {
            "os": MODAVD_MIRROR_OS,
            "arch": MODAVD_MIRROR_ARCH,
            "channel": MODAVD_MIRROR_CHANNEL,
        }
        if current is not None:
            params["current_version"] = str(current)
        if with_cdk and self._cdk:
            params["cdk"] = self._cdk
        try:
            payload = await _service_update_transport.request_mirror_resource(
                MODAVD_MIRROR_RID,
                params=params,
                proxy=proxy,
                timeout=UPDATE_API_TIMEOUT_SECONDS,
                api_root=self.api_root,
            )
        except _service_update_transport.MirrorResourceError as e:
            raise MirrorChyanError(mirror_error_text(e.code), e.code) from None
        except Exception as e:  # noqa: BLE001 - 连不上、不是 JSON 都算 Mirror 酱用不了
            detail = self._scrub(
                f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
            )
            # 不串上原异常：httpx 的异常带着请求，请求地址里有 CDK
            raise MirrorChyanError(f"连不上 Mirror 酱（{detail}）") from None
        return release_from_mirror(payload.get("data"), base=current)

    async def latest(
        self, *, proxy: httpx.Proxy | None, current: ModAvdVersion | None = None
    ) -> RemoteRelease:
        """查最新版本（查更新用）：不带 CDK，只拿版本和 release_note，没有下载链接、不消耗 CDK。"""
        return await self._query(proxy=proxy, current=current, with_cdk=False)

    async def package(
        self, *, proxy: httpx.Proxy | None, current: ModAvdVersion | None
    ) -> RemoteRelease:
        """带 CDK 要下载链接（这一步消耗 CDK；链接在服务端留 30 分钟，由调用方在内存里复用）。
        ``current`` 为 ``None`` 时只会给全量包。"""
        return await self._query(proxy=proxy, current=current, with_cdk=True)


def mirror_api_root() -> str:
    """Mirror 酱的查询根地址；环境变量 ``AUTO_MAS_MODAVD_MIRROR_API`` 可换成本地模拟服务（只供测试）。"""
    return (
        os.environ.get(MODAVD_MIRROR_API_ENV, "").strip()
        or _service_update_transport.MIRROR_RESOURCE_API
    )


def github_api_url() -> str:
    """GitHub 的查询地址；环境变量 ``AUTO_MAS_MODAVD_RELEASE_API`` 可换成本地模拟服务（只供测试）。"""
    return os.environ.get(MODAVD_RELEASE_API_ENV, "").strip() or MODAVD_RELEASE_API


def update_sources(*, github_only: bool = False) -> list[UpdateSource]:
    """查更新时按顺序问的源：先 Mirror 酱（不带 CDK，只查版本），查不到或出错再问 GitHub；``github_only``
    （MAS 设置的「更新源」选了 GitHub）时只问 GitHub。两个环境变量只供测试，不进配置、不上界面。"""
    github = GitHubReleaseSource(github_api_url())
    if github_only:
        return [github]
    return [MirrorChyanSource("", mirror_api_root()), github]


__all__ = [
    "GITHUB_SOURCE",
    "MIRROR_CDK_ERRORS",
    "MIRROR_NO_PACKAGE",
    "MIRROR_SOURCE",
    "GitHubReleaseSource",
    "MirrorChyanError",
    "MirrorChyanSource",
    "ModAvdVersion",
    "RemoteAsset",
    "RemoteRelease",
    "UpdateSource",
    "UpdateSourceError",
    "automas_too_old",
    "display_version",
    "github_api_url",
    "local_version",
    "local_version_text",
    "mirror_api_root",
    "mirror_error_text",
    "package_candidates",
    "parse_min_automas",
    "parse_version",
    "read_manifest_file",
    "release_from_github",
    "release_from_mirror",
    "requires_manifest",
    "update_sources",
]
