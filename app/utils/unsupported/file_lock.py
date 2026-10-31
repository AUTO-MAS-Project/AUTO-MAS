"""尚未提供实现的平台不能声称已取得跨进程锁。"""

from typing import BinaryIO

from ..common.errors import UnsupportedPlatformError


def acquire(handle: BinaryIO) -> None:
    raise UnsupportedPlatformError("file_lock")


def release(handle: BinaryIO) -> None:
    raise UnsupportedPlatformError("file_lock")
