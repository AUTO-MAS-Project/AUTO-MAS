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
from .paths import (
    LOCAL_CONFIG_NAME,
    managed_default_config_path,
    managed_user_config_path,
)
from .runtime_bridge import build_runtime_config


logger = get_logger("MaaEnd ScriptConfig")
MANAGED_INSTANCE_ID = "AUTO-MAS"
MANAGED_INSTANCE_NAME = "AUTO-MAS"


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
        self.maaend_config_dir = self.maaend_root_path / "config"
        self.maaend_config_path = self.maaend_config_dir / LOCAL_CONFIG_NAME
        self.user_managed_config_path = managed_user_config_path(
            self.script_info.script_id, self.cur_user_item.user_id
        )
        self.default_managed_config_path = managed_default_config_path(
            self.script_info.script_id
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

        # 配置接管：清理 MaaEnd 原有 config，再注入 AUTO-MAS 托管配置
        if self.maaend_config_dir.exists():
            shutil.rmtree(self.maaend_config_dir, ignore_errors=True)
        self.maaend_config_dir.mkdir(parents=True, exist_ok=True)

        seed_candidates = [
            self.user_managed_config_path,
            self.default_managed_config_path,
        ]
        for seed_path in seed_candidates:
            if seed_path.exists():
                shutil.copy(seed_path, self.maaend_config_path)
                self._normalize_to_single_managed_instance()
                return

        self.maaend_config_path.write_text(
            json.dumps({"instances": []}, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._normalize_to_single_managed_instance()

    def _normalize_to_single_managed_instance(self):
        """Force local MaaEnd config to a single managed instance."""

        config_data: dict = {}
        if self.maaend_config_path.exists():
            try:
                loaded = json.loads(self.maaend_config_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    config_data = loaded
            except Exception:
                config_data = {}

        selected_instance: dict = {}
        instances = config_data.get("instances", [])
        if isinstance(instances, list):
            active_id = str(config_data.get("lastActiveInstanceId", "")).strip()
            if active_id:
                for instance in instances:
                    if isinstance(instance, dict) and str(instance.get("id", "")).strip() == active_id:
                        selected_instance = dict(instance)
                        break
            if not selected_instance:
                for instance in instances:
                    if isinstance(instance, dict):
                        selected_instance = dict(instance)
                        break

        selected_instance["id"] = MANAGED_INSTANCE_ID
        selected_instance["name"] = MANAGED_INSTANCE_NAME
        config_data["instances"] = [selected_instance]
        config_data["lastActiveInstanceId"] = MANAGED_INSTANCE_ID
        self.maaend_config_path.write_text(
            json.dumps(config_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @staticmethod
    def _prune_cache_dir(managed_path: Path):
        """Keep only managed config file in cache directory."""

        cache_dir = managed_path.parent
        cache_dir.mkdir(parents=True, exist_ok=True)
        for child in cache_dir.iterdir():
            if child == managed_path:
                continue
            if child.is_file():
                child.unlink(missing_ok=True)
            elif child.is_dir():
                shutil.rmtree(child, ignore_errors=True)

    @staticmethod
    def _normalize_controller_type(controller_name: str) -> str | None:
        if controller_name == "Win32-Window-Background":
            return "Win32-Window-Background"
        if controller_name == "Win32-Window":
            return "Win32-Window"
        if controller_name == "Win32-Front":
            return "Win32-Front"
        if controller_name == "ADB":
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
            raise ValueError("No MaaEnd instances in managed config")

        active_id = config_data.get("lastActiveInstanceId")
        selected_instance = next(
            (instance for instance in instances if instance.get("id") == active_id), None
        )
        if selected_instance is None:
            selected_instance = instances[0]

        resource_name = str(selected_instance.get("resourceName", "")).strip()
        controller_name = str(selected_instance.get("controllerName", "")).strip()
        controller_type = self._normalize_controller_type(controller_name)

        was_locked = self.script_config.is_locked
        if was_locked:
            await self.script_config.unlock()
        try:
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

        self._normalize_to_single_managed_instance()
        await self._readback_config()

        self.user_managed_config_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(self.maaend_config_path, self.user_managed_config_path)
        self._prune_cache_dir(self.user_managed_config_path)

        if self.cur_user_item.user_id == "Default":
            self.default_managed_config_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(self.maaend_config_path, self.default_managed_config_path)
            self._prune_cache_dir(self.default_managed_config_path)

        was_locked = self.script_config.is_locked
        if was_locked:
            await self.script_config.unlock()
        try:
            await self.script_config.set("MaaEnd", "ConfigLocked", True)
        finally:
            if was_locked:
                await self.script_config.lock()

        if self.cur_user_item.user_id != "Default":
            runtime_user_cfg = self.user_config[uuid.UUID(self.cur_user_item.user_id)]
            runtime_path = build_runtime_config(
                self.script_info.script_id,
                self.cur_user_item.user_id,
                self.script_config,
                runtime_user_cfg,
                source_path=self.user_managed_config_path,
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
