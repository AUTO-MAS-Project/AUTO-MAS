#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""增量补丁工具 hpatchz 的按需获取。

各游戏的官方增量包用的是 HDiffPatch 格式，应用它需要 ``hpatchz`` 可执行体。
上游 sisong/HDiffPatch 为 MIT，与本项目 AGPL 兼容；仓库不跟踪二进制，
因此首次需要打增量时下载、比对 sha256、解出可执行体并缓存复用。

这是个会被拿去改写游戏文件的可执行体，不能来源不明 —— 校验不过就直接失败。
"""

from __future__ import annotations

import asyncio
import hashlib
import zipfile
from collections.abc import Awaitable, Callable
from pathlib import Path

import httpx

from app.utils import get_logger
from app.utils.io import atomic_write

logger = get_logger("增量补丁工具")

ProgressHook = Callable[[str], Awaitable[None]]

_HPATCHZ_VERSION = "v5.1.3"
_HPATCHZ_URL = (
    "https://github.com/sisong/HDiffPatch/releases/download/"
    f"{_HPATCHZ_VERSION}/hdiffpatch_{_HPATCHZ_VERSION}_bin_windows64.zip"
)
_HPATCHZ_ZIP_SHA256 = "77f141386e5d8f785c1c846e10fbbc19b6c05aa00e3f59cc44670fb3f0e2ae94"
_HPATCHZ_MEMBER = "windows64/hpatchz.exe"
_HPATCHZ_CACHE_DIR = Path.cwd() / "data" / "cache" / "hpatchz"


def _install_hpatchz(zip_path: Path, exe: Path) -> None:
    """把发行包里的 ``hpatchz.exe`` 原子落到缓存路径。

    Args:
        zip_path: 已通过 sha256 校验的发行包。
        exe: 缓存里的 ``hpatchz.exe`` 路径。
    """
    with zipfile.ZipFile(zip_path) as archive:
        atomic_write(exe, archive.read(_HPATCHZ_MEMBER))


async def ensure_hpatchz(
    *, on_progress: ProgressHook | None = None, timeout: float = 120.0
) -> Path:
    """确保本地有 hpatchz，没有则下载并校验 sha256 后缓存。

    Args:
        on_progress: 进度回调，收一行面向用户的文案。
        timeout: 下载超时（秒）。

    Returns:
        缓存中的 ``hpatchz.exe`` 路径。

    Raises:
        RuntimeError: 下载内容的 sha256 与固定值不符时。
    """

    exe = _HPATCHZ_CACHE_DIR / "hpatchz.exe"
    # 敢只看文件在不在，是因为落位走原子改名：中途被杀只会留下 .tmp
    if exe.is_file():
        return exe

    if on_progress is not None:
        await on_progress(f"正在获取增量补丁工具 hpatchz {_HPATCHZ_VERSION}...")
    logger.info("正在获取增量补丁工具 hpatchz {}", _HPATCHZ_VERSION)
    zip_path = _HPATCHZ_CACHE_DIR / "hpatchz.zip"
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(_HPATCHZ_URL)
        response.raise_for_status()
        payload = response.content

    actual = hashlib.sha256(payload).hexdigest()
    if actual != _HPATCHZ_ZIP_SHA256:
        raise RuntimeError(
            f"hpatchz 校验失败: 期望 {_HPATCHZ_ZIP_SHA256} 实际 {actual}"
        )
    try:
        await asyncio.to_thread(atomic_write, zip_path, payload)
        await asyncio.to_thread(_install_hpatchz, zip_path, exe)
    finally:
        zip_path.unlink(missing_ok=True)
    logger.info("hpatchz 就绪: {}", exe)
    return exe
