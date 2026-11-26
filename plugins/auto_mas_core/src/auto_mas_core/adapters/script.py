from app.models.config.script import DesktopSessionRunFields
from app.plugin.base.script import (
    DesktopSessionCheckReason,
    ScriptAdapterPlugin,
    ScriptTypeDecl,
)
from app.task import (
    MODE_WORKERS,
    AutoProxyWorker,
    ModeWorker,
    ScriptConfigWorker,
    ScriptViewWorker,
    UserExpander,
)
from app.task.run_flow import (
    RunPoint,
    begin_attempt,
    game_update_result,
    observe_run,
    operation,
    point,
)
from app.task.user_expander import ScriptSkip


def in_desktop_session() -> bool:
    """当前任务是否需要通过分身进程句柄管理启动与停止。"""
    from app.utils.common.process.session import desktop_process_target

    return desktop_process_target.get() is not None


__all__ = [
    "in_desktop_session",
    "DesktopSessionCheckReason",
    "DesktopSessionRunFields",
    "MODE_WORKERS",
    "AutoProxyWorker",
    "ScriptViewWorker",
    "ModeWorker",
    "ScriptAdapterPlugin",
    "ScriptConfigWorker",
    "UserExpander",
    "ScriptSkip",
    "ScriptTypeDecl",
    "RunPoint",
    "begin_attempt",
    "game_update_result",
    "observe_run",
    "operation",
    "point",
]
