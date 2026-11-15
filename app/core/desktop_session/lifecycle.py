"""协调桌面分身数据交接的后端入口。"""

import asyncio
import os
from hmac import compare_digest
from uuid import UUID

from .ownership import (
    CONTROL_TOKEN,
    EXECUTOR_SESSION,
    EXECUTOR_TOKEN,
    PARENT_CHILD_SESSION,
)

# 普通 API 和上下游进程不需要知道控制凭据。
_control_token = os.environ.pop(CONTROL_TOKEN, "")
_executor_token = os.environ.pop(EXECUTOR_TOKEN, "")
_executor_session = os.environ.pop(EXECUTOR_SESSION, "")
_parent_child_session = os.environ.pop(PARENT_CHILD_SESSION, "")
_handoff = False
_commands_inflight = 0
CONTROL_HEADER = "x-mas-desktop-session"


def executor_session() -> int | None:
    return int(_executor_session) if _executor_session else None


def admit_command() -> bool:
    """跟踪绕过 HTTP 中间件执行的调度命令。"""
    global _commands_inflight
    if _executor_session or _handoff:
        return False
    _commands_inflight += 1
    return True


def release_command() -> None:
    global _commands_inflight
    _commands_inflight -= 1


def authenticated(value: str | None) -> bool:
    expected = _executor_token if _executor_session else _control_token
    return bool(
        expected and value and value.isascii() and compare_digest(expected, value)
    )


class DesktopSessionConflict(RuntimeError):
    """当前调度状态不允许该桌面分身操作。"""


class _DesktopSessionLifecycle:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.draining = False
        self.inflight = 0
        self.scope_state: tuple[int | None, bool, int | None] = (None, False, None)

    @property
    def is_child(self) -> bool:
        return bool(_executor_session)

    @property
    def handed_off(self) -> bool:
        return _handoff

    def configure_process_scope(self) -> None:
        from app.utils.common.process.session import configure_parent_scope

        if _control_token and not _executor_session:
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

    async def handoff(self, *, background_ready: bool) -> None:
        from app.core import Power, ShutdownCoordinator, TaskManager

        global _handoff
        async with self.lock:
            if (
                self.draining
                or self.inflight
                or _commands_inflight
                or not TaskManager.idle
                or Power.power_task is not None
            ):
                raise DesktopSessionConflict("主会话有任务、更新或配置操作正在运行")
            if not background_ready:
                raise DesktopSessionConflict("主会话尚未完成后台初始化")
            self.draining = True
            _handoff = True
            TaskManager.pause_admission()
            await ShutdownCoordinator.run_teardown()
            # Runtime 在关闭指令前会把自行退出的后端重新拉起。

    async def start_queues(self, queue_ids: list[UUID]) -> list[dict[str, str]]:
        from app.core import Config, TaskManager
        from app.models.task import TaskMode
        from app.utils import get_logger
        from app.utils.contracts.power import PowerSignal
        from app.utils.windows.desktop_session.native import session_state

        logger = get_logger("桌面分身")
        results = []
        async with self.lock:
            if self.draining:
                raise DesktopSessionConflict("桌面分身正在关闭")
            if session_state(int(_executor_session)) != 0:
                raise DesktopSessionConflict("桌面分身连接已断开")
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
                    task_id = await TaskManager.start(TaskMode.AUTO_PROXY, {0: node})
                    item["taskId"] = str(task_id)
                except (RuntimeError, ValueError) as exc:
                    logger.warning(f"任务 {uid} 派发失败: {exc}")
                    item["code"] = "dispatch_failed"
        return results

    async def exit_executor(self) -> None:
        from app.core import Config, ShutdownCoordinator, TaskManager

        async with self.lock:
            self.draining = True
            TaskManager.pause_admission()
            await ShutdownCoordinator.run_teardown()
            Config.server.should_exit = True


DesktopSessionLifecycle = _DesktopSessionLifecycle()
