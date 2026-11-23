"""主 MAS 的桌面分身调度和进程范围。"""

import asyncio
import os
from collections.abc import Callable
from dataclasses import dataclass
from hmac import compare_digest
from time import monotonic
from typing import TYPE_CHECKING, Literal
from uuid import UUID

if TYPE_CHECKING:
    from app.models.schema import TaskSelectionNode
    from app.utils.common.process.session import DesktopProcessTarget


CONTROL_TOKEN = "AUTO_MAS_DESKTOP_CONTROL_TOKEN"
PARENT_CHILD_SESSION = "AUTO_MAS_DESKTOP_PARENT_CHILD_SESSION"

_control_token = os.environ.pop(CONTROL_TOKEN, "")
_parent_child_session = os.environ.pop(PARENT_CHILD_SESSION, "")
CONTROL_HEADER = "x-mas-desktop-session"
# 覆盖停止任务、恢复宿主和注销等待；控制端失联后允许会话重新派发。
_CLOSE_RESERVATION_SECONDS = 180


def _support_probe(config: object) -> bool | Callable[[], bool]:
    """同步读取能力参数，按需构造只读取上游资源的检查。"""
    from app.models.config import (
        BetterGIConfig,
        GeneralConfig,
        HSRConfig,
        MaaEndConfig,
        MaaFWConfig,
        OkNteConfig,
        OkwwConfig,
        ZzzOdConfig,
    )
    from app.utils import IS_ELEVATED

    if isinstance(config, GeneralConfig):
        return not config.Game.Enabled or config.Game.Type != "Emulator"
    if isinstance(config, MaaEndConfig):
        from app.task.MaaEnd.resource_loader import load_maaend_controller_protocol

        path = config.Info.Path
        if path is None:
            return False
        controller = str(config.Game.ControllerType).strip()

        def check_maaend() -> bool:
            try:
                return load_maaend_controller_protocol(path, controller) == "Win32"
            except (OSError, KeyError, ValueError):
                return False

        return check_maaend
    if isinstance(config, MaaFWConfig):
        from app.task.MaaFW.tools.core.interface.service import MaaFWInterfaceService
        from app.task.MaaFW.tools.core.runner.run_plan import (
            _select_controller,
            resolve_run_selection,
        )
        from app.task.MaaFW.tools.embedded.embedded_project import (
            resolve_maafw_project_root,
        )

        root = resolve_maafw_project_root(str(config.uid), config)
        controller = str(config.Info.Controller)
        emulator_selected = config.Emulator.Id != "-"
        resource = str(config.Info.Resource)

        def check_maafw() -> bool:
            try:
                interface = MaaFWInterfaceService().load(root)
                name, _ = resolve_run_selection(
                    interface,
                    configured_controller=controller,
                    emulator_selected=emulator_selected,
                    configured_resource=resource,
                )
                return _select_controller(interface, name).type == "Win32"
            except (OSError, ValueError):
                return False

        return check_maafw
    if isinstance(config, (HSRConfig, OkNteConfig, OkwwConfig)):
        return True
    if isinstance(config, BetterGIConfig):
        return (
            not config.Run.UseAdmin or IS_ELEVATED
        ) and not config.Update.TakeoverEnabled
    return isinstance(config, ZzzOdConfig) and IS_ELEVATED


def supports_task(config: object) -> bool:
    """校验托管是否可在桌面分身执行。"""
    probe = _support_probe(config)
    return probe() if callable(probe) else probe


async def query_task_support(config: object) -> bool:
    """给详情查询复用同一能力判断，把资源 I/O 放在工作线程。"""
    probe = _support_probe(config)
    return await asyncio.to_thread(probe) if callable(probe) else probe


def authenticated(value: str | None) -> bool:
    return bool(
        _control_token
        and value
        and value.isascii()
        and compare_digest(_control_token, value)
    )


class DesktopSessionConflict(RuntimeError):
    """当前调度状态不允许该桌面分身操作。"""


class DesktopSessionDisconnected(DesktopSessionConflict):
    """连接桌面分身后可以重试本次任务。"""


@dataclass(frozen=True)
class _CloseReservation:
    session_id: int
    attempt_id: UUID
    expires_at: float


class _DesktopSessionLifecycle:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.task_ids: set[UUID] = set()
        self.admitted = 0
        self._close_reservation: _CloseReservation | None = None
        self._released_close_attempts: dict[tuple[int, UUID], float] = {}
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
        if session_id != self.scope_state[0]:
            self.admitted = 0
            self._close_reservation = None
        self.scope_state = (session_id, connecting)

    def prune_and_list_tasks(self) -> tuple[UUID, ...]:
        """丢弃已结束的分身任务登记，返回仍在运行的任务。"""

        from app.core import TaskManager

        self.task_ids.intersection_update(TaskManager.task_info)
        return tuple(self.task_ids)

    async def execution_state(self) -> tuple[bool, int]:
        async with self.lock:
            return not self.prune_and_list_tasks(), self.admitted

    def _current_close_reservation(self, now: float) -> _CloseReservation | None:
        reservation = self._close_reservation
        if reservation is not None and reservation.expires_at <= now:
            self._close_reservation = None
        return self._close_reservation

    async def close_status(
        self,
        session_id: int,
        mode: Literal["inspect", "idle", "confirmed", "release"],
        *,
        attempt_id: UUID | None = None,
    ) -> tuple[bool, bool | None, bool]:
        """检查关闭条件，允许关闭时锁住该会话的新任务入口。"""
        from app.utils.windows.desktop_session.inventory import has_unmanaged_processes
        from app.utils.windows.desktop_session.native import child_session

        async with self.lock:
            has_tasks = bool(self.prune_and_list_tasks())
            now = monotonic()
            reservation = self._current_close_reservation(now)
            self._released_close_attempts = {
                key: deadline
                for key, deadline in self._released_close_attempts.items()
                if deadline > now
            }
            if mode != "inspect":
                if attempt_id is None:
                    raise ValueError("关闭请求缺少操作标识")
                attempt = (session_id, attempt_id)
                owned = reservation is not None and attempt == (
                    reservation.session_id,
                    reservation.attempt_id,
                )
                if mode == "release":
                    # 释放可能比超时的请求更早到达，阻止迟到的同一次请求重新加锁。
                    self._released_close_attempts[attempt] = (
                        now + _CLOSE_RESERVATION_SECONDS
                    )
                    if owned:
                        self._close_reservation = None
                    return has_tasks, None, False
                if attempt in self._released_close_attempts or (
                    reservation is not None and not owned
                ):
                    return has_tasks, None, False
            try:
                matches = child_session() == session_id
            except OSError:
                matches = False
            if not matches:
                return has_tasks, None, False
            unmanaged = (
                None if mode == "confirmed" else has_unmanaged_processes(session_id)
            )
            reserved = mode == "confirmed" or (
                mode == "idle" and not has_tasks and unmanaged is False
            )
            if reserved and attempt_id is not None:
                self._close_reservation = _CloseReservation(
                    session_id, attempt_id, now + _CLOSE_RESERVATION_SECONDS
                )
            return has_tasks, unmanaged, reserved

    async def stop_tasks(self) -> bool:
        from app.core import TaskManager

        async with self.lock:
            await asyncio.gather(
                *(TaskManager.stop(uid) for uid in self.prune_and_list_tasks())
            )
            return not self.prune_and_list_tasks()

    def _connected_target(self) -> "DesktopProcessTarget":
        session_id, connecting = self.scope_state
        reservation = self._current_close_reservation(monotonic())
        if reservation is not None and reservation.session_id == session_id:
            raise DesktopSessionConflict("桌面分身正在关闭")
        if session_id is None or connecting:
            raise DesktopSessionDisconnected("桌面分身连接已断开")

        from app.core import Config
        from app.utils.common.process.session import DesktopProcessTarget
        from app.utils.windows.desktop_session.native import (
            child_session,
            session_state,
        )

        if child_session() != session_id or session_state(session_id) != 0:
            raise DesktopSessionDisconnected("桌面分身连接已断开")
        return DesktopProcessTarget(session_id, Config.source_path, Config.work_path)

    async def start_configured_script(self, node: "TaskSelectionNode") -> UUID | None:
        """仅在手动启动单个托管时按其设置选用桌面分身。"""
        if node.uid != "-" or len(node.children) != 1:
            return None

        from app.core import Config, TaskManager
        from app.models.config.script import DesktopSessionRunFields
        from app.models.task import TaskMode
        from app.utils.common.process.session import desktop_process_target

        async with self.lock:
            script = Config.ScriptConfig.get(node.children[0].uid)
            run = getattr(script, "Run", None)
            if (
                not isinstance(run, DesktopSessionRunFields)
                or run.ExecutionSession == "main"
            ):
                return None
            if not supports_task(script):
                raise DesktopSessionConflict("当前托管配置不支持桌面分身")

            target = self._connected_target()
            self.prune_and_list_tasks()
            token = desktop_process_target.set(target)
            try:
                task_id = await TaskManager.start(TaskMode.AUTO_PROXY, {0: node})
            finally:
                desktop_process_target.reset(token)
            self.task_ids.add(task_id)
            self.admitted += 1
            return task_id

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
        from app.utils.common.process.session import desktop_process_target
        from app.utils.contracts.power import PowerSignal

        logger = get_logger("桌面分身")
        results = []
        async with self.lock:
            desktop = self._connected_target()
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
                        self.admitted += 1
                    item["taskId"] = str(task_id)
                except UnsupportedDesktopTask:
                    item["code"] = "unsupported_target"
                except (RuntimeError, ValueError) as exc:
                    logger.warning(f"任务 {uid} 派发失败: {exc}")
                    item["code"] = "dispatch_failed"
        return results


DesktopSessionLifecycle = _DesktopSessionLifecycle()
