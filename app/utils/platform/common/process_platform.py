import asyncio
from contextlib import suppress

import psutil

from .errors import UnsupportedPlatformError


class CommonProcessPlatform:
    creation_flags = 0
    # 非 Windows 没有 Job Object 概念，breakaway 位恒为 0，调用点传
    # breakaway=True 也不会改变行为。
    breakaway_flags = 0
    detached_flags = 0

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
