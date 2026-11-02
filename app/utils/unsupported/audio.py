"""尚无实现的音频能力。"""

from collections.abc import Iterable

from ..common.errors import UnsupportedPlatformError


async def mute_once(pids: Iterable[int]) -> dict[int, bool]:
    raise UnsupportedPlatformError("audio")


async def restore_processes(states: dict[int, bool]) -> dict[int, bool]:
    raise UnsupportedPlatformError("audio")
