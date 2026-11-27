"""真实宿主模块 app.utils.windows.desktop_session.process_runner 的 SDK 导出：只开放 ``__all__`` 列出的名字。"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

__all__ = ["launch_desktop_process", "open_in_desktop", "run_desktop_action"]

if TYPE_CHECKING:
    from app.utils.windows.desktop_session.process_runner import (
        launch_desktop_process as launch_desktop_process,
    )
    from app.utils.windows.desktop_session.process_runner import (
        open_in_desktop as open_in_desktop,
    )
    from app.utils.windows.desktop_session.process_runner import (
        run_desktop_action as run_desktop_action,
    )
else:

    def __getattr__(name: str) -> Any:
        """按需从宿主 app.utils.windows.desktop_session.process_runner 取得已开放的同名能力；其余名字不对插件承诺。"""
        if name not in __all__:
            raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
        return getattr(
            import_module("app.utils.windows.desktop_session.process_runner"), name
        )
