from __future__ import annotations

from pathlib import Path
from typing import Any

from .installer import install_python_runtime
from .pool import MaaFWRuntimePool, RuntimeInstaller


class MaaFWRuntimePoolService:
    """宿主运行池入口，提供池实例与路由身份。"""

    def __init__(
        self,
        pool_root: str | Path | None = None,
        *,
        installer: RuntimeInstaller | None = install_python_runtime,
    ) -> None:
        root = pool_root or (Path.cwd() / "config" / "maafw_runtime_pool")
        self.pool = MaaFWRuntimePool(root, installer=installer)

    def storage_info(self) -> dict[str, Any]:
        return self.pool.storage_info()
