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

"""BAAH 控制器。

按用户逐个拉起 BAAH 自动代理任务，结束时统一组装任务报告并推送。
"""

import uuid
from datetime import datetime

from app.core import Config
from app.core.emulator_manager import EmulatorManager
from app.core.ws import Publisher, protocol
from app.models.config import BAAHConfig, BAAHUserConfig
from app.models.ConfigBase import MultipleConfig
from app.models.emulator import DeviceBase
from app.models.schema import WSTaskNoticeData
from app.models.task import ScriptItem, TaskExecuteBase, UserItem
from app.task.emulator_core import close_emulator
from app.tools.push_log import build_user_result_text
from app.utils import get_logger
from app.utils.constants import TASK_MODE_ZH

from .AutoProxy import AutoProxyTask
from .tools import push_notification

logger = get_logger("BAAH 调度器")

METHOD_BOOK: dict[str, type[AutoProxyTask]] = {
    "AutoProxy": AutoProxyTask,
}


class BAAHManager(TaskExecuteBase):
    """BAAH 控制器"""

    def __init__(self, script_info: ScriptItem):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.check_result = "-"
        self.emulator_manager: DeviceBase | None = None

    async def check(self) -> str:
        """校验 BAAH 脚本配置是否可用"""

        if self.task_info.mode not in METHOD_BOOK:
            return "不支持的任务模式, 请检查任务配置！"

        script_config = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]
        if not isinstance(script_config, BAAHConfig):
            return "脚本配置类型错误, 不是 BAAH 脚本类型"

        if script_config.get("Emulator", "Id") == "-" or script_config.get(
            "Emulator", "Index"
        ) in ["", "-"]:
            return "未完成模拟器配置, 请检查脚本配置中的模拟器设置！"

        if not str(script_config.get("Info", "RootPath")).strip():
            return "未填写 BAAH 程序目录, 请检查脚本配置中的程序目录设置！"

        if not str(script_config.get("Script", "BAAHPath")).strip():
            return "未填写 BAAH 主程序路径, 请检查脚本配置中的主程序路径设置！"

        return "Pass"

    async def prepare(self):
        """运行前准备"""

        await Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].lock()
        self.script_config = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]
        self.user_config = MultipleConfig([BAAHUserConfig])
        await self.user_config.load(await self.script_config.UserData.toDict())
        logger.success(f"{self.script_info.script_id} 已锁定, BAAH 脚本配置提取完成")

        self.script_info.user_list = [
            UserItem(user_id=str(uid), name=config.get("Info", "Name"), status="等待")
            for uid, config in self.user_config.items()
            if config.get("Info", "Status")
            and config.get("Info", "RemainedDay") != 0
            and self.task_info.is_target_user(str(uid))
        ]
        logger.info(f"用户列表加载完成, 已筛选用户数: {len(self.script_info.user_list)}")

        # 初始化模拟器管理器：模拟器的启动与关闭统一由本软件调度,
        # BAAH 自身不再负责拉起模拟器
        self.emulator_manager: DeviceBase = await EmulatorManager.get_emulator_instance(
            self.script_config.get("Emulator", "Id")
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

        if not isinstance(self.script_config, BAAHConfig):
            raise RuntimeError("脚本配置类型错误, 不是 BAAH 脚本类型")

        for self.script_info.current_index in range(len(self.script_info.user_list)):
            task = METHOD_BOOK[self.task_info.mode](
                self.script_info,
                self.script_config,
                self.user_config,
                self.emulator_manager,
            )
            await self.spawn(task)

    async def final_task(self):
        """运行结束后的收尾工作"""

        if self.check_result != "Pass":
            self.script_info.status = "异常"
            return self.check_result

        logger.info("BAAH 任务已结束, 开始执行后续操作")

        await Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].unlock()
        logger.success(f"已解锁脚本配置 {self.script_info.script_id}")

        if self.task_info.mode == "AutoProxy":
            await close_emulator(self)
            await Config.ScriptConfig[
                uuid.UUID(self.script_info.script_id)
            ].UserData.load(await self.user_config.toDict())
            await Config.ScriptConfig.save()

            error_count = sum(
                1 for u in self.script_info.user_list if u.status == "异常"
            )
            over_count = sum(1 for u in self.script_info.user_list if u.status == "完成")
            wait_count = sum(1 for u in self.script_info.user_list if u.status == "等待")

            title = (
                f"{datetime.now().strftime('%m-%d')} | "
                f"{self.script_info.name or '空白'}的"
                f"{TASK_MODE_ZH[self.task_info.mode]}任务报告"
            )
            ## 按用户交错组装「用户结果行 + 该用户节点详情」，
            ## 失败类型条目仅在本次任务存在未完成用户时纳入报告
            has_uncompleted = error_count + wait_count > 0
            user_result_text = build_user_result_text(
                self.script_info.user_list, has_uncompleted
            )
            result = {
                "title": f"{TASK_MODE_ZH[self.task_info.mode]}任务报告",
                "script_name": self.script_info.name or "空白",
                "start_time": self.begin_time,
                "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "completed_count": over_count,
                "uncompleted_count": error_count + wait_count,
                "result": user_result_text,
            }

            try:
                await push_notification(
                    mode="代理结果",
                    title=title,
                    message=result,
                    user_config=None,
                    task_info=self.task_info,
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

        self.script_info.status = "完成"

    async def on_crash(self, e: Exception):

        self.script_info.status = "异常"
        logger.opt(exception=True).warning(f"BAAH 任务出现异常: {e}")
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level="error", message=f"BAAH 任务出现异常: {e}"),
        )

