from __future__ import annotations

import asyncio
import json
import os
import queue
import re
import shlex
import subprocess
import threading
import uuid
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

import psutil

from app.core import Config
from app.core.ws import Publisher, protocol
from app.models.schema import WSTaskNoticeData
from app.models.emulator import DeviceBase, DeviceInfo
from app.models.task import LogRecord, ScriptItem, TaskExecuteBase
from app.services import Notify
from app.task.general.tools import execute_script_task
from app.utils import ProcessInfo, ProcessManager, get_logger
from app.utils.constants import UTC4
from app.task.MaaFW.tools.core.automas_maafw_controller_win32.service import (
    MaaFWWin32ControllerService,
)
from app.task.MaaFW.tools.core.automas_maafw_interface.models import MaaFWController, MaaFWInterface
from app.task.MaaFW.tools.core.automas_maafw_interface.preview import build_adb_emulator_extra_capabilities
from app.task.MaaFW.tools.core.automas_maafw_interface.service import MaaFWInterfaceService
from app.task.MaaFW.tools.core.automas_maafw_runner.models import (
    MaaFWDeviceConfig,
    MaaFWRunPlan,
    MaaFWRunResult,
    MaaFWSkippedTaskPlan,
)
from app.task.MaaFW.tools.core.automas_maafw_runner.run_plan import MaaFWRunPlanError
from app.task.MaaFW.tools.core.automas_maafw_runner.service import MaaFWRunnerService

from .project_path import release_project_path, try_reserve_project_path
from .runtime_route import MaaFWManagedExecutionRoute, managed_execution_route


logger = get_logger("MaaFW 插件自动代理")


# MaaFW 的 ADB 截图/输入方法枚举（EmulatorExtras 硬件加速相关）在此镜像为整型常量，
# 而非 `from maa.controller import MaaAdb*Enum`。本模块受导入边界约束
# （tests/plugins/test_maafw_import_boundaries.py 禁止导入时把 maa 载入 sys.modules），
# 直接 import maa 会加载原生绑定，故改为对齐 plugins/pypi/site-packages/maa/define.py
# 的取值：
#   screencap Default = All & ~RawByNetcat & ~MinicapDirect & ~MinicapStream = -57
#   screencap EmulatorExtras = 1 << 6 (64)
#   input Default = All & ~EmulatorExtras = -9；input All = ~0 = -1；EmulatorExtras = 1 << 3 (8)
_ADB_SCREENCAP_DEFAULT = -57
_ADB_SCREENCAP_EMULATOR_EXTRAS = 1 << 6
_ADB_INPUT_DEFAULT = -9
_ADB_INPUT_ALL = -1
_ADB_INPUT_EMULATOR_EXTRAS = 1 << 3
_WIN32_SCREENCAP_METHODS = {
    "GDI": 1,
    "FramePool": 1 << 1,
    "DXGI_DesktopDup": 1 << 2,
    "DXGI_DesktopDup_Window": 1 << 3,
    "PrintWindow": 1 << 4,
    "ScreenDC": 1 << 5,
}
_WIN32_INPUT_METHODS = {
    "Seize": 1,
    "SendMessage": 1 << 1,
    "PostMessage": 1 << 2,
    "LegacyEvent": 1 << 3,
    "PostThreadMessage": 1 << 4,
    "SendMessageWithCursorPos": 1 << 5,
    "PostMessageWithCursorPos": 1 << 6,
    "SendMessageWithWindowPos": 1 << 7,
    "PostMessageWithWindowPos": 1 << 8,
}
_SUBPROCESS_OUTPUT_ENCODINGS = ("utf-8", "gbk", "shift_jis", "utf-16")
_RUN_OVERVIEW_LOG_VALUE_LIMIT = 1200
_FRAMEWORK_UI_LOG_MAX_CHARS = 1200
# worker 输出转发每处理这么多行就让出一次事件循环。取 50 是因为原生诊断
# 的洪峰约每秒几十行，这个粒度下让出频率约每秒一次，开销可忽略。
_RELAY_YIELD_EVERY_LINES = 50
# 启动/附着游戏后定位其窗口的等待秒数
WINDOW_SEARCH_TIMEOUT_SECONDS = 5.0
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
_VERBOSE_FRAMEWORK_LOG_MARKERS = (
    "Transceiver::send] send canceled",
    "Transceiver::send_and_recv] failed to send req",
    "AgentClient::connect] failed to send_and_recv",
    "after convert, x_point:",
)
_NATIVE_FRAMEWORK_LOG_MARKERS = (
    "MaaNS::",
    "PipelineParser.cpp",
    "Context.cpp",
    "Tasker.cpp",
    "Node.cpp",
    "Transceiver.cpp",
    "AgentClient.cpp",
)
_FRAMEWORK_DEBUG_PAYLOAD_MARKERS = (
    "override_pipeline",
    "task_ptr->entry()",
    '"expected":',
    '"pipeline_override":',
)

_RAW_FAILURE_UI_LOG_MARKERS = (
    "任务失败，将继续后续任务:",
    "MaaFW 任务执行失败:",
    "[MaaFW Tasker] 失败:",
    "任务执行失败: <entry=",
)
_NATIVE_FRAMEWORK_STATUS_RE = re.compile(
    r"(?:\*\*)?\[\d{4}-\d{2}-\d{2}[^\]]*\]\[(?:ERR|WARN|INFO|DEBUG)\]",
    re.IGNORECASE,
)
_FRAMEWORK_COORDINATE_RE = re.compile(
    r"(?:^|\]\s*)x:\s*-?\d+,\s*y:\s*-?\d+,\s*width:\s*\d+,\s*height:\s*\d+",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class MaaFWAdbControlProfile:
    """描述某模拟器实例的 ADB EmulatorExtras 能力与 controller extras 配置。"""

    emulator_type: str | None
    screencap_extra: bool
    input_extra: bool
    config: dict[str, Any]


class _FrameworkLogWriter:
    """在专用线程中按提交顺序写入一次运行的框架日志。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._queue: queue.Queue[tuple[str, str, str] | None] = queue.Queue()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._open_error: Exception | None = None
        self._write_error: Exception | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run,
            name="maafw-framework-log-writer",
            daemon=True,
        )
        self._thread.start()
        self._ready.wait()
        if self._open_error is not None:
            self.close()
            raise self._open_error

    def write(self, source: str, message: str) -> None:
        if self._thread is None:
            return
        timestamp = datetime.now().astimezone().strftime("%H:%M:%S.%f")[:-3]
        try:
            self._queue.put((timestamp, source, str(message or "")))
        except Exception:
            return

    def close(self) -> None:
        thread = self._thread
        if thread is None:
            return
        self._queue.join()
        self._queue.put(None)
        thread.join()
        self._thread = None
        if self._write_error is not None:
            raise RuntimeError(
                f"MaaFW 框架日志写入不完整: {self._write_error}"
            ) from self._write_error

    def _run(self) -> None:
        log_file: Any | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            log_file = self.path.open(
                "a",
                encoding="utf-8",
                buffering=1,
            )
        except Exception as exc:
            self._open_error = exc
            self._ready.set()
            return

        self._ready.set()
        try:
            while True:
                item = self._queue.get()
                try:
                    if item is None:
                        return
                    timestamp, source, message = item
                    cleaned = _clean_framework_output(message)
                    for line in cleaned.splitlines() or [""]:
                        try:
                            log_file.write(f"[{timestamp}] [{source}] {line}\n")
                        except Exception as exc:
                            if self._write_error is None:
                                self._write_error = exc
                            continue
                except Exception as exc:
                    if self._write_error is None:
                        self._write_error = exc
                finally:
                    self._queue.task_done()
        finally:
            try:
                log_file.close()
            except Exception as exc:
                if self._write_error is None:
                    self._write_error = exc


class MaaFWPluginAutoProxyTask(TaskExecuteBase):
    """MaaFW 插件版 AutoProxy 执行器。"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: Any,
        user_config: Mapping[uuid.UUID, Any],
        emulator_manager: DeviceBase | None,
        project_update_logs: list[str] | None = None,
    ):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config
        self.emulator_manager = emulator_manager
        self.project_update_logs = list(project_update_logs or [])
        self.cur_user_item = self.script_info.user_list[self.script_info.current_index]
        self.cur_user_uid = uuid.UUID(self.cur_user_item.user_id)
        self.cur_user_config = self.user_config[self.cur_user_uid]
        self.project_path = Path(self.script_config.get("Info", "Path")).resolve()
        self.interface_model: MaaFWInterface | None = None
        self.base_run_plan: MaaFWRunPlan | None = None
        self.run_plan: MaaFWRunPlan | None = None
        self.cur_user_log: LogRecord | None = None
        self.cur_user_log_started_at: datetime | None = None
        self.check_result = "-"
        self.curdate = datetime.now(tz=UTC4).strftime("%Y-%m-%d")
        self.run_complete = False
        self.opened_emulator = False
        self.opened_game = False
        self.game_process_manager = ProcessManager()
        self.project_lock_key: str | None = None
        self.runner_process: asyncio.subprocess.Process | None = None
        self.pretask_process: asyncio.subprocess.Process | None = None
        self._cached_adb_address: str | None = None
        self._cached_device_info: DeviceInfo | None = None
        self._cached_adb_path: str | None = None
        self._cached_adb_profile: MaaFWAdbControlProfile | None = None
        self.maafw_runtime_pool_root: Path | None = None
        self.maafw_runtime_pool_id: str | None = None
        self.maafw_managed_execution = False
        self.maafw_managed_project: Mapping[str, Any] | None = None
        self.maafw_managed_runtime_binding: Mapping[str, Any] | None = None
        self.maafw_managed_route: MaaFWManagedExecutionRoute | None = None

    async def check(self) -> str:
        proxy_times = (
            self.cur_user_config.get("Data", "ProxyTimes")
            if self.cur_user_config.get("Data", "LastProxyDate") == self.curdate
            else 0
        )
        if (
            self.script_config.get("Run", "ProxyTimesLimit") != 0
            and proxy_times >= self.script_config.get("Run", "ProxyTimesLimit")
        ):
            self.cur_user_item.status = "跳过"
            return "今日代理次数已达上限，跳过该用户"

        if not await self._try_enter_project_path():
            self.cur_user_item.status = "跳过"
            return "同一路径 MaaFW 脚本正在运行或更新，已跳过本次启动"

        keep_reservation = False
        try:
            try:
                (
                    self.interface_model,
                    self.base_run_plan,
                    self.run_plan,
                    game_path_error,
                ) = await asyncio.to_thread(
                    self._load_run_state_for_check,
                )
            except Exception as exc:
                self.cur_user_item.status = "异常"
                return f"无法构建 MaaFW 运行计划，请检查项目和任务配置: {exc}"

            if not self.run_plan.tasks:
                self.cur_user_item.status = "跳过"
                return "MaaFW 周期任务已在本周或本月完成，跳过本次运行"

            if self.run_plan.controllerType == "Adb":
                emulator_id = self.script_config.get("Emulator", "Id")
                emulator_index = self.script_config.get("Emulator", "Index")
                if emulator_id == "-" or emulator_index in ("", "-"):
                    self.cur_user_item.status = "异常"
                    return "当前 MaaFW controller 需要 ADB，请在脚本管理页选择模拟器和实例"
            elif game_path_error is not None:
                self.cur_user_item.status = "异常"
                return game_path_error

            keep_reservation = True
            return "Pass"
        finally:
            if not keep_reservation:
                await self._release_project_path()

    async def prepare(self) -> None:
        start_time = datetime.now()
        self.cur_user_log_started_at = start_time
        self.cur_user_item.log_record[start_time] = self.cur_user_log = LogRecord()
        if self.project_update_logs:
            self.cur_user_log.content.extend(self.project_update_logs)
            self.script_info.log = "".join(self.cur_user_log.content[-80:])

    async def main_task(self) -> None:
        self.curdate = datetime.now(tz=UTC4).strftime("%Y-%m-%d")
        self.check_result = await self.check()
        if self.check_result != "Pass":
            if self.cur_user_item.status == "异常":
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="error",
                        message=(
                            f"用户 {self.cur_user_item.name} 检查未通过: "
                            f"{self.check_result}"
                        ),
                    ),
                )
            self.script_info.log = self.check_result
            return

        await self._mark_run_started()
        await self.prepare()
        self.cur_user_item.status = "运行"
        logger.info(f"开始代理 MaaFW 用户: {self.cur_user_uid}")
        if self.run_plan is not None:
            selected_preset = str(
                self.cur_user_config.get("Task", "SelectedPreset") or ""
            ).strip()
            self._append_log(
                _format_run_overview_log(
                    self.run_plan,
                    selected_preset=selected_preset,
                )
            )

        try:
            await self._run_pretasks()
            for index in range(self.script_config.get("Run", "RunTimesLimit")):
                if self.run_complete:
                    break

                self._append_log(
                    f"用户 {self.cur_user_item.name} - 尝试次数: "
                    f"{index + 1}/{self.script_config.get('Run', 'RunTimesLimit')}"
                )
                if self.cur_user_config.get("Info", "IfScriptBeforeTask"):
                    await execute_script_task(
                        Path(self.cur_user_config.get("Info", "ScriptBeforeTask")),
                        "脚本前任务",
                    )

                try:
                    if self.run_plan is None or self.interface_model is None:
                        raise RuntimeError("MaaFW 运行计划尚未初始化")
                    await self._ensure_desktop_game_started()
                    device_config = await self._build_device_config(
                        self.run_plan,
                        self.interface_model,
                    )
                    result = await self._run_maafw(device_config)
                except Exception as exc:
                    message = f"MaaFW 运行异常: {exc}"
                    self._append_log(message)
                    if self.cur_user_log is not None:
                        self.cur_user_log.status = message
                    await Publisher.send(
                        id=self.task_info.task_id,
                        type=protocol.TASK_NOTICE,
                        data=WSTaskNoticeData(level="error", message=message),
                    )
                    continue
                finally:
                    if self.cur_user_config.get("Info", "IfScriptAfterTask"):
                        await execute_script_task(
                            Path(self.cur_user_config.get("Info", "ScriptAfterTask")),
                            "脚本后任务",
                        )

                await self._mark_period_tasks_completed(result.completedTasks)
                if result.success:
                    self.run_complete = True
                    if self.cur_user_log is not None:
                        self.cur_user_log.status = "Success!"
                    completed_task_labels = _format_completed_task_labels(
                        self.run_plan,
                        result.completedTasks,
                    )
                    self._append_log(
                        "MaaFW 任务完成: " + ", ".join(completed_task_labels)
                    )
                else:
                    message = _failed_task_user_summary(result, self.run_plan)
                    if self.cur_user_log is not None:
                        self.cur_user_log.status = message
                    self._append_log(message)
                    await self._refresh_run_plan_after_period_update()
                    if self.run_plan is not None and not self.run_plan.tasks:
                        self.run_complete = True
                        self._append_log("MaaFW 剩余周期任务已完成，停止本轮重试")
        finally:
            await self._shutdown_runner()
            await self._close_emulator()
            await self._close_game()
            await self._release_project_path()

    async def final_task(self) -> None:
        await self._shutdown_runner()
        if self.check_result != "Pass":
            await self._release_project_path()
            return

        await self._close_emulator()
        await self._close_game()
        await self._save_user_logs()
        if self.run_complete:
            if (
                self.cur_user_config.get("Data", "ProxyTimes") == 0
                and self.cur_user_config.get("Info", "RemainedDay") != -1
            ):
                await self.cur_user_config.set(
                    "Info",
                    "RemainedDay",
                    self.cur_user_config.get("Info", "RemainedDay") - 1,
                )
            await self.cur_user_config.set(
                "Data",
                "ProxyTimes",
                self.cur_user_config.get("Data", "ProxyTimes") + 1,
            )
            await self.cur_user_config.set("Data", "LastProxyStatus", "成功")
            self.cur_user_item.status = "完成"
            await self._send_success_notify()
        else:
            await self.cur_user_config.set("Data", "LastProxyStatus", "失败")
            if self.cur_user_item.status == "运行":
                self.cur_user_item.status = "异常"

        await self._release_project_path()

    async def on_crash(self, e: Exception) -> None:
        self.cur_user_item.status = "异常"
        logger.exception(f"MaaFW 插件自动代理任务出现异常: {e}")
        if self.cur_user_log is not None:
            self.cur_user_log.status = f"MaaFW 插件自动代理任务出现异常: {e}"
        try:
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(
                    level="error",
                    message=f"MaaFW 内置运行任务出现异常: {e}",
                ),
            )
        except Exception:
            pass
        await self._shutdown_runner()
        await self._close_emulator()
        await self._close_game()
        if self.cur_user_log is not None:
            with suppress(Exception):
                await self._save_user_logs()
        await self._release_project_path()

    def _mas_manages_game_launch(self) -> bool:
        """MAS 是否负责启动/关闭游戏。

        只有两种模式：AttachOnly（脚本或用户自己启动，MAS 不碰）与
        DirectExe（MAS 启动并按 CloseOnFinish 关闭）。此前这里根本没读过
        LaunchMode，Win32 controller 无论哪种模式都强制索要 exe。
        """

        mode = str(self.script_config.get("Game", "LaunchMode") or "AttachOnly").strip()
        return mode == "DirectExe"

    def _resolve_game_launch_path(self) -> Path | None:
        """DirectExe 模式下 MAS 要启动的客户端 exe。"""

        raw = str(self.script_config.get("Game", "LaunchPath") or "").strip()
        return Path(raw) if raw else None

    def _load_run_state_for_check(
        self,
    ) -> tuple[MaaFWInterface, MaaFWRunPlan, MaaFWRunPlan, str | None]:
        interface_model = MaaFWInterfaceService().load(self.project_path)
        base_run_plan = self._build_run_plan(interface_model)
        run_plan = self._filter_period_once_tasks(base_run_plan)

        game_path_error: str | None = None
        if (
            run_plan.tasks
            and run_plan.controllerType == "Win32"
            and self._mas_manages_game_launch()
        ):
            game_path = self._resolve_game_launch_path()
            if game_path is None or not game_path.is_file():
                game_path_error = (
                    "当前 MaaFW controller 需要由 MAS 启动游戏，请在脚本管理页选择实际游戏 exe"
                )
        return interface_model, base_run_plan, run_plan, game_path_error

    def _build_run_plan(self, interface_model: MaaFWInterface) -> MaaFWRunPlan:
        task_snapshot = _load_json_dict(self.cur_user_config.get("Task", "TaskSnapshot"))
        selected_preset = str(self.cur_user_config.get("Task", "SelectedPreset") or "").strip()
        controller_name = self._select_controller_name(interface_model)
        resource_name = self._select_resource_name(interface_model, controller_name)
        try:
            return MaaFWRunnerService().build_plan(
                self.project_path,
                interface_model,
                controller_name=controller_name,
                resource_name=resource_name,
                selected_preset=selected_preset if selected_preset and not task_snapshot else None,
                task_snapshot=task_snapshot or None,
            )
        except Exception as exc:
            raise MaaFWRunPlanError(str(exc)) from exc

    def _select_controller_name(self, interface_model: MaaFWInterface) -> str | None:
        configured_controller = str(self.script_config.get("Info", "Controller") or "").strip()

        wants_adb = self.script_config.get("Emulator", "Id") != "-"
        if wants_adb:
            if configured_controller:
                controller = _find_controller(interface_model, configured_controller)
                if controller.type == "Adb":
                    return controller.name
            adb_controller = next(
                (controller for controller in interface_model.controller if controller.type == "Adb"),
                None,
            )
            if adb_controller is not None:
                return adb_controller.name
        if configured_controller:
            return configured_controller
        return None

    def _select_resource_name(
        self,
        interface_model: MaaFWInterface,
        controller_name: str | None,
    ) -> str | None:
        configured_resource = str(self.script_config.get("Info", "Resource") or "").strip()
        if configured_resource:
            return configured_resource
        if controller_name is None:
            return None
        for resource in interface_model.resource:
            if not resource.controller or controller_name in resource.controller:
                return resource.name
        return None

    async def _build_device_config(
        self,
        plan: MaaFWRunPlan,
        interface_model: MaaFWInterface,
    ) -> MaaFWDeviceConfig:
        if plan.controllerType == "Adb":
            address, device_info = await self._resolve_adb_address()
            adb_path = await self._resolve_adb_path(address, device_info)
            adb_profile = await self._build_adb_control_profile()
            return MaaFWDeviceConfig(
                type="Adb",
                adbPath=adb_path,
                address=address,
                screencapMethods=self._resolve_adb_screencap_methods(adb_profile),
                inputMethods=self._resolve_adb_input_methods(adb_profile),
                config=adb_profile.config,
                adbReadyTimeout=self._resolve_adb_ready_timeout(),
            )

        if plan.controllerType == "Win32":
            controller = _find_controller(interface_model, plan.controllerName)
            win32_config = controller.win32
            return MaaFWDeviceConfig(
                type="Win32",
                hWnd=await self._resolve_window_handle(controller),
                screencapMethod=_resolve_win32_method(
                    self.script_config.get("Device", "Win32ScreencapMethod"),
                    win32_config.screencap if win32_config else None,
                    _WIN32_SCREENCAP_METHODS,
                    _WIN32_SCREENCAP_METHODS["DXGI_DesktopDup"],
                ),
                mouseMethod=_resolve_win32_method(
                    self.script_config.get("Device", "Win32MouseMethod"),
                    win32_config.mouse if win32_config else None,
                    _WIN32_INPUT_METHODS,
                    _WIN32_INPUT_METHODS["Seize"],
                ),
                keyboardMethod=_resolve_win32_method(
                    self.script_config.get("Device", "Win32KeyboardMethod"),
                    win32_config.keyboard if win32_config else None,
                    _WIN32_INPUT_METHODS,
                    _WIN32_INPUT_METHODS["Seize"],
                ),
            )

        raise RuntimeError(f"当前仅支持 Adb/Win32 controller: {plan.controllerType}")

    async def _resolve_adb_address(self) -> tuple[str, DeviceInfo | None]:
        if self._cached_adb_address is not None:
            return self._cached_adb_address, self._cached_device_info
        if self.emulator_manager is None:
            raise RuntimeError("当前 controller 需要 ADB，请在脚本管理页选择模拟器")

        emulator_index = self.script_config.get("Emulator", "Index")
        if emulator_index in ("", "-"):
            raise RuntimeError("当前 controller 需要 ADB，请在脚本管理页选择模拟器实例")

        self._append_log(f"正在启动模拟器: {emulator_index}")
        self.opened_emulator = True
        device_info = await self.emulator_manager.open(emulator_index)
        if Config.get("Function", "IfSilence"):
            with suppress(Exception):
                await self.emulator_manager.setVisible(emulator_index, False)
        if not device_info.adb_address or device_info.adb_address == "Unknown":
            raise RuntimeError("模拟器未返回可用 ADB 地址")

        self._cached_adb_address = device_info.adb_address
        self._cached_device_info = device_info
        self._append_log(f"模拟器启动完成，ADB 地址: {device_info.adb_address}")
        return device_info.adb_address, device_info

    async def _resolve_adb_path(
        self,
        address: str,
        device_info: DeviceInfo | None,
    ) -> str | None:
        if self._cached_adb_path is not None:
            return self._cached_adb_path
        configured_path = str(self.script_config.get("Device", "AdbPath") or "").strip()
        if configured_path and Path(configured_path).exists():
            self._cached_adb_path = configured_path
            self._append_log(f"ADB 路径选择: 脚本配置; 路径={configured_path}")
            return configured_path
        if configured_path:
            self._append_log(
                f"脚本配置的 ADB 路径不存在，继续自动解析: {configured_path}"
            )

        derived_path = self._derive_adb_path_from_emulator_config()
        if derived_path is not None and derived_path.exists():
            self._cached_adb_path = str(derived_path)
            self._append_log(
                f"ADB 路径选择: 模拟器安装目录; 路径={self._cached_adb_path}"
            )
            return self._cached_adb_path

        title = f"（{device_info.title}）" if device_info else ""
        self._append_log(
            f"主程序未解析到 ADB 路径{title}，将由 MaaFW Runner 按设备地址发现"
        )
        return None

    def _derive_adb_path_from_emulator_config(self) -> Path | None:
        emulator_id = self.script_config.get("Emulator", "Id")
        if emulator_id == "-":
            return None
        with suppress(Exception):
            emulator_config = Config.EmulatorConfig[uuid.UUID(emulator_id)]
            emulator_path = Path(emulator_config.get("Info", "Path"))
            return emulator_path.parent / "adb.exe"
        return None

    async def _build_adb_control_profile(self) -> MaaFWAdbControlProfile:
        """解析当前模拟器的 EmulatorExtras 能力，并构造 MuMu/雷电 controller extras 配置。"""
        if self._cached_adb_profile is not None:
            return self._cached_adb_profile

        emulator_id = self.script_config.get("Emulator", "Id")
        emulator_index = self.script_config.get("Emulator", "Index")
        if emulator_id == "-" or emulator_index in ("", "-"):
            self._cached_adb_profile = MaaFWAdbControlProfile(None, False, False, {})
            return self._cached_adb_profile

        try:
            emulator_config = Config.EmulatorConfig[uuid.UUID(emulator_id)]
            emulator_type = str(emulator_config.get("Info", "Type") or "")
            emulator_path = Path(emulator_config.get("Info", "Path"))
            # build_adb_emulator_extra_capabilities 通过 find_spec 探测运行时 maa，
            # 不会把 maa 载入 sys.modules，满足导入边界约束；返回 {type: {screencap,input}}。
            capabilities = build_adb_emulator_extra_capabilities()
            capability = capabilities.get(emulator_type, {})
            screencap_extra = bool(capability.get("screencap", False))
            input_extra = bool(capability.get("input", False))
            if emulator_type == "ldplayer" and screencap_extra:
                config = await self._build_ldplayer_adb_controller_config(
                    emulator_path,
                    emulator_index,
                )
                self._cached_adb_profile = MaaFWAdbControlProfile(
                    emulator_type,
                    screencap_extra,
                    input_extra,
                    config,
                )
                return self._cached_adb_profile
            if emulator_type == "mumu" and (screencap_extra or input_extra):
                config = self._build_mumu_adb_controller_config(
                    emulator_path,
                    emulator_index,
                )
                self._cached_adb_profile = MaaFWAdbControlProfile(
                    emulator_type,
                    screencap_extra,
                    input_extra,
                    config,
                )
                return self._cached_adb_profile
            self._cached_adb_profile = MaaFWAdbControlProfile(
                emulator_type,
                screencap_extra,
                input_extra,
                {},
            )
            return self._cached_adb_profile
        except Exception as exc:
            logger.warning(f"构造 MaaFW ADB extra 配置失败，使用默认配置: {exc}")

        self._cached_adb_profile = MaaFWAdbControlProfile(None, False, False, {})
        return self._cached_adb_profile

    def _resolve_adb_ready_timeout(self) -> int | None:
        """按该模拟器自己的 Info.MaxWaitTime 决定等 adb 的耐心。

        LDPlayer.open() 在 in_android==1 之后只 sleep 3 秒就返回「启动完成」
        （不传 package_name 时不走 30 秒分支），此时 Android 里的 adbd 常常还
        没起来。第一层把等待交给项目外壳，内置运行这条等待是唯一的缓冲，
        插件版固定 30 秒在冷启动的雷电上不够用。

        取不到模拟器配置时返回 None，由 runner 用自己的常量兜底。
        """

        manager = self.emulator_manager
        config = getattr(manager, "config", None) if manager is not None else None
        if config is None:
            return None
        try:
            value = int(config.get("Info", "MaxWaitTime"))
        except Exception:  # noqa: BLE001 - 取不到就交给 runner 兜底
            return None
        return value if value > 0 else None

    def _resolve_adb_screencap_methods(self, profile: MaaFWAdbControlProfile) -> int:
        extra_method = _ADB_SCREENCAP_EMULATOR_EXTRAS
        if profile.emulator_type in {"ldplayer", "mumu"}:
            default_methods = _ADB_SCREENCAP_DEFAULT
            if profile.screencap_extra:
                # 只给模拟器增强这一种，与第一层写死的 ScreencapMethods=64 一致。
                #
                # 此前返回的是 default_methods | extra_method，而 -57 本身已含
                # 1<<6，等于把全部方法交给 MaaFW 测速。雷电上 ADB 系截图
                # （RawWithGzip 等）拿不到游戏的 GPU 渲染层：图有正常的
                # 1280x720，内容却是空的，于是识别全程无命中、一次点击都发不出，
                # 每个任务空转到超时。测速只比快慢、不比对不对，必然选错。
                return extra_method
            return _remove_method(default_methods, extra_method, default_methods)
        return _remove_method(
            int(self.script_config.get("Device", "AdbScreencapMethods")),
            extra_method,
            _remove_method(
                _ADB_SCREENCAP_DEFAULT,
                extra_method,
                _ADB_SCREENCAP_DEFAULT,
            ),
        )

    def _resolve_adb_input_methods(self, profile: MaaFWAdbControlProfile) -> int:
        extra_input_method = _ADB_INPUT_EMULATOR_EXTRAS
        if profile.emulator_type == "mumu" and profile.input_extra:
            return _ADB_INPUT_ALL
        if profile.emulator_type in {"ldplayer", "mumu"}:
            return _ADB_INPUT_DEFAULT

        configured = int(self.script_config.get("Device", "AdbInputMethods"))
        if not profile.input_extra:
            return _remove_method(
                configured,
                extra_input_method,
                _ADB_INPUT_DEFAULT,
            )
        return configured

    async def _build_ldplayer_adb_controller_config(
        self,
        emulator_path: Path,
        emulator_index: str,
    ) -> dict[str, Any]:
        emulator_root = emulator_path.parent
        index = int(emulator_index)
        pid = 0

        # get_device_info 仅存在于部分模拟器管理器（雷电有，MuMu 无），
        # 且 list2 可能超时/异常，故整体兜底为实例索引 + pid=0。
        if self.emulator_manager is not None:
            try:
                devices = await self.emulator_manager.get_device_info(emulator_index)
                device = devices.get(emulator_index)
                if device is not None:
                    index = device.idx
                    pid = device.pid
            except Exception as exc:
                logger.warning(f"获取雷电模拟器 extra 信息失败，使用实例索引兜底: {exc}")

        ld_config: dict[str, Any] = {
            "enable": True,
            "index": index,
            "path": str(emulator_root).replace("\\", "/"),
            "pid": pid,
        }
        ld_library = emulator_root / "ldopengl64.dll"
        if ld_library.exists():
            ld_config["lib"] = str(ld_library).replace("\\", "/")

        return {
            "extras": {
                "ld": ld_config,
            },
        }

    @staticmethod
    def _build_mumu_adb_controller_config(
        emulator_path: Path,
        emulator_index: str,
    ) -> dict[str, Any]:
        emulator_root = emulator_path.parent.parent
        mumu_config: dict[str, Any] = {
            "enable": True,
            "index": int(emulator_index),
            "path": str(emulator_root).replace("\\", "/"),
        }
        for library in (
            emulator_root / "nx_main" / "sdk" / "external_renderer_ipc.dll",
            emulator_root / "shell" / "sdk" / "external_renderer_ipc.dll",
        ):
            if library.exists():
                mumu_config["lib"] = str(library).replace("\\", "/")
                break

        return {
            "extras": {
                "mumu": mumu_config,
            },
        }

    async def _resolve_window_handle(self, controller: MaaFWController) -> int:
        configured_hwnd = self.script_config.get("Device", "HWnd")
        parsed_hwnd = _optional_int(configured_hwnd)
        if parsed_hwnd:
            return parsed_hwnd
        matches = await asyncio.to_thread(_match_controller_windows, controller)
        if not matches:
            raise RuntimeError("未找到匹配 MaaFW Win32 controller 的窗口")
        return int(matches[0].hWnd)

    async def _run_maafw(self, device_config: MaaFWDeviceConfig) -> MaaFWRunResult:
        if self.run_plan is None:
            raise RuntimeError("MaaFW 运行计划尚未初始化")
        timeout = self.script_config.get("Run", "RunTimeLimit") * 60
        try:
            return await asyncio.wait_for(
                self._run_maafw_worker(device_config),
                timeout=timeout,
            )
        except asyncio.TimeoutError as exc:
            await self._terminate_runner_process()
            raise RuntimeError("MaaFW 任务运行超时") from exc
        except asyncio.CancelledError:
            await self._terminate_runner_process()
            raise

    async def _run_maafw_worker(
        self,
        device_config: MaaFWDeviceConfig,
    ) -> MaaFWRunResult:
        if self.run_plan is None:
            raise RuntimeError("MaaFW 运行计划尚未初始化")

        service = MaaFWRunnerService()
        loop = asyncio.get_running_loop()
        runtime_pool_root = self.maafw_runtime_pool_root
        runtime_pool_id = str(self.maafw_runtime_pool_id or "").strip()
        if runtime_pool_root is None or not runtime_pool_id:
            raise RuntimeError(
                "MaaFW 运行任务缺少由 maafw.runtime_pool.v1 注入的 root/poolId"
            )
        if self.maafw_managed_execution:
            managed_route = self.maafw_managed_route
            if managed_route is None:
                raise RuntimeError(
                    "MaaFW Managed 执行缺少已预校验的可信 runtime route"
                )
        else:
            managed_route = managed_execution_route(
                managed_execution=False,
                project=self.maafw_managed_project,
                runtime_binding=self.maafw_managed_runtime_binding,
                expected_pool_id=runtime_pool_id,
            )
        native_debug_log_path = self.project_path / "debug" / "maafw.log"
        try:
            native_debug_log_offset = (
                await asyncio.to_thread(native_debug_log_path.stat)
            ).st_size
        except OSError:
            native_debug_log_offset = 0

        def send_runner_log(message: str) -> None:
            loop.call_soon_threadsafe(self._append_log, message)

        prepare_environment_task = asyncio.create_task(
            asyncio.to_thread(
                service.prepare_environment,
                self.project_path,
                runtime_pool_root=runtime_pool_root,
                runtime_requirements=(
                    managed_route.runtime_requirements if managed_route else None
                ),
                runtime_requirement=(
                    managed_route.maafw_requirement if managed_route else None
                ),
                runtime_id=managed_route.runtime_id if managed_route else None,
                runtime_pool_id=runtime_pool_id,
                runtime_python_constraint=(
                    managed_route.python_constraint if managed_route else None
                ),
                lease_owner=f"automas-script-maafw:{self.script_info.script_id}",
                lease_ttl_seconds=max(
                    600,
                    int(self.script_config.get("Run", "RunTimeLimit") or 30) * 60
                    + 600,
                ),
                # worker 跑在 runtime pool 的隔离 venv 里，代码要靠 PYTHONPATH
                # 找到本仓。插件形态下这里给的是插件目录（get_plugin_import_paths），
                # 树内对应物就是仓库根。只给代码路径、不给宿主 venv 的
                # site-packages，隔离 venv 里的 maafw 因此仍然优先。
                import_paths=[Path.cwd()],
                send_log=send_runner_log,
            )
        )
        try:
            runner_environment = await asyncio.shield(prepare_environment_task)
        except asyncio.CancelledError:

            async def release_after_prepare() -> None:
                try:
                    prepared_after_cancel = await prepare_environment_task
                except BaseException:
                    return
                with suppress(Exception):
                    await asyncio.to_thread(
                        service.release_environment,
                        prepared_after_cancel,
                    )

            cleanup_task = asyncio.create_task(release_after_prepare())
            with suppress(asyncio.CancelledError):
                await asyncio.shield(cleanup_task)
            raise
        job_path: Path | None = None
        worker_id: str | None = None
        try:
            runner_plan = self.run_plan
            if runner_environment.maafw_version or managed_route is not None:
                runner_plan = self.run_plan.model_copy(deep=True)
            if managed_route is not None:
                runner_plan.managedSharedAgentDependenciesComplete = (
                    managed_route.shared_agent_dependencies_complete
                )
                runner_plan.managedPythonAgentIndexes = list(
                    managed_route.managed_python_agent_indexes
                )
            if runner_environment.maafw_version:
                runner_plan.piEnv["PI_CLIENT_MAAFW_VERSION"] = (
                    f"v{runner_environment.maafw_version.lstrip('v')}"
                )
            payload = service.create_job_payload(runner_plan, device_config)
            work_dir = Path.cwd() / "runtime" / "maafw_runner_jobs"
            job_path = await asyncio.to_thread(service.write_job_file, payload, work_dir)
            process = await asyncio.create_subprocess_exec(
                str(runner_environment.python_executable),
                "-m",
                "app.task.MaaFW.tools.core.automas_maafw_runner.worker",
                str(job_path),
                cwd=str(Path.cwd()),
                env=runner_environment.env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            worker_id = service.register_worker(process)
        except BaseException:
            if job_path is not None:
                with suppress(Exception):
                    await asyncio.to_thread(job_path.unlink)
            with suppress(Exception):
                await asyncio.to_thread(service.release_environment, runner_environment)
            service.unregister_worker(worker_id)
            raise
        self.runner_process = process
        result_payload: dict[str, Any] | None = None
        stderr_lines: list[str] = []
        framework_log_path: Path | None = None
        framework_log_writer: _FrameworkLogWriter | None = None

        try:
            started_at = self.cur_user_log_started_at or datetime.now()
            local_started_at = started_at.replace(
                tzinfo=datetime.now().astimezone().tzinfo
            ).astimezone(UTC4)
            framework_log_dir = (
                Path.cwd()
                / "history"
                / local_started_at.strftime("%Y-%m-%d")
                / self.cur_user_item.name
            )
            framework_log_path = framework_log_dir / (
                f"{local_started_at.strftime('%H-%M-%S')}.maafw.log"
            )
            writer = _FrameworkLogWriter(framework_log_path)
            await asyncio.to_thread(writer.start)
            framework_log_writer = writer
            self._append_log(f"MaaFW 框架调试日志写入中: {framework_log_path}")
        except Exception as exc:
            if framework_log_writer is not None:
                with suppress(Exception):
                    await asyncio.to_thread(framework_log_writer.close)
                framework_log_writer = None
            self._append_log(f"MaaFW 框架调试日志创建失败: {exc}")

        def write_framework_log(source: str, message: str) -> None:
            if framework_log_writer is None:
                return
            framework_log_writer.write(source, message)

        async def read_stdout() -> None:
            nonlocal result_payload
            if process.stdout is None:
                return
            processed = 0
            async for raw_line in process.stdout:
                # StreamReader 缓冲里有数据时 `async for` 不会挂起，会一路取到
                # 缓冲耗尽为止。MaaFramework 的原生诊断动辄每秒几十行、单次运行
                # 几千行，这个循环于是能连续独占事件循环数十秒——真机上表现为
                # 界面日志停更、API 不响应、点了停止没反应，等这波处理完才一起
                # 恢复。定期显式让出，代价可以忽略。
                processed += 1
                if processed % _RELAY_YIELD_EVERY_LINES == 0:
                    await asyncio.sleep(0)
                # Worker protocol events are UTF-8 JSON, while MaaFramework
                # native diagnostics may be written directly to stdout using
                # the Windows ACP/GBK code page.  Decode protocol lines
                # strictly first and use the existing multi-codec fallback
                # for native text so Chinese diagnostics are not persisted as
                # replacement characters.
                try:
                    line = raw_line.decode("utf-8", errors="strict").strip()
                except UnicodeDecodeError:
                    line = _decode_subprocess_output(raw_line).strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    write_framework_log("worker-stdout", line)
                    if _should_forward_framework_log(line):
                        self._append_log(_framework_ui_message(line))
                    continue

                event_type = event.get("type")
                if event_type == "log":
                    message = str(event.get("message") or "")
                    write_framework_log("runner", message)
                    if _should_forward_framework_log(message):
                        self._append_log(_framework_ui_message(message))
                elif event_type == "result" and isinstance(event.get("data"), dict):
                    result_payload = event["data"]
                elif event_type == "error":
                    message = str(event.get("message") or "")
                    write_framework_log("runner-error", message)
                    # Keep the complete error in the per-run framework log,
                    # but apply the same native-noise filter as ordinary
                    # framework diagnostics.  Worker error events can contain
                    # an entire native parser/backtrace blob and must not
                    # flood the user-facing task log.
                    if _should_forward_framework_log(message):
                        self._append_log(_framework_ui_message(message))

        async def read_stderr() -> None:
            if process.stderr is None:
                return
            processed = 0
            async for raw_line in process.stderr:
                processed += 1
                if processed % _RELAY_YIELD_EVERY_LINES == 0:
                    await asyncio.sleep(0)  # 同 read_stdout：别独占事件循环
                line = _clean_framework_output(_decode_subprocess_output(raw_line)).strip()
                if not line:
                    continue
                write_framework_log("worker-stderr", line)
                stderr_lines.append(line)
                del stderr_lines[:-20]

        stdout_task = asyncio.create_task(read_stdout())
        stderr_task = asyncio.create_task(read_stderr())

        async def drain_readers(*, propagate_errors: bool) -> None:
            _, pending_readers = await asyncio.wait(
                (stdout_task, stderr_task),
                timeout=5.0,
            )
            for task in pending_readers:
                task.cancel()
            reader_results = await asyncio.gather(
                stdout_task,
                stderr_task,
                return_exceptions=True,
            )
            if propagate_errors:
                for result in reader_results:
                    if isinstance(result, Exception):
                        raise result

        try:
            returncode = await process.wait()
            await drain_readers(propagate_errors=True)
        finally:
            if process.returncode is None:
                await self._terminate_runner_process()
            elif self.runner_process is process:
                self.runner_process = None
            await drain_readers(propagate_errors=False)
            if framework_log_writer is not None:
                finalize_errors: list[str] = []
                try:
                    native_delta = await asyncio.to_thread(
                        _read_native_debug_log_delta,
                        native_debug_log_path,
                        native_debug_log_offset,
                    )
                    if native_delta:
                        write_framework_log(
                            "debug/maafw.log",
                            native_delta,
                        )
                except Exception as exc:
                    finalize_errors.append(f"原生 debug 日志读取失败: {exc}")
                try:
                    await asyncio.to_thread(framework_log_writer.close)
                except Exception as exc:
                    finalize_errors.append(str(exc))
                if framework_log_path is not None:
                    if finalize_errors:
                        self._append_log(
                            "MaaFW 框架调试日志保存不完整: "
                            + "；".join(finalize_errors)
                            + f"；文件: {framework_log_path}"
                        )
                    else:
                        self._append_log(
                            f"MaaFW 框架调试日志已保存: {framework_log_path}"
                        )
            with suppress(Exception):
                await asyncio.to_thread(job_path.unlink)
            with suppress(Exception):
                await asyncio.to_thread(service.release_environment, runner_environment)
            service.unregister_worker(worker_id)

        if result_payload is not None:
            return MaaFWRunResult.model_validate(result_payload)
        message = f"MaaFW runner worker exited without result: {returncode}"
        detail = "\n".join(stderr_lines[-5:]).strip()
        if detail and _should_forward_framework_log(detail):
            message += f": {_framework_ui_message(detail)}"
        elif detail:
            # Native stderr is already preserved in the per-run framework log.
            # Do not copy parser/backtrace blobs into the normal task log when
            # the worker exits without a protocol result.
            message += ": MaaFW worker 未返回任务结果，完整原生日志已保存到本次运行的 .maafw.log"
        raise RuntimeError(message)

    async def _shutdown_runner(self) -> None:
        await self._terminate_pretask_process()
        await self._terminate_runner_process()

    async def _run_pretasks(self) -> None:
        if self.run_plan is None:
            raise RuntimeError("MaaFW 运行计划尚未初始化")

        env = os.environ.copy()
        env.update(self.run_plan.piEnv)
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        for pretask in self.run_plan.pretasks:
            display_name = _task_display_name(pretask)
            self._append_log(f"开始应用运行前设置: {display_name}")
            process = await asyncio.create_subprocess_exec(
                pretask.executable,
                *pretask.args,
                cwd=self.run_plan.path,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                creationflags=creationflags,
            )
            self.pretask_process = process
            try:
                output, _ = await process.communicate()
            finally:
                if process.returncode is not None and self.pretask_process is process:
                    self.pretask_process = None

            detail = _decode_subprocess_output(output).strip()
            if detail:
                for line in detail.splitlines():
                    self._append_log(f"[运行前设置] {line}")
            if process.returncode != 0:
                error_detail = detail.splitlines()[-1] if detail else "没有输出错误详情"
                raise RuntimeError(
                    f"运行前设置 {display_name} 执行失败（退出码 {process.returncode}）: "
                    f"{error_detail}"
                )
            self._append_log(f"运行前设置完成: {display_name}")

    async def _terminate_pretask_process(self) -> None:
        process = self.pretask_process
        self.pretask_process = None
        if process is None or process.returncode is not None:
            return

        try:
            process.terminate()
            await asyncio.wait_for(process.wait(), timeout=5)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
        except ProcessLookupError:
            return
        except Exception as exc:
            logger.warning(f"MaaFW 运行前设置进程清理失败: {exc}")

    async def _terminate_runner_process(self) -> None:
        process = self.runner_process
        self.runner_process = None
        if process is None or process.returncode is not None:
            return

        try:
            process.terminate()
            await asyncio.wait_for(process.wait(), timeout=5)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
        except ProcessLookupError:
            return
        except Exception as exc:
            logger.warning(f"MaaFW runner worker 清理失败: {exc}")

    def _filter_period_once_tasks(self, plan: MaaFWRunPlan) -> MaaFWRunPlan:
        daily_tasks = set(_load_json_list(self.script_config.get("Run", "DailyOnceTasks")))
        weekly_tasks = set(_load_json_list(self.script_config.get("Run", "WeeklyOnceTasks")))
        monthly_tasks = set(_load_json_list(self.script_config.get("Run", "MonthlyOnceTasks")))
        if not daily_tasks and not weekly_tasks and not monthly_tasks:
            return plan

        daily_key, weekly_key, monthly_key = _current_period_keys()
        records = self._load_period_task_records()
        runnable_tasks = []
        skipped_tasks = []
        for task in plan.tasks:
            daily_done = (
                task.name in daily_tasks and records["daily"].get(task.name) == daily_key
            )
            weekly_done = task.name in weekly_tasks and records["weekly"].get(task.name) == weekly_key
            monthly_done = (
                task.name in monthly_tasks and records["monthly"].get(task.name) == monthly_key
            )
            if daily_done or weekly_done or monthly_done:
                if daily_done:
                    reason = "今日已正常完成"
                elif monthly_done:
                    reason = "本月已正常完成"
                else:
                    reason = "本周已正常完成"
                skipped_tasks.append(
                    MaaFWSkippedTaskPlan(
                        name=task.name,
                        label=task.label,
                        entry=task.entry,
                        reason=reason,
                    )
                )
                continue
            runnable_tasks.append(task)
        return plan.model_copy(
            update={
                "tasks": runnable_tasks,
                "skippedTasks": [*plan.skippedTasks, *skipped_tasks],
            },
        )

    async def _refresh_run_plan_after_period_update(self) -> None:
        if self.base_run_plan is not None:
            self.run_plan = await asyncio.to_thread(
                self._filter_period_once_tasks,
                self.base_run_plan,
            )

    def _load_period_task_records(self) -> dict[str, dict[str, str]]:
        raw_records = _load_json_dict(self.cur_user_config.get("Data", "PeriodTaskRecords"))
        records: dict[str, dict[str, str]] = {"daily": {}, "weekly": {}, "monthly": {}}
        for period in records:
            raw_period_records = raw_records.get(period, {})
            if isinstance(raw_period_records, dict):
                records[period] = {
                    str(task_name): str(period_key)
                    for task_name, period_key in raw_period_records.items()
                }
        return records

    async def _mark_period_tasks_completed(self, completed_tasks: list[str]) -> None:
        if not completed_tasks:
            return
        daily_tasks = set(_load_json_list(self.script_config.get("Run", "DailyOnceTasks")))
        weekly_tasks = set(_load_json_list(self.script_config.get("Run", "WeeklyOnceTasks")))
        monthly_tasks = set(_load_json_list(self.script_config.get("Run", "MonthlyOnceTasks")))
        if not daily_tasks and not weekly_tasks and not monthly_tasks:
            return

        daily_key, weekly_key, monthly_key = _current_period_keys()
        records = self._load_period_task_records()
        changed = False
        for task_name in set(completed_tasks).intersection(daily_tasks):
            if records["daily"].get(task_name) != daily_key:
                records["daily"][task_name] = daily_key
                changed = True
        for task_name in set(completed_tasks).intersection(weekly_tasks):
            if records["weekly"].get(task_name) != weekly_key:
                records["weekly"][task_name] = weekly_key
                changed = True
        for task_name in set(completed_tasks).intersection(monthly_tasks):
            if records["monthly"].get(task_name) != monthly_key:
                records["monthly"][task_name] = monthly_key
                changed = True
        if changed:
            await self.cur_user_config.set(
                "Data",
                "PeriodTaskRecords",
                json.dumps(records, ensure_ascii=False),
            )

    async def _mark_run_started(self) -> None:
        if self.cur_user_config.get("Data", "LastProxyDate") != self.curdate:
            await self.cur_user_config.set("Data", "LastProxyDate", self.curdate)
            await self.cur_user_config.set("Data", "ProxyTimes", 0)
        await self.cur_user_config.set("Data", "LastProxyStatus", "运行中")

    async def _close_emulator(self) -> None:
        if not self.opened_emulator or self.emulator_manager is None:
            return
        try:
            await self.emulator_manager.close(self.script_config.get("Emulator", "Index"))
        except Exception as exc:
            logger.warning(f"MaaFW 插件清理模拟器失败: {exc}")
        finally:
            self.opened_emulator = False

    async def _ensure_desktop_game_started(self) -> None:
        """Win32 场景下由 MAS 负责启动/激活桌面游戏客户端，供后续窗口解析使用。"""
        if self.run_plan is None or self.run_plan.controllerType != "Win32":
            return
        if self.opened_game:
            return
        if not self._mas_manages_game_launch():
            # AttachOnly：游戏由脚本或用户自己起，MAS 只负责找窗口。窗口找不到时
            # _resolve_window_handle 会给出「未找到匹配 MaaFW Win32 controller
            # 的窗口」，比在这里索要一个本模式用不上的 exe 更贴题。
            return

        game_path = self._resolve_game_launch_path()
        if game_path is None or not await asyncio.to_thread(game_path.is_file):
            raise RuntimeError("当前 MaaFW controller 需要由 MAS 启动游戏，请在脚本管理页选择实际游戏 exe")

        if self.interface_model is not None and self.run_plan is not None:
            controller = _find_controller(
                self.interface_model,
                self.run_plan.controllerName,
            )
            matches = await asyncio.to_thread(_match_controller_windows, controller)
            if matches:
                selected = matches[0]
                self._append_log(
                    "检测到游戏客户端窗口: "
                    f"hWnd={selected.hWnd}, class={selected.className}, "
                    f"title={selected.windowName}"
                )
                await self._activate_desktop_game_window(game_path)
                return

        if await asyncio.to_thread(_is_process_path_running, game_path):
            message = f"检测到游戏进程已在运行，跳过由 MAS 重复启动游戏: {game_path.name}"
            logger.info(message)
            self.script_info.log = message
            await self._wait_for_desktop_game_ready(game_path)
            await self._activate_desktop_game_window(game_path)
            return

        game_arguments = shlex.split(str(self.script_config.get("Game", "Arguments") or "").strip())
        logger.info(f"启动游戏: {game_path} - {self.script_config.get('Game', 'Arguments')}")
        await self.game_process_manager.open_process(
            game_path,
            *game_arguments,
            cwd=game_path.parent,
        )

        try:
            await self._wait_for_desktop_game_ready(game_path)
        except Exception:
            with suppress(Exception):
                await self.game_process_manager.kill()
            raise

        self.opened_game = True
        await self._activate_desktop_game_window(game_path)

    async def _wait_for_desktop_game_ready(
        self,
        game_path: Path,
        poll_interval: float = 1.0,
    ) -> None:
        wait_time = max(0, int(self.script_config.get("Game", "WaitTime") or 0))
        if self.run_plan is None or self.interface_model is None:
            raise RuntimeError("MaaFW 运行计划未完成初始化")

        configured_hwnd = self.script_config.get("Device", "HWnd")
        explicit_hwnd = _optional_int(configured_hwnd)
        controller = _find_controller(self.interface_model, self.run_plan.controllerName)

        self._append_log(
            f"正在等待游戏客户端窗口就绪，最大等待时间 {wait_time}s: {game_path.name}"
        )
        if wait_time <= 0:
            if not await asyncio.to_thread(_is_process_path_running, game_path):
                raise RuntimeError(f"游戏进程未启动: {game_path.name}")
            if explicit_hwnd:
                self._append_log(f"已配置窗口句柄，跳过窗口正则等待: {explicit_hwnd}")
                return
            if not await asyncio.to_thread(_match_controller_windows, controller):
                raise RuntimeError(f"游戏窗口未就绪: {game_path.name}")
            return

        waited = 0.0
        process_detected = False
        while waited < wait_time:
            if not explicit_hwnd:
                matches = await asyncio.to_thread(_match_controller_windows, controller)
                if matches:
                    selected = matches[0]
                    self._append_log(
                        "检测到游戏客户端窗口: "
                        f"hWnd={selected.hWnd}, class={selected.className}, "
                        f"title={selected.windowName}"
                    )
                    return

            if await asyncio.to_thread(_is_process_path_running, game_path):
                if not process_detected:
                    self._append_log(f"检测到游戏进程已启动: {game_path.name}")
                    process_detected = True

                if explicit_hwnd:
                    self._append_log(f"已配置窗口句柄，跳过窗口正则等待: {explicit_hwnd}")
                    return

                matches = await asyncio.to_thread(_match_controller_windows, controller)
                if matches:
                    selected = matches[0]
                    self._append_log(
                        "检测到游戏客户端窗口: "
                        f"hWnd={selected.hWnd}, class={selected.className}, "
                        f"title={selected.windowName}"
                    )
                    return

            sleep_seconds = min(poll_interval, wait_time - waited)
            await asyncio.sleep(sleep_seconds)
            waited += sleep_seconds

        if not explicit_hwnd:
            matches = await asyncio.to_thread(_match_controller_windows, controller)
            if matches:
                selected = matches[0]
                self._append_log(
                    "检测到游戏客户端窗口: "
                    f"hWnd={selected.hWnd}, class={selected.className}, "
                    f"title={selected.windowName}"
                )
                return

        if await asyncio.to_thread(_is_process_path_running, game_path):
            if explicit_hwnd:
                self._append_log(f"已配置窗口句柄，跳过窗口正则等待: {explicit_hwnd}")
                return

            matches = await asyncio.to_thread(_match_controller_windows, controller)
            if matches:
                selected = matches[0]
                self._append_log(
                    "检测到游戏客户端窗口: "
                    f"hWnd={selected.hWnd}, class={selected.className}, "
                    f"title={selected.windowName}"
                )
                return

            raise RuntimeError(f"游戏窗口在 {wait_time}s 内未就绪: {game_path.name}")

        raise RuntimeError(f"游戏进程在 {wait_time}s 内未启动: {game_path.name}")

    async def _activate_desktop_game_window(self, game_path: Path) -> None:
        try:
            # 第二个参数是**秒数**，不是截止时刻。dev 的 #473 把计时改成单调时钟后
            # 内部是 `time.monotonic() + timeout_seconds`，传 datetime 会直接
            # TypeError（真机上表现为「游戏进程已启动，但定位窗口失败」，窗口没被
            # 前置，随后第一个任务识别不到而失败）。
            await self.game_process_manager.search_process(
                ProcessInfo(exe=str(game_path.resolve())),
                WINDOW_SEARCH_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            logger.warning(f"MaaFW 定位游戏进程窗口失败: {exc}")
            self._append_log(f"游戏进程已启动，但定位窗口失败: {exc}")
            return

        activate_end_time = datetime.now() + timedelta(seconds=5)
        while datetime.now() < activate_end_time:
            if await self.game_process_manager.activate_window():
                self._append_log("游戏窗口已置于前台")
                return
            await asyncio.sleep(0.5)

        self._append_log("游戏窗口前置失败，将继续启动 MaaFW 任务")

    async def _close_game(self) -> None:
        if not self.opened_game:
            return
        if not self.script_config.get("Game", "CloseOnFinish"):
            return

        try:
            await self.game_process_manager.kill()
        except Exception as exc:
            logger.warning(f"MaaFW 清理时关闭游戏失败: {exc}")
        finally:
            self.opened_game = False

    async def _try_enter_project_path(self) -> bool:
        project_lock_key = await try_reserve_project_path(self.project_path)
        if project_lock_key is None:
            return False
        self.project_lock_key = project_lock_key
        return True

    async def _release_project_path(self) -> None:
        if self.project_lock_key is None:
            return
        await release_project_path(self.project_lock_key)
        self.project_lock_key = None

    async def _save_user_logs(self) -> None:
        for timestamp, log_item in self.cur_user_item.log_record.items():
            dt = timestamp.replace(tzinfo=datetime.now().astimezone().tzinfo).astimezone(UTC4)
            log_path = (
                Path.cwd()
                / f"history/{dt.strftime('%Y-%m-%d')}/{self.cur_user_item.name}/{dt.strftime('%H-%M-%S')}.log"
            )
            if not log_item.content:
                log_item.content = ["未捕获到任何 MaaFW 运行日志"]
            if log_item.status == "未开始监看日志":
                log_item.status = "MaaFW 任务被中止"
            await Config.save_general_log(log_path, log_item.content, log_item.status)

    async def _send_success_notify(self) -> None:
        try:
            await Notify.push_plyer(
                "MaaFW 自动代理任务完成",
                f"已完成用户 {self.cur_user_item.name} 的 MaaFW 自动代理任务",
                f"已完成 {self.cur_user_item.name} 的 MaaFW 自动代理任务",
                3,
            )
        except Exception as exc:
            logger.warning(f"MaaFW 插件用户通知发送失败: {exc}")

    def _append_log(self, message: str) -> None:
        logger.info(message)
        if self.cur_user_log is not None:
            self.cur_user_log.content.append(_format_user_log_line(message))
            self.script_info.log = "".join(self.cur_user_log.content[-80:])
        else:
            self.script_info.log = str(message)


def _find_controller(interface_model: MaaFWInterface, controller_name: str) -> MaaFWController:
    controller = next(
        (item for item in interface_model.controller if item.name == controller_name),
        None,
    )
    if controller is None:
        raise RuntimeError(f"未找到 controller: {controller_name}")
    return controller


def _match_controller_windows(controller: MaaFWController) -> list[Any]:
    # 插件形态下先查 maafw.controller.win32 服务契约再回退到直接实例化；
    # 树内没有服务契约层，直连实现（移植指南 §4 规则 4）
    service = MaaFWWin32ControllerService()
    controller_payload = controller.model_dump(mode="json", by_alias=True)
    return list(service.match_controller_windows(controller_payload))


def _is_process_path_running(executable_path: Path) -> bool:
    target_path = executable_path.resolve()
    for proc in psutil.process_iter(["exe"]):
        with suppress(psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            raw_exe = proc.info.get("exe") or proc.exe()
            if raw_exe and Path(raw_exe).resolve() == target_path:
                return True
    return False


def _optional_int(value: Any) -> int | None:
    if value in (None, "", "-"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _resolve_win32_method(
    configured_value: Any,
    interface_method: str | None,
    method_values: dict[str, int],
    default: int,
) -> int:
    configured = _optional_int(configured_value) or 0
    if configured:
        return configured
    if interface_method:
        return method_values.get(interface_method, default)
    return default


def _decode_subprocess_output(data: bytes) -> str:
    if not data:
        return ""
    for encoding in _SUBPROCESS_OUTPUT_ENCODINGS:
        try:
            return data.decode(encoding, errors="strict")
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("latin1", errors="replace")


def _clean_framework_output(message: str) -> str:
    return _ANSI_ESCAPE_RE.sub("", str(message or ""))


def _framework_ui_message(message: str) -> str:
    """Bound worker diagnostics copied to the user-facing task log.

    Complete native output is already retained in ``*.maafw.log``. A malformed
    task/encoding error can otherwise contain megabytes of JSON or a parser
    trace and make the normal task page unusable.
    """

    cleaned = _clean_framework_output(message).strip()
    if len(cleaned) <= _FRAMEWORK_UI_LOG_MAX_CHARS:
        return cleaned
    lines = cleaned.splitlines()
    compact = "\n".join(line[:240] for line in lines[:8]).strip()
    omitted = max(0, len(cleaned) - len(compact))
    summary = (
        f"{compact}\n… 上述内容已省略 {omitted} 个字符，"
        "完整内容请查看本次运行的 .maafw.log"
    )
    return summary[:_FRAMEWORK_UI_LOG_MAX_CHARS]


def _should_forward_framework_log(message: str) -> bool:
    if any(marker in message for marker in _RAW_FAILURE_UI_LOG_MARKERS):
        return False
    cleaned = _clean_framework_output(message).strip()
    if _FRAMEWORK_COORDINATE_RE.search(cleaned):
        return False
    if any(marker in cleaned for marker in _VERBOSE_FRAMEWORK_LOG_MARKERS):
        return False
    # Native MaaFramework diagnostics are always retained in the per-run
    # ``*.maafw.log`` file.  They are intentionally not copied into the user
    # facing script log: one failed override can otherwise emit the same
    # parser backtrace once per task and hide the actionable summary.
    if any(marker in cleaned for marker in _NATIVE_FRAMEWORK_LOG_MARKERS):
        return False
    if _NATIVE_FRAMEWORK_STATUS_RE.search(cleaned) and ".cpp" in cleaned:
        return False
    # Some MaaFramework/Agent diagnostics do not include a C++ source marker
    # but embed an entire pipeline JSON document in one line.  Keep the full
    # payload in the per-run ``*.maafw.log`` and leave the normal task page to
    # the concise runner error that follows it.
    if len(cleaned) > _FRAMEWORK_UI_LOG_MAX_CHARS and (
        any(marker in cleaned for marker in _FRAMEWORK_DEBUG_PAYLOAD_MARKERS)
        or cleaned.startswith(("{", "["))
    ):
        return False
    return True


def _remove_method(methods: int, method: int, fallback: int) -> int:
    """从位掩码中剔除 method 位；若结果为 0（无可用方法）则回退到 fallback。"""
    filtered = methods & ~method
    return filtered or fallback


def _load_json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        with suppress(json.JSONDecodeError):
            data = json.loads(value)
            if isinstance(data, dict):
                return data
    return {}


def _load_json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        with suppress(json.JSONDecodeError):
            data = json.loads(value)
            if isinstance(data, list):
                return [str(item) for item in data if str(item).strip()]
    return []


def _read_native_debug_log_delta(path: Path, start_offset: int) -> str:
    try:
        current_size = path.stat().st_size
    except FileNotFoundError:
        return ""
    start_offset = start_offset if current_size >= start_offset else 0
    with path.open("rb") as native_debug_log_file:
        native_debug_log_file.seek(start_offset)
        return _decode_subprocess_output(native_debug_log_file.read())


_FAILURE_REASON_MAX_CHARS = 200


def _failure_reason_for_user(result: Any) -> str:
    """从运行结果里取一句可读的失败原因。

    runner 会把异常原文放进 ``errorMessage``，但它同时也用
    ``MaaFW 任务执行失败: {exc}`` 发一条日志——那条命中
    ``_RAW_FAILURE_UI_LOG_MARKERS`` 会被当框架噪声过滤掉。若这里再不取，
    Python 侧异常（如缺模块）在任务页上就只剩「任务执行失败」四个字。

    框架自身的失败原文可能是整段原生 backtrace，因此只取首个非空行并截断；
    完整内容仍在本次运行的 ``*.maafw.log`` 里。
    """

    raw = str(getattr(result, "errorMessage", "") or "").strip()
    if not raw:
        return ""
    first_line = next(
        (line.strip() for line in raw.splitlines() if line.strip()), ""
    )
    if not first_line:
        return ""
    if len(first_line) > _FAILURE_REASON_MAX_CHARS:
        first_line = first_line[:_FAILURE_REASON_MAX_CHARS] + "…"
    return first_line


def _failed_task_user_summary(result: Any, plan: Any | None) -> str:
    failed_task = str(getattr(result, "failedTask", "") or "").strip()
    reason = _failure_reason_for_user(result)
    suffix = f"：任务执行失败{'：' + reason if reason else ''}"
    tasks = tuple(getattr(plan, "tasks", ()) or ()) if plan is not None else ()
    if tasks:
        for task in tasks:
            task_name = str(getattr(task, "name", "") or "").strip()
            task_entry = str(getattr(task, "entry", "") or "").strip()
            if failed_task and failed_task not in {task_name, task_entry}:
                continue
            return f"{_task_display_name(task)}{suffix}"
    return f"{failed_task or 'MaaFW 任务'}{suffix}"


def _task_display_name(task: Any) -> str:
    label = getattr(task, "label", None)
    if isinstance(label, str) and label.strip() and not label.lstrip().startswith("$"):
        return label.strip()
    return str(getattr(task, "name", ""))


def _format_completed_task_labels(
    plan: MaaFWRunPlan | None,
    task_names: list[str],
) -> list[str]:
    labels_by_name = (
        {task.name: _task_display_name(task) for task in plan.tasks}
        if plan is not None
        else {}
    )
    return [labels_by_name.get(task_name, task_name) for task_name in task_names]


def _format_run_overview_log(
    plan: MaaFWRunPlan,
    *,
    selected_preset: str,
) -> str:
    task_names = " -> ".join(_task_display_name(task) for task in plan.tasks) or "-"
    if len(task_names) > _RUN_OVERVIEW_LOG_VALUE_LIMIT:
        task_names = task_names[:_RUN_OVERVIEW_LOG_VALUE_LIMIT] + "..."
    project_name = (
        plan.projectLabel.strip()
        if isinstance(plan.projectLabel, str)
        and plan.projectLabel.strip()
        and not plan.projectLabel.lstrip().startswith("$")
        else plan.projectName
    )
    project_version = str(plan.piEnv.get("PI_VERSION") or "").strip() or "未知"
    return (
        "MaaFW 运行总览: "
        f"project={project_name}; version={project_version}; "
        f"controller={plan.controllerName}; resource={plan.resourceName}; "
        f"preset={selected_preset or '自定义'}; "
        f"enabled_tasks({len(plan.tasks)})={task_names}"
    )


def _current_period_keys(now: datetime | None = None) -> tuple[str, str, str]:
    current = now or datetime.now(tz=UTC4)
    iso_year, iso_week, _ = current.isocalendar()
    return (
        current.strftime("%Y-%m-%d"),
        f"{iso_year}-W{iso_week:02d}",
        current.strftime("%Y-%m"),
    )


def _format_user_log_line(message: str) -> str:
    timestamp = datetime.now().astimezone().strftime("%H:%M:%S")
    lines = str(message).splitlines() or [""]
    return "".join(f"[{timestamp}] {line}\n" for line in lines)
