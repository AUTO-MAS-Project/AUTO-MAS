#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
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
import asyncio
import shutil
from pathlib import Path

from app.core import Config
from app.models.task import TaskExecuteBase, ScriptItem
from app.models.ConfigBase import MultipleConfig
from app.models.config import SrcConfig, SrcUserConfig
from app.models.emulator import DeviceBase
from app.services import System
from app.utils import get_logger, ProcessManager
from .tools import poor_yaml_read, poor_yaml_write

logger = get_logger("SRC 脚本设置")


class ScriptConfigTask(TaskExecuteBase):
    """脚本设置模式"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: SrcConfig,
        user_config: MultipleConfig[SrcUserConfig],
        emulator_manager: DeviceBase,
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

        self.src_process_manager = ProcessManager()
        self.wait_event = asyncio.Event()

        self.src_root_path = Path(self.script_config.get("Info", "Path"))
        self.src_set_path = self.src_root_path / "config"
        self.src_exe_path = self.src_root_path / "src.exe"

    async def main_task(self):

        await self.prepare()

        await self.set_src()
        logger.info(f"启动MAA进程: {self.src_exe_path}")
        self.wait_event.clear()
        await self.src_process_manager.open_process(self.src_exe_path)
        await self.wait_event.wait()

    async def set_src(self):
        """配置SRC运行参数"""

        logger.info(f"开始配置MAA运行参数: 设置脚本 {self.cur_user_item.user_id}")

        await self.src_process_manager.kill()
        await System.kill_process(self.src_exe_path)

        if (
            Path.cwd()
            / f"data/{self.script_info.script_id}/{self.cur_user_item.user_id}/ConfigFile"
        ).exists():
            shutil.copytree(
                (
                    Path.cwd()
                    / f"data/{self.script_info.script_id}/{self.cur_user_item.user_id}/ConfigFile"
                ),
                self.src_set_path,
                dirs_exist_ok=True,
            )

        if not (self.src_set_path / "src.json").exists():
            for json_path in self.src_set_path.glob("*.json"):
                if json_path.name != "template.json":
                    shutil.copy(json_path, self.src_set_path / "src.json")
                    break
            else:
                shutil.copy(
                    self.src_set_path / "template.json", self.src_set_path / "src.json"
                )

        src_set = json.loads(
            (self.src_set_path / "src.json").read_text(encoding="utf-8")
        )
        deploy_set = poor_yaml_read((self.src_set_path / "deploy.yaml"))

        # 不直接运行任务
        deploy_set["Run"] = None

        # 模拟器基础配置
        src_set["Alas"]["Emulator"]["GameClient"] = "android"
        src_set["Alas"]["Emulator"]["GameLanguage"] = "cn"
        src_set["Alas"]["Emulator"]["AdbRestart"] = True

        # 错误处理方式
        src_set["Alas"]["Error"]["Restart"] = "game"

        # 任务间切换方式
        src_set["Alas"]["Optimization"]["WhenTaskQueueEmpty"] = "close_game"

        # 养成规划
        src_set["Dungeon"]["PlannerTarget"]["Enable"] = False

        (self.src_set_path / "src.json").write_text(
            json.dumps(src_set, ensure_ascii=False, indent=4), encoding="utf-8"
        )
        poor_yaml_write(
            deploy_set,
            self.src_set_path / "deploy.yaml",
            (
                self.src_set_path / "deploy.template-cn.yaml"
                if (self.src_set_path / "deploy.template-cn.yaml").exists()
                else None
            ),
        )
        logger.success(f"SRC运行参数配置完成: 设置脚本 {self.cur_user_item.user_id}")

    async def final_task(self):

        await self.src_process_manager.kill()
        await System.kill_process(self.src_exe_path)

        shutil.rmtree(
            Path.cwd()
            / f"data/{self.script_info.script_id}/{self.cur_user_item.user_id}/ConfigFile",
            ignore_errors=True,
        )
        (
            Path.cwd()
            / f"data/{self.script_info.script_id}/{self.cur_user_item.user_id}/ConfigFile"
        ).mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            self.src_set_path,
            Path.cwd()
            / f"data/{self.script_info.script_id}/{self.cur_user_item.user_id}/ConfigFile",
            dirs_exist_ok=True,
        )

    async def on_crash(self, e: Exception):
        self.cur_user_item.status = "异常"
        logger.exception(f"脚本设置任务出现异常: {e}")
        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Info",
            data={"Error": f"脚本设置任务出现异常: {e}"},
        )
