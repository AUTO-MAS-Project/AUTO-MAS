"""Bounded, credential-safe archive diagnostics shared by all managed downloads.

This is diagnostic evidence, not an installer acceptance or integrity check.
Never store raw signed URLs, ZIP entry lists, arbitrary text files or payloads.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

_MAX_ENTRIES = 100_000
_MAX_MARKERS = 6
_VERSION = re.compile(r"v?\d{1,4}(?:\.\d{1,4}){1,4}(?:[-.][A-Za-z0-9.-]+)?")
_MARKER_NAMES = {"version.txt", "version", "version.json"}


def safe_origin(url: str) -> str:
    """Only retain protocol and hostname, excluding query, path and credentials."""
    try:
        parsed = urlsplit(url)
        return f"{parsed.scheme}://{parsed.hostname}" if parsed.hostname else "(hidden)"
    except ValueError:
        return "(hidden)"


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
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            result["format"] = "zip"
            result["entries"] = len(entries)
            result["expanded_bytes"] = sum(i.file_size for i in entries)
            if len(entries) > _MAX_ENTRIES:
                result["inspection"] = "entry_limit"
                return result
            roots = sorted(
                {
                    i.filename.replace("\\", "/").split("/")[0]
                    for i in entries
                    if i.filename
                }
            )
            # Use only the count, not raw entry names: they can contain user data.
            result["root_count"] = len(roots)
            # Only whitelist known release root names; arbitrary filenames stay private.
            known_roots = {"update", "March7thAssistant", "March7thAssistant_full"}
            result["known_roots"] = sorted(set(roots) & known_roots)
            markers: list[dict[str, str]] = []
            for item in entries:
                if len(markers) >= _MAX_MARKERS:
                    break
                parts = item.filename.replace("\\", "/").lower().split("/")
                if (
                    item.is_dir()
                    or item.file_size > 256
                    or not parts
                    or parts[-1] not in _MARKER_NAMES
                ):
                    continue
                try:
                    with archive.open(item) as reader:
                        value = reader.read(257).decode("utf-8", errors="replace")
                    match = _VERSION.search(value)
                    if match is not None:
                        # No arbitrary filename or file content in diagnostics.
                        markers.append({"name": parts[-1], "version": match.group(0)})
                except (OSError, ValueError, RuntimeError, zipfile.BadZipFile):
                    continue
            result["version_markers"] = markers
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
