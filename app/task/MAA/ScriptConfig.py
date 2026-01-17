#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

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

import json
import asyncio
import shutil
from pathlib import Path

from app.core import Config
from app.models.task import TaskExecuteBase, ScriptItem
from app.models.ConfigBase import MultipleConfig
from app.models.config import MaaConfig, MaaUserConfig
from app.models.emulator import DeviceBase
from app.services import System
from app.utils import get_logger, ProcessManager
from app.utils.constants import MAA_TASKS

logger = get_logger("MAA 脚本设置")


class ScriptConfigTask(TaskExecuteBase):
    """脚本设置模式"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: MaaConfig,
        user_config: MultipleConfig[MaaUserConfig],
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

        self.maa_process_manager = ProcessManager()
        self.wait_event = asyncio.Event()

        self.maa_root_path = Path(self.script_config.get("Info", "Path"))
        self.maa_set_path = self.maa_root_path / "config/gui.json"
        self.maa_exe_path = self.maa_root_path / "MAA.exe"

    async def main_task(self):

        await self.prepare()

        await self.set_maa()
        logger.info(f"启动MAA进程: {self.maa_exe_path}")
        self.wait_event.clear()
        await self.maa_process_manager.open_process(self.maa_exe_path)
        await self.wait_event.wait()

    async def set_maa(self):
        """配置MAA运行参数"""

        logger.info(f"开始配置MAA运行参数: 设置脚本 {self.cur_user_item.user_id}")

        await self.maa_process_manager.kill()
        await System.kill_process(self.maa_exe_path)

        if (
            Path.cwd()
            / f"data/{self.script_info.script_id}/{self.cur_user_item.user_id}/ConfigFile/gui.json"
        ).exists():
            shutil.copy(
                Path.cwd()
                / f"data/{self.script_info.script_id}/{self.cur_user_item.user_id}/ConfigFile/gui.json",
                self.maa_set_path,
            )

        maa_set = json.loads(self.maa_set_path.read_text(encoding="utf-8"))

        # 多配置使用默认配置
        if maa_set["Current"] != "Default":
            maa_set["Configurations"]["Default"] = maa_set["Configurations"][
                maa_set["Current"]
            ]
            maa_set["Current"] = "Default"
        for i in range(1, 9):
            maa_set["Global"][f"Timer.Timer{i}"] = "False"

        # 任务间切换方式
        maa_set["Configurations"]["Default"]["MainFunction.PostActions"] = "0"

        # 不直接运行任务
        maa_set["Configurations"]["Default"]["Start.StartGame"] = "True"
        maa_set["Configurations"]["Default"]["Start.RunDirectly"] = "False"
        maa_set["Configurations"]["Default"]["Start.OpenEmulatorAfterLaunch"] = "False"

        # 更新配置
        maa_set["Global"]["VersionUpdate.ScheduledUpdateCheck"] = "False"
        maa_set["Global"]["VersionUpdate.AutoDownloadUpdatePackage"] = "False"
        maa_set["Global"]["VersionUpdate.AutoInstallUpdatePackage"] = "False"

        # 静默模式相关配置
        if Config.get("Function", "IfSilence"):
            maa_set["Global"]["Start.MinimizeDirectly"] = "False"

        # 任务配置
        for task in MAA_TASKS:
            maa_set["Configurations"]["Default"][
                f"TaskQueue.{task}.IsChecked"
            ] = "False"
        self.maa_set_path.write_text(
            json.dumps(maa_set, ensure_ascii=False, indent=4), encoding="utf-8"
        )
        logger.success(f"MAA运行参数配置完成: 设置脚本 {self.cur_user_item.user_id}")

    async def final_task(self):

        await self.maa_process_manager.kill()
        await System.kill_process(self.maa_exe_path)

        (
            Path.cwd()
            / f"data/{self.script_info.script_id}/{self.cur_user_item.user_id}/ConfigFile"
        ).mkdir(parents=True, exist_ok=True)
        shutil.copy(
            self.maa_set_path,
            Path.cwd()
            / f"data/{self.script_info.script_id}/{self.cur_user_item.user_id}/ConfigFile/gui.json",
        )

    async def on_crash(self, e: Exception):
        self.cur_user_item.status = "异常"
        logger.exception(f"脚本设置任务出现异常: {e}")
        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Info",
            data={"Error": f"脚本设置任务出现异常: {e}"},
        )
