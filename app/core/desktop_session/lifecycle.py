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
        OkNteConfig,
        OkwwConfig,
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
    # MFW 托管按确切类型认（不靠继承：M9A、MSS 以后不再继承 MaaFWConfig）
    from app.task.MaaFW.registration import MAAFW_FAMILY_TYPES

    if type(config) in MAAFW_FAMILY_TYPES:
        from app.task.game import game_is_emulator
        from app.task.MaaFW.blocks.maafw_interface.interface.service import (
            MaaFWInterfaceService,
        )
        from app.task.MaaFW.blocks.maafw_interface.runner.run_plan import (
            _select_controller,
            resolve_run_selection,
        )
        from app.task.MaaFW.blocks.maafw_project_update.host.embedded_project import (
            resolve_maafw_project_root,
        )

        try:
            interface = MaaFWInterfaceService().load(
                resolve_maafw_project_root(str(config.uid), config)
            )
            name, _ = resolve_run_selection(
                interface,
                configured_controller=str(config.Info.Controller),
                emulator_selected=game_is_emulator(config),
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
        self.scope_state: tuple[int | None, bool] = (None, False)

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
            )

            def parent_scope() -> int | None:
                # 断开预览后，Windows 仍可保留子会话和其中运行的程序。
                try:
                    return parent_session if child_session() is not None else None
                except OSError:
                    return parent_session

            configure_parent_scope(parent_scope)

    def set_process_scope(self, *, session_id: int | None, connecting: bool) -> None:
        self.scope_state = (session_id, connecting)

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

    async def dispatch_queues(
        self,
        queue_ids: list[UUID],
        *,
        preview_only: bool,
        main_session_queue_ids: set[UUID],
    ) -> list[dict[str, str]]:
        """预览运行位置，或按确认的会话派发所选队列和托管。"""
        from app.core import Config, TaskManager
        from app.core.task_manager import UnsupportedDesktopTask, script_config_name
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
            session_id, connecting = self.scope_state
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
            if not preview_only:
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
                    "label": queue.Info.Name
                    if queue is not None
                    else script_config_name(script)
                    if script is not None
                    else str(uid),
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
                    if preview_only:
                        entries = (
                            [
                                Config.ScriptConfig.get(row.Info.ScriptId)
                                for row in queue.QueueItem.values()
                                if row.Info.ScriptId != "-"
                                # 所属插件不可用的托管运行时会被跳过，预检同样不算它。
                                and not Config.ScriptConfig.is_unresolved(
                                    row.Info.ScriptId
                                )
                            ]
                            if queue is not None
                            else [script]
                        )
                        if any(entry is None for entry in entries):
                            item["code"] = "dispatch_failed"
                        elif any(not supports_task(entry) for entry in entries):
                            item["code"] = "unsupported_target"
                        continue
                    node = (
                        {"uid": str(uid)}
                        if queue is not None
                        else {"uid": "-", "children": {0: {"uid": str(uid)}}}
                    )
                    in_main_session = uid in main_session_queue_ids
                    scope = desktop_process_target.set(
                        None if in_main_session else desktop
                    )
                    try:
                        task_id = await TaskManager.start(
                            TaskMode.AUTO_PROXY, {0: node}
                        )
                    finally:
                        desktop_process_target.reset(scope)
                    if not in_main_session:
                        self.task_ids.add(task_id)
                    item["taskId"] = str(task_id)
                except UnsupportedDesktopTask:
                    item["code"] = "unsupported_target"
                except (RuntimeError, ValueError) as exc:
                    logger.warning(f"任务 {uid} 派发失败: {exc}")
                    item["code"] = "dispatch_failed"
        return results


DesktopSessionLifecycle = _DesktopSessionLifecycle()
