#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.


import uuid
from datetime import datetime
from pathlib import Path

from app.core import Config, EmulatorManager
from app.models.ConfigBase import MultipleConfig
from app.models.config import SimpleConfig, SimpleUserConfig
from app.models.task import ScriptItem, TaskExecuteBase, UserItem
from app.services import Notify
from app.task.general.tools import push_notification
from app.utils import ProcessManager, get_logger
from app.utils.constants import TASK_MODE_ZH
from .AutoProxy import SimpleAutoProxyTask


logger = get_logger("简易脚本调度器")

METHOD_BOOK: dict[str, type[SimpleAutoProxyTask]] = {
    "AutoProxy": SimpleAutoProxyTask,
}


class SimpleManager(TaskExecuteBase):
    """简易脚本控制器"""

    def __init__(self, script_info: ScriptItem):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        script_config = Config.ScriptConfig[uuid.UUID(script_info.script_id)]
        if not isinstance(script_config, SimpleConfig):
            raise RuntimeError("脚本配置类型错误, 不是简易脚本类型")

        self.task_info = script_info.task_info
        self.script_info: ScriptItem = script_info
        self.script_config: SimpleConfig = script_config
        self.user_config: MultipleConfig[SimpleUserConfig] = MultipleConfig(
            [SimpleUserConfig]
        )
        self.emulator_manager = None
        self.game_process_manager: ProcessManager | None = None
        self.check_result: str = "-"
        self.begin_time: str = ""
        self.prepared = False

    async def check(self) -> str:
        """校验简易脚本配置是否可用"""

        if self.task_info.mode not in METHOD_BOOK:
            return "简易脚本仅支持自动代理任务"

        script_path = Path(self.script_config.get("Script", "ScriptPath"))
        if not script_path.is_file():
            return "请设置脚本路径"

        if (
            self.script_config.get("Script", "IfTrackProcess")
            and not self.script_config.get("Script", "TrackProcessName")
            and not self.script_config.get("Script", "TrackProcessExe")
            and not self.script_config.get("Script", "TrackProcessCmdline")
        ):
            return "开启追踪子进程后, 需至少填写一项追踪进程信息！"

        if self.script_config.get("Game", "Enabled"):
            game_type = self.script_config.get("Game", "Type")
            if game_type == "Emulator" and (
                self.script_config.get("Game", "EmulatorId") == "-"
                or self.script_config.get("Game", "EmulatorIndex") in ["", "-"]
            ):
                return "未完成模拟器配置, 请检查脚本配置中的模拟器设置！"
            if (
                game_type == "Client"
                and not Path(self.script_config.get("Game", "Path")).exists()
            ):
                return "未完成游戏配置, 请检查脚本配置中的游戏设置！"
            if game_type == "URL" and (
                not self.script_config.get("Game", "URL")
                or not self.script_config.get("Game", "ProcessName")
            ):
                return "未完成URL配置, 请检查脚本配置中的URL和进程名称设置！"

        return "Pass"

    async def prepare(self) -> None:
        """锁定配置并加载用户列表"""

        await self.script_config.lock()
        await self.user_config.load(await self.script_config.UserData.toDict())
        self.prepared = True
        logger.success(f"{self.script_info.script_id}已锁定, 简易脚本配置提取完成")

        if self.script_config.get("Game", "Enabled"):
            if self.script_config.get("Game", "Type") == "Emulator":
                self.emulator_manager = await EmulatorManager.get_emulator_instance(
                    self.script_config.get("Game", "EmulatorId")
                )
            else:
                self.game_process_manager = ProcessManager()

        self.script_info.user_list = [
            UserItem(
                user_id=str(uid),
                name=config.get("Info", "Name"),
                status="等待",
            )
            for uid, config in self.user_config.items()
            if config.get("Info", "Status") and config.get("Info", "RemainedDay") != 0
        ]
        logger.info(
            f"用户列表加载完成, 已筛选用户数: {len(self.script_info.user_list)}"
        )

    async def main_task(self) -> None:
        """依次执行所有启用用户"""

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

        for self.script_info.current_index in range(len(self.script_info.user_list)):
            task = METHOD_BOOK[self.task_info.mode](
                script_info=self.script_info,
                script_config=self.script_config,
                user_config=self.user_config,
                game_manager=(
                    self.emulator_manager
                    if self.script_config.get("Game", "Type") == "Emulator"
                    else self.game_process_manager
                )
                if self.script_config.get("Game", "Enabled")
                else None,
            )
            await self.spawn(task)

    async def final_task(self) -> str | None:
        """解锁配置、写回用户状态并发送汇总通知"""

        if self.check_result != "Pass":
            self.script_info.status = "异常"
            return self.check_result

        if self.script_config.is_locked:
            await self.script_config.unlock()
            logger.success(f"已解锁脚本配置 {self.script_info.script_id}")

        await self.script_config.UserData.load(await self.user_config.toDict())
        await Config.ScriptConfig.save()

        error_user = [u.name for u in self.script_info.user_list if u.status == "异常"]
        over_user = [u.name for u in self.script_info.user_list if u.status == "完成"]
        wait_user = [u.name for u in self.script_info.user_list if u.status == "等待"]

        title = (
            f"{datetime.now().strftime('%m-%d')} | "
            f"{self.script_info.name or '空白'}的{TASK_MODE_ZH[self.task_info.mode]}任务报告"
        )
        result = {
            "title": f"{TASK_MODE_ZH[self.task_info.mode]}任务报告",
            "script_name": self.script_info.name or "空白",
            "start_time": self.begin_time,
            "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "completed_count": len(over_user),
            "uncompleted_count": len(error_user) + len(wait_user),
            "result": self.script_info.result,
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

        self.script_info.status = (
            "异常"
            if any(user.status == "异常" for user in self.script_info.user_list)
            else "完成"
        )
        return None

    async def on_crash(self, e: Exception) -> None:
        """记录调度异常并确保配置解锁"""

        self.script_info.status = "异常"
        logger.exception(f"简易脚本任务出现异常: {e}")

        try:
            if self.script_config.is_locked:
                await self.script_config.unlock()
        except Exception as unlock_error:
            logger.exception(f"解锁简易脚本配置失败: {unlock_error}")

        if self.prepared:
            try:
                await self.script_config.UserData.load(await self.user_config.toDict())
                await Config.ScriptConfig.save()
            except Exception as save_error:
                logger.exception(f"写回简易脚本用户配置失败: {save_error}")

        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Info",
            data={"Error": f"简易脚本任务出现异常: {e}"},
        )
