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


import uuid
import shutil
from pathlib import Path
from datetime import datetime

from app.core import Config, EmulatorManager
from app.models.task import TaskExecuteBase, ScriptItem, UserItem
from app.models.ConfigBase import MultipleConfig
from app.models.config import GeneralConfig, GeneralUserConfig
from app.services import Notify
from app.utils import get_logger, ProcessManager
from .tools import push_notification
from .AutoProxy import AutoProxyTask
from .ScriptSetup import ScriptSetupTask


logger = get_logger("通用调度器")

METHOD_BOOK: dict[str, type[AutoProxyTask | ScriptSetupTask]] = {
    "自动代理": AutoProxyTask,
    "设置脚本": ScriptSetupTask,
}


class GeneralManager(TaskExecuteBase):
    """通用脚本控制器"""

    def __init__(self, script_info: ScriptItem):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.check_result = "-"

    async def check(self) -> str:
        """校验通用脚本配置是否可用"""
        if self.task_info.mode not in METHOD_BOOK:
            return "不支持的任务模式，请检查任务配置！"
        if not isinstance(
            Config.ScriptConfig[uuid.UUID(self.script_info.script_id)], GeneralConfig
        ):
            return "脚本配置类型错误, 不是通用脚本类型"
        if Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].get(
            "Game", "Enabled"
        ):
            if (
                Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].get(
                    "Game", "Type"
                )
                == "Emulator"
            ) and (
                Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].get(
                    "Game", "EmulatorId"
                )
                == "-"
                or Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].get(
                    "Game", "EmulatorIndex"
                )
                in ["", "-"]
            ):
                return "未完成模拟器配置, 请检查脚本配置中的模拟器设置！"
            elif (
                Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].get(
                    "Game", "Type"
                )
                == "Client"
            ) and not Path(
                Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].get(
                    "Game", "Path"
                )
            ).exists():
                return "未完成游戏配置, 请检查脚本配置中的游戏设置！"

        return "Pass"

    async def prepare(self):
        """运行前准备"""

        # 锁定脚本配置并加载用户配置
        await Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].lock()
        self.script_config = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]
        self.user_config = MultipleConfig([GeneralUserConfig])
        await self.user_config.load(await self.script_config.UserData.toDict())
        logger.success(f"{self.script_info.script_id}已锁定, 通用脚本配置提取完成")

        self.script_config_path = Path(self.script_config.get("Script", "ConfigPath"))
        self.temp_path = Path.cwd() / f"data/{self.script_info.script_id}/Temp"

        if Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].get(
            "Game", "Enabled"
        ):
            if (
                Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].get(
                    "Game", "Type"
                )
                == "Emulator"
            ):
                self.emulator_manager = await EmulatorManager.get_emulator_instance(
                    self.script_config.get("Game", "EmulatorId")
                )

            elif (
                Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].get(
                    "Game", "Type"
                )
                == "Client"
            ):
                self.game_process_manager = ProcessManager()

            elif (
                    Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].get(
                        "Game", "Type"
                    )
                    == "URL"
            ):
                self.game_process_manager = ProcessManager()

        # 备份原始配置
        logger.info(f"记录通用脚本配置文件: {self.script_config_path}")
        self.temp_path.mkdir(parents=True, exist_ok=True)
        if self.script_config_path.exists():
            if self.script_config.get("Script", "ConfigPathMode") == "Folder":
                shutil.copytree(
                    self.script_config_path, self.temp_path, dirs_exist_ok=True
                )
            elif self.script_config.get("Script", "ConfigPathMode") == "File":
                shutil.copy(self.script_config_path, self.temp_path / "config.temp")

        # 构建用户列表
        if self.task_info.mode == "设置脚本":
            self.script_info.user_list = [
                UserItem(
                    user_id=self.task_info.user_id or "Default", name="", status="等待"
                )
            ]
        else:
            self.script_info.user_list = [
                UserItem(
                    user_id=str(uid), name=config.get("Info", "Name"), status="等待"
                )
                for uid, config in self.user_config.items()
                if config.get("Info", "Status")
                and config.get("Info", "RemainedDay") != 0
            ]
        logger.info(
            f"用户列表加载完成, 已筛选用户数: {len(self.script_info.user_list)}"
        )

    async def main_task(self):

        self.check_result = await self.check()
        if self.check_result != "Pass":
            logger.error(f"未通过配置检查: {self.check_result}")
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={"Error": self.check_result},
            )
            return

        self.begin_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await self.prepare()

        if not isinstance(self.script_config, GeneralConfig):
            raise RuntimeError("脚本配置类型错误, 不是通用脚本类型")

        for self.script_info.current_index in range(len(self.script_info.user_list)):
            task = METHOD_BOOK[self.task_info.mode](
                self.script_info,
                self.script_config,
                self.user_config,
                (
                    (
                        self.emulator_manager
                        if (self.script_config.get("Game", "Type") == "Emulator")
                        else self.game_process_manager
                    )
                    if self.script_config.get("Game", "Enabled")
                    else None
                ),
            )

            await self.spawn(task)

    async def final_task(self):
        """运行结束后的收尾工作"""

        if self.check_result != "Pass":
            self.script_info.status = "异常"
            return self.check_result

        logger.info("通用脚本任务已结束, 开始执行后续操作")
        await Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].unlock()
        logger.success(f"已解锁脚本配置 {self.script_info.script_id}")

        if self.task_info.mode == "自动代理":

            await Config.ScriptConfig[
                uuid.UUID(self.script_info.script_id)
            ].UserData.load(await self.user_config.toDict())
            await Config.ScriptConfig.save()

            error_user = [
                u.name for u in self.script_info.user_list if u.status == "异常"
            ]
            over_user = [
                u.name for u in self.script_info.user_list if u.status == "完成"
            ]
            wait_user = [
                u.name for u in self.script_info.user_list if u.status == "等待"
            ]

            title = f"{datetime.now().strftime('%m-%d')} | {self.script_info.name or '空白'}的{self.task_info.mode}任务报告"
            result = {
                "title": f"{self.task_info.mode}任务报告",
                "script_name": self.script_info.name or "空白",
                "start_time": self.begin_time,
                "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "completed_count": len(over_user),
                "uncompleted_count": len(error_user) + len(wait_user),
                "failed_user": error_user,
                "waiting_user": wait_user,
            }

            await Notify.push_plyer(
                title.replace("报告", "已完成！"),
                f"已完成用户数: {len(over_user)}, 未完成用户数: {len(error_user) + len(wait_user)}",
                f"已完成用户数: {len(over_user)}, 未完成用户数: {len(error_user) + len(wait_user)}",
                10,
            )
            try:
                await push_notification("代理结果", title, result, None)
            except Exception as e:
                logger.exception(f"推送代理结果时出现异常: {e}")
                await Config.send_websocket_message(
                    id=self.task_info.task_id,
                    type="Info",
                    data={"Error": f"推送代理结果时出现异常: {e}"},
                )

            # text = (
            #     f"任务开始时间: {result['start_time']}, 结束时间: {result['end_time']}\n"
            #     f"已完成数: {result['completed_count']}, 未完成数: {result['uncompleted_count']}\n"
            # )
            # if error_user:
            #     text += (
            #         f"{self.mode[2:4]}未成功的用户: \n" + "\n".join(error_user) + "\n"
            #     )
            # if wait_user:
            #     text += f"\n未开始{self.mode[2:4]}的用户: \n" + "\n".join(wait_user)

        # 复原通用脚本配置文件
        if (
            self.script_config.get("Script", "ConfigPathMode") == "Folder"
            and self.temp_path.exists()
        ):
            logger.info(f"复原通用脚本配置文件: {self.temp_path}")
            shutil.copytree(self.temp_path, self.script_config_path, dirs_exist_ok=True)
            shutil.rmtree(self.temp_path)
        elif (
            self.script_config.get("Script", "ConfigPathMode") == "File"
            and (self.temp_path / "config.temp").exists()
        ):
            logger.info(f"复原通用脚本配置文件: {self.temp_path / 'config.temp'}")
            shutil.copy(self.temp_path / "config.temp", self.script_config_path)
            shutil.rmtree(self.temp_path)

        self.script_info.status = "完成"

    async def on_crash(self, e: Exception):

        self.script_info.status = "异常"
        logger.exception(f"通用脚本任务出现异常: {e}")
        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Info",
            data={"Error": f"通用脚本任务出现异常: {e}"},
        )
