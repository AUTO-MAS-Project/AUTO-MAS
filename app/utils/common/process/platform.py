import asyncio
from contextlib import suppress

import psutil

from app.utils.common.errors import UnsupportedPlatformError
from app.utils.contracts.process import (
    ElevatedProcess,
    TaskProcessJob,
)


def breakaway_rejected(
    error: OSError, *, flags: int, breakaway_flags: int
) -> int | None:
    """判定 CreateProcess 是否因 Job 不允许脱离被拒，返回去掉脱离位后的标志。

    父进程若恰好处在不允许 breakaway 的 Job 里，带 CREATE_BREAKAWAY_FROM_JOB
    的 CreateProcess 会以 ERROR_ACCESS_DENIED（WinError 5）失败；此时去掉该位
    重试一次，子进程留在当前 Job 里。其他原因返回 None，由调用方原样抛出。
    """

    if not flags & breakaway_flags or getattr(error, "winerror", None) != 5:
        return None
    return flags & ~breakaway_flags


class CommonProcessPlatform:
    @staticmethod
    def create_task_job() -> TaskProcessJob | None:
        return None

    supports_elevation = False
    agent_flags = 0
    creation_flags = 0
    # 非 Windows 没有 Job Object 概念，breakaway 位恒为 0，调用点传
    # breakaway=True 也不会改变行为。
    breakaway_flags = 0

    @staticmethod
    def prepare_elevated() -> ElevatedProcess:
        raise UnsupportedPlatformError("elevated_process")

    async def open_protocol(self, protocol_url: str) -> None:
        raise UnsupportedPlatformError("open_protocol")

    async def kill_process(self, pid: int, kill_tree: bool = False) -> tuple[bool, str]:
        """用 psutil 终止进程，返回 (是否成功, 失败原因)。"""

        try:
            proc = psutil.Process(pid)
        except psutil.NoSuchProcess:
            return False, "进程不存在"

        targets = [proc]
        if kill_tree:
            with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
                targets = proc.children(recursive=True) + [proc]

        for target in targets:
            with suppress(psutil.NoSuchProcess):
                try:
                    target.kill()
                except psutil.AccessDenied:
                    return False, f"权限不足, PID: {target.pid}"

        _, alive = await asyncio.to_thread(psutil.wait_procs, targets, timeout=5)
        if alive:
            return False, f"{len(alive)} 个进程未在超时内退出"
        return True, ""


platform_process = CommonProcessPlatform()
