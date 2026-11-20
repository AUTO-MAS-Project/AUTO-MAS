"""存量专项的客户端调用借用当前游戏插件，不再各自创建游戏进程管理器。"""

from pathlib import Path
from typing import Any

from app.models.config.game_binding import GameBindingOwner
from app.plugin.base.client import ClientControl
from app.task.game import current_game_session
from app.utils import ProcessManager


def client_executable_path(owner: GameBindingOwner) -> Path | None:
    """任务使用账号覆盖目标；管理接口在任务外读取配置中登记的目标。"""
    control = _bound_client(owner)
    return control.executable_path if control is not None else None


def client_launcher_path(owner: GameBindingOwner) -> Path | None:
    control = _bound_client(owner)
    return control.launcher_path if control is not None else None


def _bound_client(owner: GameBindingOwner) -> ClientControl | None:
    from app.core import Config

    session = current_game_session.get()
    if session is not None:
        return session.control if isinstance(session.control, ClientControl) else None
    uid = owner.game.game_id
    if uid == "-":
        parent = owner.parent.parent if owner.parent is not None else None
        if not isinstance(parent, GameBindingOwner):
            return None
        uid = parent.game.game_id
        if uid == "-":
            return None
    entry = Config.GameConfig.get(uid)
    return (
        entry._control
        if entry is not None and isinstance(entry._control, ClientControl)
        else None
    )


_METHODS = {
    "clear",
    "kill",
    "close",
    "is_running",
    "is_visible",
    "activate_window",
    "show_window",
    "hide_window",
    "minimize_window",
    "open_process",
    "open_protocol",
    "search_process",
}
_PROPERTIES = {"main_pid", "main_hwnd", "target_process"}


class ClientProcess(ProcessManager):
    """[兼容旧专项] 保留原过程调用面，所有本地游戏操作先核对当前票据。"""

    def __getattribute__(self, name: str) -> Any:
        if name in _METHODS:

            async def invoke(*args, **kwargs):
                session = current_game_session.get()
                if session is None:
                    raise RuntimeError("客户端操作不在托管执行会话内")
                if session.control is None:
                    # URL/云端由既有上游入口启动，没有可伪造的本地游戏可执行文件。
                    return await getattr(super(ClientProcess, self), name)(
                        *args, **kwargs
                    )
                if (
                    not isinstance(session.control, ClientControl)
                    or session.device_uid is None
                    or session.ticket is None
                ):
                    raise TypeError("当前目标不是本地游戏客户端")
                manager = session.control.checked_process(
                    session.device_uid, ticket=session.ticket
                )
                if name == "open_process":
                    return await session.control.start_process(
                        session.device_uid, *args, ticket=session.ticket, **kwargs
                    )
                if name == "search_process":
                    return await session.control.track_process(
                        session.device_uid, *args, ticket=session.ticket, **kwargs
                    )
                if name == "kill":
                    return await session.control.stop_process(
                        session.device_uid, ticket=session.ticket
                    )
                if name == "open_protocol":
                    return await session.control.start_protocol(
                        session.device_uid, *args, ticket=session.ticket, **kwargs
                    )
                return await getattr(manager, name)(*args, **kwargs)

            return invoke
        if name in _PROPERTIES:
            session = current_game_session.get()
            if (
                session is not None
                and isinstance(session.control, ClientControl)
                and session.device_uid is not None
                and session.ticket is not None
            ):
                return getattr(
                    session.control.checked_process(
                        session.device_uid, ticket=session.ticket
                    ),
                    name,
                )
        return super().__getattribute__(name)
