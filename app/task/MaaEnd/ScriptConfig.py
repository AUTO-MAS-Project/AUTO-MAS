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
from copy import deepcopy

from app.core import Config
from app.models.task import TaskExecuteBase, ScriptItem
from app.models.ConfigBase import MultipleConfig
from app.models.config import MaaEndConfig, MaaEndUserConfig
from app.models.emulator import DeviceBase
from app.services import System
from app.utils import get_logger, ProcessManager

logger = get_logger("MaaEnd 脚本设置")


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
        self.user_config = user_config
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

        if self.config_file_path.exists():
            shutil.copytree(
                self.config_file_path, self.maaend_set_path, dirs_exist_ok=True
            )

        # 初始化任务实例
        maaend_set = json.loads(
            (self.maaend_set_path / "mxu-MaaEnd.json").read_text(encoding="utf-8")
        )
        maaend_instances = maaend_set["instances"]

        # 创建任务项单例
        selected_instance = None
        for instance in maaend_instances:
            if instance["id"] == "automas":
                selected_instance = instance
                break
        else:
            for instance in maaend_instances:
                if instance["id"] == maaend_set["lastActiveInstanceId"]:
                    selected_instance = instance
                    break
        if selected_instance is None:
            selected_instance = (
                maaend_instances[0]
                if len(maaend_instances) > 0
                else {"id": "automas", "name": "AUTO-MAS", "tasks": []}
            )

        if "tasks" not in selected_instance:
            selected_instance["tasks"] = []
        selected_instance["id"] = "automas"
        selected_instance["name"] = "AUTO-MAS"
        maaend_set["instances"] = [selected_instance]
        maaend_set["lastActiveInstanceId"] = "automas"

        # 不直接运行任务
        maaend_set["settings"]["autoStartInstanceId"] = "automas"
        maaend_set["settings"]["autoRunOnLaunch"] = False

        (self.maaend_set_path / "mxu-MaaEnd.json").write_text(
            json.dumps(maaend_set, ensure_ascii=False, indent=4), encoding="utf-8"
        )
        logger.success(
            f"MaaEnd 运行参数配置完成: 设置脚本 {self.cur_user_item.user_id}"
        )

    async def final_task(self):

        await self.maaend_process_manager.kill()
        await System.kill_process(self.maaend_exe_path)

        shutil.rmtree(self.config_file_path, ignore_errors=True)
        self.config_file_path.mkdir(parents=True, exist_ok=True)
        shutil.copytree(self.maaend_set_path, self.config_file_path)

    async def on_crash(self, e: Exception):
        self.cur_user_item.status = "异常"
        logger.exception(f"脚本设置任务出现异常: {e}")
        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Info",
            data={"Error": f"脚本设置任务出现异常: {e}"},
        )
