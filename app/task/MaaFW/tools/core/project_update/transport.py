"""Resumable HTTP transport for MaaFW update artifacts."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence
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
# 直连的尝试次数与退避。GitHub CDN 在国内抽风是成片的，3 次 × 1s 常常整片
# 落在同一个坏窗口里；而续传是免费的——重试从断点接着下，等久一点的代价只是
# 等，不是重下。指数退避覆盖到 40s 上下，足够跨过多数瞬时故障。
# 第 n 次尝试失败后等 ``RETRY_DELAYS[n-1]``，超出长度取最后一个。
RETRY_COUNT = 5
RETRY_DELAYS = (1.0, 3.0, 9.0, 27.0)
# 退避期间看取消的间隔：睡满 27s 再看一眼，用户点的停止就要等半分钟才生效。
CANCEL_POLL_SECONDS = 0.5
HTTP_HEADERS = {"User-Agent": "AutoMasGui"}
CANCELLED_MESSAGE = "MaaFW update package download cancelled"
DEFAULT_TIMEOUT = httpx.Timeout(30.0)
# 备选源每个只试一次，所以连不上要早点认输——默认的 30s 连接超时乘以四个
# 镜像就是两分钟白等。读超时仍是 30s：镜像连上了但慢，那是下载本身的事。
ALTERNATE_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class UpdateDownloadCancelled(RuntimeError):
    """调用方置位 ``cancel_event`` 后下载主动停下。

    这不是网络错误，**绝不能进重试循环**：用户点的是停止。``.partial`` 与
    checkpoint 元数据原样留着，下次运行按既有的 Range 逻辑续传。
    """


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


@dataclass
class CachePruneReport:
    removed_artifacts: int = 0
    removed_bytes: int = 0
    skipped_busy: int = 0


# 下载好的更新包留在缓存里给同一项目的其它副本命中（按 源 + 版本 + 文件名 定位），
# 但一个版本只在发版后的几天里有人要；之后就是纯占地。
CACHE_RETENTION_SECONDS = 7 * 86400


def prune_update_cache(
    cache_root: Path | None = None, *, max_age_seconds: float = CACHE_RETENTION_SECONDS
) -> CachePruneReport:
    """删掉 ``max_age_seconds`` 内没人碰过的更新包（完整的与断点半成品都算）。

    「碰过」看 ``artifact.json`` 的 mtime：下载中每个进度点、缓存命中时都会重写它。
    正被下载 / 落地的条目持有 ``artifact.lock``，拿不到锁就跳过；锁文件本身从不删。
    """

    report = CachePruneReport()
    root = (cache_root or DEFAULT_CACHE_ROOT).resolve(strict=False)
    if not root.is_dir():
        return report
    cutoff = time.time() - max(0.0, max_age_seconds)
    for directory in sorted(root.iterdir()):
        if not directory.is_dir() or not re.fullmatch(r"[0-9a-f]{24}", directory.name):
            continue
        marker = directory / "artifact.json"
        try:
            reference = marker if marker.is_file() else directory
            if reference.stat().st_mtime >= cutoff:
                continue
        except OSError:
            continue
        try:
            lock = artifact_lock(root, directory.name, timeout=0)
        except ValueError:
            continue
        removed_any = False
        try:
            with lock:
                for entry in list(directory.iterdir()):
                    if entry.name == "artifact.lock" or not entry.is_file():
                        continue
                    size = entry.stat().st_size
                    entry.unlink()
                    report.removed_bytes += size
                    removed_any = True
        except TimeoutError:
            report.skipped_busy += 1
            continue
        except OSError:
            continue
        if removed_any:
            report.removed_artifacts += 1
    return report


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
    cancel_event: threading.Event | None = None,
    alternates: Sequence[tuple[str, str]] = (),
    expected_size: int | None = None,
) -> DownloadOutcome:
    """Download an artifact with Range/validator-aware checkpointing.

    ``cancel_event`` 置位后抛 :class:`UpdateDownloadCancelled`：每写完一个
    chunk 检查一次，所以「多久停下来」取决于还有没有字节在到达——整条连接
    卡死时要等 httpx 的读超时才会观察到。

    ``alternates`` 是 ``(名字, 地址)`` 的备选源（加速镜像），**先于
    ``download_url`` 逐个尝试，每个只试一次**，全部失败才回到直连并走既有的
    重试。核心包不认识「镜像」这个概念，清单由调用方给。

    经第三方转发的字节必须能校验：**没有 ``expected_sha256`` 时 ``alternates``
    整个忽略**，否则一个被改过的包会被当成正常更新落地。``expected_size``
    （发布方元数据里的资产大小）用来在下载开始前就否掉「回了一个 HTML 错误
    页却带 200」的镜像，直连不做这个比对。
    """

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

        def cancelled() -> bool:
            return cancel_event is not None and cancel_event.is_set()

        def record_cancelled() -> None:
            """把取消记进 journal；断点与元数据都不动，留给下次续传。"""

            store.update(
                "cancelled",
                downloadedBytes=(
                    partial_path.stat().st_size if partial_path.is_file() else 0
                ),
                totalBytes=_optional_int(metadata.get("totalBytes")),
            )

        def restart_from_zero() -> dict[str, Any]:
            """验证器变了：丢掉断点重来，并交回刷新后的元数据。

            ``_download_attempt`` 是就地改传进去的那份 dict 的，所以这里必须
            重新读盘并让调用方**重新绑定** ``metadata``，否则下一次尝试带着
            已经作废的 etag / downloadedBytes 去要 Range。
            """

            partial_path.unlink(missing_ok=True)
            fresh = _read_json(metadata_path)
            fresh.update(
                {
                    "downloadedBytes": 0,
                    "resumedFromBytes": 0,
                    "etag": None,
                    "lastModified": None,
                    "complete": False,
                    "completePath": None,
                }
            )
            _atomic_json_write(metadata_path, fresh)
            return fresh

        def finish(outcome: DownloadOutcome, *, attempt: int) -> DownloadOutcome:
            """下载成功的收尾；备选源与直连共用一份，别写成两处。"""

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
            send_update_log(f"MaaFW update package downloaded: {outcome.size} bytes")
            # 正常路径也要有 ``downloaded`` 事件（原来只有缓存命中才发）：
            # 宿主靠它知道「下载已结束、事务马上开始」——最后一个 chunk 到
            # 事务发出 plan_validated 之间还有 sha256 与项目指纹那几十秒，
            # 这段里点停止已经停不住下载线程之后的事了，文案不能再说
            # 「下次续传」。
            emit(
                {
                    "stage": "downloaded",
                    "status": "completed",
                    "downloaded_bytes": outcome.size,
                    "resumed_from_bytes": outcome.resumed_from,
                    "total_bytes": outcome.total_bytes,
                    "cache_hit": False,
                    "operation_id": store.operation_id,
                }
            )
            return outcome

        # 备选源（加速镜像）先试。它们只有在能对 sha256 时才安全：镜像是第三方
        # 转发，没有摘要就没有任何办法确认收到的是发布方那个包。
        candidates: list[tuple[str, str]] = [
            (str(name or "").strip() or "备选源", str(url or "").strip())
            for name, url in (alternates or ())
            if str(url or "").strip()
        ]
        if candidates and not expected:
            send_update_log("资产无 sha256 摘要，不走镜像")
            candidates = []

        for mirror_name, mirror_url in candidates:
            if cancelled():
                record_cancelled()
                raise UpdateDownloadCancelled(CANCELLED_MESSAGE)
            # 开始就说在用哪个源：几百兆要下几分钟，事后再说等于没说。
            # 失败会紧跟一行「不可用」，两行连着看就是完整的一次尝试。
            send_update_log(f"下载源：{mirror_name}")
            try:
                outcome = await _download_attempt(
                    partial_path=partial_path,
                    metadata_path=metadata_path,
                    metadata=metadata,
                    download_url=_validate_url(mirror_url),
                    expected_sha256=expected,
                    max_bytes=max_bytes,
                    operation=store,
                    proxy=proxy,
                    progress=emit,
                    cancel_event=cancel_event,
                    timeout=ALTERNATE_TIMEOUT,
                    expected_total=expected_size
                    or _optional_int(metadata.get("totalBytes")),
                )
            except UpdateDownloadCancelled:
                # 和直连一样排在 ``except Exception`` 之前：用户点的停止不是
                # 「这个镜像不行」，不能换下一个继续下。
                record_cancelled()
                raise
            except _RestartFromZero as exc:
                metadata = restart_from_zero()
                send_update_log(
                    f"镜像 {mirror_name} 不可用（{_reason(exc)}），改试下一个"
                )
                continue
            except Exception as exc:
                send_update_log(
                    f"镜像 {mirror_name} 不可用（{_reason(exc)}），改试下一个"
                )
                continue
            return finish(outcome, attempt=1)

        if candidates:
            send_update_log("全部镜像不可用，改为直连 GitHub")

        last_error: Exception | None = None
        for attempt in range(1, RETRY_COUNT + 1):
            if cancelled():
                record_cancelled()
                raise UpdateDownloadCancelled(CANCELLED_MESSAGE)
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
                    cancel_event=cancel_event,
                )
                return finish(outcome, attempt=attempt)
            except _RestartFromZero:
                metadata = restart_from_zero()
                continue
            except UpdateDownloadCancelled:
                # 必须排在 ``except Exception`` 之前：取消是用户的决定，
                # 当成网络错误重试就是「点了停止还在下」。
                record_cancelled()
                raise
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
                delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS)) - 1]
                if not await _sleep_unless_cancelled(delay, cancelled):
                    record_cancelled()
                    raise UpdateDownloadCancelled(CANCELLED_MESSAGE) from exc
        message = redact_text(last_error or "download failed")
        kept = partial_path.stat().st_size if partial_path.is_file() else 0
        store.update("failed", downloadedBytes=kept, error=message[:500])
        detail = (
            f"MaaFW update package download failed after {RETRY_COUNT} attempts: "
            f"{message}"
        )
        if kept > 0:
            # 断点是留着的，下次运行接着下——不说这一句，用户看到「失败」就会
            # 以为这几百兆白下了，转头去删缓存目录。
            known_total = expected_size or _optional_int(metadata.get("totalBytes"))
            progress_text = (
                f"已下载 {_megabytes(kept)} / {_megabytes(known_total)} MB"
                if known_total
                else f"已下载 {_megabytes(kept)} MB"
            )
            detail += f"（{progress_text} 已保留，下次运行续传）"
        raise RuntimeError(detail)


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
    cancel_event: threading.Event | None = None,
    timeout: httpx.Timeout = DEFAULT_TIMEOUT,
    expected_total: int | None = None,
) -> DownloadOutcome:
    if cancel_event is not None and cancel_event.is_set():
        raise UpdateDownloadCancelled(CANCELLED_MESSAGE)
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
        proxy=proxy, follow_redirects=False, timeout=timeout
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

                # 大小不对就在这里认输，**必须排在下面的验证器比对之前**：
                # 断点是带 etag 的，而回错误页的镜像通常根本不发 etag，先走到
                # ETag 分支就会判成 _RestartFromZero 把断点删掉——本该被否掉的
                # 镜像反而把已下好的几百兆冲了。直连不传 expected_total，行为不变。
                _reject_unexpected_total(
                    (
                        _parse_content_range(
                            str(response.headers.get("content-range") or "")
                        )
                        or (0, 0, None)
                    )[2]
                    if response.status_code == 206
                    else _content_length(response),
                    expected_total,
                )

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
                    _reject_unexpected_total(total, expected_total)
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
                        downloaded += len(chunk)
                        if downloaded > max_bytes:
                            raise RuntimeError("update package exceeds size limit")
                        await handle.write(chunk)
                        if downloaded % (CHUNK_SIZE * 16) < len(chunk):
                            # 每 1MB 落一次断点：fsync 与元数据原子改写都是同步
                            # IO，放到线程里，别每兆一次卡住事件循环。
                            await handle.flush()
                            await asyncio.to_thread(
                                _write_checkpoint,
                                partial_path,
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
                        if cancel_event is not None and cancel_event.is_set():
                            # 先把这一刻的字节数落盘再抛，否则 ``.partial`` 的
                            # 大小和元数据里的 downloadedBytes 对不上，下次续传
                            # 的 Range 就从错误的位置要起。
                            await handle.flush()
                            metadata["downloadedBytes"] = downloaded
                            await asyncio.to_thread(
                                _write_checkpoint,
                                partial_path,
                                metadata_path,
                                metadata,
                            )
                            raise UpdateDownloadCancelled(CANCELLED_MESSAGE)
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


def _write_checkpoint(
    partial_path: Path, metadata_path: Path, metadata: dict[str, Any]
) -> None:
    _sync_file(partial_path)
    _atomic_json_write(metadata_path, metadata)


def _sync_file(path: Path) -> None:
    try:
        with path.open("rb") as handle:
            os.fsync(handle.fileno())
    except OSError:
        pass


async def _sleep_unless_cancelled(delay: float, cancelled: Callable[[], bool]) -> bool:
    """退避等待；被取消返回 ``False``，正常等满返回 ``True``。

    切成 :data:`CANCEL_POLL_SECONDS` 一段是为了「点了停止立刻停」：整段睡完
    再看标志，最后那次退避要让用户等 27 秒才有反应。
    """

    waited = 0.0
    while waited < delay:
        if cancelled():
            return False
        step = min(CANCEL_POLL_SECONDS, delay - waited)
        await asyncio.sleep(step)
        waited += step
    return not cancelled()


def _megabytes(value: float | int | None) -> str:
    """字节数 → 一位小数的 MB 数字（不带单位，由调用方拼）。"""

    return f"{(value or 0) / (1024 * 1024):.1f}"


def _reject_unexpected_total(total: int | None, expected_total: int | None) -> None:
    """备选源声明的总长与已知大小对不上就当它不可用。

    只在调用方给了 ``expected_total`` 时生效（目前只有镜像走这条）。服务端
    没给 Content-Length 时 ``total`` 是 None——那不算矛盾，交给最后的 sha256
    校验兜底。
    """

    if expected_total is None or total is None or total == expected_total:
        return
    raise RuntimeError(f"包大小不符: {total} != {expected_total}")


def _reason(exc: BaseException) -> str:
    """异常 → 能进日志的一句话原因。

    httpx 的超时类异常 ``str()`` 常常是空串，只剩「不可用（）」这种看不出
    所以然的行，所以空了就退回类名。
    """

    return redact_text(exc).strip()[:200] or type(exc).__name__


def _optional_int(value: Any) -> int | None:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


__all__ = [
    "CACHE_RETENTION_SECONDS",
    "CANCELLED_MESSAGE",
    "CachePruneReport",
    "DownloadOutcome",
    "UpdateDownloadCancelled",
    "download_resumable",
    "prune_update_cache",
]
