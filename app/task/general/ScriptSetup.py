#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 AUTO-MAS Team

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

#   Contact: DLmaster_361@163.com


import asyncio
import shutil
from pathlib import Path

from app.core import Broadcast, Config
from app.models.task import TaskExecuteBase, ScriptItem
from app.models.ConfigBase import MultipleConfig
from app.models.config import GeneralConfig, GeneralUserConfig
from app.services import System
from app.utils import get_logger, ProcessManager

logger = get_logger("MAA 脚本设置")


class ScriptSetupTask(TaskExecuteBase):
    """脚本设置模式"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: GeneralConfig,
        user_config: MultipleConfig[GeneralUserConfig],
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

        self.general_process_manager = ProcessManager()
        self.wait_event = asyncio.Event()

        self.script_root_path = Path(self.script_config.get("Info", "RootPath"))
        self.script_path = Path(self.script_config.get("Script", "ScriptPath"))

        arguments_list = []
        path_list = []

        for argument in [
            _.strip()
            for _ in str(self.script_config.get("Script", "Arguments")).split("|")
            if _.strip()
        ]:
            arg = [_.strip() for _ in argument.split("%") if _.strip()]
            if len(arg) > 1:
                path_list.append((self.script_path / arg[0]).resolve())
                arguments_list.append(
                    [_.strip() for _ in arg[1].split(" ") if _.strip()]
                )
            elif len(arg) > 0:
                path_list.append(self.script_path)
                arguments_list.append(
                    [_.strip() for _ in arg[0].split(" ") if _.strip()]
                )

        self.script_exe_path = path_list[0] if len(path_list) > 0 else self.script_path
        self.script_arguments = arguments_list[0] if len(arguments_list) > 0 else []
        self.script_set_exe_path = (
            path_list[1] if len(path_list) > 1 else self.script_path
        )
        self.script_set_arguments = arguments_list[1] if len(arguments_list) > 1 else []
        self.script_config_path = Path(self.script_config.get("Script", "ConfigPath"))

    async def main_task(self):

        await self.prepare()

        await self.set_general()
        # 创建通用脚本任务
        logger.info(
            f"运行脚本任务: {self.script_set_exe_path}, 参数: {self.script_set_arguments}"
        )
        await self.general_process_manager.open_process(
            self.script_set_exe_path,
            self.script_set_arguments,
            tracking_time=(
                60 if self.script_config.get("Script", "IfTrackProcess") else 0
            ),
        )

        # 等待用户完成配置
        self.wait_event.clear()
        await self.wait_event.wait()

    async def set_general(self) -> None:
        """配置通用脚本运行参数"""

        logger.info(f"开始配置脚本运行参数: 脚本设置 {self.cur_user_item.user_id}")

        await System.kill_process(self.script_set_exe_path)

        if (
            self.script_config.get("Script", "ConfigPathMode") == "Folder"
            and (
                Path.cwd()
                / f"data/{self.script_info.script_id}/{self.cur_user_item.user_id}/ConfigFile"
            ).exists()
        ):
            shutil.copytree(
                Path.cwd()
                / f"data/{self.script_info.script_id}/{self.cur_user_item.user_id}/ConfigFile",
                self.script_config_path,
                dirs_exist_ok=True,
            )
        elif (
            self.script_config.get("Script", "ConfigPathMode") == "File"
            and (
                Path.cwd()
                / f"data/{self.script_info.script_id}/{self.cur_user_item.user_id}/ConfigFile"
                / self.script_config_path.name
            ).exists()
        ):
            shutil.copy(
                Path.cwd()
                / f"data/{self.script_info.script_id}/{self.cur_user_item.user_id}/ConfigFile"
                / self.script_config_path.name,
                self.script_config_path,
            )

        logger.success(f"MAA运行参数配置完成: 设置脚本 {self.cur_user_item.user_id}")

    async def final_task(self):

        await self.general_process_manager.kill(if_force=True)
        await System.kill_process(self.script_exe_path)
        await System.kill_process(self.script_set_exe_path)
        del self.general_process_manager

        (
            Path.cwd()
            / f"data/{self.script_info.script_id}/{self.cur_user_item.user_id}/ConfigFile"
        ).mkdir(parents=True, exist_ok=True)
        if self.script_config.get("Script", "ConfigPathMode") == "Folder":
            shutil.copytree(
                self.script_config_path,
                Path.cwd()
                / f"data/{self.script_info.script_id}/{self.cur_user_item.user_id}/ConfigFile",
                dirs_exist_ok=True,
            )
            logger.success(
                f"通用脚本配置已保存到: {Path.cwd() / f'data/{self.script_info.script_id}/{self.cur_user_item.user_id}/ConfigFile'}"
            )
        elif self.script_config.get("Script", "ConfigPathMode") == "File":
            shutil.copy(
                self.script_config_path,
                Path.cwd()
                / f"data/{self.script_info.script_id}/{self.cur_user_item.user_id}/ConfigFile"
                / self.script_config_path.name,
            )
            logger.success(
                f"通用脚本配置已保存到: {Path.cwd() / f'data/{self.script_info.script_id}/{self.cur_user_item.user_id}/ConfigFile' / self.script_config_path.name}"
            )

    async def on_crash(self, e: Exception):
        self.cur_user_item.status = "异常"
        logger.exception(f"脚本设置任务出现异常: {e}")
        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Info",
            data={"Error": f"脚本设置任务出现异常: {e}"},
        )
