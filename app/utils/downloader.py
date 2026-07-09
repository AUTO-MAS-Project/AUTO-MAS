#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""通用文件下载器

支持:
- httpx 流式下载
- .part 断点续传 (Range header)
- md5 校验
- 磁盘空间预检
- 取消 (asyncio.Event)
- 并行分卷下载 (download_many)
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
from pathlib import Path
from typing import Any, Callable, Optional

import httpx

from app.utils import get_logger

logger = get_logger("下载器")

# 进度回调类型: (downloaded, total, speed) -> None
ProgressCallback = Callable[[int, int, float], Any]


async def download_file(
    url: str,
    dest: Path,
    *,
    expected_md5: Optional[str] = None,
    expected_size: Optional[int] = None,
    progress: Optional[ProgressCallback] = None,
    cancel_event: Optional[asyncio.Event] = None,
    chunk_size: int = 1024 * 1024,
    timeout: float = 300.0,
    headers: Optional[dict[str, str]] = None,
) -> Path:
    """下载单个文件到 dest, 支持断点续传

    Args:
        url: 下载地址
        dest: 目标路径
        expected_md5: 期望的 md5 (可选, 用于校验)
        expected_size: 期望的文件大小 (可选)
        progress: 进度回调 (downloaded_bytes, total_bytes, speed_bps)
        cancel_event: 取消事件
        chunk_size: 下载块大小
        timeout: 单次请求超时
        headers: 额外请求头

    Returns:
        下载完成的文件路径

    Raises:
        RuntimeError: 校验失败 / 磁盘空间不足 / 被取消
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part_file = dest.with_suffix(dest.suffix + ".part")

    # 检查已完成文件
    if dest.exists() and dest.stat().st_size > 0:
        if expected_md5:
            actual = await _md5_file(dest)
            if actual == expected_md5:
                logger.debug(f"文件已存在且校验通过: {dest}")
                if progress:
                    progress(dest.stat().st_size, dest.stat().st_size, 0.0)
                return dest
        elif expected_size and dest.stat().st_size == expected_size:
            logger.debug(f"文件已存在且大小匹配: {dest}")
            if progress:
                progress(dest.stat().st_size, expected_size, 0.0)
            return dest

    # 磁盘空间预检
    total_size = expected_size or 0
    _check_disk_space(dest.parent, total_size)

    # 断点续传: 获取已下载部分大小
    resume_pos = 0
    if part_file.exists():
        resume_pos = part_file.stat().st_size
        if expected_size and resume_pos >= expected_size:
            # .part 已完整, 重命名
            part_file.rename(dest)
            return dest
        logger.debug(f"断点续传: 从 {resume_pos} 字节继续下载 {url}")

    req_headers = {}
    if headers:
        req_headers.update(headers)
    if resume_pos > 0:
        req_headers["Range"] = f"bytes={resume_pos}-"

    downloaded = resume_pos
    last_reported = resume_pos
    last_time = asyncio.get_event_loop().time()

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout, connect=30.0),
        follow_redirects=True,
    ) as client:
        async with client.stream("GET", url, headers=req_headers) as resp:
            resp.raise_for_status()

            # 获取总大小
            if resume_pos > 0 and resp.status_code == 206:
                content_range = resp.headers.get("content-range", "")
                if "/" in content_range:
                    total_size = int(content_range.split("/")[-1])
                else:
                    total_size = resume_pos + int(
                        resp.headers.get("content-length", 0)
                    )
            else:
                # 不是续传, 从头开始
                resume_pos = 0
                downloaded = 0
                total_size = expected_size or int(
                    resp.headers.get("content-length", 0)
                )

            mode = "ab" if resume_pos > 0 else "wb"
            with open(part_file, mode) as f:
                async for chunk in resp.aiter_bytes(chunk_size):
                    if cancel_event and cancel_event.is_set():
                        logger.info(f"下载已取消: {url}")
                        raise asyncio.CancelledError("下载被用户取消")

                    f.write(chunk)
                    downloaded += len(chunk)

                    now = asyncio.get_event_loop().time()
                    elapsed = now - last_time
                    if elapsed >= 0.5 and progress:
                        speed = (downloaded - last_reported) / elapsed
                        progress(downloaded, total_size, speed)
                        last_reported = downloaded
                        last_time = now

            # 最终进度
            if progress:
                progress(downloaded, total_size, 0.0)

    # md5 校验
    if expected_md5:
        logger.debug(f"校验 md5: {part_file}")
        actual = await _md5_file(part_file)
        if actual != expected_md5:
            part_file.unlink(missing_ok=True)
            raise RuntimeError(
                f"md5 校验失败: 期望 {expected_md5}, 实际 {actual}"
            )

    # 重命名 .part -> 最终文件
    if dest.exists():
        dest.unlink()
    part_file.rename(dest)
    logger.debug(f"下载完成: {dest}")
    return dest


async def download_many(
    urls: list[str],
    dest_dir: Path,
    *,
    expected_items: Optional[list[dict[str, Any]]] = None,
    progress: Optional[ProgressCallback] = None,
    cancel_event: Optional[asyncio.Event] = None,
    concurrency: int = 4,
    timeout: float = 300.0,
) -> list[Path]:
    """并行下载多个分卷文件, 聚合进度

    Args:
        urls: 下载地址列表
        dest_dir: 目标目录
        expected_items: 每项 {"url": ..., "md5": ..., "size": ..., "name": ...}
        progress: 聚合进度回调
        cancel_event: 取消事件
        concurrency: 并发数
        timeout: 单文件超时

    Returns:
        下载完成的文件路径列表
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    # 计算总大小
    total_size = 0
    item_info: list[dict[str, Any]] = []
    for i, url in enumerate(urls):
        info = {"url": url}
        if expected_items and i < len(expected_items):
            info["md5"] = expected_items[i].get("md5")
            info["size"] = expected_items[i].get("size", 0)
            info["name"] = expected_items[i].get("name", _filename_from_url(url))
            total_size += info["size"] or 0
        else:
            info["name"] = _filename_from_url(url)
        info["dest"] = dest_dir / info["name"]
        item_info.append(info)

    # 已下载字节聚合
    downloaded_map: dict[int, int] = {i: 0 for i in range(len(urls))}
    last_time = asyncio.get_event_loop().time()
    last_reported_sum = 0

    def _aggregate_progress(idx: int, dl: int, total: int, speed: float) -> None:
        nonlocal last_time, last_reported_sum
        downloaded_map[idx] = dl
        if not progress:
            return
        now = asyncio.get_event_loop().time()
        elapsed = now - last_time
        if elapsed >= 0.5:
            current_sum = sum(downloaded_map.values())
            speed_avg = (current_sum - last_reported_sum) / elapsed
            progress(current_sum, total_size, speed_avg)
            last_reported_sum = current_sum
            last_time = now

    semaphore = asyncio.Semaphore(concurrency)

    async def _download_one(idx: int) -> Path:
        info = item_info[idx]
        async with semaphore:
            def _cb(dl: int, total: int, speed: float) -> None:
                _aggregate_progress(idx, dl, total, speed)

            return await download_file(
                info["url"],
                info["dest"],
                expected_md5=info.get("md5"),
                expected_size=info.get("size"),
                progress=_cb,
                cancel_event=cancel_event,
                timeout=timeout,
            )

    results = await asyncio.gather(*[_download_one(i) for i in range(len(urls))])

    if progress:
        progress(total_size, total_size, 0.0)

    return results


async def _md5_file(path: Path) -> str:
    """异步计算文件 md5"""
    md5 = hashlib.md5()
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None, _read_file_in_chunks, path, md5
    )
    return md5.hexdigest()


def _read_file_in_chunks(path: Path, md5: hashlib._Hash, chunk: int = 1024 * 1024) -> None:
    """在线程池中读取文件并更新 md5"""
    with open(path, "rb") as f:
        while True:
            data = f.read(chunk)
            if not data:
                break
            md5.update(data)


def _check_disk_space(dest_dir: Path, required: int) -> None:
    """检查磁盘空间是否足够"""
    if required <= 0:
        return
    usage = shutil.disk_usage(str(dest_dir))
    # 预留 1GB 余量
    needed = required + 1024 * 1024 * 1024
    if usage.free < needed:
        raise RuntimeError(
            f"磁盘空间不足: 需要 {needed / 1024 / 1024 / 1024:.1f} GB, "
            f"可用 {usage.free / 1024 / 1024 / 1024:.1f} GB"
        )


def _filename_from_url(url: str) -> str:
    """从 URL 提取文件名"""
    name = url.split("/")[-1].split("?")[0]
    return name if name else "download"
