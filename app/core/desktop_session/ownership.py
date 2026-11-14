"""同一 MAS 工作目录的 Windows 后端写入互斥。"""

import os
from contextlib import contextmanager
from pathlib import Path

EXECUTOR_SESSION = "AUTO_MAS_DESKTOP_EXECUTOR_SESSION"
EXECUTOR_TOKEN = "AUTO_MAS_DESKTOP_EXECUTOR_TOKEN"
CONTROL_TOKEN = "AUTO_MAS_DESKTOP_CONTROL_TOKEN"
RESUME = "AUTO_MAS_DESKTOP_RESUME"


@contextmanager
def data_owner(root: Path):
    """在真正的写端生命周期持有锁，进程退出时由系统释放。"""
    if os.name != "nt":
        yield
        return
    from app.utils import file_lock

    lock_path = root / "temp" / "desktop-session-data.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        try:
            file_lock.acquire(handle)
        except OSError:
            raise RuntimeError("另一 MAS 后端正在使用同一工作目录") from None
        try:
            yield
        finally:
            file_lock.release(handle)
