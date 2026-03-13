#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright (C) 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

import json
import uuid
import shutil
import asyncio
from pathlib import Path

from app.core import Config
from app.models.task import TaskExecuteBase, ScriptItem
from app.models.ConfigBase import MultipleConfig
from app.models.config import MaaEndConfig, MaaEndUserConfig
from app.services import System
from app.utils import get_logger, ProcessManager
from .runtime_bridge import build_runtime_config


logger = get_logger("MaaEnd ScriptConfig")


class ScriptConfigTask(TaskExecuteBase):
    """MaaEnd script config session."""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: MaaEndConfig,
        user_config: MultipleConfig[MaaEndUserConfig],
    ):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem is not bound to TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config
        self.cur_user_item = self.script_info.user_list[self.script_info.current_index]

    async def prepare(self):

        self.process_manager = ProcessManager()
        self.wait_event = asyncio.Event()

        self.maaend_root_path = Path(self.script_config.get("Info", "Path"))
        self.maaend_exe_path = self.maaend_root_path / "MaaEnd.exe"
        self.maaend_config_path = self.maaend_root_path / "config" / "mxu-MaaEnd.json"
        self.user_config_cache_path = (
            Path.cwd()
            / f"data/{self.script_info.script_id}/{self.cur_user_item.user_id}/ConfigFile/mxu-MaaEnd.json"
        )

    async def main_task(self):

        await self.prepare()

        await self.set_maaend()
        logger.info(f"Start MaaEnd config process: {self.maaend_exe_path}")
        self.wait_event.clear()
        await self.process_manager.open_process(self.maaend_exe_path)
        await self._wait_for_exit_or_confirm()

    async def _wait_for_exit_or_confirm(self):
        while True:
            if self.wait_event.is_set():
                return
            if not await self.process_manager.is_running():
                return
            await asyncio.sleep(0.5)

    async def set_maaend(self):
        """Prepare MaaEnd local config before opening the external config UI."""

        await self.process_manager.kill()
        await System.kill_process(self.maaend_exe_path)

        if self.user_config_cache_path.exists():
            self.maaend_config_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(self.user_config_cache_path, self.maaend_config_path)

    @staticmethod
    def _normalize_controller_type(controller_name: str) -> str | None:
        controller_name = controller_name.lower()
        if controller_name.startswith("win32-window-background"):
            return "Win32-Window-Background"
        if controller_name.startswith("win32-window"):
            return "Win32-Window"
        if controller_name.startswith("win32-front"):
            return "Win32-Front"
        if controller_name.startswith("adb"):
            return "ADB"
        return None

    async def _readback_config(self):
        if not self.maaend_config_path.exists():
            raise FileNotFoundError(
                f"MaaEnd config file not found: {self.maaend_config_path}"
            )

        config_data = json.loads(self.maaend_config_path.read_text(encoding="utf-8"))
        instances = config_data.get("instances", [])
        if not instances:
            raise ValueError("No MaaEnd instances in mxu-MaaEnd.json")

        active_id = config_data.get("lastActiveInstanceId")
        selected_instance = next(
            (instance for instance in instances if instance.get("id") == active_id), None
        )
        if selected_instance is None:
            selected_instance = instances[0]

        preset_id = str(selected_instance.get("id", "")).strip()
        resource_name = str(selected_instance.get("resourceName", "")).strip()
        controller_name = str(selected_instance.get("controllerName", "")).strip()
        controller_type = self._normalize_controller_type(controller_name)

        was_locked = self.script_config.is_locked
        if was_locked:
            await self.script_config.unlock()
        try:
            if preset_id:
                await self.script_config.set("MaaEnd", "PresetTask", preset_id)

                if self.cur_user_item.user_id != "Default":
                    user_uid = uuid.UUID(self.cur_user_item.user_id)
                    await self.user_config[user_uid].set(
                        "Task", "PresetOverride", preset_id
                    )

            if resource_name:
                await self.script_config.set("MaaEnd", "ResourceProfile", resource_name)

            if controller_type is not None:
                await self.script_config.set("Run", "ControllerType", controller_type)
            elif controller_name:
                logger.warning(f"Unsupported MaaEnd controllerName: {controller_name}")
        finally:
            if was_locked:
                await self.script_config.lock()

    async def final_task(self):

        await self.process_manager.kill()
        await System.kill_process(self.maaend_exe_path)

        await self._readback_config()

        self.user_config_cache_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(self.maaend_config_path, self.user_config_cache_path)

        if self.cur_user_item.user_id != "Default":
            runtime_user_cfg = self.user_config[uuid.UUID(self.cur_user_item.user_id)]
            runtime_path = build_runtime_config(
                self.script_info.script_id,
                self.cur_user_item.user_id,
                self.script_config,
                runtime_user_cfg,
            )
            logger.info(f"MaaEnd runtime config generated: {runtime_path}")

        self.cur_user_item.status = "完成"

    async def on_crash(self, e: Exception):
        self.cur_user_item.status = "异常"
        logger.exception(f"MaaEnd script config task failed: {e}")
        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Info",
            data={"Error": f"MaaEnd script config task failed: {e}"},
        )
