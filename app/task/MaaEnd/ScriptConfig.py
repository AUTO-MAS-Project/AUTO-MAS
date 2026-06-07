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
import uuid
from pathlib import Path

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
        if self.cur_user_item.user_id == "Default":
            self.config_mode = "简洁"
        else:
            self.cur_user_uid = uuid.UUID(self.cur_user_item.user_id)
            self.cur_user_config = self.user_config[self.cur_user_uid]
            self.config_mode = self.cur_user_config.get("Info", "Mode")

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

        if self.config_mode == "自定义":
            # 自定义模式直接打开用户完整配置，并临时收束为单个 AUTOMAS 实例
            if not (self.config_file_path / "mxu-MaaEnd.json").exists():
                raise FileNotFoundError(
                    "未找到用户的 MaaEnd 配置文件, 请先完成「MaaEnd 配置」步骤"
                )
            shutil.rmtree(self.maaend_set_path, ignore_errors=True)
            shutil.copytree(self.config_file_path, self.maaend_set_path)
            maaend_set = json.loads(
                (self.maaend_set_path / "mxu-MaaEnd.json").read_text(
                    encoding="utf-8"
                )
            )
            selected_instance = None
            for instance in maaend_set["instances"]:
                if instance["id"] == "automas":
                    selected_instance = instance
                    break
            else:
                for instance in maaend_set["instances"]:
                    if instance["id"] == maaend_set.get("lastActiveInstanceId"):
                        selected_instance = instance
                        break
            if selected_instance is None:
                selected_instance = (
                    maaend_set["instances"][0]
                    if len(maaend_set["instances"]) > 0
                    else {"id": "automas", "name": "AUTO-MAS", "tasks": []}
                )

            if "tasks" not in selected_instance:
                selected_instance["tasks"] = []
            selected_instance["id"] = "automas"
            selected_instance["name"] = "AUTO-MAS"
            maaend_set["instances"] = [selected_instance]
            maaend_set["settings"]["autoRunOnLaunch"] = False
        else:
            # 预设模式保留完整实例列表，仅切换到当前控制器对应实例
            config_path = self.config_file_path / "mxu-MaaEnd.json"
            maaend_set = None
            if config_path.exists():
                maaend_set = json.loads(config_path.read_text(encoding="utf-8"))
                preset_controllers = {
                    instance.get("controllerName")
                    for instance in maaend_set.get("instances", [])
                }
                if "Win32-Front" not in preset_controllers:
                    logger.warning(
                        f"用户 {self.cur_user_item.user_id} 的 MaaEnd 预设配置不完整，已使用模板重新初始化"
                    )
                    maaend_set = None

            if maaend_set is None:
                # 首次进入或从自定义切回预设时，用模板初始化完整配置
                self.config_file_path.mkdir(parents=True, exist_ok=True)
                maaend_set = json.loads(
                    (
                        Path.cwd() / "res/templates/MaaEnd/config/mxu-MaaEnd.json"
                    ).read_text(encoding="utf-8")
                )
                for maaend_instance in maaend_set.get("instances", []):
                    for task in maaend_instance.get("tasks", []):
                        task["enabled"] = True
                config_path.write_text(
                    json.dumps(maaend_set, ensure_ascii=False, indent=4),
                    encoding="utf-8",
                )

            target_instance = None
            for instance in maaend_set.get("instances", []):
                if instance.get("controllerName") == self.script_config.get(
                    "Game", "ControllerType"
                ):
                    target_instance = instance
                    break
            if target_instance is None:
                raise ValueError(
                    f"预设配置中未找到控制器 {self.script_config.get('Game', 'ControllerType')} 对应的实例，建议重新配置"
                )
            maaend_set["lastActiveInstanceId"] = target_instance["id"]
            shutil.rmtree(self.maaend_set_path, ignore_errors=True)
            self.maaend_set_path.mkdir(parents=True, exist_ok=True)

        (self.maaend_set_path / "mxu-MaaEnd.json").write_text(
            json.dumps(maaend_set, ensure_ascii=False, indent=4),
            encoding="utf-8",
        )
        logger.success(
            f"MaaEnd 运行参数配置完成: 设置脚本 {self.cur_user_item.user_id}"
        )

    async def final_task(self):

        await self.maaend_process_manager.kill()
        await System.kill_process(self.maaend_exe_path)

        if self.config_mode == "自定义":
            # 自定义模式直接回写 MaaEnd 当前完整配置
            shutil.rmtree(self.config_file_path, ignore_errors=True)
            self.config_file_path.mkdir(parents=True, exist_ok=True)
            shutil.copytree(self.maaend_set_path, self.config_file_path, dirs_exist_ok=True)
        else:
            # 预设模式仅提取编辑后的 OptionValues，覆盖回对应预设实例
            maaend_set = json.loads(
                (self.maaend_set_path / "mxu-MaaEnd.json").read_text(
                    encoding="utf-8"
                )
            )
            config_path = self.config_file_path / "mxu-MaaEnd.json"
            preset_config = json.loads(config_path.read_text(encoding="utf-8"))

            preset_instance = None
            for instance in preset_config.get("instances", []):
                if instance.get("controllerName") == self.script_config.get(
                    "Game", "ControllerType"
                ):
                    preset_instance = instance
                    break
            if preset_instance is None:
                raise ValueError(
                    f"预设配置中未找到控制器 {self.script_config.get('Game', 'ControllerType')} 对应的实例，建议重新配置"
                )

            edited_instance = None
            for instance in maaend_set.get("instances", []):
                if instance.get("controllerName") == self.script_config.get(
                    "Game", "ControllerType"
                ):
                    edited_instance = instance
                    break
            if edited_instance is None:
                raise ValueError(
                    f"运行配置中未找到控制器 {self.script_config.get('Game', 'ControllerType')} 对应的实例，建议重新打开 ScriptConfig 后重新配置"
                )

            # 预设模式只同步任务选项，实例结构和其他本地设置保留用户配置原状
            preset_tasks = {
                task.get("taskName"): task for task in preset_instance.get("tasks", [])
            }
            for task in edited_instance.get("tasks", []):
                preset_task = preset_tasks.get(task.get("taskName"))
                if preset_task is not None:
                    preset_task["optionValues"] = task.get("optionValues", {})
            config_path.write_text(
                json.dumps(preset_config, ensure_ascii=False, indent=4),
                encoding="utf-8",
            )

    async def on_crash(self, e: Exception):
        self.cur_user_item.status = "异常"
        logger.exception(f"脚本设置任务出现异常: {e}")
        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Info",
            data={"Error": f"脚本设置任务出现异常: {e}"},
        )
