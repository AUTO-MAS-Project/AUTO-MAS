"""GitHub 发行包按 HTTP Range 区间差量（#1118 方案 B）。

GitHub 源以前一律下整包（识宝 185 MB、MPA 173 MB），哪怕两版之间只改了几个文件。这里只读
发行包的中央目录，按 CRC32 + 大小与当前载荷逐条目比对，只把变了的条目按区间取回来，没变的
从当前载荷硬链接（与 ``clone_payload_into`` 同一口径：库里的链接、小文件复制），在
``.staging/rpk-*`` 里拼成一棵「虚拟全量包」，再交给 ``payloads.build_from_package`` 按全量包
的语义建新载荷（stale 规则一字不改）。结果与整包下载后建出的载荷逐字节一致：

- 白名单与整包同一张：在中央目录建的空文件骨架（interface 及其 ``import``、``welcome`` 写真
  内容，大小取中央目录里记的）叠在当前载荷上，用 ``package_projection_rules`` 算，与整包解压后
  的叠加视图同样的输入；算出的条目表直接交给 ``build_from_package``（``package_entries``），
  不在缺着外壳文件的虚拟树上再投影一遍。
- 包的形态与整包解压的认法对不上的（根上有 ``changes.json`` / ``payload/`` / ``files/``、
  保留目录、重名条目、整包解压会改写的条目名、只差大小写的目录段）不走区间，改下整包。

只直连 ``github.com``（与投影补齐同一约束）：加速镜像是第三方转发，按区间取回的字节只有
条目级 CRC32、没有整包 sha256 可校验。区间这一路任何一步失败都抛
:class:`RangeDeltaUnavailable`，调用方丢掉这一批、同一次更新里照常下全量包（全量可以走镜像）；
用户停止抛 :class:`RangeDeltaCancelled`，照常取消、不退回。

零宿主耦合：标准库、``httpx`` 与本包内的模块。
"""

from __future__ import annotations

import logging
import os
import zipfile
import zlib
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

import httpx

from .apply import _EntryBoundary, _zip_member_parts
from .blob_store import place_fresh
from .contracts import RESERVED_PROJECT_DIRS
from .payloads import PayloadError, lineage_key, manifest_files, remove_tree
from .projection import (
    ProjectionError,
    describe_dropped_code_files,
    filter_package_entries,
    package_projection_rules,
    package_takeover_dirs,
)
from .projection_heal import (
    HealSkip,
    RangeHTTPReader,
    RangeReadCancelled,
    _norm_version,
    _parse_json,
    format_size,
    package_entries,
    read_entry,
    write_archive_skeleton,
)
from .timing import format_duration

logger = logging.getLogger("automas.maafw.project_update.range_delta")

#: 设成 1 时 GitHub 源不走区间、Mirror 酱源不要差量包，一律下全量包（验收比对与应急用，
#: 不进配置、不上界面）。
FORCE_FULL_PACKAGE_ENV = "AUTO_MAS_MAAFW_FORCE_FULL_PACKAGE"
# 要取回的条目压缩后合计超过发行包的这个比例，或条目数超过上限，就不按区间取、改下整包：
# 变化这么大时逐段要回来不比整包省多少，还多了几百次请求。
MAX_FETCH_RATIO = 0.4
MAX_FETCH_ENTRIES = 3000
# 相邻两个要取的条目之间隔得不到这么多就合成一次 Range（连同间隙一起要回来）；一次最多要
# 这么大（缓存在内存里，单个条目更大时它自己一组）。
MERGE_GAP_BYTES = 1024 * 1024
MAX_GROUP_BYTES = 8 * 1024 * 1024
# 条目的本地文件头比中央目录多出来的扩展字段估个余量；估少了 zipfile 自己会再读一块。
_LOCAL_HEADER_SLACK = 1024
_LOCAL_HEADER_SIZE = 30
# 更新不像运行前检查那样同步等着：单次请求给足时间，整段没有总时长上限（用户可以停止）。
HTTP_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_COPY_CHUNK = 1024 * 1024
# 直连太慢就放弃区间（只在整包能走加速镜像时才设，见 :class:`RangeSpeedGuard`）：国内直连
# GitHub 常年只有 100 多 KB/s，40% 预算的上限对识宝约 74 MB，按这个速度要十几分钟，
# 不如按镜像下整包。估算「已用时 + 剩余计划字节 / 实测吞吐」超过这个秒数就放弃。
SPEED_GUARD_BUDGET_SECONDS = 120.0
# 不论估算多少，整次区间（读文件目录 + 取回）用时超过这个就放弃。
SPEED_GUARD_HARD_LIMIT_SECONDS = SPEED_GUARD_BUDGET_SECONDS * 1.5
# 吞吐样本够了才估：花在网络上至少这么多秒，或者至少收到这么多字节（取先到的）。
SPEED_GUARD_MIN_SAMPLE_SECONDS = 3.0
SPEED_GUARD_MIN_SAMPLE_BYTES = 512 * 1024
_CANCEL_CHECK_EVERY = 200
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


class RangeDeltaUnavailable(RuntimeError):
    """这次不能按区间差量（原因即 ``str(exc)``）：调用方丢掉这一批，改下全量包。"""


class RangeDeltaCancelled(RuntimeError):
    """用户停止了更新：照常取消，不退回全量包。"""


class RangeSpeedGuard:
    """直连按需下载的速度保护：整包能走加速镜像时才由调用方建，不能退就不设。

    读取器每收到一块调一次 :meth:`observe`（``RangeHTTPReader(on_chunk=...)``）；样本够了
    就按「网络已用时 + 剩余字节 / 实测吞吐」估，超过 :data:`SPEED_GUARD_BUDGET_SECONDS`
    抛 :class:`HealSkip`（区间这一路的失败，调用方照常退回整包）；网络已用时超过
    :data:`SPEED_GUARD_HARD_LIMIT_SECONDS` 无论估多少都放弃。

    **只看花在网络请求里的时间**（读取器累计的 ``network_seconds``）：本地的活——列旧载荷
    大小、算投影规则、逐文件 CRC、取回阶段链接 / 复制——不算。大载荷放在慢盘上时网络再快
    也会被墙钟拖过预算，而退回整包同样要做这些本地活（还多解压一遍），按墙钟放弃只会更慢。
    所以不另设墙钟总上限；单次读取 30 秒没数据由读取超时兜住。

    剩余字节分两段：读到包尾的结束记录后按「读完中央目录还要多少」估（``phase`` 为
    「读文件目录」），定好取回计划后按整次计划估；结束记录读到之前只看硬上限。
    """

    def __init__(self) -> None:
        self.budget = SPEED_GUARD_BUDGET_SECONDS
        self.hard_limit = SPEED_GUARD_HARD_LIMIT_SECONDS
        self.min_seconds = SPEED_GUARD_MIN_SAMPLE_SECONDS
        self.min_bytes = SPEED_GUARD_MIN_SAMPLE_BYTES
        #: 到当前这一段结束时从远端一共读的字节（读目录时是读完目录，之后是整次计划）。
        self.planned_total: int | None = None
        #: 估算的是哪一段，进日志。
        self.phase = "按需下载"

    def observe(self, reader: RangeHTTPReader) -> None:
        received, seconds = reader.received, reader.network_seconds
        if seconds > self.hard_limit:
            raise HealSkip(
                f"直连 GitHub {self.phase}，网络已用 {format_duration(seconds)}，"
                f"超过上限 {format_duration(self.hard_limit)}，改为按镜像下整包"
            )
        if self.planned_total is None or received <= 0 or seconds <= 0:
            return
        if seconds < self.min_seconds and received < self.min_bytes:
            # 样本太小：开头的握手、跳转会把速度算得很低，不据此放弃。
            return
        rate = received / seconds
        remaining = max(0, self.planned_total - received) / rate
        if seconds + remaining > self.budget:
            raise HealSkip(
                f"直连 GitHub 实测 {format_size(int(rate))}/s，{self.phase}预计还要 "
                f"{format_duration(remaining)}（网络已用 {format_duration(seconds)}），"
                f"超过 {format_duration(self.budget)}，改为按镜像下整包"
            )


def force_full_package() -> bool:
    """环境变量 :data:`FORCE_FULL_PACKAGE_ENV` 要求一律下全量包。"""

    return os.environ.get(FORCE_FULL_PACKAGE_ENV, "").strip().casefold() in _TRUE_VALUES


def is_github_download(url: str) -> bool:
    """发行包地址在 GitHub 上（与投影补齐同一判据）：只有这种才按区间读。"""

    host = (urlsplit(str(url or "")).hostname or "").casefold()
    return host == "github.com" or host.endswith(".github.com")


def _open_client(proxy: httpx.Proxy | None) -> httpx.Client:
    """测试替换这里注入 ``MockTransport``。"""

    return httpx.Client(proxy=proxy, follow_redirects=True, timeout=HTTP_TIMEOUT)


@dataclass
class RangeDelta:
    """读完中央目录、比对完当前载荷的结果。``entries`` 是白名单内的全部条目，其中
    ``reuse`` 从当前载荷搬（值是当前载荷里的文件），``fetch`` 按区间取回。用完 ``close``。"""

    client: httpx.Client
    reader: RangeHTTPReader
    archive: zipfile.ZipFile
    entries: dict[str, zipfile.ZipInfo]
    reuse: dict[str, Path]
    fetch: dict[str, zipfile.ZipInfo]
    #: 读中央目录（及 interface / import）已经花掉的字节。
    probe_bytes: int = 0
    #: 按 :func:`plan_range_fetch` 算出的取回阶段要发的字节（含文件头、合并的间隙、块对齐）。
    planned_fetch_bytes: int = 0
    #: 新包整体接管的目录（与整包落地同一个 ``package_takeover_dirs``，同一套规则算）。
    takeover_dirs: frozenset[str] = frozenset()

    @property
    def size(self) -> int:
        """发行包大小。"""

        return self.reader.size

    @property
    def planned_bytes(self) -> int:
        """整次区间更新计划从远端读的字节：已读的中央目录 + 取回阶段要发的。"""

        return self.probe_bytes + self.planned_fetch_bytes

    @property
    def fetch_bytes(self) -> int:
        """要取回的条目压缩后合计（名义大小：不含文件头与合并区间时顺带要回来的间隙）。"""

        return sum(info.compress_size for info in self.fetch.values())

    @property
    def fetch_expanded(self) -> int:
        return sum(info.file_size for info in self.fetch.values())

    @property
    def transferred(self) -> int:
        """到目前为止实际从远端读了多少（含中央目录）。"""

        return self.reader.fetched

    def close(self) -> None:
        for closer in (self.archive.close, self.reader.close, self.client.close):
            try:
                closer()
            except Exception:  # noqa: BLE001 - 收尾
                pass


# --------------------------------------------------------------------------
# 读中央目录、算白名单、与当前载荷比对
# --------------------------------------------------------------------------


def _check_layout(
    archive: zipfile.ZipFile, interface_rel: str, infos: Mapping[str, zipfile.ZipInfo]
) -> None:
    """整包解压后认包的几处特殊口径，区间这一路复现不了的就不走区间。"""

    chosen = infos[interface_rel].filename
    prefix = chosen[: len(chosen) - len(interface_rel)]
    tops = {
        PurePosixPath(rel).parts[0]
        for rel in infos
        if len(PurePosixPath(rel).parts) > 1
    }
    if prefix and "changes.json" in {info.filename for info in archive.infolist()}:
        raise RangeDeltaUnavailable("发行包根上有 changes.json")
    if tops & {"payload", "files"}:
        # 整包解压时包根下有这两个目录就把它当成载荷根（``apply._resolve_payload_root``）。
        raise RangeDeltaUnavailable("发行包根上有 payload/ 或 files/ 目录")
    seen: set[str] = set()
    directories: dict[str, str] = {}
    for info in archive.infolist():
        name = info.filename
        if info.is_dir() or not name.startswith(prefix):
            continue
        rel = name[len(prefix) :]
        parts = PurePosixPath(rel).parts
        if parts and parts[0] in RESERVED_PROJECT_DIRS:
            raise RangeDeltaUnavailable(f"发行包里有更新器的保留目录：{name}")
        if "/".join(_zip_member_parts(name)) != name:
            # 整包解压按 ``_zip_member_parts`` 规整落点（Windows 非法字符换成 _、去各段
            # 结尾的点和空格），文件名与包里写的不同；区间按原名取，两边对不上。
            raise RangeDeltaUnavailable(f"发行包里有解压时会被改名的条目：{name}")
        key = rel.casefold()
        if key in seen:
            # 整包解压时后一个覆盖前一个，按条目表取的是前一个。
            raise RangeDeltaUnavailable(f"发行包里有重名条目：{name}")
        seen.add(key)
        for depth in range(1, len(parts)):
            directory = "/".join(parts[:depth])
            known = directories.setdefault(directory.casefold(), directory)
            if known != directory:
                # ``a/X`` 与 ``A/y``：整包解压落进同一个目录，条目表里却是两个路径。
                raise RangeDeltaUnavailable(
                    f"发行包里有只差大小写的目录：{known}、{directory}"
                )


def _same_content(path: Path, info: zipfile.ZipInfo) -> bool:
    """当前载荷里这个文件与条目内容相同：大小相同才算 CRC32（读的是本地盘）。"""

    try:
        if path.is_symlink() or not path.is_file():
            return False
        if path.stat().st_size != info.file_size:
            return False
        crc = 0
        with path.open("rb") as handle:
            while chunk := handle.read(_COPY_CHUNK):
                crc = zlib.crc32(chunk, crc)
    except OSError:
        return False
    return crc == info.CRC


def _local_sizes(directory: Path) -> dict[str, int]:
    """当前载荷里每个文件的大小（叠加视图的底层，整包落地时就是 stat 它们）。"""

    sizes: dict[str, int] = {}
    for current, _dirs, files in os.walk(directory):
        base = Path(current)
        for name in files:
            path = base / name
            try:
                sizes[path.relative_to(directory).as_posix()] = path.stat().st_size
            except (OSError, ValueError):
                continue
    return sizes


def open_range_delta(
    url: str,
    size: int,
    *,
    old_manifest: Mapping[str, object],
    old_payload_dir: Path,
    lineage: str,
    target_version: str,
    workdir: Path,
    proxy: httpx.Proxy | None = None,
    cancelled: Callable[[], bool] | None = None,
    send_log: Callable[[str], None] | None = None,
    speed_guard: RangeSpeedGuard | None = None,
) -> RangeDelta:
    """读远端发行包的中央目录，算出白名单内的条目、哪些能从当前载荷搬、哪些要取回。

    只花读中央目录（和 interface 及其 import）的流量。用不了抛
    :class:`RangeDeltaUnavailable`，停止抛 :class:`RangeDeltaCancelled`。
    """

    old_root = Path(old_payload_dir)
    client = _open_client(proxy)
    reader: RangeHTTPReader | None = None
    archive: zipfile.ZipFile | None = None
    skeleton = Path(workdir) / f"rk-{os.urandom(4).hex()}"
    try:
        # 最多读整包那么多：再多就不如整包下载了（超了按「要读的太多」退回全量）。
        reader = RangeHTTPReader(
            client,
            url,
            expected_size=size or None,
            max_bytes=size if size > 0 else 2**63,
            cancelled=cancelled,
            over_limit_reason=(
                f"要读的超过上限 {format_size(size)}（整包大小），不如直接下整包"
            ),
            on_chunk=speed_guard.observe if speed_guard is not None else None,
        )
        if speed_guard is not None:
            # 包尾一读到就知道中央目录多大：从这一刻起按「读完目录还要多久」估，极慢的
            # 直连不必等目录读完才放弃。定好取回计划后再换成整次计划。
            remaining = _central_directory_bytes(reader)
            if remaining is not None:
                speed_guard.phase = "读文件目录"
                speed_guard.planned_total = reader.received + remaining
                speed_guard.observe(reader)
        try:
            archive = zipfile.ZipFile(reader)  # type: ignore[arg-type]
        except zipfile.BadZipFile as exc:
            raise RangeDeltaUnavailable(f"发行包的文件目录读不了：{exc}") from exc
        interface_rel, infos = package_entries(archive)
        _check_layout(archive, interface_rel, infos)
        try:
            data = _parse_json(read_entry(archive, infos[interface_rel], interface_rel))
            same = lineage_key(data) == lineage
        except (ValueError, PayloadError) as exc:
            raise RangeDeltaUnavailable(
                f"发行包里的 interface.json 读不了：{exc}"
            ) from exc
        if not same:
            raise RangeDeltaUnavailable("发行包与本机的项目对不上")
        if _norm_version(data.get("version")) != _norm_version(target_version):
            raise RangeDeltaUnavailable(
                f"发行包的版本是 {data.get('version')}，不是 {target_version}"
            )
        # 整包落地时名叫 changes.json 的文件一律不算条目（``apply.build_package_plan``）。
        candidates = {
            rel: info
            for rel, info in infos.items()
            if PurePosixPath(rel).name != "changes.json"
        }
        chosen = infos[interface_rel].filename
        prefix = chosen[: len(chosen) - len(interface_rel)]
        directories = [
            info.filename[len(prefix) :].rstrip("/")
            for info in archive.infolist()
            if info.is_dir()
            and info.filename.startswith(prefix)
            and info.filename[len(prefix) :].strip("/")
        ]
        write_archive_skeleton(
            archive, interface_rel, infos, skeleton, directories=directories
        )
        sizes = _local_sizes(old_root)
        sizes.update({rel: info.file_size for rel, info in infos.items()})
        try:
            rules = package_projection_rules(skeleton, old_root, sizes=sizes)
        except ProjectionError as exc:
            raise RangeDeltaUnavailable(f"算不出发行包的投影白名单：{exc}") from exc
        kept, dropped = filter_package_entries(rules, candidates)
        if send_log is not None:
            # 与整包落地（``apply._project_package_entries``）同样的三行。
            if dropped:
                send_log(f"内嵌投影：包内 {len(dropped)} 个条目不在白名单内，未落盘")
            code_hint = describe_dropped_code_files(rules, dropped)
            if code_hint:
                send_log(f"内嵌投影：{code_hint}")
            for warning in rules.warnings:
                send_log(f"内嵌投影：{warning}")
        entries = {rel: candidates[rel] for rel in sorted(kept)}
        if "interface.json" not in entries and "interface.jsonc" not in entries:
            raise RangeDeltaUnavailable("白名单里没有 interface.json")

        old_files = manifest_files(old_manifest)
        reuse: dict[str, Path] = {}
        fetch: dict[str, zipfile.ZipInfo] = {}
        for index, (rel, info) in enumerate(entries.items()):
            if (
                cancelled is not None
                and index % _CANCEL_CHECK_EVERY == 0
                and cancelled()
            ):
                raise RangeDeltaCancelled("update cancelled")
            local = old_root / rel
            if rel in old_files and _same_content(local, info):
                reuse[rel] = local
            else:
                fetch[rel] = info
        _groups, planned = plan_range_fetch(
            fetch,
            size=reader.size,
            block_size=reader.block_size,
            cached=reader.blocks,
        )
        delta = RangeDelta(
            client=client,
            reader=reader,
            archive=archive,
            entries=entries,
            reuse=reuse,
            fetch=fetch,
            probe_bytes=reader.fetched,
            planned_fetch_bytes=planned,
            takeover_dirs=package_takeover_dirs(rules, kept),
        )
        # 预算按真正要发的字节算（文件头、合并的间隙、块对齐都算上，已读的中央目录也算），
        # 不按名义压缩大小：分散的小改动拉回来的往往是名义的几倍（MPA 88 KB 要读 846 KB）。
        if (
            len(fetch) > MAX_FETCH_ENTRIES
            or delta.planned_bytes > reader.size * MAX_FETCH_RATIO
        ):
            raise RangeDeltaUnavailable(
                f"变化的文件太多（{len(fetch)} 个、名义 {format_size(delta.fetch_bytes)}、"
                f"计划传输 {format_size(delta.planned_bytes)}，发行包 "
                f"{format_size(reader.size)}），超过按区间取回的上限"
            )
        if speed_guard is not None:
            # 计划定了才能估剩余：读文件目录这段的吞吐已经在样本里，这里先估一次，
            # 慢到估出来就超的不必开始取回。
            speed_guard.phase = "按需下载"
            speed_guard.planned_total = delta.planned_bytes
            speed_guard.observe(reader)
        return delta
    except BaseException as exc:
        for closer in (
            archive.close if archive is not None else None,
            reader.close if reader is not None else None,
            client.close,
        ):
            if closer is not None:
                try:
                    closer()
                except Exception:  # noqa: BLE001 - 收尾
                    pass
        if isinstance(exc, RangeReadCancelled):
            raise RangeDeltaCancelled("update cancelled") from exc
        if isinstance(exc, HealSkip):
            raise RangeDeltaUnavailable(str(exc)) from exc
        raise
    finally:
        try:
            remove_tree(skeleton)
        except OSError:
            logger.warning(
                "MaaFW 区间比对用的骨架目录没删掉，留待启动时清理：%s", skeleton
            )


# --------------------------------------------------------------------------
# 取回变了的条目，拼成虚拟全量包
# --------------------------------------------------------------------------


def _fetch_groups(
    fetch: Mapping[str, zipfile.ZipInfo],
) -> list[tuple[int, int, list[tuple[str, zipfile.ZipInfo]]]]:
    """按条目在包里的位置排好，间隔小于 :data:`MERGE_GAP_BYTES` 的合成一次请求。"""

    groups: list[tuple[int, int, list[tuple[str, zipfile.ZipInfo]]]] = []
    for rel, info in sorted(fetch.items(), key=lambda item: item[1].header_offset):
        start = info.header_offset
        end = (
            start
            + _LOCAL_HEADER_SIZE
            + len(info.filename.encode("utf-8"))
            + len(info.extra)
            + _LOCAL_HEADER_SLACK
            + info.compress_size
            - 1
        )
        if groups:
            first, last, members = groups[-1]
            if start - last <= MERGE_GAP_BYTES and end - first < MAX_GROUP_BYTES:
                members.append((rel, info))
                groups[-1] = (first, max(last, end), members)
                continue
        groups.append((start, end, [(rel, info)]))
    return groups


def plan_range_fetch(
    fetch: Mapping[str, zipfile.ZipInfo],
    *,
    size: int,
    block_size: int,
    cached: Iterable[int] = (),
) -> tuple[list[tuple[int, int, list[tuple[str, zipfile.ZipInfo]]]], int]:
    """取回阶段的请求计划：``(分组, 要发的字节)``。

    :func:`fetch_range_delta` 就按这里的分组发：每组 ``reader.prefetch(组首条目, 组尾)``
    补齐缺的块（块对齐、最后一块截到包尾）、取完 ``reader.forget(组尾)`` 丢掉组尾所在块
    之前的缓存；这里按同样的块运算记账，预算判定用的就是将要发的字节。``cached``：读中央
    目录时已经缓存的块号。条目的本地头比估的长时 zipfile 会多读一块，不在计划里（罕见）。
    """

    groups = _fetch_groups(fetch)
    have = set(cached)
    planned = 0
    for _start, end, members in groups:
        planned += _missing_block_bytes(
            members[0][1].header_offset,
            end,
            size=size,
            block_size=block_size,
            have=have,
        )
        limit = end // block_size
        have = {index for index in have if index >= limit}
    return groups, planned


def _missing_block_bytes(
    start: int, end: int, *, size: int, block_size: int, have: set[int]
) -> int:
    """``reader.prefetch(start, end)`` 会发的字节（缺的块按块对齐、最后一块截到包尾），
    并把这些块记进 ``have``。与 ``RangeHTTPReader._ensure`` 同一块运算。"""

    missing = 0
    for index in range(start // block_size, min(end, size - 1) // block_size + 1):
        if index not in have:
            missing += min(size, (index + 1) * block_size) - index * block_size
            have.add(index)
    return missing


def _central_directory_bytes(reader: RangeHTTPReader) -> int | None:
    """读到包尾的结束记录（zip64 时连同 zip64 结束记录）后，读中央目录还要发多少字节。

    zipfile 读中央目录是一次 ``read(大小)``，读取器把缺的块合成一个 Range 请求，中途只有
    逐块的 ``on_chunk``：速度保护在那里按这个数估「读完目录还要多久」。用的是标准库的
    ``zipfile._EndRecData``（ZipFile 自己也是先调它），读过的包尾块留在缓存里不重读。
    读不出来返回 None（那就只有硬上限管着，ZipFile 随后会照常报错）。
    """

    end_record = getattr(zipfile, "_EndRecData", None)
    size_index = getattr(zipfile, "_ECD_SIZE", None)
    location_index = getattr(zipfile, "_ECD_LOCATION", None)
    if end_record is None or size_index is None or location_index is None:
        # 私有接口换了（将来的 Python）：只剩硬上限管着读目录这一段。
        return None
    try:
        endrec = end_record(reader)
        if not endrec:
            return None
        size_cd = int(endrec[size_index])
        # 中央目录紧挨在结束记录前面（zip64 时中间还隔着几十字节的 zip64 记录，估算不计较）。
        end = int(endrec[location_index])
    except (
        OSError,
        ValueError,
        zipfile.BadZipFile,
        AttributeError,
        TypeError,
        IndexError,
    ):
        return None
    start = max(0, end - size_cd)
    return _missing_block_bytes(
        start,
        end - 1,
        size=reader.size,
        block_size=reader.block_size,
        have=set(reader.blocks),
    )


def _extract_entry(
    archive: zipfile.ZipFile, info: zipfile.ZipInfo, rel: str, target: Path
) -> None:
    """解压一个条目到新文件（独占新建）：CRC32 由 zipfile 在读到结尾时校验。"""

    target.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    try:
        with archive.open(info) as source, target.open("xb") as sink:
            while chunk := source.read(_COPY_CHUNK):
                sink.write(chunk)
                written += len(chunk)
    except (RangeReadCancelled, HealSkip):
        raise
    except NotImplementedError as exc:
        raise RangeDeltaUnavailable(f"{rel} 无法解压：{exc}") from exc
    except (EOFError, zipfile.BadZipFile, zlib.error, RuntimeError) as exc:
        raise RangeDeltaUnavailable(f"{rel} 校验失败：{exc}") from exc
    if written != info.file_size:
        raise RangeDeltaUnavailable(f"{rel} 大小与发行包的文件目录不符")


def fetch_range_delta(
    delta: RangeDelta,
    package_dir: Path,
    *,
    cancelled: Callable[[], bool] | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> dict[str, Path]:
    """在 ``package_dir`` 里拼出虚拟全量包：没变的从当前载荷搬，变了的按区间取回、校验。

    返回白名单内的全部条目（包内相对路径 → ``package_dir`` 下的文件），交给
    ``build_from_package(package_entries=...)``。``progress(已取回, 要取回)`` 按压缩字节报。
    任何一个条目失败都抛 :class:`RangeDeltaUnavailable`，调用方丢掉整个 ``package_dir``。
    """

    def check_cancel() -> None:
        if cancelled is not None and cancelled():
            raise RangeDeltaCancelled("update cancelled")

    package_dir = Path(package_dir)
    package_dir.mkdir(parents=True, exist_ok=True)
    boundary = _EntryBoundary(package_dir)
    for rel in delta.entries:
        if not boundary.contains(rel):
            raise RangeDeltaUnavailable(f"发行包里有不安全的路径：{rel}")
    try:
        for index, (rel, source) in enumerate(sorted(delta.reuse.items())):
            if index % _CANCEL_CHECK_EVERY == 0:
                check_cancel()
            # 与 ``clone_payload_into`` 同一口径：库里的（多链接）挂硬链接，其余复制。
            place_fresh(source, package_dir / rel, link=source.stat().st_nlink > 1)
        total = delta.fetch_bytes
        done = 0
        if progress is not None:
            progress(done, total)
        groups, _planned = plan_range_fetch(
            delta.fetch,
            size=delta.reader.size,
            block_size=delta.reader.block_size,
            cached=delta.reader.blocks,
        )
        for _start, end, members in groups:
            check_cancel()
            delta.reader.prefetch(members[0][1].header_offset, end)
            for rel, info in members:
                _extract_entry(delta.archive, info, rel, package_dir / rel)
                done += info.compress_size
                if progress is not None:
                    progress(done, total)
            # 读过的块不会再用：单组最多 MAX_GROUP_BYTES 留在内存里。
            delta.reader.forget(end)
    except RangeReadCancelled as exc:
        raise RangeDeltaCancelled("update cancelled") from exc
    except HealSkip as exc:
        raise RangeDeltaUnavailable(str(exc)) from exc
    except OSError as exc:
        raise RangeDeltaUnavailable(f"拼新版本文件失败：{exc}") from exc
    return {rel: package_dir / rel for rel in delta.entries}


__all__ = [
    "FORCE_FULL_PACKAGE_ENV",
    "MAX_FETCH_ENTRIES",
    "MAX_FETCH_RATIO",
    "RangeDelta",
    "RangeDeltaCancelled",
    "RangeDeltaUnavailable",
    "RangeSpeedGuard",
    "fetch_range_delta",
    "force_full_package",
    "is_github_download",
    "open_range_delta",
    "plan_range_fetch",
]
