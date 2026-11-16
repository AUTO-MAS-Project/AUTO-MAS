"""Linux/macOS 的非阻塞 flock 实现。"""

import fcntl
from typing import BinaryIO


def acquire(handle: BinaryIO) -> None:
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def release(handle: BinaryIO) -> None:
    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
