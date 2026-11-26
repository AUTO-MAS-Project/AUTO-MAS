"""复用旧归档的原始压缩数据，按区间重建官方 ZIP；最终整包摘要决定是否可用。

另含按 HTTP Range 读远端文件的只读文件对象（:class:`RangeHTTPReader`）与直连速度保护
（:class:`RangeSpeedGuard`），没有 MFW 语义：MFW 的项目更新 / 补齐与 MaaEnd 的整包重建都用它。
"""

import hashlib
import re
import struct
import threading
import time
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO
from urllib.parse import urlsplit

import httpx


def _data_offset(stream: BinaryIO, item: zipfile.ZipInfo) -> int:
    stream.seek(item.header_offset)
    header = stream.read(30)
    if len(header) != 30 or header[:4] != b"PK\x03\x04":
        raise ValueError("ZIP 本地文件头损坏")
    name_size, extra_size = struct.unpack_from("<HH", header, 26)
    return item.header_offset + 30 + name_size + extra_size


def rebuild_zip(
    baseline: Path,
    remote: BinaryIO,
    destination: Path,
    size: int,
    digest: str,
    cancelled: threading.Event,
    *,
    progress: Callable[[int, int], None] | None = None,
    max_changed_entries: int = 3000,
) -> tuple[int, int]:
    """只写独立目标归档，不读写安装目录。CRC/大小仅用于挑选可复用数据。

    同内容也可能使用不同压缩字节；最终必须通过调用方独立提供的官方 SHA256，
    不一致时调用方丢弃并全量下载。头、数据描述符、中央目录及注释均取目标原文。
    """
    reused = changed = 0

    def copy(source: BinaryIO, output: BinaryIO, start: int, length: int) -> None:
        if start < 0 or length < 0:
            raise ValueError("ZIP 区间重叠")
        source.seek(start)
        while length:
            if cancelled.is_set():
                raise InterruptedError("ZIP 重建已取消")
            chunk = source.read(min(length, 1024 * 1024))
            if not chunk:
                raise ValueError("ZIP 区间不完整")
            output.write(chunk)
            length -= len(chunk)
            if progress is not None:
                progress(output.tell(), size)

    with zipfile.ZipFile(remote) as target, zipfile.ZipFile(baseline) as old:
        entries = sorted(target.infolist(), key=lambda item: item.header_offset)
        if len(entries) > 100_000 or len({item.filename for item in entries}) != len(
            entries
        ):
            raise ValueError("ZIP 条目过多或重名")
        previous = {item.filename: item for item in old.infolist()}

        def same(item: zipfile.ZipInfo) -> bool:
            candidate = previous.get(item.filename)
            return (
                candidate is not None
                and not candidate.flag_bits & 1
                and (
                    candidate.CRC,
                    candidate.file_size,
                    candidate.compress_size,
                    candidate.compress_type,
                )
                == (item.CRC, item.file_size, item.compress_size, item.compress_type)
            )

        if sum(not same(item) for item in entries) > max_changed_entries:
            raise ValueError("变化条目超过限制，使用全量")
        with baseline.open("rb") as source, destination.open("xb") as output:
            cursor = 0
            for item in entries:
                if cancelled.is_set():
                    raise InterruptedError("ZIP 重建已取消")
                start = _data_offset(remote, item)
                if item.flag_bits & 1 or start + item.compress_size > size:
                    raise ValueError("不支持加密或越界 ZIP 条目")
                copy(remote, output, cursor, start - cursor)
                candidate = previous.get(item.filename)
                if candidate is not None and same(item):
                    copy(
                        source,
                        output,
                        _data_offset(source, candidate),
                        item.compress_size,
                    )
                    reused += 1
                else:
                    copy(remote, output, start, item.compress_size)
                    changed += 1
                cursor = start + item.compress_size
            copy(remote, output, cursor, size - cursor)
    if cancelled.is_set():
        raise InterruptedError("ZIP 重建已取消")
    with destination.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if destination.stat().st_size != size or actual != digest:
        raise ValueError("Range 重建包未通过官方整包 SHA256 校验")
    return reused, changed


# --------------------------------------------------------------------------
# 按 HTTP Range 读远端文件
# --------------------------------------------------------------------------

# 远端按这么大的块对齐读、缓存：zipfile 的多次小读取落在同一块里就不再发请求。
RANGE_BLOCK_SIZE = 64 * 1024
# 一次最多从远端读这么多（中央目录 + 缺的条目）：MaaFgo 一万多条目的中央目录 1.6 MB。
MAX_REMOTE_BYTES = 64 * 1024 * 1024
HTTP_HEADERS = {"User-Agent": "AutoMasGui"}

# 直连太慢就放弃区间（只在整包能走加速镜像时才设，见 :class:`RangeSpeedGuard`）：国内直连
# GitHub 常年只有 100 多 KB/s，40% 预算的上限对识宝约 74 MB，按这个速度要十几分钟，
# 不如按镜像下整包。估算「已用时 + 剩余计划字节 / 实测吞吐」超过这个秒数就放弃。
SPEED_GUARD_BUDGET_SECONDS = 120.0
# 不论估算多少，整次区间（读文件目录 + 取回）用时超过这个就放弃。
SPEED_GUARD_HARD_LIMIT_SECONDS = SPEED_GUARD_BUDGET_SECONDS * 1.5
# 吞吐样本够了才估：花在网络上至少这么多秒，或者至少收到这么多字节（取先到的）。
SPEED_GUARD_MIN_SAMPLE_SECONDS = 3.0
SPEED_GUARD_MIN_SAMPLE_BYTES = 512 * 1024
_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)


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


def format_size(size: int) -> str:
    return f"{size / 1024:.1f} KB" if size < 1024 * 1024 else f"{size / 2**20:.1f} MB"


def format_duration(seconds: float) -> str:
    """用时 → 「12.3 秒」（60 秒以下，一位小数）/「1 分 46 秒」/「1 小时 2 分」。

    与 MFW 项目更新的 ``timing.format_duration`` 同一写法（一律向下取整到显示精度）。
    """

    value = max(0.0, float(seconds or 0.0))
    if value < 60:
        # 加一点余量再截：2.3 * 10 在浮点里是 22.999…，直接截会说成「2.2 秒」。
        return f"{int(value * 10 + 1e-6) / 10:.1f} 秒"
    total = int(value)
    if total < 3600:
        return f"{total // 60} 分 {total % 60} 秒"
    return f"{total // 3600} 小时 {(total % 3600) // 60} 分"


def parse_content_range(value: str) -> tuple[int, int, int | None] | None:
    match = re.fullmatch(r"bytes\s+(\d+)-(\d+)/(\d+|\*)", value.strip(), re.IGNORECASE)
    if not match:
        return None
    total = None if match.group(3) == "*" else int(match.group(3))
    return int(match.group(1)), int(match.group(2)), total


def _redact_url(raw_url: str) -> str:
    """只留 URL 的来源与路径：查询串里可能带 CDK / 令牌。"""

    value = str(raw_url or "").strip()
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "<redacted-url>"
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return "<redacted-url>"
    host = parsed.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme.lower()}://{host}{port}{parsed.path or '/'}"


def _reason(exc: BaseException) -> str:
    """异常 → 能进日志的一句话原因（URL 打码、截 200 字）。

    httpx 的超时类异常 ``str()`` 常常是空串，只剩「不可用（）」这种看不出所以然的行，
    所以空了就退回类名。
    """

    text = _URL_RE.sub(lambda match: _redact_url(match.group(0)), str(exc or ""))
    return text.strip()[:200] or type(exc).__name__


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
        pieces, total = self._request_pieces(start, end, split=None)
        return b"".join(pieces), total

    def _request_pieces(
        self, start: int, end: int, *, split: int | None
    ) -> tuple[list[bytes], int | None]:
        """发一次 Range 请求，响应体按 ``split`` 字节切成块交回（``None`` = 不切）。

        边收边切：以前先整段放进 bytearray、再 ``bytes()`` 一份、再切块，一个几十 MB
        的条目峰值是两三份；现在同一时刻只多一个块。
        """

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
        pieces: list[bytes] = []
        received = 0
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
                parsed = parse_content_range(content_range)
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
                    received += len(chunk)
                    self.received += len(chunk)
                    if received > expected:
                        raise HealSkip("下载服务器回的区间比请求的长")
                    while split is not None and len(buffer) >= split:
                        pieces.append(bytes(buffer[:split]))
                        del buffer[:split]
                    if self.cancelled is not None and self.cancelled():
                        raise RangeReadCancelled("update cancelled")
                    if self.on_chunk is not None:
                        self.network_seconds += time.monotonic() - request_started
                        request_started = time.monotonic()
                        self.on_chunk(self)
        except httpx.HTTPError as exc:
            # 与整包下载的失败原因同一口径（打码、截 200 字；超时类 str 为空时只剩类名）。
            detail = _reason(exc)
            name = type(exc).__name__
            raise HealSkip(
                f"读取发行包失败：{name if detail == name else f'{name}: {detail}'}"
                f"（区间 {start}-{end}）"
            ) from exc
        finally:
            self.network_seconds += time.monotonic() - request_started
        if received != expected:
            raise HealSkip("下载服务器回的区间不完整")
        self.fetched += expected
        if buffer:
            pieces.append(bytes(buffer))
        return pieces, parsed[2]

    def ensure_window(self, end: int, window: int) -> None:
        """边读边取的读法（单个很大的条目）：丢掉当前位置之前的块，当前位置所在块
        还没缓存时，从当前位置起预读最多 ``window`` 字节（到 ``end`` 为止）。

        与整段 ``prefetch`` 要的是同一批块（只是分几次要），所以取回计划的字节数不变；
        内存里同时最多留一个窗口。"""

        self.forget(self.position)
        # 当前位置所在块多半是上一次读剩下的半块，看下一块：没缓存就从当前位置起取一窗。
        ahead = self.position // self.block_size + 1
        if ahead > min(end, self.size - 1) // self.block_size or ahead in self.blocks:
            return
        self.prefetch(self.position, min(end, self.position + window - 1))

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
            pieces = self._request_pieces(start, end, split=self.block_size)[0]
            for index, piece in zip(run, pieces):
                self.blocks[index] = piece

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
