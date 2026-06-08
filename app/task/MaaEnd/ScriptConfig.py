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


import json
import shutil
import asyncio
from pathlib import Path
from typing import Any

from app.core import Config
from app.models.task import TaskExecuteBase, ScriptItem
from app.models.ConfigBase import MultipleConfig
from app.models.config import MaaEndConfig, MaaEndUserConfig
from app.models.emulator import DeviceBase
from app.services import System
from app.utils import get_logger, ProcessManager

logger = get_logger("MaaEnd 脚本设置")


def normalize_maaend_config(
    maaend_set: dict[str, Any],
    controller_type: str,
    template_set: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """将 MaaEnd 配置收束为 AUTO-MAS 单实例配置"""

    def select_instance(source_set: dict[str, Any]) -> dict[str, Any] | None:
        instances = source_set.get("instances")
        if not isinstance(instances, list) or len(instances) == 0:
            return None

        last_active_instance_id = source_set.get("lastActiveInstanceId")
        for instance in instances:
            if isinstance(instance, dict) and instance.get("id") == last_active_instance_id:
                return instance

        for instance in instances:
            if isinstance(instance, dict):
                return instance
        return None

    selected_instance = select_instance(maaend_set)
    if selected_instance is None and template_set is not None:
        selected_instance = select_instance(template_set)
    if selected_instance is None:
        raise ValueError("MaaEnd 配置文件中未找到可用实例")

    selected_instance["id"] = "automas"
    selected_instance["name"] = "AUTO-MAS"
    selected_instance.pop("customName", None)
    selected_instance["controllerName"] = controller_type
    selected_instance.setdefault("tasks", [])

    maaend_set["instances"] = [selected_instance]
    maaend_set["lastActiveInstanceId"] = "automas"
    return maaend_set


class ScriptConfigTask(TaskExecuteBase):
    """MaaEnd 脚本设置模式"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: MaaEndConfig,
        user_config: MultipleConfig[MaaEndUserConfig],
        emulator_manager: DeviceBase | None,
    ):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.cur_user_item = self.script_info.user_list[self.script_info.current_index]

    async def prepare(self):

        self.maaend_process_manager = ProcessManager()
        self.wait_event = asyncio.Event()

        self.maaend_root_path = Path(self.script_config.get("Info", "Path"))
        self.maaend_set_path = self.maaend_root_path / "config"
        self.maaend_exe_path = self.maaend_root_path / "MaaEnd.exe"
        self.config_file_path = (
            Path.cwd()
            / f"data/{self.script_info.script_id}/{self.cur_user_item.user_id}/ConfigFile"
        )

    async def main_task(self):

        await self.prepare()

        await self.set_maaend()
        logger.info(f"启动 MaaEnd 进程: {self.maaend_exe_path}")
        self.wait_event.clear()
        await self.maaend_process_manager.open_process(self.maaend_exe_path)
        await self.wait_event.wait()

    async def set_maaend(self):
        """配置 MaaEnd 运行参数"""

        logger.info(f"开始配置 MaaEnd 运行参数: 设置脚本 {self.cur_user_item.user_id}")

        await self.maaend_process_manager.kill()
        await System.kill_process(self.maaend_exe_path)

        if (self.config_file_path / "mxu-MaaEnd.json").exists():
            shutil.rmtree(self.maaend_set_path, ignore_errors=True)
            shutil.copytree(self.config_file_path, self.maaend_set_path)
        else:
            maaend_template_path = (
                Path.cwd() / "res/templates/MaaEnd/config/mxu-MaaEnd.json"
            )
            if maaend_template_path.exists():
                shutil.rmtree(self.maaend_set_path, ignore_errors=True)
                self.maaend_set_path.mkdir(parents=True, exist_ok=True)
                shutil.copy2(
                    maaend_template_path, self.maaend_set_path / "mxu-MaaEnd.json"
                )

        maaend_set_path = self.maaend_set_path / "mxu-MaaEnd.json"
        if not maaend_set_path.exists():
            raise FileNotFoundError(
                "未找到 MaaEnd 配置文件, 请检查 MaaEnd 路径设置或先启动 MaaEnd 完成配置文件生成"
            )

        maaend_set = json.loads(maaend_set_path.read_text(encoding="utf-8"))
        maaend_template_path = (
            Path.cwd() / "res/templates/MaaEnd/config/mxu-MaaEnd.json"
        )
        template_config = (
            json.loads(maaend_template_path.read_text(encoding="utf-8"))
            if maaend_template_path.exists()
            else None
        )
        maaend_set = normalize_maaend_config(
            maaend_set,
            self.script_config.get("Game", "ControllerType"),
            template_config,
        )

        maaend_set_path.write_text(
            json.dumps(maaend_set, ensure_ascii=False, indent=4),
            encoding="utf-8",
        )
        logger.success(
            f"MaaEnd 运行参数配置完成: 设置脚本 {self.cur_user_item.user_id}"
        )

    async def final_task(self):

        await self.maaend_process_manager.kill()
        await System.kill_process(self.maaend_exe_path)

        shutil.rmtree(self.config_file_path, ignore_errors=True)
        self.config_file_path.mkdir(parents=True, exist_ok=True)
        shutil.copytree(self.maaend_set_path, self.config_file_path, dirs_exist_ok=True)
        config_path = self.config_file_path / "mxu-MaaEnd.json"
        maaend_set = json.loads(config_path.read_text(encoding="utf-8"))
        maaend_set = normalize_maaend_config(
            maaend_set, self.script_config.get("Game", "ControllerType")
        )
        config_path.write_text(
            json.dumps(maaend_set, ensure_ascii=False, indent=4), encoding="utf-8"
        )

    async def on_crash(self, e: Exception):
        self.cur_user_item.status = "异常"
        logger.exception(f"脚本设置任务出现异常: {e}")
        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Info",
            data={"Error": f"脚本设置任务出现异常: {e}"},
        )
