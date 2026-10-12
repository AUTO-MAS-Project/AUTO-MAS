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
