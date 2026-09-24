"""下载更新包：Range 续传 + sha256 校验。

自建站与 GitHub 都实测支持 Range（HTTP 206），断点续传对 170–750MB 的包很
划算。源不提供哈希时退化为压缩包完整性测试——那不算校验失败，只是少一层
保障。
"""

from __future__ import annotations

import asyncio
import hashlib
import zipfile
from collections.abc import Callable
from pathlib import Path

import httpx

from app.utils.logger import get_logger

from .discover import HSRUpdateError, UpdateCandidate

logger = get_logger("HSR 更新下载")

_USER_AGENT = "AutoMasGui"
_CHUNK = 256 * 1024
_RETRIES = 3
_RETRY_DELAY = 1.0
_TIMEOUT = httpx.Timeout(30.0, read=300.0)

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

    ``should_abort`` 每收一块就问一次。收尾期的更新跑在 ``asyncio.shield``
    里，取消传不进来，只能这样协作式地停——否则用户按了停止还要等一个
    几百 MB 的下载走完，期间外部目录锁一直被占着。
    """

    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")

    last_error: Exception | None = None
    for attempt in range(1, _RETRIES + 1):
        try:
            await _fetch(
                candidate.download_url,
                partial,
                proxy=proxy,
                progress=progress,
                should_abort=should_abort,
            )
            break
        except HSRUpdateAborted:
            # 半截文件留着：下次 Range 续传能接上，用户不必从头下。
            raise
        except Exception as exc:  # noqa: BLE001 - 网络异常形态多，统一重试
            last_error = exc
            logger.warning(
                f"HSR 更新：下载 {candidate.engine} {candidate.latest_version} "
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
    proxy: httpx.Proxy | None,
    progress: ProgressFn | None,
    should_abort: AbortFn | None = None,
) -> None:
    resume_from = partial.stat().st_size if partial.exists() else 0
    headers = {"User-Agent": _USER_AGENT}
    if resume_from:
        headers["Range"] = f"bytes={resume_from}-"

    async with httpx.AsyncClient(
        proxy=proxy, follow_redirects=True, timeout=_TIMEOUT
    ) as client:
        async with client.stream("GET", url, headers=headers) as response:
            if resume_from and response.status_code == 200:
                # 服务端忽略了 Range，从头开始。
                resume_from = 0
            elif resume_from and response.status_code != 206:
                response.raise_for_status()
                resume_from = 0
            else:
                response.raise_for_status()

            total = _total_size(response, resume_from)
            mode = "ab" if resume_from else "wb"
            written = resume_from
            with open(partial, mode) as handle:
                async for chunk in response.aiter_bytes(_CHUNK):
                    if should_abort and should_abort():
                        raise HSRUpdateAborted("用户已请求停止，本轮不再更新")
                    handle.write(chunk)
                    written += len(chunk)
                    if progress:
                        progress(written, total)


def _total_size(response: httpx.Response, resume_from: int) -> int:
    content_range = response.headers.get("Content-Range")
    if content_range and "/" in content_range:
        try:
            return int(content_range.rsplit("/", 1)[1])
        except ValueError:
            pass
    length = response.headers.get("Content-Length")
    if length:
        try:
            return int(length) + resume_from
        except ValueError:
            pass
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
