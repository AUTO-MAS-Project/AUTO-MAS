"""按版本存放的 MaaFW Python binding 与官方原生库（运行池布局 v2）。

    <pool>/bindings/maafw-<pep440>/   maa/**（纯 py，bin/ 只有占位）+ maafw-<ver>.dist-info + binding.json
    <pool>/native/maafw-<pep440>/     官方 wheel 的 maa/bin/** + native.json

runner venv（base）里不再装 ``maafw``：worker 靠 ``PYTHONPATH`` 里的 binding 目录
``import maa``，靠 ``MAAFW_BINARY_PATH`` 指到副本自带的 ``maafw/`` 或这里的 native
目录（``maa/__init__.py`` 读这个变量，``Library.open`` 在 ``Library.version()`` 之前
只记路径不加载）。一个 maafw 版本只有一份 0.3 MB 的 binding，DLL 只在项目没自带时
才落地一份，运行池不再每个版本各拷一套 venv。

来源顺序（方案 D3）：PyPI / 镜像官方 wheel（平台标签 ``win_amd64`` / ``win_arm64``）
→ MaaFramework tag 源码（无 DLL，只对自带原生库的项目有意义）。每个目录都带全量
清单（相对路径 + 大小 + sha256），命中判据是清单全量校验通过，不合即当不存在重建；
校验结果按进程缓存。目录里从不写 pyc：worker 与自检子进程都设
``PYTHONPYCACHEPREFIX=<pool>/.pycache``，清单才稳定。

本模块只用标准库 + ``packaging``（方案 D12）；不读 ``Config``，代理、索引候选、离线
标记都由调用方传入。
"""

from __future__ import annotations

import hashlib
import html.parser
import json
import os
import platform as platform_module
import re
import shutil
import struct
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from ._shared import (
    MaaFWRuntimePoolError,
    assert_existing_chain_has_no_reparse,
    assert_not_reparse,
    format_time,
    parse_time,
    pool_lock,
    remove_tree_best_effort,
    utc_now,
    write_json_atomic,
)
from .binding_fallback import (
    BINDING_SOURCE_PREFIX,
    BINDING_SRC_CACHE_RELATIVE_PATH,
    NO_BUNDLED_DLL_MARKER_NAME,
    NO_BUNDLED_DLL_MARKER_TEXT,
    MaaFWBindingFallbackError,
    download_source_archive,
    pep440_to_maafw_tag,
    validate_source_archive,
)
from .host_environment import (
    LOOPBACK_NO_PROXY_HOSTS,
    strip_host_python_environment,
)

BINDINGS_DIRECTORY_NAME = "bindings"
NATIVE_DIRECTORY_NAME = "native"
STAGING_DIRECTORY_NAME = ".staging"
PYCACHE_DIRECTORY_NAME = ".pycache"
BINDING_MANIFEST_NAME = "binding.json"
NATIVE_MANIFEST_NAME = "native.json"
BINDING_LAYOUT_VERSION = 2
VERSION_DIRECTORY_PREFIX = "maafw-"
NATIVE_DLL_NAME = "MaaFramework.dll"
#: worker 与自检起来时 ``Library.open`` 至少要这三份库在同一目录。
NATIVE_REQUIRED_LIBRARIES = ("MaaFramework.dll", "MaaAgentClient.dll", "MaaToolkit.dll")
DEFAULT_PACKAGE_INDEX = "https://pypi.org/simple/"
INDEX_FETCH_TIMEOUT_SECONDS = 30
WHEEL_DOWNLOAD_TIMEOUT_SECONDS = 180
SELF_CHECK_TIMEOUT_SECONDS = 60
_DOWNLOAD_CHUNK_SIZE = 256 * 1024
#: 官方 wheel 实测 60 MB 上下；给一个远超正常值的上限，防止跟错跳转把整站页面当 wheel 落盘。
_MAX_WHEEL_BYTES = 512 * 1024 * 1024
_VERSION_DIRECTORY_RE = re.compile(r"^maafw-(?P<version>[0-9][0-9A-Za-z.!+-]*)$")
_WHEEL_FILENAME_RE = re.compile(
    r"^maafw-(?P<version>[^-]+)-(?P<python>[^-]+)-(?P<abi>[^-]+)-(?P<platform>[^-]+)\.whl$",
    re.IGNORECASE,
)

#: 收割时不铺的安装器私有文件（不在 wheel 里，各安装器各写各的）。
_INSTALLER_PRIVATE_FILES = frozenset(
    {"INSTALLER", "REQUESTED", "direct_url.json", "uv_cache.json"}
)

_VERIFIED_CACHE_GUARD = threading.Lock()
#: 进程内校验缓存：目录 → (清单 mtime_ns, 清单内容, {相对路径: (大小, mtime_ns)})。
#: 命中时只 stat 每个文件比大小和 mtime，不再重算 sha256（native 里是几十 MB 的
#: DLL）；任一文件变了、或清单换了，整个目录重新全量校验。
_VERIFIED_CACHE: dict[str, tuple[int, dict[str, Any], dict[str, tuple[int, int]]]] = {}


class MaaFWBindingError(RuntimeError):
    """binding / native 目录准备失败。文案面向用户，调用方原样带出。"""


class MaaFWBindingUnavailableError(MaaFWBindingError):
    """索引上确实没有这个版本（或离线且本地没有）——不是网络故障。"""


class MaaFWBindingNetworkError(MaaFWBindingError):
    """所有索引候选都连不上：网络故障，不能当成「没有这个版本」去走源码兜底。"""


@dataclass(frozen=True)
class BindingInfo:
    """一份就绪的 binding：worker 环境与回收对账都从这里取事实。"""

    version: str
    directory: Path
    source: str
    requires_dist: tuple[str, ...]
    native_dll_sha256: str | None
    native_directory: Path | None
    self_checked: bool

    @property
    def is_source_built(self) -> bool:
        return self.source.startswith("github-source")


# ---------------------------------------------------------------------------
# 路径与版本
# ---------------------------------------------------------------------------


def normalize_version(value: Any) -> str:
    text = str(value or "").strip()
    try:
        return str(Version(text))
    except InvalidVersion as exc:
        raise MaaFWBindingError(f"maafw 版本不合法: {value!r}") from exc


def binding_directory(pool_root: Path, version: str) -> Path:
    return (
        Path(pool_root)
        / BINDINGS_DIRECTORY_NAME
        / f"{VERSION_DIRECTORY_PREFIX}{normalize_version(version)}"
    )


def native_directory(pool_root: Path, version: str) -> Path:
    return (
        Path(pool_root)
        / NATIVE_DIRECTORY_NAME
        / f"{VERSION_DIRECTORY_PREFIX}{normalize_version(version)}"
    )


def pycache_directory(pool_root: Path) -> Path:
    return Path(pool_root) / PYCACHE_DIRECTORY_NAME


def directory_version(name: str) -> str | None:
    """``maafw-5.13.0`` → ``5.13.0``；不是版本目录的形状返回 None。"""

    match = _VERSION_DIRECTORY_RE.match(str(name or ""))
    if match is None:
        return None
    try:
        return str(Version(match.group("version")))
    except InvalidVersion:
        return None


def wheel_platform_tag() -> str:
    """官方 wheel 是平台标签 ``maafw-<ver>-py3-none-win_amd64.whl``（arm64 是 ``win_arm64``）。"""

    if sys.platform != "win32":
        raise MaaFWBindingError("MaaFW 官方 wheel 的平台标签只在 Windows 上解析")
    if struct.calcsize("P") != 8:
        raise MaaFWBindingError("不支持 32 位 Python 宿主")
    machine = platform_module.machine().casefold()
    if "arm" in machine or "aarch" in machine:
        return "win_arm64"
    return "win_amd64"


# ---------------------------------------------------------------------------
# 清单
# ---------------------------------------------------------------------------


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _build_file_entries(root: Path, *, exclude_names: Iterable[str]) -> list[list[Any]]:
    """目录清单：``[相对 posix 路径, 大小, sha256]`` 按路径排序。``__pycache__`` 与清单文件自身不算。"""

    excluded = set(exclude_names)
    entries: list[list[Any]] = []
    for directory, directory_names, file_names in os.walk(root):
        directory_names[:] = sorted(
            name for name in directory_names if name != "__pycache__"
        )
        directory_path = Path(directory)
        for name in sorted(file_names):
            relative = (directory_path / name).relative_to(root).as_posix()
            if relative in excluded or name.endswith(".pyc"):
                continue
            file_path = directory_path / name
            entries.append([relative, file_path.stat().st_size, _sha256_of(file_path)])
    return entries


def _entries_digest(entries: Sequence[Sequence[Any]]) -> str:
    payload = json.dumps(
        [list(item) for item in entries], ensure_ascii=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _read_manifest(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _verify_directory(root: Path, manifest_name: str) -> dict[str, Any] | None:
    """清单全量校验（存在 + 大小 + sha256）；通过返回清单，否则 None。按进程缓存。"""

    manifest_path = root / manifest_name
    try:
        assert_not_reparse(root)
        assert_not_reparse(manifest_path)
        mtime_ns = manifest_path.stat().st_mtime_ns
    except (OSError, MaaFWRuntimePoolError):
        return None
    key = os.path.normcase(str(root))
    with _VERIFIED_CACHE_GUARD:
        cached = _VERIFIED_CACHE.get(key)
    if cached is not None and cached[0] == mtime_ns:
        if _stats_unchanged(root, cached[2]):
            return dict(cached[1])
        _forget_verified(root)
    manifest = _read_manifest(manifest_path)
    if manifest is None or manifest.get("layoutVersion") != BINDING_LAYOUT_VERSION:
        return None
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        return None
    stats: dict[str, tuple[int, int]] = {}
    try:
        for item in entries:
            relative, size, digest = item
            file_path = root / Path(*PurePosixPath(str(relative)).parts)
            if file_path.is_symlink() or not file_path.is_file():
                return None
            metadata = file_path.stat()
            if metadata.st_size != int(size):
                return None
            if _sha256_of(file_path) != str(digest):
                return None
            stats[str(relative)] = (metadata.st_size, metadata.st_mtime_ns)
    except (TypeError, ValueError, OSError):
        return None
    if manifest.get("sha256") != _entries_digest(entries):
        return None
    with _VERIFIED_CACHE_GUARD:
        _VERIFIED_CACHE[key] = (mtime_ns, dict(manifest), stats)
    return dict(manifest)


def _stats_unchanged(root: Path, stats: Mapping[str, tuple[int, int]]) -> bool:
    for relative, (size, mtime_ns) in stats.items():
        file_path = root / Path(*PurePosixPath(relative).parts)
        try:
            metadata = file_path.stat()
        except OSError:
            return False
        if metadata.st_size != size or metadata.st_mtime_ns != mtime_ns:
            return False
    return True


def _forget_verified(root: Path) -> None:
    with _VERIFIED_CACHE_GUARD:
        _VERIFIED_CACHE.pop(os.path.normcase(str(root)), None)


def _info_from_manifest(
    pool_root: Path, directory: Path, manifest: Mapping[str, Any]
) -> BindingInfo:
    version = normalize_version(manifest.get("version"))
    native_dir = native_directory(pool_root, version)
    native_ok = verify_native(pool_root, version) is not None
    raw_requires = manifest.get("requiresDist")
    requires = (
        tuple(str(item) for item in raw_requires)
        if isinstance(raw_requires, list)
        else ()
    )
    return BindingInfo(
        version=version,
        directory=directory,
        source=str(manifest.get("source") or "unknown"),
        requires_dist=requires,
        native_dll_sha256=(
            str(manifest["nativeDllSha256"])
            if manifest.get("nativeDllSha256")
            else None
        ),
        native_directory=native_dir if native_ok else None,
        self_checked=bool(manifest.get("selfChecked", False)),
    )


def verify_binding(pool_root: Path, version: str) -> BindingInfo | None:
    """``bindings/maafw-<ver>`` 清单校验通过则返回它的事实，否则 None（当不存在）。"""

    pool_root = Path(pool_root)
    directory = binding_directory(pool_root, version)
    manifest = _verify_directory(directory, BINDING_MANIFEST_NAME)
    if manifest is None:
        return None
    try:
        if normalize_version(manifest.get("version")) != normalize_version(version):
            return None
    except MaaFWBindingError:
        return None
    # import 期 Library.open(<maa>/bin) 要求目录存在；清单校验只看文件，目录单独看。
    if not (directory / "maa" / "bin").is_dir():
        return None
    return _info_from_manifest(pool_root, directory, manifest)


def verify_native(pool_root: Path, version: str) -> Path | None:
    """``native/maafw-<ver>`` 清单校验通过则返回目录，否则 None。"""

    directory = native_directory(Path(pool_root), version)
    manifest = _verify_directory(directory, NATIVE_MANIFEST_NAME)
    if manifest is None:
        return None
    for name in NATIVE_REQUIRED_LIBRARIES:
        if not (directory / name).is_file():
            return None
    return directory


def list_local_bindings(pool_root: Path) -> dict[str, BindingInfo]:
    """本地所有校验通过的 binding，按版本键。"""

    pool_root = Path(pool_root)
    bindings_root = pool_root / BINDINGS_DIRECTORY_NAME
    result: dict[str, BindingInfo] = {}
    if not bindings_root.is_dir():
        return result
    for child in sorted(bindings_root.iterdir()):
        if child.is_symlink() or not child.is_dir():
            continue
        version = directory_version(child.name)
        if version is None:
            continue
        info = verify_binding(pool_root, version)
        if info is not None:
            result[version] = info
    return result


def touch_binding(
    pool_root: Path, version: str, *, now: datetime | None = None
) -> None:
    """刷新 ``lastUsedAt``（回收宽限的依据）；清单文件自身不在校验范围内，改它不影响命中。

    改完把进程内的校验缓存换成新 mtime 而不是丢掉：native 目录里是几十 MB 的
    DLL，每次运行都重算一遍 sha256 没必要——文件没动，只有清单的时间戳变了。
    """

    pool_root = Path(pool_root)
    with pool_lock(pool_root):
        for directory, manifest_name in (
            (binding_directory(pool_root, version), BINDING_MANIFEST_NAME),
            (native_directory(pool_root, version), NATIVE_MANIFEST_NAME),
        ):
            manifest_path = directory / manifest_name
            manifest = _read_manifest(manifest_path)
            if manifest is None:
                continue
            manifest["lastUsedAt"] = format_time(now or utc_now())
            write_json_atomic(manifest_path, manifest)
            _refresh_verified_after_touch(directory, manifest_path, manifest)


def _refresh_verified_after_touch(
    directory: Path, manifest_path: Path, manifest: Mapping[str, Any]
) -> None:
    key = os.path.normcase(str(directory))
    try:
        mtime_ns = manifest_path.stat().st_mtime_ns
    except OSError:
        _forget_verified(directory)
        return
    with _VERIFIED_CACHE_GUARD:
        cached = _VERIFIED_CACHE.get(key)
        if cached is not None:
            _VERIFIED_CACHE[key] = (mtime_ns, dict(manifest), cached[2])


# ---------------------------------------------------------------------------
# 进程内引用计数：prepare → release 之间、预检事务整段，binding 不得被回收
# ---------------------------------------------------------------------------

_REFCOUNT_GUARD = threading.Lock()
_BINDING_REFCOUNTS: dict[tuple[str, str], int] = {}


def _refcount_key(pool_root: Path, version: str) -> tuple[str, str]:
    return os.path.normcase(str(Path(pool_root).resolve())), normalize_version(version)


def retain_binding(pool_root: Path, version: str) -> None:
    key = _refcount_key(pool_root, version)
    with _REFCOUNT_GUARD:
        _BINDING_REFCOUNTS[key] = _BINDING_REFCOUNTS.get(key, 0) + 1


def release_binding(pool_root: Path, version: str) -> None:
    key = _refcount_key(pool_root, version)
    with _REFCOUNT_GUARD:
        count = _BINDING_REFCOUNTS.get(key, 0) - 1
        if count <= 0:
            _BINDING_REFCOUNTS.pop(key, None)
        else:
            _BINDING_REFCOUNTS[key] = count


def retained_versions(pool_root: Path) -> set[str]:
    """本进程里正被引用（prepare 后未 release、预检进行中）的 binding 版本。"""

    root_key = os.path.normcase(str(Path(pool_root).resolve()))
    with _REFCOUNT_GUARD:
        return {
            version
            for (root, version), count in _BINDING_REFCOUNTS.items()
            if root == root_key and count > 0
        }


def manifest_last_used(
    pool_root: Path, version: str, *, native: bool = False
) -> datetime | None:
    directory = (native_directory if native else binding_directory)(
        Path(pool_root), version
    )
    manifest = _read_manifest(
        directory / (NATIVE_MANIFEST_NAME if native else BINDING_MANIFEST_NAME)
    )
    if manifest is None:
        return None
    try:
        return parse_time(manifest.get("lastUsedAt") or manifest.get("builtAt"))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# 索引
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WheelLink:
    filename: str
    url: str
    sha256: str | None
    version: str | None
    platform_tag: str | None
    #: PEP 592 ``data-yanked``：撤回的版本只有精确钉住才装，范围选择不考虑。
    yanked: bool = False


@dataclass(frozen=True)
class IndexPage:
    index: str
    #: ``ok``（页面拿到了）/ ``missing``（索引可达但没有 maafw 这个包）/ ``unreachable``
    status: str
    links: tuple[WheelLink, ...]
    detail: str = ""


class _SimpleLinkParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[tuple[str, bool]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href: str | None = None
        yanked = False
        for name, value in attrs:
            lowered = name.lower()
            if lowered == "href" and value:
                href = value
            elif lowered == "data-yanked":
                yanked = True
        if href:
            self.hrefs.append((href, yanked))


def parse_simple_page(text: str, base_url: str) -> tuple[WheelLink, ...]:
    """PEP 503 simple 页：只认 ``<a href>``，文件名取 href 路径最后一段，``#sha256=`` 取校验值。"""

    parser = _SimpleLinkParser()
    parser.feed(text)
    links: list[WheelLink] = []
    for href, yanked in parser.hrefs:
        absolute = urllib.parse.urljoin(base_url, href)
        split = urllib.parse.urlsplit(absolute)
        filename = urllib.parse.unquote(PurePosixPath(split.path).name)
        sha256: str | None = None
        if split.fragment:
            fragment = urllib.parse.parse_qs(split.fragment)
            values = fragment.get("sha256")
            if values:
                sha256 = values[0].strip().lower() or None
        match = _WHEEL_FILENAME_RE.match(filename)
        version: str | None = None
        platform_tag: str | None = None
        if match is not None:
            try:
                version = str(Version(match.group("version")))
            except InvalidVersion:
                version = None
            platform_tag = match.group("platform").lower()
        links.append(
            WheelLink(
                filename=filename,
                url=urllib.parse.urlunsplit(split._replace(fragment="")),
                sha256=sha256,
                version=version,
                platform_tag=platform_tag,
                yanked=yanked,
            )
        )
    return tuple(links)


def _build_opener(proxy_url: str | None, url: str) -> urllib.request.OpenerDirector:
    """回环地址（Runtime 中继）不挂代理；其它按调用方给的代理，为空时走系统代理。"""

    host = urllib.parse.urlsplit(url).hostname or ""
    proxy = str(proxy_url or "").strip()
    if host in LOOPBACK_NO_PROXY_HOSTS:
        return urllib.request.build_opener(urllib.request.ProxyHandler({}))
    if proxy:
        return urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        )
    return urllib.request.build_opener()


def _project_page_url(index: str) -> str:
    base = str(index).strip()
    if not base.endswith("/"):
        base += "/"
    return urllib.parse.urljoin(base, "maafw/")


def fetch_index_page(
    index: str,
    *,
    proxy_url: str | None = None,
    timeout: float = INDEX_FETCH_TIMEOUT_SECONDS,
) -> IndexPage:
    """取 ``<index>/maafw/``。三态：ok / missing（404）/ unreachable（其它一切）。"""

    url = _project_page_url(index)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "AUTO-MAS",
            # 只认 HTML：JSON 版 simple 页镜像支持参差，HTML 谁都有。
            "Accept": "text/html, application/vnd.pypi.simple.v1+html;q=0.9, */*;q=0.1",
        },
    )
    try:
        with _build_opener(proxy_url, url).open(request, timeout=timeout) as response:
            raw = response.read(8 * 1024 * 1024)
            charset = response.headers.get_content_charset() or "utf-8"
            final_url = response.geturl() or url
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return IndexPage(index=index, status="missing", links=(), detail="HTTP 404")
        return IndexPage(
            index=index, status="unreachable", links=(), detail=f"HTTP {exc.code}"
        )
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return IndexPage(index=index, status="unreachable", links=(), detail=str(exc))
    try:
        text = raw.decode(charset, errors="replace")
        links = parse_simple_page(text, final_url)
    except Exception as exc:  # noqa: BLE001 - 解析失败当该索引不可用
        return IndexPage(
            index=index, status="unreachable", links=(), detail=f"解析失败: {exc}"
        )
    return IndexPage(index=index, status="ok", links=links)


def select_wheel(
    links: Iterable[WheelLink], version: str, platform_tag: str
) -> WheelLink | None:
    target = normalize_version(version)
    for link in links:
        if link.version == target and link.platform_tag == platform_tag:
            return link
    return None


def available_versions(
    links: Iterable[WheelLink], platform_tag: str, *, include_yanked: bool = False
) -> list[str]:
    versions = {
        link.version
        for link in links
        if link.version is not None
        and link.platform_tag == platform_tag
        and (include_yanked or not link.yanked)
    }
    return sorted(versions, key=Version)


# ---------------------------------------------------------------------------
# 版本选择（方案 D14）
# ---------------------------------------------------------------------------


def parse_maafw_requirement(requirement: str) -> Requirement:
    try:
        parsed = Requirement(str(requirement).strip())
    except InvalidRequirement as exc:
        raise MaaFWBindingError(f"maafw requirement 不合法: {requirement!r}") from exc
    if canonicalize_name(parsed.name) != "maafw":
        raise MaaFWBindingError(f"requirement 必须约束 maafw: {requirement!r}")
    return parsed


def exact_version_of(requirement: str) -> str | None:
    """``maafw==5.13.0`` → ``5.13.0``；范围 / 无约束 → None。"""

    parsed = parse_maafw_requirement(requirement)
    specifiers = list(parsed.specifier)
    if len(specifiers) != 1 or specifiers[0].operator not in {"==", "==="}:
        return None
    value = specifiers[0].version.strip()
    if not value or "*" in value:
        return None
    return normalize_version(value)


#: runner 侧 import 了 ``maa.event_sink``，5.0.0 才有（见 runner/environment.py 的说明）；
#: 范围 / 无约束声明做版本选择时把它当隐式下限，精确钉住的不动。
RUNNER_MINIMUM_MAAFW_VERSION = Version("5.0.0")


def _best_matching(versions: Iterable[str], specifier: SpecifierSet) -> str | None:
    """满足 specifier 的最高版本；预发布只在 specifier 明确含预发布、或没有正式版能满足时才考虑（pip 规则）。"""

    candidates = [
        item
        for item in (Version(value) for value in versions)
        if item >= RUNNER_MINIMUM_MAAFW_VERSION
    ]
    # prereleases=None 让 SpecifierSet 自己决定：specifier 里点名了预发布（>=5.14.0b1）
    # 才放行预发布，否则只看正式版。
    matching = [
        item for item in candidates if specifier.contains(item, prereleases=None)
    ]
    if not matching:
        # 没有正式版能满足时才退而考虑预发布（pip 的行为）；离线只有预发布时也靠这条。
        matching = [
            item for item in candidates if specifier.contains(item, prereleases=True)
        ]
    if not matching:
        return None
    return str(max(matching))


SELECTIONS_FILE_NAME = "binding-selections.json"


def _selections_path(pool_root: Path) -> Path:
    return Path(pool_root) / BINDINGS_DIRECTORY_NAME / SELECTIONS_FILE_NAME


def _project_key(project_path: str | Path) -> str:
    return os.path.normcase(str(Path(project_path).resolve(strict=False)))


def _read_selections(pool_root: Path) -> dict[str, Any]:
    payload = _read_manifest(_selections_path(pool_root))
    entries = payload.get("projects") if payload else None
    return dict(entries) if isinstance(entries, dict) else {}


def remembered_selection(
    pool_root: Path, project_path: str | Path, requirement: str
) -> str | None:
    """这个项目上次按同一个 requirement 选中的版本（D14 (a)），没有或 requirement 变了返回 None。"""

    entry = _read_selections(pool_root).get(_project_key(project_path))
    if not isinstance(entry, dict):
        return None
    if str(entry.get("requirement") or "") != str(requirement):
        return None
    try:
        return normalize_version(entry.get("version"))
    except MaaFWBindingError:
        return None


def remember_selection(
    pool_root: Path, project_path: str | Path, requirement: str, version: str
) -> None:
    pool_root = Path(pool_root)
    with pool_lock(pool_root):
        entries = _read_selections(pool_root)
        key = _project_key(project_path)
        current = entries.get(key)
        if (
            isinstance(current, dict)
            and current.get("requirement") == str(requirement)
            and current.get("version") == normalize_version(version)
        ):
            return
        entries[key] = {
            "requirement": str(requirement),
            "version": normalize_version(version),
            "selectedAt": format_time(utc_now()),
        }
        write_json_atomic(
            _selections_path(pool_root),
            {"layoutVersion": BINDING_LAYOUT_VERSION, "projects": entries},
        )


def prune_selections(pool_root: Path, live_project_paths: Iterable[str | Path]) -> None:
    """回收时把已不在权威集合里的项目条目清掉。"""

    pool_root = Path(pool_root)
    keep = {_project_key(item) for item in live_project_paths}
    with pool_lock(pool_root):
        entries = _read_selections(pool_root)
        pruned = {key: value for key, value in entries.items() if key in keep}
        if pruned != entries:
            write_json_atomic(
                _selections_path(pool_root),
                {"layoutVersion": BINDING_LAYOUT_VERSION, "projects": pruned},
            )


def select_local_version(
    pool_root: Path,
    requirement: str,
    *,
    native_needed: bool = False,
    project_path: str | Path | None = None,
) -> str | None:
    """本地已校验的 binding 里满足 requirement 的版本（D14 第 1 条），没有则 None。

    精确钉住：本地有就是它。范围 / 无约束：先看这个项目上次选中的（仍满足且本地
    还在就沿用，免得兄弟项目一钉高版本就跟着漂），否则取满足 specifier 的最高
    版本；项目没自带 DLL 时源码打包的 binding 不算候选。
    """

    parsed = parse_maafw_requirement(requirement)
    exact = exact_version_of(requirement)
    local = list_local_bindings(pool_root)
    if exact is not None:
        return exact if exact in local else None
    usable = {
        version
        for version, info in local.items()
        if not (native_needed and info.is_source_built)
    }
    if project_path is not None:
        remembered = remembered_selection(pool_root, project_path, requirement)
        if remembered in usable and parsed.specifier.contains(
            Version(remembered), prereleases=True
        ):
            return remembered
    return _best_matching(usable, parsed.specifier)


def select_index_version(
    requirement: str,
    *,
    index_candidates: Sequence[str] | None,
    proxy_url: str | None = None,
) -> str:
    """索引上满足 requirement 的最高版本（D14 第 2 条）：只看本平台标签的 wheel，排除撤回的。

    每个候选归成两态：确定「索引可达但无此包 / 无满足的版本」或不可达。任一候选
    给出确定结论就采纳；全部不可达抛 ``MaaFWBindingNetworkError``。
    """

    parsed = parse_maafw_requirement(requirement)
    tag = wheel_platform_tag()
    failures: list[str] = []
    definite_missing: list[str] = []
    for index in index_candidates or (DEFAULT_PACKAGE_INDEX,):
        page = fetch_index_page(index, proxy_url=proxy_url)
        if page.status == "unreachable":
            failures.append(f"{index}: {page.detail}")
            continue
        if page.status == "missing":
            definite_missing.append(index)
            continue
        chosen = _best_matching(available_versions(page.links, tag), parsed.specifier)
        if chosen is not None:
            return chosen
        definite_missing.append(index)
    if definite_missing:
        raise MaaFWBindingUnavailableError(
            f"索引上没有满足 {requirement} 的 maafw（平台 {tag}）: "
            + ", ".join(definite_missing)
        )
    raise MaaFWBindingNetworkError(
        "所有包索引都连不上，无法解析 maafw 版本: " + "; ".join(failures)
    )


def resolve_binding_version(
    pool_root: Path,
    requirement: str,
    *,
    native_needed: bool,
    project_path: str | Path | None,
    index_candidates: Sequence[str] | None,
    offline: bool,
    proxy_url: str | None = None,
) -> str:
    """requirement → 精确 binding 版本（D14 全套）。选中的范围结果按项目记住。"""

    exact = exact_version_of(requirement)
    if exact is not None:
        return exact
    local = select_local_version(
        pool_root, requirement, native_needed=native_needed, project_path=project_path
    )
    if local is not None:
        if project_path is not None:
            remember_selection(pool_root, project_path, requirement, local)
        return local
    if offline:
        raise MaaFWBindingUnavailableError(
            f"离线模式，且本地没有满足 {requirement} 的 maafw binding"
        )
    chosen = select_index_version(
        requirement, index_candidates=index_candidates, proxy_url=proxy_url
    )
    if project_path is not None:
        remember_selection(pool_root, project_path, requirement, chosen)
    return chosen


# ---------------------------------------------------------------------------
# 铺目录
# ---------------------------------------------------------------------------


def _staging_root(pool_root: Path) -> Path:
    return Path(pool_root) / STAGING_DIRECTORY_NAME


def _new_staging_dir(pool_root: Path, kind: str, version: str) -> Path:
    root = _staging_root(pool_root)
    assert_existing_chain_has_no_reparse(root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{kind}-{version}-{uuid.uuid4().hex}"
    path.mkdir(parents=False, exist_ok=False)
    return path


def _trash_dir(pool_root: Path, name: str) -> Path:
    root = _staging_root(pool_root)
    root.mkdir(parents=True, exist_ok=True)
    return root / f"trash-{name}-{uuid.uuid4().hex}"


def _swap_in(pool_root: Path, staged: Path, target: Path) -> None:
    """把 staging 目录原子换入目标位置；目标已存在时先挪到 trash 再换（``os.replace`` 到非空目录会失败）。"""

    target.parent.mkdir(parents=True, exist_ok=True)
    assert_not_reparse(target)
    if target.exists() or target.is_symlink():
        trash = _trash_dir(pool_root, target.name)
        target.replace(trash)
        remove_tree_best_effort(trash)
    staged.replace(target)
    _forget_verified(target)


def _write_binding_manifest(
    directory: Path,
    *,
    version: str,
    source: str,
    requires_dist: Sequence[str],
    native_dll_sha256: str | None,
    self_checked: bool,
    last_used_at: datetime | None,
) -> dict[str, Any]:
    entries = _build_file_entries(directory, exclude_names=(BINDING_MANIFEST_NAME,))
    now = utc_now()
    manifest = {
        "layoutVersion": BINDING_LAYOUT_VERSION,
        "kind": "auto-mas-maafw-binding",
        "version": version,
        "source": source,
        "files": entries,
        "sha256": _entries_digest(entries),
        "requiresDist": list(requires_dist),
        "nativeDllSha256": native_dll_sha256,
        "builtAt": format_time(now),
        "lastUsedAt": format_time(last_used_at or now),
        "selfChecked": bool(self_checked),
    }
    write_json_atomic(directory / BINDING_MANIFEST_NAME, manifest)
    return manifest


def _write_native_manifest(
    directory: Path,
    *,
    version: str,
    source: str,
    last_used_at: datetime | None,
) -> dict[str, Any]:
    entries = _build_file_entries(directory, exclude_names=(NATIVE_MANIFEST_NAME,))
    now = utc_now()
    dll_entry = next((item for item in entries if item[0] == NATIVE_DLL_NAME), None)
    manifest = {
        "layoutVersion": BINDING_LAYOUT_VERSION,
        "kind": "auto-mas-maafw-native",
        "version": version,
        "source": source,
        "files": entries,
        "sha256": _entries_digest(entries),
        "nativeDllSha256": dll_entry[2] if dll_entry is not None else None,
        "builtAt": format_time(now),
        "lastUsedAt": format_time(last_used_at or now),
    }
    write_json_atomic(directory / NATIVE_MANIFEST_NAME, manifest)
    return manifest


def _is_binding_member(name: str) -> bool:
    """wheel / 源码包成员里属于 binding 目录的：``maa/**``（除 ``maa/bin/**``）+ dist-info。"""

    if name.endswith("/") or "__pycache__" in name or name.endswith(".pyc"):
        return False
    if name.startswith("maa/bin/"):
        return False
    if name.startswith("maa/"):
        return True
    return bool(re.match(r"^maafw-[^/]+\.dist-info/", name, re.IGNORECASE))


def _safe_join(root: Path, member: str) -> Path:
    parts = PurePosixPath(member).parts
    if (
        not parts
        or any(part in ("", ".", "..") for part in parts)
        or PurePosixPath(member).is_absolute()
    ):
        raise MaaFWBindingError(f"归档成员路径不安全: {member}")
    return root.joinpath(*parts)


def _requires_dist_from_metadata(text: str) -> tuple[str, ...]:
    values: list[str] = []
    for line in text.splitlines():
        if line.startswith("Requires-Dist:"):
            values.append(line.split(":", 1)[1].strip())
    return tuple(values)


def _read_wheel_metadata(archive: zipfile.ZipFile) -> tuple[str, tuple[str, ...]]:
    """dist-info 里的 Version 与 Requires-Dist。"""

    for name in archive.namelist():
        if re.match(r"^maafw-[^/]+\.dist-info/METADATA$", name, re.IGNORECASE):
            text = archive.read(name).decode("utf-8", errors="replace")
            version = ""
            for line in text.splitlines():
                if line.startswith("Version:"):
                    version = line.split(":", 1)[1].strip()
                    break
            return version, _requires_dist_from_metadata(text)
    raise MaaFWBindingError("wheel 里没有 maafw 的 dist-info/METADATA")


def _lay_out_binding_from_wheel(
    wheel_path: Path,
    binding_stage: Path,
    native_stage: Path | None,
) -> tuple[str, tuple[str, ...], str | None]:
    """把 wheel 解到 staging：binding 成员进 ``binding_stage``，``maa/bin/**`` 进 ``native_stage``（给了才铺）。

    返回 ``(METADATA 里的版本, Requires-Dist, maa/bin/MaaFramework.dll 的 sha256)``。
    """

    native_dll_sha256: str | None = None
    with zipfile.ZipFile(wheel_path) as archive:
        version, requires = _read_wheel_metadata(archive)
        names = archive.namelist()
        if not any(name == "maa/__init__.py" for name in names):
            raise MaaFWBindingError("wheel 里没有 maa/__init__.py")
        for name in names:
            if _is_binding_member(name):
                target = _safe_join(binding_stage, name)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(name))
            elif name.startswith("maa/bin/") and not name.endswith("/"):
                data = archive.read(name)
                if name == f"maa/bin/{NATIVE_DLL_NAME}":
                    native_dll_sha256 = hashlib.sha256(data).hexdigest()
                if native_stage is not None:
                    target = _safe_join(native_stage, name[len("maa/bin/") :])
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
    _write_bin_placeholder(binding_stage)
    return version, requires, native_dll_sha256


def _write_bin_placeholder(binding_stage: Path) -> None:
    bin_dir = binding_stage / "maa" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    (bin_dir / NO_BUNDLED_DLL_MARKER_NAME).write_text(
        NO_BUNDLED_DLL_MARKER_TEXT, encoding="utf-8"
    )


def _lay_out_binding_from_source(
    archive_path: Path, binding_stage: Path, *, version: str, tag: str
) -> tuple[str, ...]:
    """tag 源码包 → 铺 ``maa/**`` + 生成 dist-info（与 ``binding_fallback.build_binding_wheel`` 同一份成员过滤与 METADATA）。"""

    info = validate_source_archive(archive_path)
    dist_info = f"maafw-{version}.dist-info"
    base = f"{info.top_level}/{BINDING_SOURCE_PREFIX}"
    package_prefix = f"{base}maa/"
    record_rows: list[str] = []

    def add(relative: str, data: bytes) -> None:
        target = _safe_join(binding_stage, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        record_rows.append(f"{relative},sha256={_record_digest(data)},{len(data)}")

    with zipfile.ZipFile(archive_path) as source:
        members = [
            name
            for name in source.namelist()
            if name.startswith(package_prefix)
            and not name.endswith("/")
            and "__pycache__" not in name
            and not name.endswith(".pyc")
            and not name[len(base) :].startswith("maa/bin/")
        ]
        if not members:
            raise MaaFWBindingError("源码包的 maa/ 下没有文件")
        for name in members:
            add(str(PurePosixPath(name[len(base) :])), source.read(name))
        add(
            f"{dist_info}/licenses/LICENSE.md",
            source.read(f"{info.top_level}/LICENSE.md"),
        )
    metadata_lines = [
        "Metadata-Version: 2.1",
        "Name: maafw",
        f"Version: {version}",
        (
            f"Summary: 由 AUTO-MAS 从 MaaFramework {tag} 源码铺目录，"
            "无自带原生库（maa/bin 仅占位）"
        ),
        f"Requires-Python: {info.requires_python}",
        *(f"Requires-Dist: {dependency}" for dependency in info.dependencies),
        "License-File: LICENSE.md",
    ]
    add(f"{dist_info}/METADATA", ("\n".join(metadata_lines) + "\n").encode("utf-8"))
    add(
        f"{dist_info}/WHEEL",
        (
            "Wheel-Version: 1.0\nGenerator: auto-mas\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
        ).encode("utf-8"),
    )
    _write_bin_placeholder(binding_stage)
    record_rows.append(f"{dist_info}/RECORD,,")
    record = binding_stage / dist_info / "RECORD"
    record.write_text("\n".join(record_rows) + "\n", encoding="utf-8")
    return tuple(info.dependencies)


def _record_digest(data: bytes) -> str:
    import base64

    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest())
    return digest.rstrip(b"=").decode("ascii")


# ---------------------------------------------------------------------------
# 下载
# ---------------------------------------------------------------------------


def _download_wheel(
    link: WheelLink,
    destination: Path,
    *,
    proxy_url: str | None,
    check_cancelled: Callable[[], None] | None,
    timeout: float = WHEEL_DOWNLOAD_TIMEOUT_SECONDS,
) -> None:
    request = urllib.request.Request(link.url, headers={"User-Agent": "AUTO-MAS"})
    digest = hashlib.sha256()
    written = 0
    with _build_opener(proxy_url, link.url).open(request, timeout=timeout) as response:
        with destination.open("wb") as stream:
            while True:
                if check_cancelled is not None:
                    check_cancelled()
                chunk = response.read(_DOWNLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                written += len(chunk)
                if written > _MAX_WHEEL_BYTES:
                    raise MaaFWBindingError("wheel 响应体超过大小上限")
                digest.update(chunk)
                stream.write(chunk)
    if written == 0:
        raise MaaFWBindingError("wheel 响应体为空")
    if link.sha256 and digest.hexdigest() != link.sha256:
        raise MaaFWBindingError(
            f"wheel 校验失败: 索引声明 sha256={link.sha256[:12]}…，实际 {digest.hexdigest()[:12]}…"
        )
    if not zipfile.is_zipfile(destination):
        raise MaaFWBindingError("wheel 响应不是 zip 文件")


# ---------------------------------------------------------------------------
# 自检
# ---------------------------------------------------------------------------


def self_check_environment(
    pool_root: Path,
    *,
    binding_dir: Path,
    native_dir: Path | None,
    project_runtime_path: Path | None = None,
    import_paths: Iterable[str | Path] = (),
) -> dict[str, str]:
    """worker 同款的环境变量（``build_runner_environment`` 也用它拼 binding 那几项）。"""

    env = strip_host_python_environment()
    paths = [str(binding_dir)] + [str(Path(item)) for item in import_paths]
    env["PYTHONPATH"] = os.pathsep.join(paths)
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONSAFEPATH"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPYCACHEPREFIX"] = str(pycache_directory(pool_root))
    env["AUTO_MAS_MAAFW_BINDING_DIR"] = str(binding_dir)
    binary_path = project_runtime_path or native_dir
    if binary_path is not None:
        env["MAAFW_BINARY_PATH"] = str(binary_path)
    if native_dir is not None:
        env["AUTO_MAS_MAAFW_NATIVE_DIR"] = str(native_dir)
    return env


_SELF_CHECK_SCRIPT = (
    "import importlib.metadata as m, maa, maa.agent_client, maa.tasker, maa.toolkit;"
    "import os, pathlib;"
    "expected = pathlib.Path(os.environ['AUTO_MAS_MAAFW_BINDING_DIR']).resolve();"
    "actual = pathlib.Path(maa.__file__).resolve();"
    "assert expected in actual.parents, f'maa loaded from {actual}, not {expected}';"
    "print(m.version('maafw'))"
)


def _self_check(
    pool_root: Path,
    base_python: Path,
    *,
    binding_stage: Path,
    native_stage: Path | None,
    expected_version: str,
) -> None:
    env = self_check_environment(
        pool_root, binding_dir=binding_stage, native_dir=native_stage
    )
    try:
        result = subprocess.run(
            [str(base_python), "-c", _SELF_CHECK_SCRIPT],
            capture_output=True,
            timeout=SELF_CHECK_TIMEOUT_SECONDS,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            cwd=str(pool_root),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise MaaFWBindingError(f"binding 自检无法执行: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise MaaFWBindingError(
            f"binding 自检失败 (exit={result.returncode}): {detail[-600:]}"
        )
    reported = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    try:
        if normalize_version(reported) != normalize_version(expected_version):
            raise MaaFWBindingError(
                f"binding 自检报告的版本 {reported!r} 与目标 {expected_version} 不一致"
            )
    except MaaFWBindingError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise MaaFWBindingError(f"binding 自检输出无法解析: {reported!r}") from exc


# ---------------------------------------------------------------------------
# ensure
# ---------------------------------------------------------------------------


def ensure_binding(
    pool_root: Path,
    version: str,
    *,
    native_needed: bool,
    base_python: str | Path | None,
    index_candidates: Sequence[str] | None = None,
    offline: bool = False,
    proxy_url: str | None = None,
    check_cancelled: Callable[[], None] | None = None,
    log: Callable[[str], None] | None = None,
) -> BindingInfo:
    """确保 ``bindings/maafw-<ver>``（及 ``native_needed`` 时的 ``native/maafw-<ver>``）就绪。

    命中 → 刷新 ``lastUsedAt`` 返回。未命中：离线直接报错；否则按索引候选找官方
    wheel（任一候选给出「索引可达但没有这个版本」的确定结论就改走 tag 源码；全部
    不可达才报网络错误）。源码 binding 没有 DLL，``native_needed`` 时拒绝。
    ``base_python`` 为 None 时跳过自检（``selfChecked=False``，收割路径用）。
    """

    pool_root = Path(pool_root)
    version = normalize_version(version)
    emit = log or (lambda _message: None)
    with pool_lock(pool_root):
        existing = verify_binding(pool_root, version)
        if existing is not None and (
            not native_needed or existing.native_directory is not None
        ):
            touch_binding(pool_root, version)
            return verify_binding(pool_root, version) or existing
        if existing is not None and native_needed and existing.is_source_built:
            raise MaaFWBindingError(
                "项目未自带 MaaFramework 原生库，而本地的 binding 来自源码打包"
                f"（无 DLL，{existing.source}），无法运行"
            )
        if offline:
            raise MaaFWBindingUnavailableError(
                f"离线模式，且本地没有 maafw {version} 的 binding"
                + ("（或缺官方原生库）" if native_needed else "")
            )
        base = Path(base_python) if base_python is not None else None
        return _fetch_and_install(
            pool_root,
            version,
            native_needed=native_needed,
            base_python=base,
            index_candidates=index_candidates,
            proxy_url=proxy_url,
            check_cancelled=check_cancelled,
            log=emit,
        )


def _fetch_and_install(
    pool_root: Path,
    version: str,
    *,
    native_needed: bool,
    base_python: Path | None,
    index_candidates: Sequence[str] | None,
    proxy_url: str | None,
    check_cancelled: Callable[[], None] | None,
    log: Callable[[str], None],
) -> BindingInfo:
    tag_platform = wheel_platform_tag()
    failures: list[str] = []
    definite_missing = False
    for index in index_candidates or (DEFAULT_PACKAGE_INDEX,):
        if check_cancelled is not None:
            check_cancelled()
        page = fetch_index_page(index, proxy_url=proxy_url)
        if page.status == "unreachable":
            failures.append(f"{index}: {page.detail}")
            continue
        if page.status == "missing":
            definite_missing = True
            continue
        link = select_wheel(page.links, version, tag_platform)
        if link is None:
            definite_missing = True
            continue
        log(f"[MaaFW Runtime Pool] 下载 maafw {version} binding: {link.url}")
        return _install_from_wheel_link(
            pool_root,
            version,
            link,
            source=f"pypi:{index}",
            native_needed=native_needed,
            base_python=base_python,
            proxy_url=proxy_url,
            check_cancelled=check_cancelled,
        )
    if not definite_missing:
        raise MaaFWBindingNetworkError(
            f"所有包索引都连不上，无法下载 maafw {version}: " + "; ".join(failures)
        )
    if native_needed:
        raise MaaFWBindingUnavailableError(
            f"索引上没有 maafw {version} 的官方 wheel，而项目未自带 MaaFramework 原生库；"
            "源码打包的 binding 没有 DLL，无法运行"
        )
    tag = pep440_to_maafw_tag(version)
    if tag is None:
        raise MaaFWBindingUnavailableError(
            f"索引上没有 maafw {version}，且它映射不到 MaaFramework 的发布 tag"
            "（post/dev/local 版本没有源码包）"
        )
    log(
        f"[MaaFW Runtime Pool] 索引上没有 maafw {version}，改用 MaaFramework {tag} 源码铺 binding"
    )
    return _install_from_source(
        pool_root,
        version,
        tag,
        base_python=base_python,
        proxy_url=proxy_url,
        check_cancelled=check_cancelled,
        log=log,
    )


def _install_from_wheel_link(
    pool_root: Path,
    version: str,
    link: WheelLink,
    *,
    source: str,
    native_needed: bool,
    base_python: Path | None,
    proxy_url: str | None,
    check_cancelled: Callable[[], None] | None,
) -> BindingInfo:
    staging = _staging_root(pool_root)
    staging.mkdir(parents=True, exist_ok=True)
    wheel_path = staging / f"binding-{version}-{uuid.uuid4().hex}.whl"
    binding_stage = _new_staging_dir(pool_root, "binding", version)
    native_stage = (
        _new_staging_dir(pool_root, "native", version) if native_needed else None
    )
    try:
        _download_wheel(
            link, wheel_path, proxy_url=proxy_url, check_cancelled=check_cancelled
        )
        metadata_version, requires, dll_sha256 = _lay_out_binding_from_wheel(
            wheel_path, binding_stage, native_stage
        )
        if normalize_version(metadata_version) != version:
            raise MaaFWBindingError(
                f"wheel METADATA 的版本 {metadata_version!r} 与目标 {version} 不一致"
            )
        if native_stage is not None:
            for name in NATIVE_REQUIRED_LIBRARIES:
                if not (native_stage / name).is_file():
                    raise MaaFWBindingError(f"官方 wheel 的 maa/bin 里缺少 {name}")
        return _finish_install(
            pool_root,
            version,
            binding_stage=binding_stage,
            native_stage=native_stage,
            source=source,
            requires=requires,
            native_dll_sha256=dll_sha256,
            base_python=base_python,
        )
    finally:
        wheel_path.unlink(missing_ok=True)
        for stage in (binding_stage, native_stage):
            if stage is not None and stage.exists():
                remove_tree_best_effort(stage)


def _install_from_source(
    pool_root: Path,
    version: str,
    tag: str,
    *,
    base_python: Path | None,
    proxy_url: str | None,
    check_cancelled: Callable[[], None] | None,
    log: Callable[[str], None],
) -> BindingInfo:
    try:
        archive = download_source_archive(
            tag,
            pool_root / BINDING_SRC_CACHE_RELATIVE_PATH,
            proxy_url=proxy_url,
            check_cancelled=check_cancelled,
            log=log,
        )
    except MaaFWBindingFallbackError as exc:
        raise MaaFWBindingError(str(exc)) from exc
    binding_stage = _new_staging_dir(pool_root, "binding", version)
    try:
        try:
            requires = _lay_out_binding_from_source(
                archive, binding_stage, version=version, tag=tag
            )
        except MaaFWBindingFallbackError as exc:
            raise MaaFWBindingError(str(exc)) from exc
        return _finish_install(
            pool_root,
            version,
            binding_stage=binding_stage,
            native_stage=None,
            source=f"github-source:{tag}",
            requires=requires,
            native_dll_sha256=None,
            base_python=base_python,
        )
    finally:
        if binding_stage.exists():
            remove_tree_best_effort(binding_stage)


def _finish_install(
    pool_root: Path,
    version: str,
    *,
    binding_stage: Path,
    native_stage: Path | None,
    source: str,
    requires: Sequence[str],
    native_dll_sha256: str | None,
    base_python: Path | None,
    last_used_at: datetime | None = None,
) -> BindingInfo:
    """自检 → 写清单 → 换入（native 先、binding 后：binding 就绪即意味着它需要的 native 也在）。"""

    self_checked = False
    if base_python is not None:
        _self_check(
            pool_root,
            base_python,
            binding_stage=binding_stage,
            native_stage=native_stage,
            expected_version=version,
        )
        self_checked = True
    if native_stage is not None:
        _write_native_manifest(
            native_stage, version=version, source=source, last_used_at=last_used_at
        )
    _write_binding_manifest(
        binding_stage,
        version=version,
        source=source,
        requires_dist=requires,
        native_dll_sha256=native_dll_sha256,
        self_checked=self_checked,
        last_used_at=last_used_at,
    )
    if native_stage is not None:
        _swap_in(pool_root, native_stage, native_directory(pool_root, version))
    _swap_in(pool_root, binding_stage, binding_directory(pool_root, version))
    info = verify_binding(pool_root, version)
    if info is None:
        raise MaaFWBindingError(f"maafw {version} 的 binding 换入后校验不通过")
    return info


# ---------------------------------------------------------------------------
# 收割：从旧布局 runtime 的 site-packages 就地取 binding（零网络）
# ---------------------------------------------------------------------------


def _parse_record(text: str) -> list[tuple[str, str | None, int | None]]:
    rows: list[tuple[str, str | None, int | None]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split(",")
        path = parts[0]
        digest = parts[1] if len(parts) > 1 and parts[1] else None
        size: int | None = None
        if len(parts) > 2 and parts[2].strip():
            try:
                size = int(parts[2])
            except ValueError:
                size = None
        rows.append((path, digest, size))
    return rows


def _record_matches(path: Path, digest: str | None, size: int | None) -> bool:
    try:
        data = path.read_bytes()
    except OSError:
        return False
    if size is not None and len(data) != size:
        return False
    if digest is None:
        return True
    algorithm, _, value = digest.partition("=")
    if algorithm.lower() != "sha256":
        return False
    return _record_digest(data) == value


def harvest_binding(
    pool_root: Path,
    site_packages: Path,
    *,
    native_needed: bool,
    source_hint: str,
    last_used_at: datetime | None,
    hardlink_native: bool = True,
) -> BindingInfo | None:
    """从一个旧 runtime 的 ``site-packages`` 就地收割 binding（及需要时的 native）。

    按 ``maafw-<X>.dist-info/RECORD`` 逐文件校验（大小 + sha256），对不上就放弃这个
    版本（返回 None，调用方改走下载）。``nativeDllSha256`` 自己算一遍。源码类型
    （``source_hint`` 以 ``github-source`` 开头）不铺 native。base 此时可能还没建，
    不自检，清单记 ``selfChecked: false``；``lastUsedAt`` 承接旧 runtime 的。native
    优先硬链接（同卷零字节），失败退复制。已有校验通过的同版本 binding 时不重复收割。
    """

    pool_root = Path(pool_root)
    site_packages = Path(site_packages)
    dist_infos = sorted(site_packages.glob("maafw-*.dist-info"))
    if len(dist_infos) != 1:
        return None
    dist_info = dist_infos[0]
    try:
        version = normalize_version(dist_info.name[len("maafw-") : -len(".dist-info")])
    except MaaFWBindingError:
        return None
    source_built = str(source_hint or "").startswith("github-source")
    with pool_lock(pool_root):
        existing = verify_binding(pool_root, version)
        if existing is not None and (
            not native_needed or source_built or existing.native_directory is not None
        ):
            return existing
        try:
            record_text = (dist_info / "RECORD").read_text(encoding="utf-8")
        except OSError:
            return None
        rows = _parse_record(record_text)
        wanted = [
            (path, digest, size)
            for path, digest, size in rows
            if (
                _is_binding_member(path)
                or (path.startswith("maa/bin/") and not path.endswith("/"))
            )
            # 安装器自己加的（INSTALLER / REQUESTED / direct_url.json / uv 私有文件）
            # 不属于 wheel，不铺
            and PurePosixPath(path).name not in _INSTALLER_PRIVATE_FILES
        ]
        if not any(path == "maa/__init__.py" for path, _, _ in wanted):
            return None
        for path, digest, size in wanted:
            if path.endswith("/RECORD"):
                continue
            if not _record_matches(
                site_packages / Path(*PurePosixPath(path).parts), digest, size
            ):
                return None

        binding_stage = _new_staging_dir(pool_root, "binding", version)
        native_stage = (
            _new_staging_dir(pool_root, "native", version)
            if native_needed and not source_built
            else None
        )
        try:
            requires: tuple[str, ...] = ()
            native_dll_sha256: str | None = None
            for path, _digest, _size in wanted:
                origin = site_packages / Path(*PurePosixPath(path).parts)
                if path.startswith("maa/bin/"):
                    if source_built:
                        continue
                    if path == f"maa/bin/{NATIVE_DLL_NAME}":
                        native_dll_sha256 = _sha256_of(origin)
                    if native_stage is not None:
                        target = _safe_join(native_stage, path[len("maa/bin/") :])
                        target.parent.mkdir(parents=True, exist_ok=True)
                        _link_or_copy(origin, target, hardlink=hardlink_native)
                    continue
                target = _safe_join(binding_stage, path)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(origin, target)
                if path.lower().endswith(".dist-info/metadata"):
                    requires = _requires_dist_from_metadata(
                        origin.read_text(encoding="utf-8", errors="replace")
                    )
            _write_bin_placeholder(binding_stage)
            if native_stage is not None:
                for name in NATIVE_REQUIRED_LIBRARIES:
                    if not (native_stage / name).is_file():
                        return None
            return _finish_install(
                pool_root,
                version,
                binding_stage=binding_stage,
                native_stage=native_stage,
                source=source_hint or "harvest",
                requires=requires,
                native_dll_sha256=None if source_built else native_dll_sha256,
                base_python=None,
                last_used_at=last_used_at,
            )
        finally:
            for stage in (binding_stage, native_stage):
                if stage is not None and stage.exists():
                    remove_tree_best_effort(stage)


def _link_or_copy(origin: Path, target: Path, *, hardlink: bool) -> None:
    if hardlink:
        try:
            os.link(origin, target)
            return
        except OSError:
            pass
    shutil.copyfile(origin, target)


__all__ = [
    "BINDINGS_DIRECTORY_NAME",
    "BINDING_MANIFEST_NAME",
    "NATIVE_DIRECTORY_NAME",
    "NATIVE_MANIFEST_NAME",
    "PYCACHE_DIRECTORY_NAME",
    "BindingInfo",
    "IndexPage",
    "MaaFWBindingError",
    "MaaFWBindingNetworkError",
    "MaaFWBindingUnavailableError",
    "WheelLink",
    "available_versions",
    "binding_directory",
    "directory_version",
    "ensure_binding",
    "exact_version_of",
    "fetch_index_page",
    "harvest_binding",
    "list_local_bindings",
    "manifest_last_used",
    "native_directory",
    "normalize_version",
    "parse_simple_page",
    "prune_selections",
    "pycache_directory",
    "release_binding",
    "remember_selection",
    "remembered_selection",
    "resolve_binding_version",
    "retain_binding",
    "retained_versions",
    "select_index_version",
    "select_local_version",
    "select_wheel",
    "self_check_environment",
    "touch_binding",
    "verify_binding",
    "verify_native",
    "wheel_platform_tag",
]
