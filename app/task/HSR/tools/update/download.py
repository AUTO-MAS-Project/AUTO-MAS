"""复用 MAS 下载入口，并在发布安装包之前校验完整性。"""

from __future__ import annotations

import asyncio
import hashlib
import zipfile
from collections.abc import Callable
from pathlib import Path

import httpx

from app.core.script_update import download_script_package
from app.services.update_transport import DownloadProgress
from app.utils import get_logger
from app.utils.common.fluxdown_cli import FluxdownCancelUnconfirmed

from ...task_mapping import engine_label
from .discover import HSRUpdateError, UpdateCandidate

logger = get_logger("HSR 更新下载")

_USER_AGENT = "AutoMasGui"
_CHUNK = 256 * 1024
_RETRIES = 3
_RETRY_DELAY = 1.0

ProgressFn = Callable[[int, int], None]
AbortFn = Callable[[], bool]


class HSRUpdateAborted(HSRUpdateError):
    """用户在下载途中要求停止。不是错误，只是这一轮不更新了。"""


async def download_package(
    candidate: UpdateCandidate,
    destination: Path,
    *,
    proxy: httpx.Proxy | None = None,
    progress: ProgressFn | None = None,
    should_abort: AbortFn | None = None,
) -> Path:
    """下载到 ``destination``，返回该路径。失败时不留下半个文件。

    ``should_abort`` 在每次重试和下载进度回调中检查；取消后由公共下载器
    确认后台写入停止，半包保留供续传，只有校验成功的包才发布给安装器。
    """

    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")

    last_error: Exception | None = None
    for attempt in range(1, _RETRIES + 1):
        try:
            if should_abort and should_abort():
                raise asyncio.CancelledError
            await _fetch(
                candidate.download_url,
                partial,
                source=candidate.source,
                proxy=proxy,
                progress=progress,
                should_abort=should_abort,
            )
            break
        except FluxdownCancelUnconfirmed:
            # 后台可能仍在写入，不能重试、删包或放行用户任务。
            raise
        except HSRUpdateAborted:
            # 半截文件留着：下次 Range 续传能接上，用户不必从头下。
            raise
        except Exception as exc:  # noqa: BLE001 - 网络异常形态多，统一重试
            last_error = exc
            logger.warning(
                f"HSR 更新：下载{engine_label(candidate.engine, right=False)} "
                f"{candidate.latest_version} "
                f"第 {attempt}/{_RETRIES} 次失败：{exc}"
            )
            if attempt < _RETRIES:
                await asyncio.sleep(_RETRY_DELAY * attempt)
    else:
        # 重试用尽就删掉半截文件：目标文件名带版本号，留着它只会在数据目录里
        # 攒下一堆永远装不上的版本的残片。重试之间的续传在 _fetch 里已经做了。
        _unlink(partial)
        raise HSRUpdateError(f"下载失败：{last_error}")

    try:
        await asyncio.to_thread(_verify, partial, candidate)
    except Exception:
        _unlink(partial)
        raise

    partial.replace(destination)
    return destination


async def _fetch(
    url: str,
    partial: Path,
    *,
    source: str,
    proxy: httpx.Proxy | None,
    progress: ProgressFn | None,
    should_abort: AbortFn | None = None,
) -> None:
    async def report(downloaded: int, total: int, speed: float) -> None:
        if should_abort and should_abort():
            raise asyncio.CancelledError
        if progress:
            progress(downloaded, total)

    # 下载分发层统一处理代理、FluxDown 续传和旧后台写入权的安全回收。
    await download_script_package(
        url,
        partial,
        source=source,
        timeout=300,
        proxy=proxy,
        progress=report,
        http_download=_httpx_fetch,
    )


async def _httpx_fetch(
    url: str,
    destination: Path,
    *,
    timeout: float,
    proxy: httpx.Proxy | None = None,
    progress: DownloadProgress | None = None,
) -> int:
    """保留 HSR 的 HTTP 续传，但不绕过公共分发层的后台写入权保护。"""
    resume_from = destination.stat().st_size if destination.exists() else 0
    headers = {"User-Agent": _USER_AGENT}
    if resume_from:
        headers["Range"] = f"bytes={resume_from}-"
    async with httpx.AsyncClient(
        proxy=proxy, follow_redirects=True, timeout=httpx.Timeout(30.0, read=timeout)
    ) as client:
        async with client.stream("GET", url, headers=headers) as response:
            response.raise_for_status()
            if response.status_code == 206:
                content_range = response.headers.get("Content-Range", "")
                if not content_range.startswith(f"bytes {resume_from}-"):
                    raise HSRUpdateError("下载续传范围与已有文件不符")
            elif response.status_code == 200:
                resume_from = 0
            else:
                raise HSRUpdateError("下载响应不支持整包或续传")
            total = _total_size(response, resume_from)
            written = resume_from
            if progress:
                await progress(written, total, 0.0)
            with destination.open("ab" if resume_from else "wb") as handle:
                async for chunk in response.aiter_bytes(_CHUNK):
                    handle.write(chunk)
                    written += len(chunk)
                    if progress:
                        await progress(written, total, 0.0)
            return written


def _total_size(response: httpx.Response, resume_from: int) -> int:
    content_range = response.headers.get("Content-Range", "")
    try:
        if "/" in content_range:
            return int(content_range.rsplit("/", 1)[1])
        length = response.headers.get("Content-Length")
        return int(length) + resume_from if length else 0
    except ValueError:
        return 0


def _verify(package: Path, candidate: UpdateCandidate) -> None:
    if candidate.sha256:
        digest = _sha256(package)
        if digest.casefold() != candidate.sha256.casefold():
            raise HSRUpdateError(
                f"更新包校验失败：期望 {candidate.sha256}，实得 {digest}"
            )
        return

    # 没有哈希可比时至少确认这是个完整的压缩包，别把一段 HTML 错误页当成
    # 更新包解出去。7z 包交给解包器自己判，这里只管 zip。
    if candidate.asset_kind == "zip" and not zipfile.is_zipfile(package):
        raise HSRUpdateError("下载到的内容不是有效的压缩包，可能是下载源返回了错误页")
    logger.warning("HSR 更新：下载源未提供 sha256，已退化为压缩包完整性检查")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _unlink(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


__all__ = ["ProgressFn", "download_package"]
