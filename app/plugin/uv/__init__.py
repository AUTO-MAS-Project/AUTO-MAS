"""uv 工具链：查找、镜像、装卸包；升版预检见 ``precheck``。

市场刷新只读索引 JSON，不再经本包装元数据。
"""

from __future__ import annotations

from .ops import candidates, ensure, install, mark_ok, site_dir, uninstall
from .precheck import CoreCompat, check_core, precheck_core_bump

__all__ = [
    "CoreCompat",
    "candidates",
    "check_core",
    "ensure",
    "install",
    "mark_ok",
    "precheck_core_bump",
    "site_dir",
    "uninstall",
]
