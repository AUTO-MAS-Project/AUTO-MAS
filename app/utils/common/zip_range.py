"""复用旧归档的原始压缩数据，按区间重建官方 ZIP；最终整包摘要决定是否可用。"""

import hashlib
import struct
import threading
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO


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
