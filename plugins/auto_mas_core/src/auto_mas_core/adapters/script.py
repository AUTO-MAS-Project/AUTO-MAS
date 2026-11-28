from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from app.models.config.script import DesktopSessionRunFields
from app.plugin.base.script import (
    DesktopSessionCheckReason,
    DesktopSessionProbe,
    FirstAccountMode,
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

if TYPE_CHECKING:
    from app.utils.common.process.session import DesktopProcessTarget


def in_desktop_session() -> bool:
    """当前任务是否需要通过分身进程句柄管理启动与停止。"""
    from app.utils.common.process.session import desktop_process_target

    return desktop_process_target.get() is not None


def current_desktop_target() -> "DesktopProcessTarget | None":
    """当前任务所在的桌面分身目标；主会话里返回 None。"""
    from app.utils.common.process.session import desktop_process_target

    return desktop_process_target.get()


async def request_desktop_action(
    desktop: "DesktopProcessTarget",
    action: str,
    arguments: dict[str, str | bool | float | None],
    *,
    on_log: Callable[[str], None] | None = None,
    on_restart: Callable[[], Awaitable[None]] | None = None,
) -> tuple[int, Any]:
    """在分身进程里执行一个动作，返回 (退出码, 结果)。

    动作名由宿主提供（如 list_windows、window_in_session）或由专项插件在自己的
    ``desktop_actions`` 模块里实现。Python 编排仍留在主会话，只有需要操作分身
    窗口的动作经这里送进去执行。
    """
    from app.task.desktop_session_worker import (
        request_desktop_action as _request_desktop_action,
    )

    return await _request_desktop_action(
        desktop, action, arguments, on_log=on_log, on_restart=on_restart
    )


__all__ = [
    "current_desktop_target",
    "in_desktop_session",
    "request_desktop_action",
    "DesktopSessionCheckReason",
    "DesktopSessionProbe",
    "DesktopSessionRunFields",
    "FirstAccountMode",
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
