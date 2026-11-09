"""系统自启及定时唤醒工具契约，目标与运行参数由调用方提供。"""

from pathlib import Path
from typing import Protocol


class StartupManager(Protocol):
    supported: bool

    async def set_enabled(
        self,
        enabled: bool,
        *,
        executable: Path,
        name: str,
        description: str,
        arguments: str,
    ) -> None: ...

    async def is_enabled(self, *, name: str) -> bool: ...

    async def sync_wakeup(
        self,
        *,
        executable: Path,
        times: tuple[tuple[int, int, int], ...],
        name_prefix: str,
        description: str,
        arguments: str,
    ) -> None: ...
