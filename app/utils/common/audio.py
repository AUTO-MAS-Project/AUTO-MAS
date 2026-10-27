"""没有公共音量控制实现时明确报告缺失能力。"""

from .errors import UnsupportedPlatformError


async def mute_once(pids):
    raise UnsupportedPlatformError("audio")


async def restore_processes(states):
    raise UnsupportedPlatformError("audio")
