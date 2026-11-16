"""从旧 ZIP 复用压缩数据，重建远端 ZIP 的原始字节；调用方必须校验整包摘要。"""

import hashlib
import json
import threading
import zipfile
from pathlib import Path

MAX_PATCH_BYTES = 32 * 1024**2


def file_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def apply_patch(
    baseline: Path,
    patch: Path,
    destination: Path,
    size: int,
    digest: str,
    cancelled: threading.Event,
) -> None:
    """重建归档，独立官方大小与 SHA256 校验通过才允许调用方安装。"""
    if patch.stat().st_size > MAX_PATCH_BYTES:
        raise ValueError("增量包过大")
    with zipfile.ZipFile(patch) as archive:
        info = archive.getinfo("manifest.json")
        if info.file_size > 16 * 1024**2:
            raise ValueError("增量清单过大")
        metadata = json.loads(archive.read(info))
        actual_base = file_digest(baseline)
        bundle = metadata.get("version") == 2
        if bundle:
            metadata = {
                **metadata,
                "version": 1,
                "base_sha256": actual_base,
                "operations": metadata["plans"][actual_base],
            }
        if (
            metadata.get("version") != 1
            or metadata.get("target_size") != size
            or metadata.get("target_sha256") != digest
            or metadata.get("base_sha256") != actual_base
        ):
            raise ValueError("增量包与官方版本或本地基线不一致")
        operations = metadata["operations"]
        if len(operations) > 300_000 or archive.getinfo("payload").file_size > size:
            raise ValueError("增量包展开超限")
        with baseline.open("rb") as old, archive.open("payload") as payload:
            with destination.open("xb") as output:
                written = 0
                for kind, offset, length in operations:
                    if (
                        kind not in {"old", "new"}
                        or not isinstance(offset, int)
                        or not isinstance(length, int)
                        or offset < 0
                        or length < 0
                        or written + length > size
                    ):
                        raise ValueError("增量重建区间无效")
                    source = old if kind == "old" else payload
                    if kind == "new" and (
                        offset < payload.tell()
                        or (not bundle and offset != payload.tell())
                    ):
                        raise ValueError("增量数据顺序无效")
                    source.seek(offset)
                    remaining = length
                    while remaining:
                        if cancelled.is_set():
                            raise InterruptedError("增量重建已取消")
                        chunk = source.read(min(remaining, 1024 * 1024))
                        if not chunk:
                            raise ValueError("增量数据不完整")
                        output.write(chunk)
                        remaining -= len(chunk)
                    written += length
    if destination.stat().st_size != size or file_digest(destination) != digest:
        raise ValueError("重建包未通过官方 SHA256 校验")
