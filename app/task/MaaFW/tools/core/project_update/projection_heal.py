"""旧投影规则建的载荷按当前规则补齐一次：检查 → 只取缺的条目 → 同版本重建 → 登记。

v5.6.0 的投影逐级匹配目录名，把 MaaFgo v2.0.03 的 ``agent/battle/runtime/`` 当成外壳剔掉
（agent 一起来就 ``ModuleNotFoundError``），MaaEnd v2.30.1 的 ``resource/image/UI/`` 丢了
655 张图。规则改好之后，按旧规则建好、登记好的载荷不会自己恢复——同版本重新登记顶不掉
latest，运行前检查也只会说「已是最新」。这里给这些载荷补一次：

1. **每个载荷只查一次**：清单里 ``projectionRevision`` 不低于当前规则版本的（按当前规则
   建的），或已按当前版本检查过的（``projectionCheck``：没缺 / 已补齐 / 查不了），不再查。
   拿不到比对依据、补齐失败的有限次重试。
2. **只比两版规则之差**（``projection_legacy.newly_kept``）：当前规则保留、载荷那一版规则
   剔掉、载荷里又没有的文件才算缺。没被误伤的项目（M9A 等）一个文件都不补。
3. **比对依据按代价从低到高**：本地导入且来源目录还是同一版本 → 来源目录；更新包下载缓存
   里有同版本的完整包 → 本地 zip；都没有才读 GitHub Release 资产：包一层只读、可 seek 的
   :class:`RangeHTTPReader` 交给标准库 ``zipfile``，读中央目录与缺的条目时才按 64 KB 对齐
   发 HTTP Range，解析、解压、CRC 校验全在标准库里。Mirror 酱的一次性签名地址不碰；GitHub
   CDN 不认后缀式 Range（``bytes=-N`` 回 501），总大小用 ``bytes=0-0`` 的 Content-Range 拿；
   服务端回 200 全量时不读响应体，直接放弃。**不下载整包。** 发行包的白名单要按整包算
   （顶层条目的去留看大小与内容），所以按中央目录在 staging 里建一棵空文件骨架（interface 及
   其 ``import``、``welcome`` 写真内容），大小取中央目录里记的。
4. **重建**：旧载荷 + 取回的文件在 staging 里建成同版本的新载荷 →（取回的文件会影响运行
   环境时才）预检 → 并入共用库 → 登记（``projectionRevision`` 更高，``payloads.register``
   允许它顶替同版本的 latest）→ 由调用方切视图、同步同组脚本。重建失败时把取回的文件交给
   调用方（``fallback``）直接放进触发脚本的视图，本次照常运行。

零宿主耦合：标准库、``httpx``、``json5`` 与本包内的模块（GitHub Release 的资产查找复用
``updater`` 里的实现，只在真要联网时才导入）。

按区间读远端 zip 的零件（:class:`RangeHTTPReader`、:func:`package_entries`、
:func:`read_entry`、:func:`write_archive_skeleton`）也给 GitHub 源的区间差量更新用
（``range_delta.py``）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
import zipfile
import zlib
from collections import Counter
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

import httpx
import json5

from .apply import _EntryBoundary
from .contracts import (
    RESERVED_PROJECT_DIRS,
    RUNTIME_STATE_FILES,
    is_within,
    safe_relative_path,
)
from .payloads import (
    ORIGIN_IMPORT,
    ORIGIN_PACKAGE,
    PROJECTION_CHECK_CLEAN,
    PROJECTION_CHECK_FIELD,
    PayloadError,
    PayloadTarget,
    RegisterResult,
    clone_payload_into,
    finalize,
    lineage_key,
    lineage_lock,
    manifest_files,
    manifest_path,
    payload_dir,
    projection_revision_of,
    read_lineage,
    read_manifest,
    register,
    remove_tree,
    write_json_atomic,
    write_lineage,
)
from .projection import (
    PROJECTION_REVISION,
    ROOT,
    SHARED_EXCLUDED_ROOT_DIRS,
    ProjectionError,
    ProjectionRules,
    _normalize_declared_path,
    _normalize_ui_asset_path,
    _welcome_entries,
    build_projection_rules,
)
from .projection_legacy import newly_kept
from .state import DEFAULT_CACHE_ROOT
from .timing import format_duration

logger = logging.getLogger("automas.maafw.project_update.projection_heal")

CHECK_CLEAN = PROJECTION_CHECK_CLEAN
CHECK_HEALED = "healed"
CHECK_UNAVAILABLE = "unavailable"
CHECK_FAILED = "failed"
# 拿不到比对依据（断网、GitHub 连不上）或重建失败时：最多试这么多次，两次之间至少隔这么久。
# 取回的只是缺的那几个条目，重试不会重复下载大包。
MAX_ATTEMPTS = 3
RETRY_AFTER_SECONDS = 6 * 3600
# 远端按这么大的块对齐读、缓存：zipfile 的多次小读取落在同一块里就不再发请求。
RANGE_BLOCK_SIZE = 64 * 1024
# 一次最多从远端读这么多（中央目录 + 缺的条目）：MaaFgo 一万多条目的中央目录 1.6 MB。
MAX_REMOTE_BYTES = 64 * 1024 * 1024
# 检查跑在运行前、同步等着，超时比更新本身短：Range 连接 5 s、读 10 s，查 Release 的 API
# 每个请求 10 s；整次检查（找依据 + 取回缺的文件）最多 CHECK_DEADLINE_SECONDS，超了按暂时
# 失败记下、本次照常运行。更新本身的超时不受影响。
HTTP_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
API_TIMEOUT_SECONDS = 10.0
CHECK_DEADLINE_SECONDS = 45.0
HTTP_HEADERS = {"User-Agent": "AutoMasGui"}
# 一次最多补这么多：实测 MaaEnd v2.30.1 缺 655 个文件、原始 1.2 MB 左右（Range 读 1.6 MB），
# MaaFgo 3 个。再多说明比对出了意外，不在运行前悄悄下载一大批。
MAX_HEAL_FILES = 5000
MAX_HEAL_BYTES = 100 * 1024 * 1024
# 清单里记下的缺失路径最多几条。
RECORD_MISSING_ITEMS = 20
_LOG_ITEMS = 3
_INTERFACE_NAMES = ("interface.json", "interface.jsonc")
# 与 ``apply.ZIP_MAX_ENTRIES`` 同一上限。
_ZIP_ENTRY_LIMIT = 100_000
# 项目根下这些目录是用户数据 / 运行期产物（与共用库的排除表同一张），不补。
_USER_ROOT_DIRS = frozenset(SHARED_EXCLUDED_ROOT_DIRS)
# 取回的文件会影响运行环境时才在 staging 上预检（依赖清单、二进制、解释器里的东西）；
# 补的只是 agent 源码 / 资源时不预检——切过去之后按 ``envConfirmedFor`` 照常确认一次。
_ENV_INPUT_SUFFIXES = frozenset(
    {".dll", ".pyd", ".so", ".dylib", ".exe", ".whl", ".toml", ".cfg", ".lock"}
)
_ENV_INPUT_PREFIXES = ("requirements", "constraints")


class HealSkip(RuntimeError):
    """拿不到比对依据或条目不能用；``permanent`` 的不再重试，``notify`` 的给用户一行提示。"""

    def __init__(
        self, message: str, *, permanent: bool = False, notify: bool = False
    ) -> None:
        super().__init__(message)
        self.permanent = permanent
        self.notify = notify


class RangeReadCancelled(RuntimeError):
    """``RangeHTTPReader`` 的 ``cancelled()`` 为真：在读响应体的块之间停下（区间差量更新用）。"""


# --------------------------------------------------------------------------
# 远端：按区间读取的只读文件对象，交给 zipfile
# --------------------------------------------------------------------------


def _parse_content_range(value: str) -> tuple[int, int, int | None] | None:
    from .transport import _parse_content_range as parse

    return parse(value)


class RangeHTTPReader:
    """只读、可 seek 的远端文件：``read`` 时按 ``block_size`` 对齐发 HTTP Range，读过的块
    缓存起来。只接受与请求一致的 206（回 200 时不读响应体、直接放弃），累计读到
    ``max_bytes`` 就停。``cancelled()`` 为真时在响应体的块之间抛 :class:`RangeReadCancelled`
    （补齐检查不传；区间差量更新传用户的停止令牌）。"""

    def __init__(
        self,
        client: httpx.Client,
        url: str,
        *,
        expected_size: int | None = None,
        block_size: int = RANGE_BLOCK_SIZE,
        max_bytes: int = MAX_REMOTE_BYTES,
        deadline: float | None = None,
        cancelled: Callable[[], bool] | None = None,
        over_limit_reason: str = "",
        on_chunk: Callable[["RangeHTTPReader"], None] | None = None,
    ) -> None:
        self.client = client
        self.url = url
        self.block_size = block_size
        self.max_bytes = max_bytes
        # ``time.monotonic()`` 的截止时刻：过了就不再发请求（整次检查的总时长上限）。
        self.deadline = deadline
        self.cancelled = cancelled
        # 读的超过 ``max_bytes`` 时的原因：补齐检查默认说「不在运行前自动补齐」，区间差量
        # 更新另给一句（它不是运行前补齐）。
        self.over_limit_reason = over_limit_reason
        # 最后一次响应来自哪台主机（github.com 会跳到 release-assets 之类的 CDN）。
        self.final_host = ""
        # 逐块收到的字节与花在网络请求里的秒数（含没收完就失败的请求）：区间差量的速度
        # 保护据此估吞吐。``on_chunk`` 每收到一块调一次，可以抛 :class:`HealSkip` 中止读取。
        self.received = 0
        self.network_seconds = 0.0
        self.on_chunk = on_chunk
        self.blocks: dict[int, bytes] = {}
        self.position = 0
        self.fetched = 0
        self.requests = 0
        self.size = 0
        # 总大小：GitHub CDN 不认 ``bytes=-N``，用 ``bytes=0-0`` 的 Content-Range。
        total = self._request(0, 0)[1]
        if not total:
            raise HealSkip("下载服务器没给出发行包大小", permanent=True)
        if expected_size and total != expected_size:
            raise HealSkip(
                f"发行包大小与 Release 记录的不同（服务器 {total} 字节，"
                f"Release {expected_size} 字节）"
            )
        self.size = total

    def _request(self, start: int, end: int) -> tuple[bytes, int | None]:
        expected = end - start + 1
        if self.fetched + expected > self.max_bytes:
            raise HealSkip(
                self.over_limit_reason
                or f"要读的太多（超过 {format_size(self.max_bytes)}），不在运行前自动补齐",
                permanent=True,
            )
        if self.deadline is not None and time.monotonic() > self.deadline:
            raise HealSkip("读取发行包超时")
        self.requests += 1
        buffer = bytearray()
        request_started = time.monotonic()
        try:
            with self.client.stream(
                "GET",
                self.url,
                headers={**HTTP_HEADERS, "Range": f"bytes={start}-{end}"},
            ) as response:
                self.final_host = response.url.host or self.final_host
                if response.status_code != 206:
                    # 200 就是服务端不认 Range、要把整包发过来：一个字节都不读。
                    raise HealSkip(
                        f"下载服务器不支持按区间读取（HTTP {response.status_code}）",
                        permanent=response.status_code == 200,
                    )
                content_range = str(response.headers.get("content-range") or "")
                parsed = _parse_content_range(content_range)
                if (
                    parsed is None
                    or parsed[:2] != (start, end)
                    or (self.size and parsed[2] not in (None, self.size))
                ):
                    raise HealSkip(
                        f"下载服务器回的区间与请求不符（要 {start}-{end}，"
                        f"回 {content_range or '没有 Content-Range'}）"
                    )
                for chunk in response.iter_bytes():
                    buffer.extend(chunk)
                    self.received += len(chunk)
                    if len(buffer) > expected:
                        raise HealSkip("下载服务器回的区间比请求的长")
                    if self.cancelled is not None and self.cancelled():
                        raise RangeReadCancelled("update cancelled")
                    if self.on_chunk is not None:
                        self.network_seconds += time.monotonic() - request_started
                        request_started = time.monotonic()
                        self.on_chunk(self)
        except httpx.HTTPError as exc:
            from .transport import _reason

            # 与整包下载的失败原因同一口径（打码、截 200 字；超时类 str 为空时只剩类名）。
            detail = _reason(exc)
            name = type(exc).__name__
            raise HealSkip(
                f"读取发行包失败：{name if detail == name else f'{name}: {detail}'}"
                f"（区间 {start}-{end}）"
            ) from exc
        finally:
            self.network_seconds += time.monotonic() - request_started
        if len(buffer) != expected:
            raise HealSkip("下载服务器回的区间不完整")
        self.fetched += expected
        return bytes(buffer), parsed[2]

    def _ensure(self, first: int, last: int) -> None:
        """把 ``[first, last]`` 里还没有的块读进来，连续缺的合成一次请求。"""

        runs: list[list[int]] = []
        for index in range(first, last + 1):
            if index in self.blocks:
                continue
            if runs and index == runs[-1][-1] + 1:
                runs[-1].append(index)
            else:
                runs.append([index])
        for run in runs:
            start = run[0] * self.block_size
            end = min(self.size, (run[-1] + 1) * self.block_size) - 1
            data = self._request(start, end)[0]
            for offset, index in enumerate(run):
                begin = offset * self.block_size
                self.blocks[index] = data[begin : begin + self.block_size]

    def prefetch(self, start: int, end: int) -> None:
        """把 ``[start, end]`` 字节预读进缓存（缺的块合成一次请求）：区间差量把相邻的
        几个条目连同间隙一次要回来，不让 zipfile 逐条目各发一次。"""

        end = min(end, self.size - 1)
        if end < start:
            return
        self._ensure(start // self.block_size, end // self.block_size)

    def forget(self, before: int) -> None:
        """丢掉 ``before`` 字节所在块之前的缓存（读过的条目不会再读，省内存）。"""

        limit = before // self.block_size
        for index in [index for index in self.blocks if index < limit]:
            del self.blocks[index]

    def read(self, size: int | None = -1) -> bytes:
        if size is None or size < 0:
            size = self.size - self.position
        end = min(self.size, self.position + size)
        if end <= self.position:
            return b""
        first = self.position // self.block_size
        last = (end - 1) // self.block_size
        self._ensure(first, last)
        joined = b"".join(self.blocks[index] for index in range(first, last + 1))
        begin = self.position - first * self.block_size
        data = joined[begin : begin + (end - self.position)]
        self.position = end
        return data

    def seek(self, offset: int, whence: int = 0) -> int:
        base = {0: 0, 1: self.position, 2: self.size}.get(whence)
        if base is None or base + offset < 0:
            raise ValueError(f"invalid seek: {offset}, {whence}")
        self.position = base + offset
        return self.position

    def tell(self) -> int:
        return self.position

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def close(self) -> None:
        self.blocks.clear()


def _open_client(proxy: httpx.Proxy | None) -> httpx.Client:
    """测试替换这里注入 ``MockTransport``。"""

    return httpx.Client(proxy=proxy, follow_redirects=True, timeout=HTTP_TIMEOUT)


async def _github_asset(
    interface_model: Any, version: str, *, proxy: httpx.Proxy | None, shell_hint: str
) -> tuple[str, int]:
    """同版本 GitHub Release 发行包的地址与大小（选资产与更新同一套规则）。"""

    from .updater import (
        MaaFWProjectUpdateError,
        _check_github_release_update,
        _normalize_github_repo,
    )

    if interface_model is None or not _normalize_github_repo(
        str(getattr(interface_model, "github", "") or "")
    ):
        raise HealSkip("interface.json 没有声明 github 仓库", permanent=True)
    try:
        discovery = await _check_github_release_update(
            interface_model,
            current_version="",
            source_config={"project_shell_hint": shell_hint} if shell_hint else {},
            proxy=proxy,
            target_version=version,
            timeout=API_TIMEOUT_SECONDS,
        )
    except (MaaFWProjectUpdateError, httpx.HTTPError) as exc:
        raise HealSkip(f"查询 GitHub Release 失败：{exc}") from exc
    candidate = discovery.candidate if discovery is not None else None
    if candidate is None or not candidate.download_url:
        raise HealSkip(f"GitHub 上没有 {version} 的发行包", permanent=True)
    host = (urlsplit(str(candidate.download_url)).hostname or "").casefold()
    if host != "github.com" and not host.endswith(".github.com"):
        raise HealSkip("发行包不在 GitHub 上，不按区间读取", permanent=True)
    return str(candidate.download_url), int(candidate.size or 0)


# --------------------------------------------------------------------------
# 比对
# --------------------------------------------------------------------------


def _norm_version(value: Any) -> str:
    return str(value or "").strip().lstrip("vV")


def _parse_json(raw: bytes) -> dict[str, Any]:
    text = raw.decode("utf-8-sig")
    try:
        data = json.loads(text)
    except ValueError:
        data = json5.loads(text)
    if not isinstance(data, dict):
        raise ValueError("interface.json 不是对象")
    return data


def is_user_path(rel: str) -> bool:
    """项目里的用户数据 / 运行期文件：不补。"""

    parts = PurePosixPath(rel).parts
    folded = rel.casefold()
    return (
        not parts
        or parts[0].casefold() in _USER_ROOT_DIRS
        or folded in RUNTIME_STATE_FILES
        or any(part.casefold().startswith(".auto_mas") for part in parts)
    )


def _missing_files(
    rules: ProjectionRules,
    candidates: Mapping[str, Path],
    have: Callable[[str], bool],
    revision: int,
) -> list[str]:
    """``candidates``：项目相对路径 → ``rules`` 坐标里的路径。返回当前规则保留、第
    ``revision`` 版规则剔掉、``have`` 又说没有的那些。"""

    return sorted(
        rel
        for rel, relative in candidates.items()
        if not is_user_path(rel)
        and not have(rel)
        and newly_kept(rules, relative, revision)
    )


def _check_limits(missing: list[str], sizes: Mapping[str, int]) -> None:
    total = sum(sizes[rel] for rel in missing)
    if len(missing) > MAX_HEAL_FILES or total > MAX_HEAL_BYTES:
        raise HealSkip(
            f"缺 {len(missing)} 个文件、共 {format_size(total)}，超过自动补齐上限，"
            "请在脚本页重新导入或更新一次",
            permanent=True,
            notify=True,
        )


@dataclass
class Gap:
    """一次比对的结果：缺哪些文件、从哪取。``read`` 取回缺的文件内容（校验过），
    用完 ``close``。"""

    via: str
    missing: list[str]
    size: int
    reader: Callable[[], dict[str, bytes]]
    remote: RangeHTTPReader | None = None
    closers: list[Callable[[], None]] = field(default_factory=list)

    def read(self) -> dict[str, bytes]:
        return self.reader() if self.missing else {}

    @property
    def transferred(self) -> int:
        return self.remote.fetched if self.remote is not None else 0

    def close(self) -> None:
        for closer in self.closers:
            try:
                closer()
            except Exception:  # noqa: BLE001 - 收尾
                pass


def _source_gap(
    source: Path, version: str, revision: int, have: Callable[[str], bool]
) -> Gap | None:
    """本地导入且来源目录还是这个版本：直接按新旧规则扫来源目录；版本不对返回 None。"""

    try:
        rules = build_projection_rules(source, strict=False)
        interface = next(
            rules.interface_base / name
            for name in _INTERFACE_NAMES
            if (rules.interface_base / name).is_file()
        )
        if _norm_version(_parse_json(interface.read_bytes()).get("version")) != (
            _norm_version(version)
        ):
            return None
    except (ProjectionError, StopIteration, OSError, ValueError):
        return None
    root = rules.source_root
    candidates: dict[str, Path] = {}
    for current, _dirs, files in os.walk(root):
        for name in files:
            path = Path(current) / name
            if path.is_symlink():
                continue
            relative = path.relative_to(root)
            try:
                output = rules.output_path(relative)
            except ProjectionError:
                continue
            if output != ROOT:
                candidates[output.as_posix()] = relative
    missing = _missing_files(rules, candidates, have, revision)
    sizes = {rel: (root / candidates[rel]).stat().st_size for rel in missing}
    _check_limits(missing, sizes)

    def read() -> dict[str, bytes]:
        return {rel: (root / candidates[rel]).read_bytes() for rel in missing}

    return Gap(via="导入目录", missing=missing, size=sum(sizes.values()), reader=read)


def package_entries(
    archive: zipfile.ZipFile,
) -> tuple[str, dict[str, zipfile.ZipInfo]]:
    """发行包的 interface 条目与「interface 所在目录相对路径 → 条目」。

    路径安全与更新解压同一判据：有越界 / 绝对路径、符号链接的包整个不用（只比对、不落盘
    也不用：骨架就建在 staging 里）。更新器的保留目录不算条目。
    """

    members = archive.infolist()
    if len(members) > _ZIP_ENTRY_LIMIT:
        raise HealSkip("发行包条目太多", permanent=True)
    interfaces = [
        info
        for info in members
        if not info.is_dir() and PurePosixPath(info.filename).name in _INTERFACE_NAMES
    ]
    if not interfaces:
        raise HealSkip("发行包里没有 interface.json", permanent=True)
    chosen = min(
        interfaces,
        key=lambda info: (len(PurePosixPath(info.filename).parts), info.filename),
    )
    parent = PurePosixPath(chosen.filename).parent.as_posix()
    prefix = "" if parent in {"", "."} else f"{parent}/"
    names = {info.filename for info in members}
    if f"{prefix}changes.json" in names:
        raise HealSkip("这是差量包，没有完整的文件表", permanent=True)
    infos: dict[str, zipfile.ZipInfo] = {}
    for info in members:
        if info.is_dir() or not info.filename.startswith(prefix):
            continue
        rel = info.filename[len(prefix) :]
        if PurePosixPath(rel).parts[:1] and (
            PurePosixPath(rel).parts[0] in RESERVED_PROJECT_DIRS
        ):
            continue
        try:
            rel = safe_relative_path(rel)
        except ValueError as exc:
            raise HealSkip(
                f"发行包里有不安全的路径：{info.filename}", permanent=True
            ) from exc
        if (info.external_attr >> 16) & 0o170000 == 0o120000:
            raise HealSkip(f"发行包里有符号链接：{info.filename}", permanent=True)
        infos.setdefault(rel, info)
    return chosen.filename[len(prefix) :], infos


def read_entry(archive: zipfile.ZipFile, info: zipfile.ZipInfo, rel: str) -> bytes:
    """用 ``zipfile`` 读一个条目：解压与 CRC32 校验都在标准库里，读到结尾时校验。"""

    try:
        with archive.open(info) as handle:
            content = handle.read(info.file_size + 1)
    except (HealSkip, RangeReadCancelled):
        raise
    except (NotImplementedError, RuntimeError) as exc:
        # 压缩方法标准库不认识 / 加密条目：再试也一样。
        raise HealSkip(f"{rel} 无法解压：{exc}", permanent=True) from exc
    except (OSError, EOFError, zipfile.BadZipFile, zlib.error) as exc:
        # CRC 对不上之类：整批丢弃，一个都不写。
        raise HealSkip(f"{rel} 校验失败：{exc}") from exc
    if len(content) != info.file_size:
        raise HealSkip(f"{rel} 大小与中央目录不符")
    return content


def write_archive_skeleton(
    archive: zipfile.ZipFile,
    interface_rel: str,
    infos: Mapping[str, zipfile.ZipInfo],
    skeleton: Path,
    *,
    directories: Iterable[str] = (),
) -> None:
    """按中央目录在 ``skeleton`` 下建空文件骨架：interface 及其 ``import``、``welcome`` 写真
    内容（按区间读取），其余是空文件，大小由调用方按中央目录另给。``directories``：包里
    显式的目录条目（空目录也建出来）。"""

    for directory in sorted(
        {str(PurePosixPath(rel).parent) for rel in infos} | set(directories)
    ):
        (skeleton / directory).mkdir(parents=True, exist_ok=True)
    for rel in infos:
        try:
            (skeleton / rel).open("xb").close()
        except OSError:
            # 大小写只差一点的重名、Windows 保留名：骨架里少一个空文件，只影响它自己。
            continue
    pending = [interface_rel]
    written: set[str] = set()
    while pending:
        rel = pending.pop()
        if rel in written or rel not in infos:
            continue
        written.add(rel)
        raw = read_entry(archive, infos[rel], rel)
        (skeleton / rel).write_bytes(raw)
        if PurePosixPath(rel).suffix.casefold() not in {".json", ".jsonc"}:
            continue
        try:
            data = _parse_json(raw)
        except ValueError:
            continue
        for raw_import in data.get("import") or []:
            if not isinstance(raw_import, str):
                continue
            try:
                pending.append(
                    _normalize_declared_path(raw_import, ROOT, "import").as_posix()
                )
            except ProjectionError:
                continue
        for raw_welcome in _welcome_entries(data.get("welcome")):
            welcome = _normalize_ui_asset_path(raw_welcome, ROOT)
            if welcome is not None:
                pending.append(welcome.as_posix())


def _archive_rules(
    archive: zipfile.ZipFile,
    interface_rel: str,
    infos: Mapping[str, zipfile.ZipInfo],
    workdir: Path,
) -> ProjectionRules:
    """发行包的投影白名单：按中央目录在 ``workdir`` 下建空文件骨架
    （:func:`write_archive_skeleton`），大小取中央目录里记的，再照常算。骨架算完即删。"""

    skeleton = Path(workdir) / f"hk-{uuid.uuid4().hex[:8]}"
    try:
        write_archive_skeleton(archive, interface_rel, infos, skeleton)
        return build_projection_rules(
            skeleton,
            strict=False,
            sizes={rel: info.file_size for rel, info in infos.items()},
        )
    except ProjectionError as exc:
        raise HealSkip(f"算不出发行包的投影白名单：{exc}", permanent=True) from exc
    finally:
        try:
            remove_tree(skeleton)
        except OSError:
            logger.warning("MaaFW 比对用的骨架目录没删掉，留待启动时清理：%s", skeleton)


def _archive_gap(
    archive: zipfile.ZipFile,
    via: str,
    *,
    lineage: str,
    version: str,
    revision: int,
    have: Callable[[str], bool],
    workdir: Path,
) -> Gap:
    """发行包（本地缓存或远端）：核对是同一项目同一版本，算缺的条目。"""

    interface_rel, infos = package_entries(archive)
    try:
        data = _parse_json(read_entry(archive, infos[interface_rel], interface_rel))
        same = lineage_key(data) == lineage
    except (ValueError, PayloadError) as exc:
        raise HealSkip(
            f"发行包里的 interface.json 读不了：{exc}", permanent=True
        ) from exc
    if not same or _norm_version(data.get("version")) != _norm_version(version):
        raise HealSkip("发行包与本机的项目或版本对不上", permanent=True)
    rules = _archive_rules(archive, interface_rel, infos, workdir)
    missing = _missing_files(rules, {rel: Path(rel) for rel in infos}, have, revision)
    sizes = {rel: infos[rel].file_size for rel in missing}
    _check_limits(missing, sizes)

    def read() -> dict[str, bytes]:
        return {rel: read_entry(archive, infos[rel], rel) for rel in missing}

    return Gap(via=via, missing=missing, size=sum(sizes.values()), reader=read)


def _cached_packages(cache_root: Path, version: str) -> list[Path]:
    """更新包下载缓存里目标版本是 ``version`` 的完整包（``data/maafw_update_cache``）。"""

    found: list[Path] = []
    if not cache_root.is_dir():
        return found
    for directory in sorted(cache_root.iterdir()):
        try:
            meta = json.loads((directory / "artifact.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(meta, dict) or not meta.get("complete"):
            continue
        if _norm_version(meta.get("targetVersion")) != _norm_version(version):
            continue
        candidate = Path(str(meta.get("completePath") or ""))
        if (
            candidate.suffix.casefold() == ".zip"
            and candidate.is_file()
            and is_within(candidate, directory)
        ):
            found.append(candidate)
    return found


def _remote_gap(
    url: str,
    size: int,
    *,
    proxy: httpx.Proxy | None,
    deadline: float | None = None,
    **kwargs: Any,
) -> Gap:
    client = _open_client(proxy)
    archive: zipfile.ZipFile | None = None
    try:
        reader = RangeHTTPReader(
            client, url, expected_size=size or None, deadline=deadline
        )
        try:
            archive = zipfile.ZipFile(reader)  # type: ignore[arg-type]
        except zipfile.BadZipFile as exc:
            raise HealSkip(f"发行包的中央目录读不了：{exc}") from exc
        gap = _archive_gap(archive, "GitHub 发行包", **kwargs)
    except BaseException:
        if archive is not None:
            archive.close()
        client.close()
        raise
    gap.remote = reader
    gap.closers.extend([archive.close, client.close])
    return gap


async def find_gap(
    *,
    lineage: str,
    version: str,
    revision: int,
    have: Callable[[str], bool],
    workdir: Path,
    source_ref: str = "",
    interface_model: Any = None,
    proxy: httpx.Proxy | None = None,
    shell_hint: str = "",
    cache_root: Path | None = None,
    deadline: float | None = None,
) -> Gap:
    """按 导入目录 → 缓存的完整包 → GitHub 发行包 的顺序找比对依据，算出缺的文件。

    ``revision``：被比对的那一份（载荷）按哪版投影规则建的；``have(rel)``：它已经有这个
    文件。``deadline``：``time.monotonic()`` 的截止时刻，远端读取过了它就不再发请求。
    拿不到依据抛 :class:`HealSkip`。调用方用完返回值要 ``close``。
    """

    common: dict[str, Any] = {
        "lineage": lineage,
        "version": version,
        "revision": revision,
        "have": have,
        "workdir": workdir,
    }
    if source_ref:
        gap = await asyncio.to_thread(
            _source_gap, Path(source_ref), version, revision, have
        )
        if gap is not None:
            return gap
    for cached in await asyncio.to_thread(
        _cached_packages, Path(cache_root or DEFAULT_CACHE_ROOT), version
    ):
        archive: zipfile.ZipFile | None = None
        try:
            archive = zipfile.ZipFile(cached)
            gap = await asyncio.to_thread(
                _archive_gap, archive, "本机缓存的发行包", **common
            )
        except (HealSkip, OSError, zipfile.BadZipFile) as exc:
            if archive is not None:
                archive.close()
            if getattr(exc, "notify", False):
                raise
            logger.info("MaaFW 缓存包 %s 不能用来比对：%s", cached, exc)
            continue
        gap.closers.append(archive.close)
        return gap
    url, size = await _github_asset(
        interface_model, version, proxy=proxy, shell_hint=shell_hint
    )
    return await asyncio.to_thread(
        _remote_gap, url, size, proxy=proxy, deadline=deadline, **common
    )


def write_missing_files(directory: Path, contents: Mapping[str, bytes]) -> int:
    """把取回的文件直接写进 ``directory``（视图）：临时名 + ``os.replace``，已存在的（期间
    有人拷进来了）不动。路径安全与更新解压同一判据，有一个不合格就整批不写。返回写了几个。"""

    boundary = _EntryBoundary(directory)
    for rel in contents:
        if not boundary.contains(rel):
            raise HealSkip(f"不安全的路径：{rel}", permanent=True)
    written = 0
    for rel, content in contents.items():
        target = directory / rel
        if os.path.lexists(target):
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex[:8]}.tmp")
        try:
            with temporary.open("xb") as handle:
                handle.write(content)
            os.replace(temporary, target)
            written += 1
        finally:
            if os.path.lexists(temporary):
                temporary.unlink()
    return written


# --------------------------------------------------------------------------
# 检查记录（写在被检查的载荷清单里，每个载荷只查一次）
# --------------------------------------------------------------------------


def _now_text() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def check_record(manifest: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """清单里按当前规则版本做的检查记录；更旧版本的记录作废（返回 None）。"""

    record = (manifest or {}).get(PROJECTION_CHECK_FIELD)
    if not isinstance(record, Mapping):
        return None
    try:
        revision = int(record.get("revision") or 0)
    except (TypeError, ValueError):
        return None
    return dict(record) if revision >= PROJECTION_REVISION else None


def check_due(manifest: Mapping[str, Any] | None, *, now: float | None = None) -> bool:
    """这个载荷要不要（再）按当前规则检查一次。"""

    if manifest is None or projection_revision_of(manifest) >= PROJECTION_REVISION:
        return False
    record = check_record(manifest)
    if record is None:
        return True
    if str(record.get("result") or "") in {CHECK_CLEAN, CHECK_HEALED}:
        return False
    if record.get("permanent") or int(record.get("attempts") or 0) >= MAX_ATTEMPTS:
        return False
    moment = time.time() if now is None else now
    return moment - float(record.get("atEpoch") or 0) >= RETRY_AFTER_SECONDS


def healed_to(manifest: Mapping[str, Any] | None) -> str | None:
    """这个载荷已按当前规则补齐成哪一份（没补过为 None）。"""

    record = check_record(manifest)
    if record is None or str(record.get("result") or "") != CHECK_HEALED:
        return None
    return str(record.get("healedTo") or "") or None


def write_check(
    root: Path, lineage: str, payload_id: str, record: Mapping[str, Any]
) -> None:
    """把检查结果写回清单（谱系短锁内读改写，清单的其余字段原样保留）。"""

    with lineage_lock(root, lineage):
        manifest = read_manifest(root, lineage, payload_id)
        if manifest is None:
            return
        manifest[PROJECTION_CHECK_FIELD] = {
            "revision": PROJECTION_REVISION,
            "at": _now_text(),
            "atEpoch": time.time(),
            **dict(record),
        }
        write_json_atomic(manifest_path(root, lineage, payload_id), manifest)


def _write_check_quietly(target: PayloadTarget, record: Mapping[str, Any]) -> None:
    try:
        write_check(target.root, target.lineage, target.payload_id, record)
    except (OSError, PayloadError) as exc:
        logger.warning(
            "MaaFW 载荷 %s 的投影检查结果写不回清单：%s", target.payload_id, exc
        )


def heal_due(root: Path, lineage: str, payload_id: str, channel: str) -> bool:
    """宿主在拿谱系锁之前的廉价判断（读两个 JSON）：要查，或别的渠道已补齐过、本渠道的
    latest 还指着旧的。"""

    try:
        manifest = read_manifest(root, lineage, payload_id)
    except PayloadError:
        return False
    if manifest is None:
        return False
    if check_due(manifest):
        return True
    healed = healed_to(manifest)
    if not healed or healed == payload_id:
        return False
    try:
        entry = read_lineage(root, lineage)["latest"].get(str(channel or ""))
        return (
            isinstance(entry, Mapping)
            and str(entry.get("id") or "") == payload_id
            and payload_dir(root, lineage, healed).is_dir()
        )
    except PayloadError:
        return False


def repoint_latest(target: PayloadTarget, healed: str) -> RegisterResult | None:
    """别的渠道已把这个载荷补齐成 ``healed``：本渠道的 latest 还指着旧的就指过去。"""

    root, lineage, channel = target.root, target.lineage, target.channel
    with lineage_lock(root, lineage):
        if not payload_dir(root, lineage, healed).is_dir():
            return None
        manifest = read_manifest(root, lineage, healed)
        if manifest is None:
            return None
        data = read_lineage(root, lineage)
        entry = data["latest"].get(channel)
        if (
            not isinstance(entry, Mapping)
            or str(entry.get("id") or "") != target.payload_id
        ):
            return None
        data["latest"][channel] = {
            **dict(entry),
            "id": healed,
            "version": str(manifest.get("version") or entry.get("version") or ""),
            "source": dict(manifest.get("source") or {}),
            "by": target.by,
            "at": _now_text(),
        }
        write_lineage(root, lineage, data)
    return RegisterResult(
        payload_id=healed,
        latest_id=healed,
        created=False,
        advanced=True,
        manifest=manifest,
        latest_available=True,
    )


# --------------------------------------------------------------------------
# 重建
# --------------------------------------------------------------------------


def needs_environment_precheck(rels: Iterable[str]) -> bool:
    """取回的文件里有没有运行环境的输入（依赖清单、二进制、解释器目录里的东西）。"""

    for rel in rels:
        path = PurePosixPath(rel.casefold())
        if path.suffix in _ENV_INPUT_SUFFIXES:
            return True
        if path.name.startswith(_ENV_INPUT_PREFIXES) and path.suffix == ".txt":
            return True
        if path.name == "pyproject.toml" or any(
            part == "site-packages" or part.endswith(".dist-info")
            for part in path.parts
        ):
            return True
    return False


def rebuild_payload(
    target: PayloadTarget,
    manifest: Mapping[str, Any],
    additions: Mapping[str, bytes],
    *,
    post_validate: Callable[[Path], Any] | None = None,
) -> RegisterResult:
    """旧载荷 + 取回的文件 → staging 里的同版本新载荷 →（按需）预检 → 并入共用库 → 登记，
    并把「已补齐成哪一份」记进旧载荷的清单。staging 之外什么都不改：任何一步失败都只是
    丢掉 staging。"""

    old_files = manifest_files(manifest)
    staging = (
        Path(target.staging_root) / f"heal-{target.lineage}-{uuid.uuid4().hex[:8]}"
    )
    try:
        staging.mkdir(parents=True, exist_ok=False)
        clone_payload_into(target.directory(), old_files, staging)
        for rel, content in sorted(additions.items()):
            destination = staging / safe_relative_path(rel)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as handle:
                handle.write(content)
        if post_validate is not None and needs_environment_precheck(additions):
            if post_validate(staging) is False:
                raise PayloadError("补齐后的版本没通过运行环境预检")
        finalized = finalize(
            staging, blob_store=target.blob_store, private=target.private_paths
        )
        damaged = target.payload_id in {
            str(item)
            for item in read_lineage(target.root, target.lineage).get("damaged") or []
        }
        # 从旧载荷原样搬来的文件内容没变，清单里的哈希直接用（被写穿过的载荷除外）。
        known = (
            {}
            if damaged
            else {rel: entry["sha256"] for rel, entry in old_files.items()}
        )
        known = {rel: sha for rel, sha in known.items() if sha}
        known.update(finalized.hashes)
        source = dict(manifest.get("source") or {})
        origins = {rel: entry["origin"] for rel, entry in old_files.items()}
        added_origin = (
            ORIGIN_PACKAGE
            if str(source.get("kind") or "") == "update"
            else ORIGIN_IMPORT
        )
        origins.update({rel: added_origin for rel in additions})
        registered = register(
            target.root,
            staging,
            lineage=target.lineage,
            channel=target.channel,
            source=source,
            by=target.by,
            version=str(manifest.get("version") or ""),
            lineage_info=target.lineage_info,
            known_hashes=known,
            origins=origins,
            bundled={
                "maafw": str(manifest.get("bundledMaaFW") or ""),
                "python": str(manifest.get("bundledPython") or ""),
            },
            projection_revision=PROJECTION_REVISION,
        )
    except BaseException:
        try:
            remove_tree(staging)
        except OSError:
            logger.warning("MaaFW 补齐 staging 清理失败，留待启动时清理：%s", staging)
        raise
    return registered


# --------------------------------------------------------------------------
# 编排
# --------------------------------------------------------------------------


def format_size(size: int) -> str:
    return f"{size / 1024:.1f} KB" if size < 1024 * 1024 else f"{size / 2**20:.1f} MB"


def describe_missing(missing: list[str]) -> str:
    """日志里怎么说缺了哪些：三个以内逐个列；多了只给最常见的目录（「resource/image/UI/Item/… 等」）。"""

    if len(missing) <= _LOG_ITEMS:
        return "、".join(missing)
    parents = Counter(PurePosixPath(rel).parent.as_posix() for rel in missing)
    top = parents.most_common(1)[0][0]
    return f"{top}/… 等" if top != "." else "、".join(missing[:_LOG_ITEMS]) + " 等"


class HealOutcome:
    """一次载荷检查的结果（``view_update.run_view_update`` 的 ``result``）。

    故意不是 dataclass：``run_view_update`` 会把 dataclass 结果按更新结果的字段改写。
    ``status``：``skipped``（不用查）/ ``clean``（没缺）/ ``healed``（补齐并登记）/
    ``repointed``（别的渠道已补齐过，本渠道的 latest 指过去）/ ``unavailable``（拿不到比对
    依据）/ ``failed``（重建失败）。``switched`` 由宿主在切完视图后填；``fallback_written``：
    重建失败后直接放进视图的文件数。
    """

    def __init__(
        self,
        status: str,
        *,
        version: str = "",
        missing: Iterable[str] = (),
        via: str = "",
        payload_id: str | None = None,
        reason: str = "",
        transferred: int = 0,
        elapsed: float = 0.0,
        fallback_written: int = 0,
    ) -> None:
        self.status = status
        self.version = version
        self.missing = sorted(missing)
        self.via = via
        self.payload_id = payload_id
        self.reason = reason
        self.transferred = transferred
        self.elapsed = elapsed
        self.fallback_written = fallback_written
        self.switched = False

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return (
            f"HealOutcome(status={self.status!r}, version={self.version!r}, "
            f"missing={len(self.missing)}, via={self.via!r}, reason={self.reason!r})"
        )


async def heal_payload(
    target: PayloadTarget,
    after_register: Callable[[RegisterResult], Awaitable[Any]] | None = None,
    *,
    interface_model: Any = None,
    proxy: httpx.Proxy | None = None,
    shell_hint: str = "",
    post_validate: Callable[[Path], Any] | None = None,
    send_log: Callable[[str], None] | None = None,
    cache_root: Path | None = None,
    fallback: Callable[[Mapping[str, bytes]], int] | None = None,
) -> HealOutcome:
    """检查 ``target`` 挂的载荷，缺文件就按同一版本补齐、登记，并 await ``after_register``。

    **从不抛异常**：结果记进清单与日志，调用方照常用当前载荷运行。重建失败时把取回的文件
    交给 ``fallback``（直接放进触发脚本的视图）。
    """

    log = send_log or (lambda _line: None)
    started = time.monotonic()
    try:
        manifest = await asyncio.to_thread(
            read_manifest, target.root, target.lineage, target.payload_id
        )
    except Exception as exc:  # noqa: BLE001 - 读不了清单就当不用查
        logger.warning("MaaFW 载荷 %s 的清单读不了：%s", target.payload_id, exc)
        return HealOutcome("skipped", reason=str(exc))
    if manifest is None:
        return HealOutcome("skipped", reason="清单不在")
    version = str(manifest.get("version") or "")

    healed = healed_to(manifest)
    if healed and healed != target.payload_id:
        try:
            repointed = await asyncio.to_thread(repoint_latest, target, healed)
        except Exception as exc:  # noqa: BLE001 - 指不过去就照旧，下次再试
            logger.warning("MaaFW 渠道 latest 指向补齐后的版本失败：%s", exc)
            repointed = None
        if repointed is not None:
            logger.info(
                "MaaFW 载荷 %s 已在别的渠道补齐成 %s，本渠道的 latest 指过去",
                target.payload_id,
                healed,
            )
            if after_register is not None:
                try:
                    await after_register(repointed)
                except Exception:  # noqa: BLE001 - latest 已指过去，下次组同步补上
                    logger.warning("MaaFW 补齐后的切换失败", exc_info=True)
            return HealOutcome("repointed", version=version, payload_id=healed)
    if not check_due(manifest):
        return HealOutcome("skipped", version=version)

    previous = check_record(manifest) or {}
    attempts = int(previous.get("attempts") or 0) + 1
    revision = projection_revision_of(manifest)
    have_keys = {rel.casefold() for rel in manifest_files(manifest)}
    source = manifest.get("source") or {}

    deadline = time.monotonic() + CHECK_DEADLINE_SECONDS

    async def locate() -> tuple[Gap, dict[str, bytes]]:
        found = await find_gap(
            lineage=target.lineage,
            version=version,
            revision=revision,
            have=lambda rel: rel.casefold() in have_keys,
            workdir=Path(target.staging_root),
            source_ref=(
                str(source.get("ref") or "")
                if str(source.get("kind") or "") == "import"
                else ""
            ),
            interface_model=interface_model,
            proxy=proxy,
            shell_hint=shell_hint,
            cache_root=cache_root,
            deadline=deadline,
        )
        try:
            return found, await asyncio.to_thread(found.read)
        except BaseException:
            await asyncio.to_thread(found.close)
            raise

    try:
        try:
            gap, contents = await asyncio.wait_for(
                locate(), timeout=CHECK_DEADLINE_SECONDS
            )
        except TimeoutError as exc:
            raise HealSkip(
                f"检查超过 {CHECK_DEADLINE_SECONDS:.0f} 秒没做完，下次再试"
            ) from exc
    except Exception as exc:  # noqa: BLE001 - 查不了只是跳过，不挡运行
        if not isinstance(exc, HealSkip):
            logger.warning("MaaFW 按当前投影规则核对载荷时出错", exc_info=True)
        permanent = bool(getattr(exc, "permanent", False))
        reason = str(exc).strip() or type(exc).__name__
        await asyncio.to_thread(
            _write_check_quietly,
            target,
            {
                "result": CHECK_UNAVAILABLE,
                "permanent": permanent,
                "attempts": attempts,
                "reason": reason[:500],
            },
        )
        message = f"检查 {version} 是否漏装文件没做成（{reason}），本次照常运行"
        logger.info(
            "MaaFW 载荷 %s：%s（第 %d 次）", target.payload_id, message, attempts
        )
        if not permanent or getattr(exc, "notify", False):
            # 暂时性的（断网、校验失败）与超上限才告诉用户，前者最多 MAX_ATTEMPTS 次；
            # 没有 GitHub 仓库、服务端不认 Range 这类查不了的只进后端日志。
            log(message)
        return HealOutcome(
            "unavailable",
            version=version,
            reason=reason,
            elapsed=time.monotonic() - started,
        )
    await asyncio.to_thread(gap.close)

    missing = sorted(contents)
    if not missing:
        await asyncio.to_thread(
            _write_check_quietly,
            target,
            {"result": CHECK_CLEAN, "via": gap.via, "attempts": attempts},
        )
        logger.info(
            "MaaFW 载荷 %s 按当前投影规则核对过（%s），没有漏装的文件",
            target.payload_id,
            gap.via,
        )
        return HealOutcome(
            "clean",
            version=version,
            via=gap.via,
            transferred=gap.transferred,
            elapsed=time.monotonic() - started,
        )

    size = sum(len(content) for content in contents.values())
    found = (
        f"检测到 {version} 缺少 {len(missing)} 个文件（{describe_missing(missing)}），"
        f"已从{gap.via}取回（{format_size(size)}"
        + (f"，下载 {format_size(gap.transferred)}" if gap.transferred else "")
        + "）"
    )
    try:
        registered = await asyncio.to_thread(
            rebuild_payload, target, manifest, contents, post_validate=post_validate
        )
    except Exception as exc:  # noqa: BLE001 - 重建失败不挡运行
        permanent = bool(getattr(exc, "permanent", False))
        reason = str(exc).strip() or type(exc).__name__
        logger.warning("MaaFW 补齐载荷 %s 失败：%s", target.payload_id, reason)
        await asyncio.to_thread(
            _write_check_quietly,
            target,
            {
                "result": CHECK_FAILED,
                "permanent": permanent,
                "attempts": attempts,
                "reason": reason[:500],
                "missingCount": len(missing),
                "missing": missing[:RECORD_MISSING_ITEMS],
            },
        )
        written = 0
        if fallback is not None:
            try:
                written = await asyncio.to_thread(fallback, contents)
            except Exception as fallback_error:  # noqa: BLE001
                logger.warning("MaaFW 补齐文件直接放进视图也失败：%s", fallback_error)
        log(
            f"{found}，但生成补齐后的版本失败（{reason}）"
            + ("，已直接放进本脚本的项目目录" if written else "")
            + f"，本次照常运行，用时 {format_duration(time.monotonic() - started)}"
        )
        return HealOutcome(
            "failed",
            version=version,
            missing=missing,
            via=gap.via,
            reason=reason,
            transferred=gap.transferred,
            elapsed=time.monotonic() - started,
            fallback_written=written,
        )

    await asyncio.to_thread(
        _write_check_quietly,
        target,
        {
            "result": CHECK_HEALED,
            "healedTo": registered.payload_id,
            "via": gap.via,
            "attempts": attempts,
            "missingCount": len(missing),
            "missing": missing[:RECORD_MISSING_ITEMS],
        },
    )
    log(
        f"{found}，已生成补齐后的版本，用时 "
        f"{format_duration(time.monotonic() - started)}"
    )
    if after_register is not None:
        try:
            await after_register(registered)
        except Exception:  # noqa: BLE001 - 载荷已在册，没切过去的下次组同步补上
            logger.warning("MaaFW 补齐后的切换失败", exc_info=True)
            log("补齐后的版本已登记，但切换脚本时出错；下次运行前会再同步")
    return HealOutcome(
        "healed",
        version=version,
        missing=missing,
        via=gap.via,
        payload_id=registered.payload_id,
        transferred=gap.transferred,
        elapsed=time.monotonic() - started,
    )


__all__ = [
    "CHECK_CLEAN",
    "CHECK_FAILED",
    "CHECK_HEALED",
    "CHECK_UNAVAILABLE",
    "Gap",
    "HealOutcome",
    "HealSkip",
    "RangeHTTPReader",
    "RangeReadCancelled",
    "check_due",
    "check_record",
    "describe_missing",
    "find_gap",
    "format_size",
    "heal_due",
    "heal_payload",
    "healed_to",
    "is_user_path",
    "needs_environment_precheck",
    "package_entries",
    "read_entry",
    "rebuild_payload",
    "repoint_latest",
    "write_archive_skeleton",
    "write_check",
    "write_missing_files",
]
