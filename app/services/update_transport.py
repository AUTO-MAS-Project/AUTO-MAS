#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.
#
#   Contact: DLmaster_361@163.com

"""更新共用的 Mirror 请求、整文件续传与范围下载，不持有游戏更新策略。"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import aclosing
from pathlib import Path
from typing import Any

import aiofiles
import httpx

from app.utils.constants import MIRROR_ERROR_INFO
from app.utils.update_files import file_size, native_path

DownloadProgress = Callable[[int, int, float], Awaitable[None]]


async def request_mirror_resource(
    resource_id: str,
    *,
    params: Mapping[str, str],
    proxy: httpx.Proxy | None = None,
    timeout: float = 10,
) -> dict[str, Any]:
    """查询 Mirror 资源，校验响应和业务码，返回完整响应体。"""
    async with httpx.AsyncClient(
        proxy=proxy, follow_redirects=True, timeout=timeout
    ) as client:
        response = await client.get(
            f"https://mirrorchyan.com/api/resources/{resource_id}/latest",
            params={"user_agent": "AutoMasGui", **params},
        )
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Mirror酱响应不是对象")
    code = payload.get("code")
    if not isinstance(code, int) or isinstance(code, bool):
        raise RuntimeError(f"Mirror酱响应 code 非整数: {code!r}")
    if code != 0:
        message = MIRROR_ERROR_INFO.get(code, str(payload.get("msg", "")))
        raise RuntimeError(f"Mirror酱 code={code}: {message}")
    if not response.is_success:
        # raise_for_status 的异常会包含完整 URL，查询参数中可能带有 CDK。
        raise RuntimeError(f"Mirror酱 HTTP 响应异常: {response.status_code}")
    return payload


async def download_file(
    url: str,
    destination: Path,
    *,
    timeout: float,
    proxy: httpx.Proxy | None = None,
    progress: DownloadProgress | None = None,
) -> int:
    """流式写入目标文件，返回字节数；进度每秒上报并在开始、结束时上报。

    timeout 限制单次网络操作，总时限、重试及临时文件清理由调用方负责。
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(
        proxy=proxy, follow_redirects=True, timeout=timeout
    ) as client:
        async with client.stream("GET", url) as response:
            if response.status_code not in (200, 206):
                raise httpx.HTTPStatusError(
                    f"下载响应异常: {response.status_code}",
                    request=response.request,
                    response=response,
                )
            # Content-Length 仅用于展示；无法解析时按未知大小处理。
            try:
                total = int(response.headers.get("content-length") or 0)
            except ValueError:
                total = 0
            if progress is not None:
                await progress(0, total, 0.0)
            downloaded = window_bytes = 0
            window_start = time.monotonic()
            async with aiofiles.open(destination, "wb") as handle:
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    await handle.write(chunk)
                    downloaded += len(chunk)
                    window_bytes += len(chunk)
                    elapsed = time.monotonic() - window_start
                    if progress is not None and elapsed >= 1:
                        await progress(downloaded, total, window_bytes / elapsed)
                        window_bytes = 0
                        window_start = time.monotonic()
            if progress is not None:
                elapsed = time.monotonic() - window_start
                await progress(
                    downloaded, total, window_bytes / elapsed if elapsed > 0 else 0.0
                )
            return downloaded


BytesProgress = Callable[[int], Awaitable[None]]
_DOWNLOAD_CHUNK = 1024**2


def _hash_prefix(digest: Any, path: Path, limit: int) -> None:
    """续传前把已有字节计入调用方的摘要，不读取前缀之外的内容。"""
    with open(native_path(path), "rb") as handle:
        remaining = limit
        while remaining:
            block = handle.read(min(16 * _DOWNLOAD_CHUNK, remaining))
            if not block:
                break
            digest.update(block)
            remaining -= len(block)


async def download_resumable(
    client: httpx.AsyncClient,
    url: str,
    destination: Path,
    *,
    expected_size: int,
    on_bytes: BytesProgress | None = None,
    digest: Any | None = None,
) -> int:
    """流式续传整文件，返回落盘大小；重试与完整性校验由调用方负责。

    on_bytes 只报告本次接收量；续传被服务器忽略时先以负数扣除被覆盖的前缀。
    digest 可传入本次下载新建的摘要，续传前自动计入已有前缀。

    落盘大小已经等于期望值时没有可续的段，`Range: bytes={N}-` 是空区间（真实 CDN 会回
    416），只能整份重来。实收超过期望值直接判废，不写进盘：磁盘门按声明体积留的余量，
    超发会把那份余量吃穿、把问题转成落地的 OSError。
    """
    done = max(file_size(destination), 0)
    if done >= expected_size:
        destination.unlink(missing_ok=True)
        done = 0
    headers = {"Range": f"bytes={done}-"} if done else {}
    async with client.stream("GET", url, headers=headers) as response:
        response.raise_for_status()
        append = bool(done and response.status_code == 206)
        if done and not append:
            if on_bytes is not None:
                await on_bytes(-done)
            done = 0
        if digest is not None and append:
            await asyncio.to_thread(_hash_prefix, digest, destination, done)
        destination.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(
            native_path(destination), "ab" if append else "wb"
        ) as sink:
            async for block in response.aiter_bytes(_DOWNLOAD_CHUNK):
                if not block:
                    continue
                if done + len(block) > expected_size:
                    raise ValueError(
                        f"实收超过声明长度: 期望 {expected_size}，已收 {done}，"
                        f"这一片 {len(block)}"
                    )
                await sink.write(block)
                done += len(block)
                if digest is not None:
                    digest.update(block)
                if on_bytes is not None:
                    await on_bytes(len(block))
    return done


async def _range_blocks(
    client: httpx.AsyncClient,
    url: str,
    offset: int,
    length: int,
    timeout: float | None,
    expected_total: int | None = None,
) -> AsyncIterator[bytes]:
    """读取指定范围；从零开始的整文件响应可由长度校验确认。"""
    if offset < 0 or length < 0:
        raise ValueError("下载范围不能为负数")
    if not length:
        return
    options = {} if timeout is None else {"timeout": timeout}
    headers = {"Range": f"bytes={offset}-{offset + length - 1}"}
    received = 0
    async with client.stream("GET", url, headers=headers, **options) as response:
        response.raise_for_status()
        if response.status_code != 206 and not (
            offset == 0 and response.status_code == 200
        ):
            raise ValueError(f"服务器未按 Range 返回（HTTP {response.status_code}）")
        if expected_total is not None:
            expected_range = f"bytes {offset}-{offset + length - 1}/{expected_total}"
            if (
                response.status_code != 206
                or response.headers.get("content-range") != expected_range
            ):
                raise ValueError(f"服务器返回的 Content-Range 与 {expected_range} 不符")
        async for block in response.aiter_bytes(_DOWNLOAD_CHUNK):
            received += len(block)
            if received > length:
                raise ValueError(f"分片长度不符: 期望 {length}，实际超过范围")
            yield block
    if received != length:
        raise ValueError(f"分片长度不符: 期望 {length}，实际 {received}")


async def read_range(
    client: httpx.AsyncClient,
    url: str,
    *,
    offset: int,
    length: int,
    timeout: float | None = None,
    expected_total: int | None = None,
) -> bytes:
    """读取范围到内存；提供 expected_total 时另核对 Content-Range。"""
    content = bytearray()
    async with aclosing(
        _range_blocks(client, url, offset, length, timeout, expected_total)
    ) as blocks:
        async for block in blocks:
            content.extend(block)
    return bytes(content)


async def download_range(
    client: httpx.AsyncClient,
    url: str,
    destination: Path,
    *,
    offset: int,
    length: int,
    timeout: float | None = None,
    on_bytes: BytesProgress | None = None,
) -> int:
    """将指定字节范围流式写到文件，返回接收量；不负责解压与校验。"""
    received = 0
    async with aiofiles.open(native_path(destination), "wb") as sink:
        async with aclosing(
            _range_blocks(client, url, offset, length, timeout)
        ) as blocks:
            async for block in blocks:
                await sink.write(block)
                received += len(block)
                if on_bytes is not None:
                    await on_bytes(len(block))
    return received
