"""Bounded, credential-safe archive diagnostics shared by all managed downloads.

This is diagnostic evidence, not an installer acceptance or integrity check.
Never store raw signed URLs, ZIP entry lists, arbitrary text files or payloads.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

# 限制实际读取量，ZIP64 和带注释的 ZIP 同样经过此预算。
_MAX_ZIP_INSPECTION_BYTES = 4 * 1024 * 1024
_MAX_MARKERS = 6
_MAX_MARKER_BYTES = 256
_MAX_COMPRESSED_MARKER_BYTES = 4096
_VERSION = re.compile(r"v?\d{1,4}(?:\.\d{1,4}){1,4}(?:[-.][A-Za-z0-9.-]+)?")
_URL_IN_ERROR = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_MARKER_NAMES = {"version.txt", "version", "version.json"}


class _ZipInspectionLimit(Exception):
    """ZIP 诊断超过读取或版本标记预算。"""


class _BoundedZipReader(io.FileIO):
    """拒绝超额的 ZIP 目录读取，避免解析器先分配超大目录。"""

    def __init__(self, path: Path) -> None:
        super().__init__(path, "rb")
        self._remaining = _MAX_ZIP_INSPECTION_BYTES

    def read(self, size: int = -1, /) -> bytes:
        if size > self._remaining:
            raise _ZipInspectionLimit
        # zipfile 查找带注释的目录尾时会在文件尾部调用无参 read。
        # 此时读至多剩余预算加一字节，用于区分恰好 EOF 与仍有数据。
        limit = self._remaining + 1 if size < 0 else size
        data = super().read(limit)
        assert data is not None
        self._remaining -= len(data)
        if self._remaining < 0:
            raise _ZipInspectionLimit
        return data


def safe_origin(url: str) -> str:
    """Only retain protocol and hostname, excluding query, path and credentials."""
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        if not host:
            return "(hidden)"
        if ":" in host:
            host = f"[{host}]"
        return f"{parsed.scheme}://{host}"
    except ValueError:
        return "(hidden)"


def redact_history_error(error: str | None) -> str | None:
    """保留错误描述，将其中的下载链接缩减为来源域名。"""
    return (
        _URL_IN_ERROR.sub(lambda match: safe_origin(match.group(0)), error)
        if error
        else error
    )


def describe_package(path: Path) -> dict[str, object]:
    """Produce small evidence while the package still exists.

    ZIP central directory inspection does not extract files. Non-ZIP payloads
    remain classified as opaque; their structure must be supplied by adapters.
    """
    result: dict[str, object] = {"schema": 1, "format": "opaque"}
    try:
        result["bytes"] = path.stat().st_size
    except OSError:
        result["availability"] = "missing"
        return result

    try:
        with _BoundedZipReader(path) as stream, zipfile.ZipFile(stream) as archive:
            entries = archive.infolist()
            roots = set()
            markers: list[dict[str, str]] = []
            attempts = 0
            for item in entries:
                relative = item.filename.replace("\\", "/")
                if relative:
                    roots.add(relative.partition("/")[0])
                name = relative.rpartition("/")[2].lower()
                if (
                    name not in _MARKER_NAMES
                    or item.file_size > _MAX_MARKER_BYTES
                    or item.compress_size > _MAX_COMPRESSED_MARKER_BYTES
                    or item.compress_type
                    not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                ):
                    continue
                if attempts >= _MAX_MARKERS:
                    raise _ZipInspectionLimit
                attempts += 1
                try:
                    with archive.open(item) as reader:
                        value = reader.read(_MAX_MARKER_BYTES + 1).decode(
                            "utf-8", errors="replace"
                        )
                except (OSError, ValueError, RuntimeError, zipfile.BadZipFile):
                    continue
                match = _VERSION.search(value)
                if match is not None:
                    markers.append({"name": name, "version": match.group(0)})
            known_roots = {"update", "March7thAssistant", "March7thAssistant_full"}
            result.update(
                format="zip",
                entries=len(entries),
                expanded_bytes=sum(item.file_size for item in entries),
                root_count=len(roots),
                known_roots=sorted(roots & known_roots),
                version_markers=markers,
            )
    except _ZipInspectionLimit:
        result["format"] = "zip"
    except (OSError, ValueError, zipfile.BadZipFile, zipfile.LargeZipFile):
        # A 7z/exe/partial file is not automatically a corrupt archive.
        try:
            with path.open("rb") as stream:
                header = stream.read(6)
            if header == b"7z\xbc\xaf\x27\x1c":
                result["format"] = "7z"
            elif header[:2] == b"PK":
                result["format"] = "zip-invalid"
        except OSError:
            pass
    return result
