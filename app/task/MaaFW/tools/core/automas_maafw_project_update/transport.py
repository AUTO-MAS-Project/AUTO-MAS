"""Resumable HTTP transport for MaaFW update artifacts."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit

import aiofiles
import httpx

from .contracts import artifact_id_for, normalise_sha256
from .state import (
    DEFAULT_CACHE_ROOT,
    UpdateOperationStore,
    artifact_lock,
    redact_text,
    redact_url,
)

CHUNK_SIZE = 64 * 1024
MAX_REDIRECTS = 10
RETRY_COUNT = 3
RETRY_DELAY = 1.0
HTTP_HEADERS = {"User-Agent": "AutoMasGui"}


class DownloadPaused(RuntimeError):
    """The operation requested a pause; its partial file remains reusable."""


class DownloadCancelled(RuntimeError):
    """The operation was cancelled while preserving its partial file."""


@dataclass(frozen=True)
class DownloadOutcome:
    artifact_id: str
    path: Path
    size: int
    sha256: str
    resumed_from: int = 0
    total_bytes: int | None = None
    etag: str | None = None
    last_modified: str | None = None
    range_supported: bool | None = None
    cache_hit: bool = False


class _RestartFromZero(RuntimeError):
    pass


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _content_length(response: httpx.Response) -> int | None:
    raw = str(response.headers.get("content-length") or "").strip()
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value >= 0 else None


def _parse_content_range(value: str) -> tuple[int, int, int | None] | None:
    match = re.fullmatch(r"bytes\s+(\d+)-(\d+)/(\d+|\*)", value.strip(), re.IGNORECASE)
    if not match:
        return None
    total = None if match.group(3) == "*" else int(match.group(3))
    return int(match.group(1)), int(match.group(2)), total


def _parse_unsatisfied_range(value: str) -> int | None:
    match = re.fullmatch(r"bytes\s+\*/(\d+)", value.strip(), re.IGNORECASE)
    return int(match.group(1)) if match else None


def _validate_url(raw_url: str) -> str:
    value = str(raw_url or "").strip()
    parsed = urlsplit(value)
    scheme = parsed.scheme.casefold()
    if scheme not in {"https", "http"} or not parsed.hostname:
        raise RuntimeError("MaaFW update URL must use HTTPS")
    if parsed.username or parsed.password:
        raise RuntimeError("MaaFW update URL must not contain credentials")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        address = None
    # A loopback HTTP endpoint is accepted for local integration/smoke
    # servers only; all remote provider/package traffic remains HTTPS.
    if scheme == "http" and not (address is not None and address.is_loopback):
        raise RuntimeError("MaaFW update URL must use HTTPS")
    if address is not None and (
        (
            scheme != "http"
            and (
                address.is_private
                or address.is_loopback
                or address.is_link_local
                or address.is_reserved
                or address.is_multicast
            )
        )
        or (scheme == "http" and not address.is_loopback)
    ):
        raise RuntimeError("MaaFW update URL cannot target a private address")
    return value


def _calculate_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_paths(root: Path, artifact_id: str) -> tuple[Path, Path, Path]:
    cache_root = root.resolve(strict=False)
    directory = (cache_root / artifact_id).resolve(strict=False)
    if not directory.is_relative_to(cache_root):
        raise RuntimeError("MaaFW artifact path escapes cache root")
    return directory, directory / "payload.part", directory / "artifact.json"


def _complete_path(directory: Path, sha256: str) -> Path:
    return directory / f"{sha256}.zip"


def _existing_complete_path(
    directory: Path,
    metadata: dict[str, Any],
    expected_sha256: str | None,
) -> Path | None:
    if not metadata.get("complete"):
        return None
    raw_path = str(metadata.get("completePath") or "").strip()
    candidate = (
        Path(raw_path).expanduser().resolve(strict=False)
        if raw_path
        else _complete_path(
            directory,
            expected_sha256 or str(metadata.get("sha256") or "").strip().lower(),
        )
    )
    if not candidate.is_absolute() or not candidate.is_relative_to(
        directory.resolve(strict=False)
    ):
        return None
    if not candidate.is_file() or candidate.stat().st_size <= 0:
        return None
    return candidate


async def download_resumable(
    *,
    source: str,
    version: str,
    download_url: str,
    expected_sha256: str | None = None,
    artifact_id: str | None = None,
    cache_root: Path | None = None,
    operation: UpdateOperationStore | None = None,
    proxy: httpx.Proxy | None = None,
    max_bytes: int = 4 * 1024 * 1024 * 1024,
    send_log: Callable[[str], None] | None = None,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> DownloadOutcome:
    """Download an artifact with Range/validator-aware checkpointing."""

    validated_url = _validate_url(download_url)
    expected = normalise_sha256(expected_sha256)
    if expected_sha256 and expected is None:
        raise RuntimeError("update package expected sha256 is invalid")
    root = (cache_root or DEFAULT_CACHE_ROOT).resolve()
    stable_id = artifact_id_for(source, version, validated_url, explicit=artifact_id)
    directory, partial_path, metadata_path = _artifact_paths(root, stable_id)
    directory.mkdir(parents=True, exist_ok=True)
    store = operation
    if store is None:
        store = UpdateOperationStore.create(
            artifactId=stable_id,
            source=source,
            targetVersion=version,
            artifactDir=str(directory),
            partialPath=str(partial_path),
        )
    send_update_log = send_log or (lambda _message: None)
    emit = progress or (lambda _event: None)

    with artifact_lock(root, stable_id):
        metadata = _read_json(metadata_path)
        metadata.update(
            {
                "schemaVersion": 1,
                "artifactId": stable_id,
                "source": source,
                "targetVersion": version,
                # Never persist MirrorChyan query parameters or signed
                # redirect URLs.  Recovery receives a freshly discovered URL.
                "url": redact_url(validated_url),
                "expectedSha256": expected,
                "partialPath": str(partial_path),
            }
        )
        existing = partial_path.stat().st_size if partial_path.is_file() else 0
        expected_total = _optional_int(metadata.get("totalBytes"))
        if existing > max_bytes or (
            expected_total is not None and expected_total > max_bytes
        ):
            partial_path.unlink(missing_ok=True)
            existing = 0
            expected_total = None
        complete_path = _existing_complete_path(directory, metadata, expected)
        if complete_path is not None:
            actual = await asyncio.to_thread(_calculate_sha256, complete_path)
            if expected and actual != expected:
                complete_path.unlink(missing_ok=True)
                metadata.update({"complete": False, "completePath": None})
            elif actual == str(metadata.get("sha256") or actual).lower():
                size = complete_path.stat().st_size
                metadata.update(
                    {
                        "downloadedBytes": size,
                        "totalBytes": _optional_int(metadata.get("totalBytes")) or size,
                        "sha256": actual,
                        "complete": True,
                        "completePath": str(complete_path),
                    }
                )
                _atomic_json_write(metadata_path, metadata)
                store.update(
                    "verified",
                    artifactId=stable_id,
                    artifactDir=str(directory),
                    partialPath=str(partial_path),
                    downloadedBytes=size,
                    resumedFromBytes=0,
                    totalBytes=metadata["totalBytes"],
                    sha256=actual,
                    cacheHit=True,
                    supportsResume=metadata.get("rangeSupported"),
                )
                emit(
                    {
                        "stage": "downloaded",
                        "status": "cache_hit",
                        "downloaded_bytes": size,
                        "resumed_from_bytes": 0,
                        "total_bytes": metadata["totalBytes"],
                        "cache_hit": True,
                        "operation_id": store.operation_id,
                    }
                )
                return DownloadOutcome(
                    artifact_id=stable_id,
                    path=complete_path,
                    size=size,
                    sha256=actual,
                    total_bytes=metadata["totalBytes"],
                    etag=str(metadata.get("etag") or "") or None,
                    last_modified=str(metadata.get("lastModified") or "") or None,
                    range_supported=metadata.get("rangeSupported"),
                    cache_hit=True,
                )
        metadata["downloadedBytes"] = existing
        _atomic_json_write(metadata_path, metadata)
        store.update(
            "downloading" if existing < (expected_total or max_bytes) else "downloaded",
            artifactId=stable_id,
            artifactDir=str(directory),
            partialPath=str(partial_path),
            downloadedBytes=existing,
            resumedFromBytes=existing,
            totalBytes=expected_total,
            supportsResume=metadata.get("rangeSupported"),
        )
        emit(
            {
                "stage": "downloading",
                "status": "running",
                "downloaded_bytes": existing,
                "resumed_from_bytes": existing,
                "total_bytes": expected_total,
                "supports_resume": metadata.get("rangeSupported"),
                "operation_id": store.operation_id,
            }
        )

        last_error: Exception | None = None
        for attempt in range(1, RETRY_COUNT + 1):
            try:
                outcome = await _download_attempt(
                    partial_path=partial_path,
                    metadata_path=metadata_path,
                    metadata=metadata,
                    download_url=validated_url,
                    expected_sha256=expected,
                    max_bytes=max_bytes,
                    operation=store,
                    proxy=proxy,
                    progress=emit,
                )
                store.update(
                    "verified",
                    downloadedBytes=outcome.size,
                    totalBytes=outcome.total_bytes,
                    sha256=outcome.sha256,
                    etag=outcome.etag,
                    lastModified=outcome.last_modified,
                    supportsResume=outcome.range_supported,
                    attempt=attempt,
                )
                send_update_log(
                    f"MaaFW update package downloaded: {outcome.size} bytes"
                )
                return outcome
            except (DownloadPaused, DownloadCancelled):
                raise
            except _RestartFromZero:
                partial_path.unlink(missing_ok=True)
                metadata = _read_json(metadata_path)
                metadata.update(
                    {
                        "downloadedBytes": 0,
                        "resumedFromBytes": 0,
                        "etag": None,
                        "lastModified": None,
                        "complete": False,
                        "completePath": None,
                    }
                )
                _atomic_json_write(metadata_path, metadata)
                continue
            except Exception as exc:
                last_error = exc
                existing = partial_path.stat().st_size if partial_path.is_file() else 0
                store.update(
                    "downloading",
                    downloadedBytes=existing,
                    attempt=attempt,
                    lastError=redact_text(exc)[:500],
                )
                if attempt >= RETRY_COUNT:
                    break
                await asyncio.sleep(RETRY_DELAY)
        message = redact_text(last_error or "download failed")
        store.update(
            "failed",
            downloadedBytes=partial_path.stat().st_size
            if partial_path.is_file()
            else 0,
            error=message[:500],
        )
        raise RuntimeError(f"MaaFW update package download failed: {message}")


async def _download_attempt(
    *,
    partial_path: Path,
    metadata_path: Path,
    metadata: dict[str, Any],
    download_url: str,
    expected_sha256: str | None,
    max_bytes: int,
    operation: UpdateOperationStore,
    proxy: httpx.Proxy | None,
    progress: Callable[[dict[str, Any]], None],
) -> DownloadOutcome:
    existing = partial_path.stat().st_size if partial_path.is_file() else 0
    resume_start = existing
    metadata["resumedFromBytes"] = resume_start
    _atomic_json_write(metadata_path, metadata)
    saved_etag = str(metadata.get("etag") or "").strip() or None
    saved_modified = str(metadata.get("lastModified") or "").strip() or None
    headers = dict(HTTP_HEADERS)
    if existing:
        headers["Range"] = f"bytes={existing}-"
        if saved_etag:
            headers["If-Range"] = saved_etag
        elif saved_modified:
            headers["If-Range"] = saved_modified

    current_url = download_url
    async with httpx.AsyncClient(
        proxy=proxy, follow_redirects=False, timeout=30.0
    ) as client:
        for redirect_count in range(MAX_REDIRECTS + 1):
            async with client.stream("GET", current_url, headers=headers) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = str(response.headers.get("location") or "").strip()
                    if not location or redirect_count >= MAX_REDIRECTS:
                        raise RuntimeError("update package redirect is invalid")
                    current_url = _validate_url(urljoin(current_url, location))
                    continue

                if response.status_code == 416:
                    response_etag = (
                        str(response.headers.get("etag") or "").strip() or None
                    )
                    response_modified = (
                        str(response.headers.get("last-modified") or "").strip() or None
                    )
                    if (
                        existing
                        and saved_etag
                        and response_etag
                        and response_etag != saved_etag
                    ):
                        raise _RestartFromZero("update package ETag changed")
                    if (
                        existing
                        and not saved_etag
                        and saved_modified
                        and response_modified
                        and response_modified != saved_modified
                    ):
                        raise _RestartFromZero("update package Last-Modified changed")
                    total = _parse_unsatisfied_range(
                        str(response.headers.get("content-range") or "")
                    )
                    if existing and total is not None and existing == total:
                        return await _finalize_partial(
                            partial_path=partial_path,
                            metadata_path=metadata_path,
                            metadata=metadata,
                            expected_sha256=expected_sha256,
                            total=total,
                            etag=response_etag or saved_etag,
                            last_modified=response_modified or saved_modified,
                            range_supported=True,
                        )
                    raise _RestartFromZero("server rejected stale range")

                if response.status_code not in {200, 206}:
                    content = (await response.aread())[:4096]
                    hint = content.decode("utf-8", errors="replace").strip()
                    raise RuntimeError(f"HTTP {response.status_code}: {hint[:300]}")

                response_etag = str(response.headers.get("etag") or "").strip() or None
                response_modified = (
                    str(response.headers.get("last-modified") or "").strip() or None
                )
                if existing and saved_etag and response_etag != saved_etag:
                    raise _RestartFromZero("update package ETag changed")
                if (
                    existing
                    and not saved_etag
                    and saved_modified
                    and response_modified != saved_modified
                ):
                    raise _RestartFromZero("update package Last-Modified changed")

                if response.status_code == 206:
                    content_range = _parse_content_range(
                        str(response.headers.get("content-range") or "")
                    )
                    if content_range is None or content_range[0] != existing:
                        raise _RestartFromZero(
                            "server returned an invalid Content-Range"
                        )
                    _start, end, total = content_range
                    if total is None:
                        total = existing + (end - _start + 1)
                    mode = "ab"
                    range_supported = True
                    transfer_resume_start = resume_start
                else:
                    total = _content_length(response)
                    if existing:
                        existing = 0
                        partial_path.unlink(missing_ok=True)
                    mode = "wb"
                    range_supported = False if "Range" in headers else None
                    # A server that ignored Range caused a safe full restart;
                    # it must not be reported as a resumed transfer.
                    transfer_resume_start = 0

                if total is not None and total > max_bytes:
                    raise RuntimeError(
                        f"update package exceeds size limit: {total} > {max_bytes}"
                    )
                metadata.update(
                    {
                        "etag": response_etag or saved_etag,
                        "lastModified": response_modified or saved_modified,
                        "totalBytes": total,
                        "rangeSupported": range_supported,
                        "finalUrl": redact_url(str(response.url)),
                        "downloadedBytes": existing,
                        "resumedFromBytes": transfer_resume_start,
                    }
                )
                _atomic_json_write(metadata_path, metadata)
                downloaded = existing
                progress(
                    {
                        "stage": "downloading",
                        "status": "running",
                        "downloaded_bytes": downloaded,
                        "total_bytes": total,
                        "resumed_from_bytes": transfer_resume_start,
                        "supports_resume": range_supported,
                        "attempt": operation.read().get("attempt", 1),
                        "operation_id": operation.operation_id,
                    }
                )
                async with aiofiles.open(partial_path, mode) as handle:
                    async for chunk in response.aiter_bytes(chunk_size=CHUNK_SIZE):
                        if not chunk:
                            continue
                        control = operation.read()
                        downloaded += len(chunk)
                        if downloaded > max_bytes:
                            raise RuntimeError("update package exceeds size limit")
                        await handle.write(chunk)
                        if control.get("cancelRequested"):
                            await handle.flush()
                            _sync_file(partial_path)
                            operation.update("cancelled", downloadedBytes=downloaded)
                            raise DownloadCancelled(
                                "MaaFW update download cancelled; partial retained"
                            )
                        if control.get("pauseRequested"):
                            await handle.flush()
                            _sync_file(partial_path)
                            _atomic_json_write(
                                metadata_path,
                                {**metadata, "downloadedBytes": downloaded},
                            )
                            operation.update("paused", downloadedBytes=downloaded)
                            raise DownloadPaused(
                                "MaaFW update download paused; partial retained"
                            )
                        if downloaded % (CHUNK_SIZE * 16) < len(chunk):
                            await handle.flush()
                            _sync_file(partial_path)
                            _atomic_json_write(
                                metadata_path,
                                {**metadata, "downloadedBytes": downloaded},
                            )
                        progress(
                            {
                                "stage": "downloading",
                                "status": "running",
                                "downloaded_bytes": downloaded,
                                "total_bytes": total,
                                "resumed_from_bytes": transfer_resume_start,
                                "supports_resume": range_supported,
                                "operation_id": operation.operation_id,
                            }
                        )
                _sync_file(partial_path)
                metadata["downloadedBytes"] = downloaded
                _atomic_json_write(metadata_path, metadata)
                if total is not None and downloaded != total:
                    raise RuntimeError(f"download incomplete: {downloaded}/{total}")
                return await _finalize_partial(
                    partial_path=partial_path,
                    metadata_path=metadata_path,
                    metadata=metadata,
                    expected_sha256=expected_sha256,
                    total=total,
                    etag=response_etag or saved_etag,
                    last_modified=response_modified or saved_modified,
                    range_supported=range_supported,
                )
    raise RuntimeError("update package redirect failed")


async def _finalize_partial(
    *,
    partial_path: Path,
    metadata_path: Path,
    metadata: dict[str, Any],
    expected_sha256: str | None,
    total: int | None,
    etag: str | None,
    last_modified: str | None,
    range_supported: bool | None,
) -> DownloadOutcome:
    if not partial_path.is_file() or partial_path.stat().st_size == 0:
        raise RuntimeError("update package is empty")
    actual = await asyncio.to_thread(_calculate_sha256, partial_path)
    if expected_sha256 and actual != expected_sha256:
        raise RuntimeError(
            f"update package sha256 mismatch: expected {expected_sha256[:12]}..., actual {actual[:12]}..."
        )
    directory = partial_path.parent
    final_path = _complete_path(directory, actual)
    if final_path.exists():
        partial_path.unlink(missing_ok=True)
    else:
        os.replace(partial_path, final_path)
    size = final_path.stat().st_size
    metadata.update(
        {
            "downloadedBytes": size,
            "totalBytes": total or size,
            "sha256": actual,
            "completePath": str(final_path),
            "complete": True,
            "etag": etag,
            "lastModified": last_modified,
            "rangeSupported": range_supported,
        }
    )
    _atomic_json_write(metadata_path, metadata)
    return DownloadOutcome(
        artifact_id=str(metadata.get("artifactId") or directory.name),
        path=final_path,
        size=size,
        sha256=actual,
        resumed_from=int(metadata.get("resumedFromBytes") or 0),
        total_bytes=total or size,
        etag=etag,
        last_modified=last_modified,
        range_supported=range_supported,
    )


def _sync_file(path: Path) -> None:
    try:
        with path.open("rb") as handle:
            os.fsync(handle.fileno())
    except OSError:
        pass


def _optional_int(value: Any) -> int | None:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


__all__ = [
    "DownloadCancelled",
    "DownloadOutcome",
    "DownloadPaused",
    "download_resumable",
]
