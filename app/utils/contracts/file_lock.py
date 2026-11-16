"""跨进程文件锁契约；竞争时抛出 OSError，重试与取消由调用者负责。"""

from typing import BinaryIO, Protocol


class FileLockAPI(Protocol):
    def acquire(self, handle: BinaryIO) -> None: ...
    def release(self, handle: BinaryIO) -> None: ...
