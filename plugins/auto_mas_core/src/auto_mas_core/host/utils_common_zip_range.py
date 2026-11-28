"""真实宿主模块 app.utils.common.zip_range 的 SDK 导出：只开放 ``__all__`` 列出的名字。"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

__all__ = [
    "HealSkip",
    "RangeHTTPReader",
    "RangeReadCancelled",
    "RangeSpeedGuard",
    "format_size",
    "rebuild_zip",
]

if TYPE_CHECKING:
    from app.utils.common.zip_range import HealSkip as HealSkip
    from app.utils.common.zip_range import RangeHTTPReader as RangeHTTPReader
    from app.utils.common.zip_range import RangeReadCancelled as RangeReadCancelled
    from app.utils.common.zip_range import RangeSpeedGuard as RangeSpeedGuard
    from app.utils.common.zip_range import format_size as format_size
    from app.utils.common.zip_range import rebuild_zip as rebuild_zip
else:

    def __getattr__(name: str) -> Any:
        """按需从宿主 app.utils.common.zip_range 取得已开放的同名能力；其余名字不对插件承诺。"""
        if name not in __all__:
            raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
        return getattr(import_module("app.utils.common.zip_range"), name)
