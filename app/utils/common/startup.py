"""不支持的平台保留自启及唤醒接口，调用方负责能力判断。"""

from pathlib import Path

from app.utils import UnsupportedPlatformError

supported = False


async def set_enabled(
    enabled: bool, *, executable: Path, name: str, description: str, arguments: str
) -> None:
    raise UnsupportedPlatformError("startup")


async def is_enabled(*, name: str) -> bool:
    raise UnsupportedPlatformError("startup")


async def sync_wakeup(
    *,
    executable: Path,
    times: tuple[tuple[int, int, int], ...],
    name_prefix: str,
    description: str,
    arguments: str,
) -> None:
    raise UnsupportedPlatformError("startup")
