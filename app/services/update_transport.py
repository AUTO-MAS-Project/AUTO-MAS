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

"""MAS 与脚本更新共用的 Mirror 请求和文件下载，不持有更新状态。"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any

import aiofiles
import httpx

from app.utils.constants import MIRROR_ERROR_INFO

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
