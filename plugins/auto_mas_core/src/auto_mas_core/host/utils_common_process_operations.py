"""真实宿主模块 app.utils.common.process.operations 的 SDK 导出：只开放 ``__all__`` 列出的名字。"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

__all__ = [
    "iter_process_info",
    "iter_processes",
    "managed_process",
    "terminate_process",
]

if TYPE_CHECKING:
    from app.utils.common.process.operations import (
        iter_process_info as iter_process_info,
    )
    from app.utils.common.process.operations import iter_processes as iter_processes
    from app.utils.common.process.operations import managed_process as managed_process
    from app.utils.common.process.operations import (
        terminate_process as terminate_process,
    )
else:

    def __getattr__(name: str) -> Any:
        """按需从宿主 app.utils.common.process.operations 取得已开放的同名能力；其余名字不对插件承诺。"""
        if name not in __all__:
            raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
        return getattr(import_module("app.utils.common.process.operations"), name)
