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


import shutil
import uuid
from datetime import datetime
from pathlib import Path

from app.core import Config
from app.models.ConfigBase import MultipleConfig
from app.models.config import MaaEndConfig, MaaEndUserConfig
from app.models.task import ScriptItem, TaskExecuteBase, UserItem
from app.services import Notify
from app.utils import get_logger
from app.utils.constants import TASK_MODE_ZH

from .AutoProxy import AutoProxyTask
from .ScriptConfig import ScriptConfigTask
from .tools import push_notification


logger = get_logger("MaaEnd 调度器")

METHOD_BOOK: dict[str, type[AutoProxyTask | ScriptConfigTask]] = {
    "AutoProxy": AutoProxyTask,
    "ScriptConfig": ScriptConfigTask,
}


class MaaEndManager(TaskExecuteBase):
    """MaaEnd 控制器"""

    def __init__(self, script_info: ScriptItem):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info

        self.check_result = "-"
        self.begin_time = "-"

        self.prepared_ok = False
        self.config_locked = False
        self.backup_created = False

        self.script_config: MaaEndConfig | None = None
        self.user_config = MultipleConfig([MaaEndUserConfig])

        self.maaend_config_dir = Path()
        self.temp_path = Path()
        self.backup_path = Path()

    async def check(self) -> str:
        if self.task_info.mode not in METHOD_BOOK:
            return "不支持的任务模式, 请检查任务配置！"

        script_config = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]
        if not isinstance(script_config, MaaEndConfig):
            return "脚本配置类型错误, 不是 MaaEnd 脚本类型"

        maaend_root_path = Path(script_config.get("Info", "Path"))
        maaend_exe_path = maaend_root_path / "MaaEnd.exe"
        if not maaend_exe_path.exists():
            return f"MaaEnd.exe文件不存在, 请检查MaaEnd路径设置！（{maaend_exe_path}）"

        if self.task_info.mode == "AutoProxy":
            controller_type = str(script_config.get("Run", "ControllerType")).strip()
            if controller_type.startswith("Win32"):
                game_path = str(script_config.get("Run", "GamePath")).strip()
                if not game_path:
                    return "Win32 控制器需要配置 Endfield.exe 路径（Run.GamePath）"
                if not Path(game_path).exists():
                    return f"Endfield.exe 路径不存在: {game_path}"

        return "Pass"

    async def prepare(self):
        await Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].lock()
        self.config_locked = True

        self.script_config = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]
        await self.user_config.load(await self.script_config.UserData.toDict())

        self.maaend_config_dir = Path(self.script_config.get("Info", "Path")) / "config"
        self.temp_path = Path.cwd() / f"data/{self.script_info.script_id}/Temp"
        self.backup_path = self.temp_path / "MaaEndConfigBackup"

        self.temp_path.mkdir(parents=True, exist_ok=True)
        if self.backup_path.exists():
            shutil.rmtree(self.backup_path, ignore_errors=True)

        if self.maaend_config_dir.exists():
            shutil.copytree(self.maaend_config_dir, self.backup_path, dirs_exist_ok=True)
            self.backup_created = True

        if self.task_info.mode == "ScriptConfig":
            self.script_info.user_list = [
                UserItem(user_id=self.task_info.user_id or "Default", name="", status="等待")
            ]
        else:
            self.script_info.user_list = [
                UserItem(user_id=str(uid), name=config.get("Info", "Name"), status="等待")
                for uid, config in self.user_config.items()
                if config.get("Info", "Status") and config.get("Info", "RemainedDay") != 0
            ]

        self.prepared_ok = True

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

        if not isinstance(self.script_config, MaaEndConfig):
            raise RuntimeError("脚本配置类型错误, 不是 MaaEnd 脚本类型")

        for self.script_info.current_index in range(len(self.script_info.user_list)):
            task = METHOD_BOOK[self.task_info.mode](
                self.script_info,
                self.script_config,
                self.user_config,
            )
            await self.spawn(task)

    async def final_task(self):
        if self.check_result != "Pass":
            self.script_info.status = "异常"
            return

        if self.config_locked:
            await Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].unlock()
            self.config_locked = False

        if self.prepared_ok and isinstance(self.script_config, MaaEndConfig):
            await Config.ScriptConfig[
                uuid.UUID(self.script_info.script_id)
            ].UserData.load(await self.user_config.toDict())

        if self.task_info.mode == "AutoProxy":
            error_user = [u.name for u in self.script_info.user_list if u.status == "异常"]
            over_user = [u.name for u in self.script_info.user_list if u.status == "完成"]
            wait_user = [u.name for u in self.script_info.user_list if u.status == "等待"]

            title = f"{datetime.now().strftime('%m-%d')} | {self.script_info.name or '空白'}的{TASK_MODE_ZH[self.task_info.mode]}任务报告"
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

        if self.backup_created and self.backup_path.exists():
            if self.maaend_config_dir.exists():
                shutil.rmtree(self.maaend_config_dir, ignore_errors=True)
            shutil.copytree(self.backup_path, self.maaend_config_dir, dirs_exist_ok=True)

        if self.backup_path.exists():
            shutil.rmtree(self.backup_path, ignore_errors=True)
        if self.temp_path.exists() and not any(self.temp_path.iterdir()):
            self.temp_path.rmdir()

        if self.script_info.status != "异常":
            self.script_info.status = "完成"

    async def on_crash(self, e: Exception):
        self.script_info.status = "异常"
        logger.exception(f"MaaEnd 任务出现异常: {e}")
        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Info",
            data={"Error": f"MaaEnd 任务出现异常: {e}"},
        )
