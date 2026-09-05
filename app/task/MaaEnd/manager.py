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

from app.core import Config, EmulatorManager
from app.core.ws import Publisher, protocol
from app.models.config import MaaEndConfig, MaaEndUserConfig
from app.models.ConfigBase import MultipleConfig
from app.models.schema import WSTaskNoticeData
from app.models.task import ScriptItem, TaskExecuteBase, UserItem
from app.tools.game_sign_notify import (
    append_task_game_sign_summary,
    finalize_task_game_sign_notification,
)
from app.utils import get_logger
from app.utils.constants import TASK_MODE_ZH

from .AutoProxy import AutoProxyTask
from .resource_loader import load_maaend_controller_protocol
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
        self.controller_protocol = ""

    async def check(self) -> str:
        if self.task_info.mode not in METHOD_BOOK:
            return "不支持的任务模式, 请检查任务配置！"

        script_config = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]

        if not isinstance(script_config, MaaEndConfig):
            return "脚本配置类型错误, 不是 MaaEnd 脚本类型"

        if not (Path(script_config.get("Info", "Path")) / "MaaEnd.exe").exists():
            return "MaaEnd.exe文件不存在, 请检查MaaEnd路径设置！"

        try:
            self.controller_protocol = load_maaend_controller_protocol(
                Path(script_config.get("Info", "Path")),
                script_config.get("Game", "ControllerType"),
            )
        except (OSError, KeyError, ValueError) as error:
            return f"MaaEnd 控制器配置读取失败: {error}"

        if self.controller_protocol == "Adb" and (
            script_config.get("Game", "EmulatorId") == "-"
            or script_config.get("Game", "EmulatorIndex") in ["", "-"]
        ):
            return "未完成模拟器配置, 请检查脚本配置中的模拟器设置！"
        elif (
            self.controller_protocol == "Win32"
            and not Path(script_config.get("Game", "Path")).exists()
        ):
            return "未完成游戏配置, 请检查脚本配置中的游戏设置！"
        if (
            self.task_info.mode == "AutoProxy"
            and not (
                Path(
                    Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].get(
                        "Info", "Path"
                    )
                )
                / "config/mxu-MaaEnd.json"
            ).exists()
        ):
            return "MaaEnd 配置文件不存在, 请检查 MaaEnd 路径设置或先启动 MaaEnd 完成配置文件生成！"

        return "Pass"

    async def prepare(self):

        # 锁定脚本配置并加载用户配置
        await Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].lock()
        self.script_config = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]
        self.user_config = MultipleConfig([MaaEndUserConfig])
        await self.user_config.load(await self.script_config.UserData.toDict())
        logger.success(f"{self.script_info.script_id}已锁定, MAAEnd配置提取完成")

        self.maaend_config_dir = Path(self.script_config.get("Info", "Path")) / "config"
        self.temp_path = Path.cwd() / f"data/{self.script_info.script_id}/Temp"

        # 初始化模拟器管理器
        if self.controller_protocol == "Adb":
            self.emulator_manager = await EmulatorManager.get_emulator_instance(
                self.script_config.get("Game", "EmulatorId")
            )
        else:
            self.emulator_manager = None

        # 备份原始配置
        shutil.rmtree(self.temp_path, ignore_errors=True)
        self.temp_path.mkdir(parents=True, exist_ok=True)
        if self.maaend_config_dir.exists():
            shutil.copytree(self.maaend_config_dir, self.temp_path, dirs_exist_ok=True)

        # 构建用户列表
        if self.task_info.mode == "ScriptConfig":
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
                and self.task_info.is_target_user(str(uid))
            ]
        logger.info(
            f"用户列表加载完成, 已筛选用户数: {len(self.script_info.user_list)}"
        )

    async def main_task(self):

        self.check_result = await self.check()
        if self.check_result != "Pass":
            logger.warning(f"未通过配置检查: {self.check_result}")
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(level="error", message=self.check_result),
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
                self.emulator_manager,
            )
            await self.spawn(task)

    async def final_task(self):

        if self.check_result != "Pass":
            self.script_info.status = "异常"
            return

        logger.info("MaaEnd 主任务已结束, 开始执行后续操作")
        await Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].unlock()
        logger.success(f"已解锁脚本配置 {self.script_info.script_id}")

        if self.task_info.mode in ["AutoProxy"]:
            if self.emulator_manager is not None:
                await self.emulator_manager.close(
                    self.script_config.get("Game", "EmulatorIndex")
                )
            await Config.ScriptConfig[
                uuid.UUID(self.script_info.script_id)
            ].UserData.load(await self.user_config.toDict())
            await Config.ScriptConfig.save()

            error_count = sum(
                1 for u in self.script_info.user_list if u.status == "异常"
            )
            over_count = sum(
                1 for u in self.script_info.user_list if u.status == "完成"
            )
            wait_count = sum(
                1 for u in self.script_info.user_list if u.status == "等待"
            )

            title = f"{datetime.now().strftime('%m-%d')} | {self.script_info.name or '空白'}的{TASK_MODE_ZH[self.task_info.mode]}任务报告"
            task_result = append_task_game_sign_summary(
                self.task_info, self.script_info.result
            )
            has_game_sign_summary = task_result != self.script_info.result
            result = {
                "title": f"{TASK_MODE_ZH[self.task_info.mode]}任务报告",
                "script_name": self.script_info.name or "空白",
                "start_time": self.begin_time,
                "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "completed_count": over_count,
                "uncompleted_count": error_count + wait_count,
                "result": task_result,
                "game_sign_summary": has_game_sign_summary,
            }

            try:
                push_result = await push_notification(
                    mode="代理结果",
                    title=title,
                    message=result,
                    user_config=None,
                    task_info=self.task_info,
                )
                finalize_task_game_sign_notification(
                    self.task_info, has_game_sign_summary, push_result
                )
            except Exception as e:
                logger.opt(exception=True).warning(f"推送代理结果时出现异常: {e}")
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="error", message=f"推送代理结果时出现异常: {e}"
                    ),
                )

        # 还原配置
        if (self.temp_path).exists():
            shutil.rmtree(self.maaend_config_dir, ignore_errors=True)
            shutil.copytree(self.temp_path, self.maaend_config_dir, dirs_exist_ok=True)
        shutil.rmtree(self.temp_path, ignore_errors=True)

        self.script_info.status = "完成"

    async def on_crash(self, e: Exception):
        self.script_info.status = "异常"
        logger.opt(exception=True).warning(f"MaaEnd任务出现异常: {e}")
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level="error", message=f"MaaEnd任务出现异常: {e}"),
        )
