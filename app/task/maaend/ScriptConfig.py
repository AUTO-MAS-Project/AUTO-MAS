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

#   Contact: DLmaster_361@163.com

import asyncio
import json
import shutil
import uuid
from pathlib import Path

from app.core import Config
from app.models.ConfigBase import MultipleConfig
from app.models.config import MaaEndConfig, MaaEndUserConfig
from app.models.task import ScriptItem, TaskExecuteBase
from app.services import System
from app.utils import ProcessManager, get_logger

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
    """MaaEnd 配置接管任务。"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: MaaEndConfig,
        user_config: MultipleConfig[MaaEndUserConfig],
    ):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config
        self.cur_user_item = self.script_info.user_list[self.script_info.current_index]

    async def prepare(self):

        self.process_manager = ProcessManager()

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
        logger.info(f"启动 MaaEnd 配置流程: {self.maaend_exe_path}")
        await self.process_manager.open_process(self.maaend_exe_path)
        await self._wait_for_exit()

    async def _wait_for_exit(self):
        while await self.process_manager.is_running():
            await asyncio.sleep(0.5)

    @staticmethod
    def _load_seed_config(path: Path) -> dict | None:
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            logger.warning(f"读取 seed 配置失败，跳过: {path} ({e})")
            return None
        if not isinstance(loaded, dict):
            logger.warning(f"seed 配置根节点不是对象，跳过: {path}")
            return None
        return loaded

    @staticmethod
    def _is_usable_seed(config_data: dict) -> bool:
        instances = config_data.get("instances")
        if not isinstance(instances, list) or not instances:
            return False

        for instance in instances:
            if not isinstance(instance, dict):
                continue
            resource_name = str(instance.get("resourceName", "")).strip()
            tasks = instance.get("tasks")
            if resource_name and isinstance(tasks, list):
                return True
        return False

    async def set_maaend(self):
        """打开 MaaEnd 配置界面前，先准备本地托管配置。"""

        await self.process_manager.kill()
        await System.kill_process(self.maaend_exe_path)

        # 先缓存一份现有本地配置，避免 seed 缺失时写入过瘦配置导致 MaaEnd 前端异常。
        local_fallback_config: dict | None = None
        if self.maaend_config_path.exists():
            local_fallback_config = self._load_seed_config(self.maaend_config_path)

        # 配置接管：清理 MaaEnd 原有 config，再注入 AUTO-MAS 托管配置
        if self.maaend_config_dir.exists():
            shutil.rmtree(self.maaend_config_dir, ignore_errors=True)
        self.maaend_config_dir.mkdir(parents=True, exist_ok=True)

        mode = "简洁"
        if self.cur_user_item.user_id != "Default":
            mode = str(
                self.user_config[uuid.UUID(self.cur_user_item.user_id)].get(
                    "Info", "Mode"
                )
                or "简洁"
            ).strip()
        if mode == "详细":
            seed_candidates = [
                self.user_managed_config_path,
                self.default_managed_config_path,
            ]
        else:
            seed_candidates = [self.default_managed_config_path]
        for seed_path in seed_candidates:
            if not seed_path.exists():
                continue
            seed_data = self._load_seed_config(seed_path)
            if seed_data is None:
                continue
            if not self._is_usable_seed(seed_data):
                logger.warning(f"seed 配置结构不完整，跳过: {seed_path}")
                continue
            self.maaend_config_path.write_text(
                json.dumps(seed_data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            self._normalize_to_single_managed_instance()
            return

        if local_fallback_config is not None and self._is_usable_seed(local_fallback_config):
            self.maaend_config_path.write_text(
                json.dumps(local_fallback_config, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        else:
            # 保底配置至少提供实例与任务数组，避免 MaaEnd 前端在读取时访问 undefined.filter
            server = "Official"
            if self.cur_user_item.user_id != "Default":
                server = str(
                    self.user_config[uuid.UUID(self.cur_user_item.user_id)].get(
                        "Info", "Server"
                    )
                    or "Official"
                ).strip()
            resource_name = "B服" if server == "Bilibili" else "官服"
            self.maaend_config_path.write_text(
                json.dumps(
                    {
                        "version": "1.0",
                        "instances": [
                            {
                                "id": MANAGED_INSTANCE_ID,
                                "name": MANAGED_INSTANCE_NAME,
                                "controllerName": "Win32-Window",
                                "resourceName": resource_name,
                                "savedDevice": {"windowName": "Endfield"},
                                "tasks": [],
                            }
                        ],
                        "lastActiveInstanceId": MANAGED_INSTANCE_ID,
                        "settings": {},
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        self._normalize_to_single_managed_instance()

    def _normalize_to_single_managed_instance(self):
        """将 MaaEnd 本地配置收敛为单个托管实例。"""

        config_data: dict = {}
        if self.maaend_config_path.exists():
            try:
                loaded = json.loads(self.maaend_config_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    config_data = loaded
            except json.JSONDecodeError as e:
                raise ValueError(
                    f"MaaEnd 配置文件不是合法 JSON: {self.maaend_config_path}"
                ) from e

        selected_instance: dict = {}
        instances = config_data.get("instances", [])
        if isinstance(instances, list):
            active_id = str(config_data.get("lastActiveInstanceId", "")).strip()
            if active_id:
                for instance in instances:
                    if (
                        isinstance(instance, dict)
                        and str(instance.get("id", "")).strip() == active_id
                    ):
                        selected_instance = dict(instance)
                        break
            if not selected_instance:
                for instance in instances:
                    if isinstance(instance, dict):
                        selected_instance = dict(instance)
                        break

        selected_instance["id"] = MANAGED_INSTANCE_ID
        selected_instance["name"] = MANAGED_INSTANCE_NAME
        if not isinstance(selected_instance.get("tasks"), list):
            selected_instance["tasks"] = []
        config_data["instances"] = [selected_instance]
        config_data["lastActiveInstanceId"] = MANAGED_INSTANCE_ID
        self.maaend_config_path.write_text(
            json.dumps(config_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @staticmethod
    def _prune_cache_dir(managed_path: Path):
        """清理缓存目录，仅保留托管配置文件。"""

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
        allowed = {
            "Win32-Window-Background",
            "Win32-Window",
            "Win32-Front",
            "ADB",
        }
        return controller_name if controller_name in allowed else None

    async def _readback_config(self):
        if not self.maaend_config_path.exists():
            raise FileNotFoundError(
                f"未找到 MaaEnd 配置文件: {self.maaend_config_path}"
            )

        config_data = json.loads(self.maaend_config_path.read_text(encoding="utf-8"))
        instances = config_data.get("instances", [])
        if not instances:
            raise ValueError("托管配置中不存在 MaaEnd 实例")

        active_id = config_data.get("lastActiveInstanceId")
        selected_instance = next(
            (instance for instance in instances if instance.get("id") == active_id),
            None,
        )
        if selected_instance is None:
            selected_instance = instances[0]

        configured_controller = str(
            self.script_config.get("Run", "ControllerType") or ""
        ).strip()
        controller_type = self._normalize_controller_type(configured_controller)

        was_locked = self.script_config.is_locked
        if was_locked:
            await self.script_config.unlock()
        try:
            if controller_type is not None:
                selected_instance["controllerName"] = controller_type
                config_data["instances"] = instances
                self.maaend_config_path.write_text(
                    json.dumps(config_data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            elif configured_controller:
                logger.warning(
                    f"脚本配置中的控制器类型暂不受支持: {configured_controller}"
                )
        finally:
            if was_locked:
                await self.script_config.lock()

    async def final_task(self):

        await self.process_manager.kill()
        await System.kill_process(self.maaend_exe_path)

        self._normalize_to_single_managed_instance()
        await self._readback_config()

        user_mode = "简洁"
        if self.cur_user_item.user_id != "Default":
            user_mode = str(
                self.user_config[uuid.UUID(self.cur_user_item.user_id)].get(
                    "Info", "Mode"
                )
                or "简洁"
            ).strip()

        if self.cur_user_item.user_id == "Default" or user_mode == "简洁":
            self.default_managed_config_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(self.maaend_config_path, self.default_managed_config_path)
            self._prune_cache_dir(self.default_managed_config_path)
        elif user_mode == "详细":
            self.user_managed_config_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(self.maaend_config_path, self.user_managed_config_path)
            self._prune_cache_dir(self.user_managed_config_path)

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
            runtime_source_path = (
                self.user_managed_config_path
                if user_mode == "详细"
                else self.default_managed_config_path
            )
            runtime_path = build_runtime_config(
                self.script_info.script_id,
                self.cur_user_item.user_id,
                self.script_config,
                runtime_user_cfg,
                source_path=runtime_source_path,
            )
            logger.info(f"已生成 MaaEnd 运行时配置: {runtime_path}")

        self.cur_user_item.status = "完成"

    async def on_crash(self, e: Exception):
        self.cur_user_item.status = "异常"
        logger.exception(f"MaaEnd 配置接管任务执行失败: {e}")
        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Info",
            data={"Error": f"MaaEnd 配置接管任务执行失败: {e}"},
        )
