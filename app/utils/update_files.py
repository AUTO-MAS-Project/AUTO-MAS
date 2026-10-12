#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""更新流程共用的文件校验、替换与目录锁，不持有游戏更新策略。"""

from __future__ import annotations

import asyncio
import hashlib
import os
import stat
from contextlib import suppress
from pathlib import Path

_LONG_PATH_THRESHOLD = 259
_directory_locks: dict[str, asyncio.Lock] = {}


def native_path(path: str | Path) -> str:
    """Windows 长路径加扩展前缀，UNC 路径使用对应的 UNC 前缀。"""
    text = str(path)
    if os.name != "nt" or len(text) < _LONG_PATH_THRESHOLD:
        return text
    absolute = os.path.abspath(text)
    if absolute.startswith("\\\\"):
        return "\\\\?\\UNC\\" + absolute.lstrip("\\\\")
    return "\\\\?\\" + absolute


def file_size(path: str | Path) -> int:
    """读取文件大小，无法读取时返回 -1。"""
    try:
        return os.stat(native_path(path)).st_size
    except OSError:
        return -1


def file_md5(path: str | Path) -> str:
    """读取完整文件并返回小写 MD5；大文件由调用方在线程中执行。"""
    with open(native_path(path), "rb") as handle:
        return hashlib.file_digest(handle, "md5").hexdigest()


async def file_matches(
    path: str | Path,
    *,
    size: int,
    md5: str | None = None,
    actual_md5: str | None = None,
) -> bool:
    """先核对大小，再核对 MD5；可复用下载过程中已计算的摘要。

    md5 为 None 时只核对大小；读取摘要失败时仍抛 OSError，由调用方处理。
    """
    if file_size(path) != size:
        return False
    if md5 is None:
        return True
    if actual_md5 is None:
        actual_md5 = await asyncio.to_thread(file_md5, path)
    return actual_md5 == md5


def replace_file(
    source: str | Path, target: str | Path, *, clear_readonly: bool = False
) -> None:
    """将已就绪的源文件原子替换到目标，缺少父目录时创建后重试。

    clear_readonly 用于允许覆盖带只读属性的目标；校验、线程调度与取消由调用方负责。
    """
    source_path, target_path = native_path(source), native_path(target)
    if clear_readonly and os.path.exists(target_path):
        with suppress(OSError):
            os.chmod(target_path, stat.S_IWRITE)
    try:
        os.replace(source_path, target_path)
    except FileNotFoundError:
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        os.replace(source_path, target_path)


def directory_lock(directory: str | Path) -> asyncio.Lock:
    """按规范化绝对路径取进程内锁，是否等待由调用方决定。"""
    key = os.path.normcase(os.path.abspath(directory))
    lock = _directory_locks.get(key)
    if lock is None:
        lock = _directory_locks[key] = asyncio.Lock()
    return lock


def resolve_within(
    root: str | Path,
    relative: str | Path,
    *,
    resolve_links: bool = True,
    reject_links: bool = False,
) -> Path:
    """解析根目录内的路径，越界时抛 ValueError。

    resolve_links 核对并返回实际路径；关闭时只核对规范化的路径字符串。
    reject_links 用于不允许符号链接或 Windows 重解析点的调用方。
    清单路径的格式校验与业务异常转换由调用方负责。
    """
    anchor = Path(os.path.abspath(root))
    target = Path(os.path.abspath(anchor / relative))
    if resolve_links:
        anchor, target = anchor.resolve(), target.resolve()
    anchor_key = os.path.normcase(str(anchor))
    target_key = os.path.normcase(str(target))
    try:
        inside = os.path.commonpath([anchor_key, target_key]) == anchor_key
    except ValueError as error:
        raise ValueError(f"无法判定路径归属: {relative!r}") from error
    if not inside:
        raise ValueError(f"路径越出根目录: {relative!r}")
    if reject_links:
        # 从原始路径逐段检查，避免 resolve 后失去链接本身的信息。
        lexical_root = Path(os.path.abspath(root))
        lexical_target = Path(os.path.abspath(lexical_root / relative))
        current = lexical_root
        for part in lexical_target.relative_to(lexical_root).parts:
            current /= part
            try:
                info = os.stat(native_path(current), follow_symlinks=False)
            except OSError:
                break
            if (
                stat.S_ISLNK(info.st_mode)
                or getattr(info, "st_reparse_tag", 0)
                or (
                    getattr(info, "st_file_attributes", 0)
                    & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
                )
            ):
                raise ValueError(f"路径经过符号链接或重解析点: {relative!r}")
    return target
