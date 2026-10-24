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

"""魔改 AVD 更新：版本号、版本更新公告与下载源。

**版本号**（ModAVD 发版规则）：``v<N>.0.<P>``，N 是构建号（与 ``Pkg.BuildId=mas-N`` 同一个数），
P 是重新打包的次数。GitHub 上的旧 tag ``v37.2.10-masN`` 当作 ``(N, 0, 0)``。本地版本有清单
（``modavd-manifest.json``）读清单的 ``version``，没有就把 ``Pkg.BuildId=mas-N`` 当作 ``vN.0.0``。

**公告**（Release 正文）：第一行是机读行 ``<!-- modavd: {...} -->``，分隔行
``<!-- modavd:github-only -->`` 以上是给 MAS 显示的更新公告，以下只在 GitHub 上看。跳了几版时，
机读行 ``changes`` 里比本地新的各版摘要合在一起显示。旧版本（mas32 及更早）没有机读行、没有
分隔行，整篇正文就是公告。

**下载源可插拔**：:class:`UpdateSource` 只回答「最新一版是什么、包在哪、多大、哈希多少」；
下载、拼新版、换上都和源无关（:mod:`.updater`、:mod:`.update_stage`）。现在只有 GitHub
（:class:`GitHubReleaseSource`），以后接别的源时加进 :func:`update_sources` 的列表即可；接 Mirror 酱时
按 ``os=win``、``arch=x64`` 请求（``constants.MODAVD_MIRROR_OS`` / ``MODAVD_MIRROR_ARCH``）。

**平台**：主包、更新包的文件名和清单的 ``platform`` 带平台（现在只有 ``win-x64``，见
``constants.MODAVD_PLATFORM``），源码包不带。只认本机平台的包（:func:`package_candidates`）。
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import httpx
from packaging import version as pep440

from app.utils import get_logger

from .components import read_mod_build
from .constants import (
    MODAVD_MANIFEST_FILE,
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
    """ModAVD 的版本号，按三段数字比较。第一段就是构建号 N（``mas-N``）。"""

    build: int
    middle: int = 0
    patch: int = 0

    def __str__(self) -> str:
        return f"v{self.build}.{self.middle}.{self.patch}"

    @property
    def label(self) -> str:
        """界面上的构建号写法：``mas-33``。"""
        return f"mas-{self.build}"


def parse_version(text: object) -> ModAvdVersion | None:
    """``v33.0.0`` / ``33.0.1`` → 三段；旧 tag ``v37.2.10-mas32`` → ``(32, 0, 0)``；别的写法返回 ``None``。"""
    value = str(text or "").strip()
    if match := _NEW_TAG.fullmatch(value):
        return ModAvdVersion(*(int(part) for part in match.groups()))
    if match := _LEGACY_TAG.fullmatch(value):
        return ModAvdVersion(int(match.group(1)))
    return None


def requires_manifest(tag: object) -> bool:
    """新写法的版本（``vX.Y.Z``，下一个公开版本 v33.0.0 起）必须带 ``modavd-manifest.json``；
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

    有清单读清单的 ``version``；没有清单（mas32 及更早）按 ``Pkg.BuildId=mas-N`` 算成 ``vN.0.0``。
    清单里的构建号和 ``sdk\\emulator`` 实际的对不上时（用户按说明手动换过 ``sdk\\emulator``，
    清单还是旧的），以实际的模拟器为准。两样都读不到返回 ``None``。
    """
    build = read_mod_build(root)
    manifest = read_manifest_file(Path(root) / MODAVD_MANIFEST_FILE) or {}
    declared = parse_version(manifest.get("version"))
    if declared is not None and (build is None or declared.build == build):
        return declared
    if build is not None:
        return ModAvdVersion(build)
    return declared


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


# ---- 公告 ------------------------------------------------------------------

_MACHINE_LINE = re.compile(r"<!--\s*modavd:\s*(\{.*\})\s*-->")
#: 分隔行：以上是更新公告（MAS、Mirror 酱显示），以下只在 GitHub 上看。
NOTES_SEPARATOR = "<!-- modavd:github-only -->"
#: 机读行 ``changes`` 里的分类，按这个顺序显示。
CHANGE_CATEGORIES = ("新增", "变更", "修复", "移除", "说明")


@dataclass(frozen=True)
class ReleaseNotes:
    """一版的公告：机读行（没有或解析不了时为空字典）与分隔行以上的正文（不含机读行）。"""

    machine: dict[str, Any] = field(default_factory=dict)
    announcement: str = ""


def parse_release_body(body: object) -> ReleaseNotes:
    """拆 Release 正文：第一行的机读行、分隔行以上的公告。

    没有机读行的是旧版本（mas32 及更早），没有摘要；没有分隔行时整篇都算公告。
    """
    lines = str(body or "").replace("\r\n", "\n").split("\n")
    machine: dict[str, Any] = {}
    if lines and (match := _MACHINE_LINE.fullmatch(lines[0].strip())):
        try:
            data = json.loads(match.group(1))
        except ValueError as e:
            logger.warning(f"ModAVD 公告的机读行解析失败，按没有摘要处理: {e}")
        else:
            if isinstance(data, dict):
                machine = data
        lines = lines[1:]
    upper: list[str] = []
    for line in lines:
        if line.strip() == NOTES_SEPARATOR:
            break
        upper.append(line)
    return ReleaseNotes(machine=machine, announcement="\n".join(upper).strip())


def newer_changes(
    machine: dict[str, Any], current: ModAvdVersion | None
) -> list[dict[str, Any]]:
    """机读行 ``changes`` 里比本地新的各版摘要，按版本从新到旧：
    ``[{"version": "v35.0.0", "label": "mas-35", "groups": [{"category": "修复", "items": [...]}]}]``。

    认不出的版本号、形状不对的段直接跳过：公告内容坏掉时只丢摘要，不影响「有新版本」的结论。
    """
    changes = machine.get("changes")
    if not isinstance(changes, dict):
        return []
    result: list[tuple[ModAvdVersion, dict[str, Any]]] = []
    for raw, section in changes.items():
        parsed = parse_version(raw)
        if parsed is None or not isinstance(section, dict):
            continue
        if current is not None and parsed <= current:
            continue
        groups = [
            {
                "category": str(category),
                "items": [item for item in items if isinstance(item, str)],
            }
            for category, items in section.items()
            if isinstance(items, list)
        ]
        groups.sort(
            key=lambda group: (
                CHANGE_CATEGORIES.index(group["category"])
                if group["category"] in CHANGE_CATEGORIES
                else len(CHANGE_CATEGORIES)
            )
        )
        result.append(
            (parsed, {"version": str(parsed), "label": parsed.label, "groups": groups})
        )
    result.sort(key=lambda item: item[0], reverse=True)
    return [entry for _, entry in result]


# ---- 下载源 ----------------------------------------------------------------


class UpdateSourceError(RuntimeError):
    """下载源查不到最新版本、或返回的东西用不了。"""


@dataclass(frozen=True)
class RemoteAsset:
    """要下载的那个包。``top_dir`` 是包里的顶层目录（GitHub 主包 ``ModAVD-<ver>-win-x64``，旧版
    ``ModAVD-37.2.10-masN``），更新包没有顶层目录时为空串。``sha256`` 拿不到时为 ``None``（只靠 zip
    自带的 CRC）。"""

    name: str
    url: str
    size: int
    sha256: str | None
    top_dir: str


@dataclass(frozen=True)
class RemoteRelease:
    """下载源报出的最新一版。"""

    source: str
    tag: str
    version: ModAvdVersion
    title: str
    page_url: str
    published_at: str
    notes: ReleaseNotes
    asset: RemoteAsset

    def as_dict(self) -> dict[str, Any]:
        """写进 ``state.json`` 的那一份：下载、续传、拼新版要用的字段。"""
        return {
            "source": self.source,
            "tag": self.tag,
            "version": str(self.version),
            "asset": {
                "name": self.asset.name,
                "url": self.asset.url,
                "size": self.asset.size,
                "sha256": self.asset.sha256,
                "topDir": self.asset.top_dir,
            },
        }


class UpdateSource(Protocol):
    """下载源：只负责报出最新一版和它的包。"""

    name: str

    async def latest(self, *, proxy: httpx.Proxy | None) -> RemoteRelease: ...


_SHA256_DIGEST = re.compile(r"sha256:([0-9a-fA-F]{64})")


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
    """``tag`` 这一版可以拿来装的包，按优先顺序：``[(附件名, 包里的顶层目录)]``。

    - 新写法（``vX.Y.Z``）的包名带平台：先要更新包 ``ModAVD-<ver>-win-x64-update.zip``（没有顶层目录），
      其次主包 ``ModAVD-<ver>-win-x64.zip``（剥掉顶层目录 ``ModAVD-<ver>-win-x64/``）。不带平台的
      ``ModAVD-<ver>.zip`` / ``-update.zip`` 从没发布过，不认；别的平台的包也不认。
    - 旧 tag ``v37.2.10-masN`` 只有主包 ``ModAVD-37.2.10-masN.zip``（顶层目录同名）。
    """
    ver = tag.strip().removeprefix("v")
    if requires_manifest(tag):
        stem = f"ModAVD-{ver}-{MODAVD_PLATFORM}"
        return [(f"{stem}-update.zip", ""), (f"{stem}.zip", stem)]
    return [(f"ModAVD-{ver}.zip", f"ModAVD-{ver}")]


def release_from_github(data: object) -> RemoteRelease:
    """GitHub ``releases/latest`` 的响应 → :class:`RemoteRelease`。包按 :func:`package_candidates` 的
    顺序挑第一个有的，解压时剥掉它的顶层目录。"""
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
    asset = _asset_from_github(assets[found[0]], found[1])
    return RemoteRelease(
        source="github",
        tag=tag,
        version=parsed,
        title=str(data.get("name") or tag),
        page_url=str(data.get("html_url") or ""),
        published_at=str(data.get("published_at") or ""),
        notes=parse_release_body(data.get("body")),
        asset=asset,
    )


class GitHubReleaseSource:
    """GitHub：``GET repos/ModAVD/ModAVD/releases/latest``，走 MAS 的代理设置。"""

    name = "github"

    def __init__(self, api_url: str = MODAVD_RELEASE_API) -> None:
        self.api_url = api_url

    async def latest(self, *, proxy: httpx.Proxy | None) -> RemoteRelease:
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


def update_sources() -> list[UpdateSource]:
    """按顺序问的下载源。环境变量 ``AUTO_MAS_MODAVD_RELEASE_API`` 可把 GitHub 的查询地址换成
    本地模拟服务（只供测试，不进配置、不上界面）。"""
    api_url = os.environ.get(MODAVD_RELEASE_API_ENV, "").strip() or MODAVD_RELEASE_API
    return [GitHubReleaseSource(api_url)]


__all__ = [
    "CHANGE_CATEGORIES",
    "NOTES_SEPARATOR",
    "GitHubReleaseSource",
    "ModAvdVersion",
    "ReleaseNotes",
    "RemoteAsset",
    "RemoteRelease",
    "UpdateSource",
    "UpdateSourceError",
    "automas_too_old",
    "local_version",
    "newer_changes",
    "package_candidates",
    "parse_release_body",
    "parse_version",
    "read_manifest_file",
    "release_from_github",
    "requires_manifest",
    "update_sources",
]
