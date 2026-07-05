#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.


import asyncio
import hashlib
import json
import os
import re
import shutil
import shlex
import subprocess
import sys
import uuid
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import IntEnum
from pathlib import Path
from typing import Any, Callable

import psutil
from maa.controller import (
    MaaAdbInputMethodEnum,
    MaaAdbScreencapMethodEnum,
    MaaWin32InputMethodEnum,
    MaaWin32ScreencapMethodEnum,
)
from maa.toolkit import Toolkit

from app.core import Config
from app.models.ConfigBase import MultipleConfig
from app.models.config import MaaFWConfig, MaaFWUserConfig
from app.models.emulator import DeviceBase, DeviceInfo
from app.models.task import LogRecord, ScriptItem, TaskExecuteBase
from app.services import Notify
from app.task.general.tools import execute_script_task
from app.utils import ProcessInfo, ProcessManager, get_logger
from app.utils.constants import UTC4

from .control_capabilities import get_adb_emulator_extra_capability
from .interface_models import MaaFWController, MaaFWInterface
from .interface_loader import load_interface_model_cached
from .run_plan import (
    MaaFWSkippedTaskPlan,
    MaaFWRunPlan,
    MaaFWRunPlanError,
    build_maafw_run_plan,
)
from .runner import MaaFWDeviceConfig, MaaFWRunResult
from .window_service import match_controller_windows, resolve_window_handle


logger = get_logger("MaaFW 自动代理")

_RUNNING_PROJECT_PATHS: set[str] = set()
_RUNNING_PROJECT_PATHS_LOCK = asyncio.Lock()
RUNNER_ENV_MANIFEST_NAME = ".auto_mas_maafw_runner_env.json"
RUNNER_VENV_PACKAGES = ("maafw==5.8.1", "pydantic==2.11.7", "json5==0.14.0")
RUNNER_VENV_TIMEOUT = 300
RUNNER_PIP_TIMEOUT = 300
RUNNER_PROCESS_KILL_TIMEOUT = 5
REQUIREMENT_NAME_RE = re.compile(
    r"^\s*([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)"
    r"\s*(?:\[[^\]]+\])?\s*(?:===|[<>=!~]=?|@|;|\s|$)"
)


@dataclass(frozen=True)
class MaaFWAdbControlProfile:
    emulator_type: str | None
    screencap_extra: bool
    input_extra: bool
    config: dict[str, Any]


class AutoProxyTask(TaskExecuteBase):
    """MaaFW 自动代理模式"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: MaaFWConfig,
        user_config: MultipleConfig[MaaFWUserConfig],
        emulator_manager: DeviceBase | None,
        project_update_logs: list[str] | None = None,
    ):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config
        self.emulator_manager = emulator_manager
        self.project_update_logs = list(project_update_logs or [])
        self.cur_user_item = self.script_info.user_list[self.script_info.current_index]
        self.cur_user_uid = uuid.UUID(self.cur_user_item.user_id)
        self.cur_user_config = self.user_config[self.cur_user_uid]
        self.check_result = "-"
        self.project_path = Path(self.script_config.get("Info", "Path"))
        self.interface_model: MaaFWInterface | None = None
        self.base_run_plan: MaaFWRunPlan | None = None
        self.run_plan: MaaFWRunPlan | None = None
        self.cur_user_log: LogRecord | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.user_start_time = datetime.now()
        self.log_start_time = datetime.now()
        self.run_complete = False
        self.opened_emulator = False
        self.opened_game = False
        self.project_lock_key: str | None = None
        self.runner_process: asyncio.subprocess.Process | None = None
        self.game_process_manager = ProcessManager()
        self._cached_adb_address: str | None = None
        self._cached_adb_path: str | None = None
        self._cached_device_info: DeviceInfo | None = None
        self._cached_adb_profile: MaaFWAdbControlProfile | None = None

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
            return "今日代理次数已达上限, 跳过该用户"

        try:
            self.interface_model = load_interface_model_cached(self.project_path)
        except Exception as exc:
            self.cur_user_item.status = "异常"
            return f"无法读取 MaaFW interface，请检查项目路径: {exc}"

        try:
            self.base_run_plan = self._build_run_plan(self.interface_model)
            self.run_plan = self._filter_period_once_tasks(self.base_run_plan)
        except MaaFWRunPlanError as exc:
            self.cur_user_item.status = "异常"
            return f"无法构造 MaaFW 运行计划: {exc}"

        if not self.run_plan.tasks:
            self.cur_user_item.status = "跳过"
            return "MaaFW 周期任务已在本周或本月完成，跳过本次运行"

        if self.run_plan.controllerType == "Adb":
            emulator_id = self.script_config.get("Emulator", "Id")
            emulator_index = self.script_config.get("Emulator", "Index")
            if emulator_id == "-" or emulator_index in ("", "-"):
                self.cur_user_item.status = "异常"
                return "当前 MaaFW controller 需要 ADB，请在脚本管理页选择模拟器和实例"
        elif self.run_plan.controllerType == "Win32":
            game_path = Path(str(self.script_config.get("Game", "Path") or "").strip())
            if not game_path.is_file():
                self.cur_user_item.status = "异常"
                return "当前 MaaFW controller 需要由 MAS 启动游戏，请在脚本管理页选择实际游戏 exe"

        if not await self._try_enter_project_path():
            self.cur_user_item.status = "跳过"
            message = "同一路径 MaaFW 脚本正在运行，已跳过本次启动"
            self.script_info.log = message
            return message

        return "Pass"

    async def prepare(self) -> None:
        self.user_start_time = datetime.now()
        self.log_start_time = datetime.now()
        self.cur_user_item.log_record[self.log_start_time] = self.cur_user_log = (
            LogRecord()
        )
        if self.project_update_logs:
            self.cur_user_log.content.extend(self.project_update_logs)
            self.script_info.log = "".join(self.cur_user_log.content[-80:])

    async def main_task(self):
        self.curdate = datetime.now(tz=UTC4).strftime("%Y-%m-%d")
        self.check_result = await self.check()
        if self.check_result != "Pass":
            if self.cur_user_item.status == "异常":
                await Config.send_websocket_message(
                    id=self.task_info.task_id,
                    type="Info",
                    data={
                        "Error": f"用户 {self.cur_user_item.name} 检查未通过: {self.check_result}"
                    },
                )
            else:
                self.script_info.log = self.check_result
            return

        await self._mark_run_started()
        await self.prepare()
        if self.run_plan is None or self.interface_model is None:
            raise RuntimeError("MaaFW 运行计划未完成初始化")

        logger.info(f"开始代理用户: {self.cur_user_uid}")
        self.cur_user_item.status = "运行"

        try:
            for i in range(self.script_config.get("Run", "RunTimesLimit")):
                if self.run_complete:
                    break

                self._append_log(
                    f"用户 {self.cur_user_item.name} - 尝试次数: "
                    f"{i + 1}/{self.script_config.get('Run', 'RunTimesLimit')}"
                )

                if self.cur_user_config.get("Info", "IfScriptBeforeTask"):
                    await execute_script_task(
                        Path(self.cur_user_config.get("Info", "ScriptBeforeTask")),
                        "脚本前任务",
                    )

                try:
                    await self._ensure_desktop_game_started()
                    device_config = await self._build_device_config(
                        self.run_plan,
                        self.interface_model,
                    )
                    result = await self._run_maafw(device_config)
                except Exception as exc:
                    self._append_log(f"MaaFW 运行异常: {exc}")
                    if self.cur_user_log is not None:
                        self.cur_user_log.status = f"MaaFW 运行异常: {exc}"
                    await Config.send_websocket_message(
                        id=self.task_info.task_id,
                        type="Info",
                        data={"Error": f"MaaFW 运行异常: {exc}"},
                    )
                    await self._reset_runner_for_retry()
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
                    self._append_log(
                        "MaaFW 任务完成: " + ", ".join(result.completedTasks)
                    )
                else:
                    message = result.errorMessage or "MaaFW 任务失败"
                    if self.cur_user_log is not None:
                        self.cur_user_log.status = message
                    self._append_log(message)
                    self._refresh_run_plan_after_period_update()
                    if self.run_plan is not None and not self.run_plan.tasks:
                        self.run_complete = True
                        self._append_log("MaaFW 剩余周期任务已完成，停止本轮重试")
                    else:
                        await self._reset_runner_for_retry()
        finally:
            await self._shutdown_runner()

    async def _mark_run_started(self) -> None:
        if self.cur_user_config.get("Data", "LastProxyDate") != self.curdate:
            await self.cur_user_config.set("Data", "LastProxyDate", self.curdate)
            await self.cur_user_config.set("Data", "ProxyTimes", 0)
        await self.cur_user_config.set("Data", "LastProxyStatus", "运行中")

    async def final_task(self):
        await self._shutdown_runner()
        if self.check_result != "Pass":
            await self._close_game()
            await self._release_project_path()
            return

        await self._close_emulator()
        await self._close_game()

        user_logs_list = []
        for t, log_item in self.cur_user_item.log_record.items():
            dt = t.replace(tzinfo=datetime.now().astimezone().tzinfo).astimezone(UTC4)
            log_path = (
                Path.cwd()
                / f"history/{dt.strftime('%Y-%m-%d')}/{self.cur_user_item.name}/{dt.strftime('%H-%M-%S')}.log"
            )
            user_logs_list.append(log_path.with_suffix(".json"))

            if not log_item.content:
                log_item.content = ["未捕获到任何 MaaFW 运行日志"]
            if log_item.status == "未开始监看日志":
                log_item.status = "MaaFW 任务被中止"

            await Config.save_general_log(log_path, log_item.content, log_item.status)

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
            logger.success(f"用户 {self.cur_user_uid} 的 MaaFW 任务已完成")
            try:
                await Notify.push_plyer(
                    "成功完成一个 MaaFW 自动代理任务！",
                    f"已完成用户 {self.cur_user_item.name} 的 MaaFW 自动代理任务",
                    f"已完成 {self.cur_user_item.name} 的 MaaFW 自动代理任务",
                    3,
                )
            except Exception as exc:
                logger.warning(f"MaaFW 用户通知发送失败: {exc}")
        else:
            await self.cur_user_config.set("Data", "LastProxyStatus", "失败")
            if self.cur_user_item.status == "运行":
                self.cur_user_item.status = "异常"
            logger.error(f"用户 {self.cur_user_uid} 的 MaaFW 任务未完成")

        await self._release_project_path()

    async def on_crash(self, e: Exception):
        self.cur_user_item.status = "异常"
        logger.exception(f"MaaFW 自动代理任务出现异常: {e}")
        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Info",
            data={"Error": f"MaaFW 自动代理任务出现异常: {e}"},
        )
        await self._shutdown_runner()
        await self._close_emulator()
        await self._close_game()
        await self._release_project_path()

    async def _try_enter_project_path(self) -> bool:
        project_lock_key = _normalize_project_path(self.project_path)
        async with _RUNNING_PROJECT_PATHS_LOCK:
            if project_lock_key in _RUNNING_PROJECT_PATHS:
                return False
            _RUNNING_PROJECT_PATHS.add(project_lock_key)
            self.project_lock_key = project_lock_key
            return True

    async def _release_project_path(self) -> None:
        if self.project_lock_key is None:
            return

        async with _RUNNING_PROJECT_PATHS_LOCK:
            _RUNNING_PROJECT_PATHS.discard(self.project_lock_key)
        self.project_lock_key = None

    def _build_run_plan(self, interface_model: MaaFWInterface) -> MaaFWRunPlan:
        task_snapshot = _load_json_dict(self.cur_user_config.get("Task", "TaskSnapshot"))
        selected_preset = str(self.cur_user_config.get("Task", "SelectedPreset") or "").strip()
        controller_name = self._select_controller_name(interface_model)
        resource_name = self._select_resource_name(interface_model, controller_name)

        return build_maafw_run_plan(
            self.project_path,
            interface_model,
            controller_name=controller_name,
            resource_name=resource_name,
            selected_preset=selected_preset if selected_preset and not task_snapshot else None,
            task_snapshot=task_snapshot or None,
        )

    def _filter_period_once_tasks(self, plan: MaaFWRunPlan) -> MaaFWRunPlan:
        weekly_tasks = set(
            _load_json_list(self.script_config.get("Run", "WeeklyOnceTasks"))
        )
        monthly_tasks = set(
            _load_json_list(self.script_config.get("Run", "MonthlyOnceTasks"))
        )
        if not weekly_tasks and not monthly_tasks:
            return plan

        weekly_key, monthly_key = _current_period_keys()
        records = self._load_period_task_records()
        runnable_tasks = []
        skipped_tasks = []

        for task in plan.tasks:
            weekly_done = (
                task.name in weekly_tasks
                and records["weekly"].get(task.name) == weekly_key
            )
            monthly_done = (
                task.name in monthly_tasks
                and records["monthly"].get(task.name) == monthly_key
            )
            if weekly_done or monthly_done:
                skipped_tasks.append(
                    MaaFWSkippedTaskPlan(
                        name=task.name,
                        label=task.label,
                        entry=task.entry,
                        reason="本月已正常完成" if monthly_done else "本周已正常完成",
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

    def _refresh_run_plan_after_period_update(self) -> None:
        if self.base_run_plan is None:
            return
        self.run_plan = self._filter_period_once_tasks(self.base_run_plan)

    def _load_period_task_records(self) -> dict[str, dict[str, str]]:
        raw_records = _load_json_dict(
            self.cur_user_config.get("Data", "PeriodTaskRecords")
        )
        records: dict[str, dict[str, str]] = {"weekly": {}, "monthly": {}}
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

        weekly_tasks = set(
            _load_json_list(self.script_config.get("Run", "WeeklyOnceTasks"))
        )
        monthly_tasks = set(
            _load_json_list(self.script_config.get("Run", "MonthlyOnceTasks"))
        )
        if not weekly_tasks and not monthly_tasks:
            return

        weekly_key, monthly_key = _current_period_keys()
        completed_task_names = set(completed_tasks)
        records = self._load_period_task_records()
        changed = False

        for task_name in completed_task_names.intersection(weekly_tasks):
            if records["weekly"].get(task_name) != weekly_key:
                records["weekly"][task_name] = weekly_key
                changed = True

        for task_name in completed_task_names.intersection(monthly_tasks):
            if records["monthly"].get(task_name) != monthly_key:
                records["monthly"][task_name] = monthly_key
                changed = True

        if changed:
            await self.cur_user_config.set(
                "Data",
                "PeriodTaskRecords",
                json.dumps(records, ensure_ascii=False),
            )

    def _select_controller_name(self, interface_model: MaaFWInterface) -> str | None:
        configured_controller = str(
            self.script_config.get("Info", "Controller")
            or self.cur_user_config.get("Info", "Controller")
            or ""
        ).strip()

        # 模拟器已选择时，优先使用 ADB controller，忽略用户配置中可能过时的 controller
        wants_adb = self.script_config.get("Emulator", "Id") != "-"
        if wants_adb:
            if configured_controller:
                controller = _find_controller(interface_model, configured_controller)
                if controller.type == "Adb":
                    return controller.name

            adb_controller = next(
                (
                    controller
                    for controller in interface_model.controller
                    if controller.type == "Adb"
                ),
                None,
            )
            if adb_controller is not None:
                return adb_controller.name

        # 无模拟器时，使用用户级 controller 偏好
        if configured_controller:
            return configured_controller

        return None

    def _select_resource_name(
        self,
        interface_model: MaaFWInterface,
        controller_name: str | None,
    ) -> str | None:
        configured_resource = str(
            self.script_config.get("Info", "Resource")
            or self.cur_user_config.get("Info", "Resource")
            or ""
        ).strip()
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
        if plan.controllerType not in {"Adb", "Win32"}:
            raise RuntimeError(
                "AUTO-MAS MaaFW Direct currently supports only Adb/Win32 "
                f"controllers; use the project UI for {plan.controllerType}"
            )

        controller = _find_controller(interface_model, plan.controllerName)

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
            )

        if plan.controllerType == "Win32":
            return MaaFWDeviceConfig(
                type="Win32",
                hWnd=self._resolve_window_handle(controller),
                screencapMethod=self._resolve_win32_screencap_method(controller),
                mouseMethod=self._resolve_win32_input_method(
                    controller.win32.mouse if controller.win32 else None,
                    "Device",
                    "Win32MouseMethod",
                    MaaWin32InputMethodEnum.Seize,
                ),
                keyboardMethod=self._resolve_win32_input_method(
                    controller.win32.keyboard if controller.win32 else None,
                    "Device",
                    "Win32KeyboardMethod",
                    MaaWin32InputMethodEnum.Seize,
                ),
            )

        raise RuntimeError(
            "AUTO-MAS MaaFW Direct currently supports only Adb/Win32 "
            f"controllers; use the project UI for {plan.controllerType}"
        )

    async def _resolve_adb_address(self) -> tuple[str, DeviceInfo | None]:
        if self._cached_adb_address is not None and self._cached_device_info is not None:
            return self._cached_adb_address, self._cached_device_info

        if self.emulator_manager is None:
            raise RuntimeError("当前 controller 需要 ADB，请在脚本管理页选择模拟器")

        emulator_index = self.script_config.get("Emulator", "Index")
        if emulator_index in ("", "-"):
            raise RuntimeError("当前 controller 需要 ADB，请在脚本管理页选择模拟器实例")

        self._append_log(f"正在启动模拟器: {emulator_index}")
        self.opened_emulator = True
        try:
            device_info = await self.emulator_manager.open(emulator_index)
        except Exception as exc:
            self._append_log(f"模拟器启动失败: {exc}")
            raise

        if Config.get("Function", "IfSilence"):
            with suppress(Exception):
                await self.emulator_manager.setVisible(emulator_index, False)

        if not device_info.adb_address or device_info.adb_address == "Unknown":
            raise RuntimeError("模拟器未返回可用 ADB 地址")

        self._append_log(f"模拟器启动完成，ADB 地址: {device_info.adb_address}")
        self._cached_adb_address = device_info.adb_address
        self._cached_device_info = device_info
        return device_info.adb_address, device_info

    async def _resolve_adb_path(
        self,
        address: str,
        device_info: DeviceInfo | None,
    ) -> str:
        if self._cached_adb_path is not None:
            return self._cached_adb_path

        with suppress(Exception):
            for adb_device in Toolkit.find_adb_devices():
                if adb_device.address == address:
                    self._cached_adb_path = str(adb_device.adb_path)
                    return self._cached_adb_path

        derived_path = self._derive_adb_path_from_emulator_config()
        if derived_path and derived_path.exists():
            self._cached_adb_path = str(derived_path)
            return self._cached_adb_path

        configured_path = str(self.script_config.get("Device", "AdbPath") or "").strip()
        if configured_path:
            adb_path = Path(configured_path)
            if adb_path.exists():
                self._cached_adb_path = str(adb_path)
                return self._cached_adb_path

        title = f"（{device_info.title}）" if device_info else ""
        raise RuntimeError(f"无法从模拟器配置找到 ADB 路径{title}，请检查脚本管理页的模拟器配置")

    async def _build_adb_control_profile(self) -> MaaFWAdbControlProfile:
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
            capability = get_adb_emulator_extra_capability(
                self.project_path,
                emulator_type,
            )
            if emulator_type == "ldplayer" and capability.screencap:
                config = await self._build_ldplayer_adb_controller_config(
                    emulator_path,
                    emulator_index,
                )
                self._cached_adb_profile = MaaFWAdbControlProfile(
                    emulator_type,
                    capability.screencap,
                    capability.input,
                    config,
                )
                return self._cached_adb_profile
            if emulator_type == "mumu" and (capability.screencap or capability.input):
                config = self._build_mumu_adb_controller_config(
                    emulator_path,
                    emulator_index,
                )
                self._cached_adb_profile = MaaFWAdbControlProfile(
                    emulator_type,
                    capability.screencap,
                    capability.input,
                    config,
                )
                return self._cached_adb_profile
            self._cached_adb_profile = MaaFWAdbControlProfile(
                emulator_type,
                capability.screencap,
                capability.input,
                {},
            )
            return self._cached_adb_profile
        except Exception as exc:
            logger.warning(f"构造 MaaFW ADB extra 配置失败，使用默认配置: {exc}")

        self._cached_adb_profile = MaaFWAdbControlProfile(None, False, False, {})
        return self._cached_adb_profile

    def _resolve_adb_screencap_methods(self, profile: MaaFWAdbControlProfile) -> int:
        extra_method = int(MaaAdbScreencapMethodEnum.EmulatorExtras)
        if profile.emulator_type in {"ldplayer", "mumu"}:
            default_methods = int(MaaAdbScreencapMethodEnum.Default)
            if profile.screencap_extra:
                return default_methods | extra_method
            return _remove_method(default_methods, extra_method, default_methods)
        return _remove_method(
            int(self.script_config.get("Device", "AdbScreencapMethods")),
            extra_method,
            _remove_method(
                int(MaaAdbScreencapMethodEnum.Default),
                extra_method,
                int(MaaAdbScreencapMethodEnum.Default),
            ),
        )

    def _resolve_adb_input_methods(self, profile: MaaFWAdbControlProfile) -> int:
        extra_input_method = int(MaaAdbInputMethodEnum.EmulatorExtras)
        if profile.emulator_type == "mumu" and profile.input_extra:
            return int(MaaAdbInputMethodEnum.All)
        if profile.emulator_type in {"ldplayer", "mumu"}:
            return int(MaaAdbInputMethodEnum.Default)

        configured = int(self.script_config.get("Device", "AdbInputMethods"))
        if not profile.input_extra:
            return _remove_method(
                configured,
                extra_input_method,
                int(MaaAdbInputMethodEnum.Default),
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

    def _derive_adb_path_from_emulator_config(self) -> Path | None:
        emulator_id = self.script_config.get("Emulator", "Id")
        if emulator_id == "-":
            return None

        with suppress(Exception):
            emulator_config = Config.EmulatorConfig[uuid.UUID(emulator_id)]
            emulator_type = emulator_config.get("Info", "Type")
            emulator_path = Path(emulator_config.get("Info", "Path"))
            if emulator_type == "ldplayer":
                return emulator_path.parent / "adb.exe"
            if emulator_type == "mumu":
                return emulator_path.parent / "adb.exe"
            return emulator_path.parent / "adb.exe"
        return None

    def _resolve_win32_screencap_method(self, controller: MaaFWController) -> int:
        configured = int(self.script_config.get("Device", "Win32ScreencapMethod") or 0)
        if configured:
            return configured
        raw_method = controller.win32.screencap if controller.win32 else None
        return _enum_value(
            MaaWin32ScreencapMethodEnum,
            raw_method,
            MaaWin32ScreencapMethodEnum.DXGI_DesktopDup,
        )

    def _resolve_window_handle(self, controller: MaaFWController) -> int:
        configured_hwnd = (
            self.cur_user_config.get("Device", "HWnd")
            or self.script_config.get("Device", "HWnd")
        )
        return resolve_window_handle(
            controller,
            configured_hwnd,
            send_log=self._append_log,
        )

    def _resolve_win32_input_method(
        self,
        raw_method: str | None,
        group: str,
        name: str,
        default: MaaWin32InputMethodEnum,
    ) -> int:
        configured = int(self.script_config.get(group, name) or 0)
        if configured:
            return configured
        return _enum_value(MaaWin32InputMethodEnum, raw_method, default)

    async def _run_maafw(self, device_config: MaaFWDeviceConfig) -> MaaFWRunResult:
        if self.run_plan is None:
            raise RuntimeError("MaaFW 运行计划未初始化")
        self.loop = asyncio.get_running_loop()
        timeout = self.script_config.get("Run", "RunTimeLimit") * 60
        try:
            return await asyncio.wait_for(
                self._run_maafw_worker(device_config),
                timeout=timeout,
            )
        except asyncio.CancelledError:
            await self._terminate_runner_process()
            raise
        except asyncio.TimeoutError as exc:
            await self._terminate_runner_process()
            raise RuntimeError("MaaFW 任务运行超时") from exc

    async def _run_maafw_worker(
        self,
        device_config: MaaFWDeviceConfig,
    ) -> MaaFWRunResult:
        if self.run_plan is None:
            raise RuntimeError("MaaFW 运行计划未初始化")

        runner_venv = self._runner_venv_path()
        runner_python = await asyncio.to_thread(self._ensure_runner_venv, runner_venv)
        job_path = await asyncio.to_thread(self._write_runner_job, device_config)
        env = self._build_runner_env(runner_venv)
        result: MaaFWRunResult | None = None
        stderr_lines: list[str] = []

        self._append_log(f"MaaFW Runner 使用隔离 venv: {runner_venv}")
        worker_path = Path(__file__).with_name("runner_worker.py")
        process = await asyncio.create_subprocess_exec(
            str(runner_python),
            str(worker_path),
            str(job_path),
            cwd=str(Path.cwd()),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self.runner_process = process

        async def read_stdout() -> None:
            nonlocal result
            if process.stdout is None:
                return
            async for raw_line in process.stdout:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    self._send_runner_log(line)
                    continue

                payload_type = payload.get("type")
                if payload_type == "log":
                    self._send_runner_log(str(payload.get("message", "")))
                elif payload_type == "result":
                    result = MaaFWRunResult.model_validate(payload.get("data"))
                elif payload_type == "error":
                    self._send_runner_log(str(payload.get("message", "")))

        async def read_stderr() -> None:
            if process.stderr is None:
                return
            async for raw_line in process.stderr:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                stderr_lines.append(line)
                del stderr_lines[:-20]

        stdout_task = asyncio.create_task(read_stdout())
        stderr_task = asyncio.create_task(read_stderr())
        try:
            returncode = await process.wait()
            await asyncio.gather(stdout_task, stderr_task)
        finally:
            if process.returncode is None:
                await self._terminate_runner_process()
            elif self.runner_process is process:
                self.runner_process = None
            stdout_task.cancel()
            stderr_task.cancel()
            with suppress(Exception):
                job_path.unlink()

        if result is not None:
            return result

        detail = "\n".join(stderr_lines[-5:]).strip()
        message = f"MaaFW Runner 子进程异常退出: exit={returncode}"
        if detail:
            message += f": {detail}"
        raise RuntimeError(message)

    async def _reset_runner_for_retry(self) -> None:
        await self._terminate_runner_process()

    async def _shutdown_runner(self) -> None:
        await self._terminate_runner_process()
        self._cached_adb_address = None
        self._cached_adb_path = None
        self._cached_device_info = None
        self._cached_adb_profile = None

    async def _terminate_runner_process(self) -> None:
        process = self.runner_process
        self.runner_process = None
        if process is None or process.returncode is not None:
            return

        try:
            process.terminate()
            await asyncio.wait_for(process.wait(), timeout=RUNNER_PROCESS_KILL_TIMEOUT)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
        except ProcessLookupError:
            return
        except Exception as exc:
            logger.warning(f"MaaFW Runner 子进程清理失败: {exc}")

    def _runner_venv_path(self) -> Path:
        return _runner_venv_path(self.project_path)

    def _ensure_runner_venv(self, venv_path: Path) -> Path:
        if self._should_rebuild_runner_venv(venv_path):
            self._reset_runner_venv(venv_path)

        if not _is_valid_venv_path(venv_path):
            venv_path.parent.mkdir(parents=True, exist_ok=True)
            bootstrap_python = _venv_bootstrap_python()
            self._append_log(
                f"[MaaFW Runner] 创建隔离 venv: {venv_path} "
                f"(引导 Python: {bootstrap_python})"
            )
            self._run_setup_command(
                [
                    bootstrap_python,
                    "-m",
                    "venv",
                    str(venv_path),
                ],
                timeout=RUNNER_VENV_TIMEOUT,
                cwd=Path.cwd(),
            )

        runner_python = _venv_python_path(venv_path)
        manifest_path = venv_path / RUNNER_ENV_MANIFEST_NAME
        manifest = self._runner_env_manifest()
        if self._is_runner_manifest_current(manifest_path, manifest):
            return runner_python

        packages = list(manifest["packages"])
        self._append_log(f"[MaaFW Runner] 安装隔离 venv 依赖: {', '.join(packages)}")
        self._run_setup_command(
            [
                str(runner_python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--quiet",
                *packages,
            ],
            timeout=RUNNER_PIP_TIMEOUT,
            cwd=self.project_path,
            env=self._build_runner_env(venv_path),
        )
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return runner_python

    def _should_rebuild_runner_venv(self, venv_path: Path) -> bool:
        if venv_path.exists() and not _is_valid_venv_path(venv_path):
            return True
        return False

    def _reset_runner_venv(self, venv_path: Path) -> None:
        runner_venv_root = Path.cwd() / "config" / "maafw_runner_venvs"
        resolved_root = runner_venv_root.resolve()
        resolved_venv = venv_path.resolve()
        if (
            resolved_venv.parent != resolved_root
            or not resolved_venv.name.startswith("maafw_runner_")
        ):
            raise RuntimeError(f"拒绝重建非托管 MaaFW Runner venv: {venv_path}")
        shutil.rmtree(venv_path, ignore_errors=True)

    def _runner_env_manifest(self) -> dict[str, Any]:
        return _runner_env_manifest(self.project_path)

    @staticmethod
    def _is_runner_manifest_current(
        manifest_path: Path,
        manifest: dict[str, Any],
    ) -> bool:
        try:
            current = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return False
        return current == manifest

    def _write_runner_job(self, device_config: MaaFWDeviceConfig) -> Path:
        if self.run_plan is None:
            raise RuntimeError("MaaFW 运行计划未初始化")

        job_dir = Path.cwd() / "runtime" / "maafw_runner_jobs"
        job_dir.mkdir(parents=True, exist_ok=True)
        job_path = (
            job_dir
            / f"{self.task_info.task_id}_{self.cur_user_uid}_{uuid.uuid4().hex}.json"
        )
        job_path.write_text(
            json.dumps(
                {
                    "plan": self.run_plan.model_dump(mode="json"),
                    "deviceConfig": device_config.model_dump(mode="json"),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return job_path

    def _build_runner_env(self, runner_venv: Path) -> dict[str, str]:
        return _build_runner_env(runner_venv)

    def _run_setup_command(
        self,
        command: list[str],
        *,
        timeout: int,
        cwd: Path,
        env: dict[str, str] | None = None,
    ) -> None:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                timeout=timeout,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=cwd,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"MaaFW Runner 环境命令超时: {command[:3]}") from exc

        if result.returncode == 0:
            return

        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(
            f"MaaFW Runner 环境命令失败 (exit={result.returncode}): {detail[:800]}"
        )

    async def _ensure_desktop_game_started(self) -> None:
        if self.run_plan is None or self.run_plan.controllerType != "Win32":
            return
        if self.opened_game:
            return

        game_path = Path(str(self.script_config.get("Game", "Path") or "").strip())
        if not game_path.is_file():
            raise RuntimeError("当前 MaaFW controller 需要由 MAS 启动游戏，请在脚本管理页选择实际游戏 exe")

        if self.interface_model is not None and self.run_plan is not None:
            controller = _find_controller(
                self.interface_model,
                self.run_plan.controllerName,
            )
            matches = match_controller_windows(controller)
            if matches:
                selected = matches[0]
                self._append_log(
                    "检测到游戏客户端窗口: "
                    f"hWnd={selected.hWnd}, class={selected.className}, "
                    f"title={selected.windowName}"
                )
                await self._activate_desktop_game_window(game_path)
                return

        if _is_process_path_running(game_path):
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

        configured_hwnd = (
            self.cur_user_config.get("Device", "HWnd")
            or self.script_config.get("Device", "HWnd")
        )
        explicit_hwnd = _optional_int(configured_hwnd)
        controller = _find_controller(self.interface_model, self.run_plan.controllerName)

        self._append_log(
            f"正在等待游戏客户端窗口就绪，最大等待时间 {wait_time}s: {game_path.name}"
        )
        if wait_time <= 0:
            if not _is_process_path_running(game_path):
                raise RuntimeError(f"游戏进程未启动: {game_path.name}")
            if explicit_hwnd:
                self._append_log(f"已配置窗口句柄，跳过窗口正则等待: {explicit_hwnd}")
                return
            if not match_controller_windows(controller):
                raise RuntimeError(f"游戏窗口未就绪: {game_path.name}")
            return

        waited = 0.0
        process_detected = False
        while waited < wait_time:
            if not explicit_hwnd:
                matches = match_controller_windows(controller)
                if matches:
                    selected = matches[0]
                    self._append_log(
                        "检测到游戏客户端窗口: "
                        f"hWnd={selected.hWnd}, class={selected.className}, "
                        f"title={selected.windowName}"
                    )
                    return

            if _is_process_path_running(game_path):
                if not process_detected:
                    self._append_log(f"检测到游戏进程已启动: {game_path.name}")
                    process_detected = True

                if explicit_hwnd:
                    self._append_log(f"已配置窗口句柄，跳过窗口正则等待: {explicit_hwnd}")
                    return

                matches = match_controller_windows(controller)
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
            matches = match_controller_windows(controller)
            if matches:
                selected = matches[0]
                self._append_log(
                    "检测到游戏客户端窗口: "
                    f"hWnd={selected.hWnd}, class={selected.className}, "
                    f"title={selected.windowName}"
                )
                return

        if _is_process_path_running(game_path):
            if explicit_hwnd:
                self._append_log(f"已配置窗口句柄，跳过窗口正则等待: {explicit_hwnd}")
                return

            matches = match_controller_windows(controller)
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
            await self.game_process_manager.search_process(
                ProcessInfo(exe=str(game_path.resolve())),
                datetime.now() + timedelta(seconds=5),
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

    async def _close_emulator(self) -> None:
        if not self.opened_emulator or self.emulator_manager is None:
            return

        try:
            await self.emulator_manager.close(self.script_config.get("Emulator", "Index"))
            self.opened_emulator = False
        except Exception as exc:
            logger.warning(f"MaaFW 清理时关闭模拟器失败: {exc}")

    def _send_runner_log(self, message: str) -> None:
        if self.cur_user_log is not None:
            self.cur_user_log.content.append(self._format_user_log_line(message))
        if self.loop is not None and not self.loop.is_closed():
            with suppress(RuntimeError):
                self.loop.call_soon_threadsafe(self._publish_runner_log, message)

    def _publish_runner_log(self, message: str) -> None:
        if self.cur_user_log is None:
            self.script_info.log = message
            return
        self.script_info.log = "".join(self.cur_user_log.content[-80:])

    def _publish_log_update(self, message: str) -> None:
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            if self.loop is not None and not self.loop.is_closed():
                with suppress(RuntimeError):
                    self.loop.call_soon_threadsafe(self._publish_runner_log, message)
            return

        if self.loop is None or running_loop is self.loop:
            self._publish_runner_log(message)
            return

        with suppress(RuntimeError):
            self.loop.call_soon_threadsafe(self._publish_runner_log, message)

    def _append_log(self, message: str) -> None:
        logger.info(message)
        if self.cur_user_log is not None:
            self.cur_user_log.content.append(self._format_user_log_line(message))
        self._publish_log_update(message)

    @staticmethod
    def _format_user_log_line(message: str) -> str:
        timestamp = datetime.now().astimezone().strftime("%H:%M:%S")
        lines = str(message).splitlines() or [""]
        return "".join(f"[{timestamp}] {line}\n" for line in lines)


def _load_json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        with suppress(json.JSONDecodeError):
            data = json.loads(value)
            if isinstance(data, dict):
                return data
    return {}


def _load_requirements_file(project_path: Path) -> list[str]:
    requirements_path = project_path / "requirements.txt"
    packages: list[str] = []
    try:
        with requirements_path.open("r", encoding="utf-8") as file:
            for raw_line in file:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                packages.append(line)
    except FileNotFoundError:
        pass
    return packages


def prepare_maafw_runner_env(
    project_path: str | Path,
    *,
    send_log: Callable[[str], None] | None = None,
) -> Path:
    resolved_project_path = Path(project_path).resolve()
    venv_path = _runner_venv_path(resolved_project_path)
    return _prepare_runner_venv(
        resolved_project_path,
        venv_path,
        send_log=send_log,
    )


def _runner_venv_path(project_path: Path) -> Path:
    project_key = str(project_path.resolve()).lower()
    digest = hashlib.sha256(project_key.encode("utf-8")).hexdigest()[:16]
    return Path.cwd() / "config" / "maafw_runner_venvs" / f"maafw_runner_{digest}"


def _prepare_runner_venv(
    project_path: Path,
    venv_path: Path,
    *,
    send_log: Callable[[str], None] | None,
) -> Path:
    if _should_rebuild_runner_venv_path(venv_path):
        _reset_runner_venv_path(venv_path)

    if not _is_valid_venv_path(venv_path):
        venv_path.parent.mkdir(parents=True, exist_ok=True)
        bootstrap_python = _venv_bootstrap_python()
        _send_runner_env_log(
            send_log,
            f"[MaaFW Runner] 创建隔离 venv: {venv_path} "
            f"(引导 Python: {bootstrap_python})",
        )
        _run_runner_setup_command(
            [
                bootstrap_python,
                "-m",
                "venv",
                str(venv_path),
            ],
            timeout=RUNNER_VENV_TIMEOUT,
            cwd=Path.cwd(),
        )

    runner_python = _venv_python_path(venv_path)
    manifest_path = venv_path / RUNNER_ENV_MANIFEST_NAME
    manifest = _runner_env_manifest(project_path)
    if _is_runner_env_manifest_current(manifest_path, manifest):
        _send_runner_env_log(send_log, f"[MaaFW Runner] 隔离 venv 已就绪: {venv_path}")
        return runner_python

    packages = list(manifest["packages"])
    _send_runner_env_log(
        send_log,
        f"[MaaFW Runner] 安装隔离 venv 依赖: {', '.join(packages)}",
    )
    _run_runner_setup_command(
        [
            str(runner_python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--quiet",
            *packages,
        ],
        timeout=RUNNER_PIP_TIMEOUT,
        cwd=project_path,
        env=_build_runner_env(venv_path),
    )
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _send_runner_env_log(send_log, f"[MaaFW Runner] 隔离 venv 依赖已准备: {venv_path}")
    return runner_python


def _should_rebuild_runner_venv_path(venv_path: Path) -> bool:
    return venv_path.exists() and not _is_valid_venv_path(venv_path)


def _reset_runner_venv_path(venv_path: Path) -> None:
    runner_venv_root = Path.cwd() / "config" / "maafw_runner_venvs"
    resolved_root = runner_venv_root.resolve()
    resolved_venv = venv_path.resolve()
    if (
        resolved_venv.parent != resolved_root
        or not resolved_venv.name.startswith("maafw_runner_")
    ):
        raise RuntimeError(f"拒绝重建非托管 MaaFW Runner venv: {venv_path}")
    shutil.rmtree(venv_path, ignore_errors=True)


def _runner_env_manifest(project_path: Path) -> dict[str, Any]:
    project_requirements = _load_requirements_file(project_path)
    return {
        "schemaVersion": 2,
        "projectPath": str(project_path.resolve()),
        "packages": _merge_runner_requirements(
            RUNNER_VENV_PACKAGES,
            project_requirements,
        ),
        "projectRequirements": project_requirements,
        "pythonVersion": f"{sys.version_info.major}.{sys.version_info.minor}",
    }


def _is_runner_env_manifest_current(
    manifest_path: Path,
    manifest: dict[str, Any],
) -> bool:
    try:
        current = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return current == manifest


def _build_runner_env(runner_venv: Path) -> dict[str, str]:
    env = os.environ.copy()
    for name in (
        "PYTHONHOME",
        "PYTHONUSERBASE",
        "PIP_TARGET",
        "PIP_PREFIX",
        "PIP_USER",
    ):
        env.pop(name, None)

    scripts_dir = runner_venv / ("Scripts" if os.name == "nt" else "bin")
    repo_root = str(Path.cwd())
    python_path = env.get("PYTHONPATH")
    env["VIRTUAL_ENV"] = str(runner_venv)
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PATH"] = f"{scripts_dir}{os.pathsep}{env.get('PATH', '')}"
    env["PYTHONPATH"] = (
        f"{repo_root}{os.pathsep}{python_path}" if python_path else repo_root
    )
    return env


def _run_runner_setup_command(
    command: list[str],
    *,
    timeout: int,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> None:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            timeout=timeout,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"MaaFW Runner 环境命令超时: {command[:3]}") from exc

    if result.returncode == 0:
        return

    detail = (result.stderr or result.stdout or "").strip()
    raise RuntimeError(
        f"MaaFW Runner 环境命令失败 (exit={result.returncode}): {detail[:800]}"
    )


def _send_runner_env_log(
    send_log: Callable[[str], None] | None,
    message: str,
) -> None:
    if send_log is not None:
        send_log(message)


def _merge_runner_requirements(
    default_packages: tuple[str, ...],
    project_packages: list[str],
) -> list[str]:
    project_package_names = {
        name
        for package in project_packages
        if (name := _requirement_distribution_name(package)) is not None
    }
    packages = [
        package
        for package in default_packages
        if _requirement_distribution_name(package) not in project_package_names
    ]
    packages.extend(project_packages)
    return packages


def _requirement_distribution_name(requirement: str) -> str | None:
    match = REQUIREMENT_NAME_RE.match(requirement)
    if match is None:
        return None
    return re.sub(r"[-_.]+", "-", match.group(1)).lower()


def _venv_python_path(venv_path: Path) -> Path:
    if os.name == "nt":
        return venv_path / "Scripts" / "python.exe"
    return venv_path / "bin" / "python"


def _is_valid_venv_path(venv_path: Path) -> bool:
    return _venv_python_path(venv_path).is_file() and (venv_path / "pyvenv.cfg").is_file()


def _venv_bootstrap_python() -> str:
    portable_python = Path.cwd() / "environment" / "python" / "python.exe"
    if portable_python.is_file():
        return str(portable_python)
    return sys.executable


def _is_process_path_running(executable_path: Path) -> bool:
    target_path = executable_path.resolve()
    for proc in psutil.process_iter(["exe"]):
        with suppress(psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            raw_exe = proc.info.get("exe") or proc.exe()
            if raw_exe and Path(raw_exe).resolve() == target_path:
                return True
    return False


def _load_json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        with suppress(json.JSONDecodeError):
            data = json.loads(value)
            if isinstance(data, list):
                return [str(item) for item in data if str(item).strip()]
    return []


def _current_period_keys() -> tuple[str, str]:
    now = datetime.now(tz=UTC4)
    iso_year, iso_week, _ = now.date().isocalendar()
    return f"{iso_year}-W{iso_week:02d}", now.strftime("%Y-%m")


def _normalize_project_path(path: Path) -> str:
    normalized = str(path.resolve()).rstrip("\\/")
    return normalized.lower() if os.name == "nt" else normalized


def _find_controller(
    interface_model: MaaFWInterface,
    controller_name: str,
) -> MaaFWController:
    controller = next(
        (
            item
            for item in interface_model.controller
            if item.name == controller_name
        ),
        None,
    )
    if controller is None:
        raise RuntimeError(f"未找到 controller: {controller_name}")
    return controller


def _optional_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed or None


def _enum_value(
    enum_class: type[IntEnum],
    raw_name: str | None,
    default: IntEnum,
) -> int:
    if not raw_name:
        return int(default)
    item = enum_class.__members__.get(raw_name)
    if item is None:
        return int(default)
    return int(item)


def _remove_method(methods: int, method: int, fallback: int) -> int:
    filtered = methods & ~method
    return filtered or fallback
