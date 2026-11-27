"""真实宿主模块 app.task.client 的 SDK 导出：只开放 ``__all__`` 列出的名字。"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

__all__ = ["ClientProcess", "client_executable_path", "client_launcher_path"]

if TYPE_CHECKING:
    from app.task.client import ClientProcess as ClientProcess
    from app.task.client import client_executable_path as client_executable_path
    from app.task.client import client_launcher_path as client_launcher_path
else:

    def __getattr__(name: str) -> Any:
        """按需从宿主 app.task.client 取得已开放的同名能力；其余名字不对插件承诺。"""
        if name not in __all__:
            raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
        return getattr(import_module("app.task.client"), name)
