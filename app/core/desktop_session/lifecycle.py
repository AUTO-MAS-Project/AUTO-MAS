"""主 MAS 的桌面分身调度和进程范围。"""

import asyncio
import os
from hmac import compare_digest
from uuid import UUID

CONTROL_TOKEN = "AUTO_MAS_DESKTOP_CONTROL_TOKEN"
PARENT_CHILD_SESSION = "AUTO_MAS_DESKTOP_PARENT_CHILD_SESSION"

_control_token = os.environ.pop(CONTROL_TOKEN, "")
_parent_child_session = os.environ.pop(PARENT_CHILD_SESSION, "")
CONTROL_HEADER = "x-mas-desktop-session"


def supports_task(config: object) -> bool:
    """仅受理已接入子会话进程与设备入口的托管配置。"""
    from app.models.config import (
        BetterGIConfig,
        GeneralConfig,
        HSRConfig,
        MaaEndConfig,
        MaaFWConfig,
        OkNteConfig,
        OkwwConfig,
        WhimboxConfig,
        ZzzOdConfig,
    )
    from app.utils import IS_ELEVATED

    if isinstance(config, GeneralConfig):
        return not config.Game.Enabled or config.Game.Type != "Emulator"
    if isinstance(config, MaaEndConfig):
        from app.task.MaaEnd.resource_loader import load_maaend_controller_protocol

        if config.Info.Path is None:
            return False
        try:
            return (
                load_maaend_controller_protocol(
                    config.Info.Path, str(config.Game.ControllerType).strip()
                )
                == "Win32"
            )
        except (OSError, KeyError, ValueError):
            return False
    if isinstance(config, MaaFWConfig):
        from app.task.MaaFW.tools.core.interface.service import MaaFWInterfaceService
        from app.task.MaaFW.tools.core.runner.run_plan import (
            _select_controller,
            resolve_run_selection,
        )
        from app.task.MaaFW.tools.embedded.embedded_project import (
            resolve_maafw_project_root,
        )

        try:
            interface = MaaFWInterfaceService().load(
                resolve_maafw_project_root(str(config.uid), config)
            )
            name, _ = resolve_run_selection(
                interface,
                configured_controller=str(config.Info.Controller),
                emulator_selected=config.Emulator.Id != "-",
                configured_resource=str(config.Info.Resource),
            )
            return _select_controller(interface, name).type == "Win32"
        except (OSError, ValueError):
            return False
    if isinstance(config, (HSRConfig, OkNteConfig, OkwwConfig)):
        return True
    if isinstance(config, BetterGIConfig):
        return (
            not config.Run.UseAdmin or IS_ELEVATED
        ) and not config.Update.TakeoverEnabled
    if isinstance(config, WhimboxConfig):
        return not config.Run.UseAdmin or IS_ELEVATED
    return isinstance(config, ZzzOdConfig) and IS_ELEVATED


def authenticated(value: str | None) -> bool:
    return bool(
        _control_token
        and value
        and value.isascii()
        and compare_digest(_control_token, value)
    )


class DesktopSessionConflict(RuntimeError):
    """当前调度状态不允许该桌面分身操作。"""


class _DesktopSessionLifecycle:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.task_ids: set[UUID] = set()
        self.scope_state: tuple[int | None, bool, int | None] = (None, False, None)

    def configure_process_scope(self) -> None:
        from app.utils.common.process.session import configure_parent_scope

        if _control_token:
            from app.utils.windows.desktop_session.native import (
                child_session,
                process_session,
            )

            parent_session = process_session(os.getpid())
            self.scope_state = (
                int(_parent_child_session) if _parent_child_session else None,
                False,
                None,
            )

            def parent_scope() -> int | None:
                tracked_session, connecting, baseline_session = self.scope_state
                if tracked_session is None and not connecting:
                    return None
                try:
                    current = child_session()
                    if current is not None and (
                        current == tracked_session
                        or (connecting and current != baseline_session)
                    ):
                        return parent_session
                except OSError:
                    return parent_session
                return None

            configure_parent_scope(parent_scope)

    def set_process_scope(self, *, session_id: int | None, connecting: bool) -> None:
        from app.utils import get_logger
        from app.utils.windows.desktop_session.native import child_session

        baseline = None
        if connecting:
            try:
                baseline = child_session()
            except OSError as exc:
                get_logger("桌面分身").warning(f"连接前无法读取 Windows 子会话: {exc}")
        self.scope_state = (session_id, connecting, baseline)

    def prune_and_list_tasks(self) -> tuple[UUID, ...]:
        """丢弃已结束的分身任务登记，返回仍在运行的任务。"""

        from app.core import TaskManager

        self.task_ids.intersection_update(TaskManager.task_info)
        return tuple(self.task_ids)

    async def idle(self) -> bool:
        async with self.lock:
            return not self.prune_and_list_tasks()

    async def stop_tasks(self) -> bool:
        from app.core import TaskManager

        async with self.lock:
            await asyncio.gather(
                *(TaskManager.stop(uid) for uid in self.prune_and_list_tasks())
            )
            return not self.prune_and_list_tasks()

    async def start_queues(self, queue_ids: list[UUID]) -> list[dict[str, str]]:
        from app.core import Config, TaskManager
        from app.core.task_manager import UnsupportedDesktopTask
        from app.models.task import TaskMode
        from app.utils import get_logger
        from app.utils.common.process.session import (
            DesktopProcessTarget,
            desktop_process_target,
        )
        from app.utils.contracts.power import PowerSignal
        from app.utils.windows.desktop_session.native import (
            child_session,
            session_state,
        )

        logger = get_logger("桌面分身")
        results = []
        async with self.lock:
            session_id, connecting, _ = self.scope_state
            if (
                session_id is None
                or connecting
                or child_session() != session_id
                or session_state(session_id) != 0
            ):
                raise DesktopSessionConflict("桌面分身连接已断开")
            desktop = DesktopProcessTarget(
                session_id, Config.source_path, Config.work_path
            )
            self.prune_and_list_tasks()
            for uid in dict.fromkeys(queue_ids):
                queue = Config.QueueConfig.get(uid)
                script = Config.ScriptConfig.get(uid) if queue is None else None
                target = queue if queue is not None else script
                item = {
                    "queueId": str(uid),
                    "taskId": "",
                    "targetKind": "queue"
                    if queue is not None
                    else "script"
                    if script is not None
                    else "unknown",
                    "code": "",
                    "label": target.Info.Name if target is not None else str(uid),
                }
                results.append(item)
                if target is None:
                    item["code"] = "target_missing"
                    continue
                if (
                    queue is not None
                    and queue.Info.AfterAccomplish != PowerSignal.NO_ACTION
                ):
                    item["code"] = "power_action"
                    continue
                try:
                    node = (
                        {"uid": str(uid)}
                        if queue is not None
                        else {"uid": "-", "children": {0: {"uid": str(uid)}}}
                    )
                    scope = desktop_process_target.set(desktop)
                    try:
                        task_id = await TaskManager.start(
                            TaskMode.AUTO_PROXY, {0: node}
                        )
                    finally:
                        desktop_process_target.reset(scope)
                    self.task_ids.add(task_id)
                    item["taskId"] = str(task_id)
                except UnsupportedDesktopTask:
                    item["code"] = "unsupported_target"
                except (RuntimeError, ValueError) as exc:
                    logger.warning(f"任务 {uid} 派发失败: {exc}")
                    item["code"] = "dispatch_failed"
        return results


DesktopSessionLifecycle = _DesktopSessionLifecycle()
