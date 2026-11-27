"""真实宿主模块 app.task.run_flow 的 SDK 导出：只开放 ``__all__`` 列出的名字。"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

__all__ = [
    "PointState",
    "RunPoint",
    "RunStage",
    "begin_attempt",
    "game_update_result",
    "observe_run",
    "operation",
    "point",
]

if TYPE_CHECKING:
    from app.task.run_flow import PointState as PointState
    from app.task.run_flow import RunPoint as RunPoint
    from app.task.run_flow import RunStage as RunStage
    from app.task.run_flow import begin_attempt as begin_attempt
    from app.task.run_flow import game_update_result as game_update_result
    from app.task.run_flow import observe_run as observe_run
    from app.task.run_flow import operation as operation
    from app.task.run_flow import point as point
else:

    def __getattr__(name: str) -> Any:
        """按需从宿主 app.task.run_flow 取得已开放的同名能力；其余名字不对插件承诺。"""
        if name not in __all__:
            raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
        return getattr(import_module("app.task.run_flow"), name)
