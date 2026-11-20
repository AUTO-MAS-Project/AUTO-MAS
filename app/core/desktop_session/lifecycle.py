"""主 MAS 的桌面分身调度和进程范围。"""

import asyncio
import os
from collections.abc import Awaitable, Callable
from hashlib import sha256
from hmac import compare_digest
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from app.models.schema import TaskSelectionNode
    from app.utils.common.process.session import DesktopProcessTarget

from app.plugin.errors import PluginPrecheckError

CONTROL_TOKEN = "AUTO_MAS_DESKTOP_CONTROL_TOKEN"
PARENT_CHILD_SESSION = "AUTO_MAS_DESKTOP_PARENT_CHILD_SESSION"

_control_token = os.environ.pop(CONTROL_TOKEN, "")
_parent_child_session = os.environ.pop(PARENT_CHILD_SESSION, "")
CONTROL_HEADER = "x-mas-desktop-session"


def supports_task(config: object) -> bool:
    """仅受理已接入子会话进程与设备入口的托管配置。"""
    return not _task_dispatch_code(config)


def _task_dispatch_code(config: object) -> str:
    from app.core import Config
    from app.models.config import (
        BAAHConfig,
        BetterGIConfig,
        GeneralConfig,
        HSRConfig,
        M9AConfig,
        MaaEndConfig,
        MaaFWConfig,
        OkNteConfig,
        OkwwConfig,
        ZzzOdConfig,
    )
    from app.models.config.game_binding import GameBindingOwner
    from app.utils import IS_ELEVATED

    if isinstance(config, (M9AConfig, BAAHConfig)):
        return "emulator_required"
    if isinstance(config, GeneralConfig):
        return (
            "emulator_required"
            if config.Game.Enabled and config.Game.Type == "Emulator"
            else ""
        )
    if isinstance(config, (HSRConfig, OkNteConfig, OkwwConfig)):
        return ""
    if isinstance(config, GameBindingOwner):
        # 从宿主登记识别专项，兼容尚未绑定模拟器的旧版托管。
        classes = Config.script_classes
        if type(config) in (classes.get(key) for key in ("MAA", "M9A", "SRC", "BAAH")):
            return "emulator_required"
        if config.game.game_id != "-":
            target = Config.GameConfig.get(config.game.game_id)
            if target is not None and target.info.type == "emulator":
                return "emulator_required"
    if isinstance(config, MaaEndConfig):
        from app.task.MaaEnd.resource_loader import load_maaend_controller_protocol

        if config.Info.Path is None:
            return "unsupported_target"
        try:
            controller = load_maaend_controller_protocol(
                config.Info.Path, str(config.Game.ControllerType).strip()
            )
        except (OSError, KeyError, ValueError):
            return "unsupported_target"
        return "" if controller == "Win32" else "emulator_required"
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
            controller = _select_controller(interface, name).type
        except (OSError, ValueError):
            return "unsupported_target"
        if controller == "Win32":
            return ""
        if controller == "Adb":
            return "emulator_required"
    if isinstance(config, BetterGIConfig):
        if (
            not config.Run.UseAdmin or IS_ELEVATED
        ) and not config.Update.TakeoverEnabled:
            return ""
    if isinstance(config, ZzzOdConfig) and IS_ELEVATED:
        return ""
    return "unsupported_target"


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
        self.closing_preview = False

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

    @staticmethod
    def _preview_owner_file() -> Path:
        from app.core import Config

        return Config.debug_path / "desktop-session" / "preview-owner"

    def reserve_preview(self) -> None:
        from app.utils.common.io import atomic_write

        # Runtime 可以就地重启后端。用当前 Electron 启动的标识恢复预览占用。
        atomic_write(
            self._preview_owner_file(), sha256(_control_token.encode()).digest()
        )

    def release_preview(self) -> None:
        self._preview_owner_file().unlink(missing_ok=True)

    def assert_preview_closed(self) -> None:
        """停止或替换插件前，预览必须先停止任务并结束原生宿主。"""
        if not _control_token:
            return
        try:
            owner = self._preview_owner_file().read_bytes()
        except FileNotFoundError:
            return
        except OSError as exc:
            raise PluginPrecheckError("无法确认桌面分身预览已关闭") from exc
        if owner == sha256(_control_token.encode()).digest():
            raise PluginPrecheckError("请先关闭桌面分身预览窗口")

    async def set_process_scope(
        self, *, session_id: int | None, connecting: bool
    ) -> None:
        async with self.lock:
            self.scope_state = (session_id, connecting)

    def _connected_target(self) -> "DesktopProcessTarget":
        from app.core import Config
        from app.utils.common.process.session import DesktopProcessTarget
        from app.utils.windows.desktop_session.native import (
            child_session,
            session_state,
        )

        session_id, connecting = self.scope_state
        if (
            self.closing_preview
            or session_id is None
            or connecting
            or child_session() != session_id
            or session_state(session_id) != 0
        ):
            raise DesktopSessionConflict("桌面分身不可用，请先打开并连接桌面分身")
        return DesktopProcessTarget(session_id, Config.source_path, Config.work_path)

    async def start_configured_script(
        self, root: "TaskSelectionNode", launch: Callable[[], Awaitable[UUID]]
    ) -> UUID | None:
        from app.core import Config, Plugin
        from app.models.config.script import DesktopSessionRunFields
        from app.utils.common.process.session import desktop_process_target

        if root.uid != "-" or len(root.children) != 1:
            return None
        try:
            script_id = UUID(root.children[0].uid)
        except ValueError:
            return None  # 交给调度入口报告无效的要求树。

        async with self.lock:
            script = Config.ScriptConfig.get(script_id)
            run = getattr(script, "Run", None)
            if (
                not isinstance(run, DesktopSessionRunFields)
                or run.ExecutionSession == "main"
            ):
                return None
            if not supports_task(script):
                raise DesktopSessionConflict(
                    "此托管当前无法在桌面分身运行，请检查托管设置"
                )
            if (
                not _control_token
                or Plugin.services.get("desktop_session.launcher") is None
            ):
                raise DesktopSessionConflict("请先启用桌面分身插件，并打开分身预览")
            token = desktop_process_target.set(self._connected_target())
            try:
                task_id = await launch()
                self.task_ids.add(task_id)
                return task_id
            finally:
                desktop_process_target.reset(token)

    async def set_preview_closing(self, *, closing: bool) -> bool:
        async with self.lock:
            self.closing_preview = closing
            return not self.prune_and_list_tasks()

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
        from app.utils.common.process.session import desktop_process_target
        from app.utils.contracts.power import PowerSignal

        logger = get_logger("桌面分身")
        results = []
        async with self.lock:
            desktop = None
            if not preview_only:
                desktop = self._connected_target()
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
                    in_main_session = uid in main_session_queue_ids
                    if preview_only or in_main_session:
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
                            continue
                        codes = {_task_dispatch_code(entry) for entry in entries}
                        if preview_only:
                            if "emulator_required" in codes:
                                item["code"] = "emulator_required"
                            elif "unsupported_target" in codes:
                                item["code"] = "unsupported_target"
                            continue
                        if "emulator_required" not in codes:
                            item["code"] = "dispatch_failed"
                            continue
                    node = (
                        {"uid": str(uid)}
                        if queue is not None
                        else {"uid": "-", "children": {0: {"uid": str(uid)}}}
                    )
                    scope = desktop_process_target.set(
                        None if in_main_session else desktop
                    )
                    try:
                        task_id = await TaskManager.start(
                            TaskMode.AUTO_PROXY, {0: node}, use_configured_session=False
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
