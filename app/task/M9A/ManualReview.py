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


import uuid
import asyncio
from pathlib import Path
from datetime import datetime

from app.core import Config, Broadcast
from app.models.task import TaskExecuteBase, ScriptItem
from app.models.ConfigBase import MultipleConfig
from app.models.config import M9AConfig, M9AUserConfig
from app.models.emulator import DeviceBase
from app.utils import get_logger
from app.utils.constants import STARRAIL_PACKAGE_NAME, UTC4

logger = get_logger("M9A人工排查")


class ManualReviewTask(TaskExecuteBase):
    """人工排查模式"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: M9AConfig,
        user_config: MultipleConfig[M9AUserConfig],
        emulator_manager: DeviceBase,
    ):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config
        self.emulator_manager = emulator_manager
        self.cur_user_item = self.script_info.user_list[self.script_info.current_index]
        self.cur_user_uid = uuid.UUID(self.cur_user_item.user_id)
        self.cur_user_config = self.user_config[self.cur_user_uid]
        self.check_result = "-"

    async def check(self) -> str:

        if (
            self.cur_user_config.get("Info", "Mode") == "详细"
            and not (
                Path.cwd()
                / f"data/{self.script_info.script_id}/{self.cur_user_uid}/ConfigFile"
            ).exists()
        ):
            self.cur_user_item.status = "异常"
            return "未找到用户的 M9A 配置文件，请先在用户配置页完成 「M9A配置」 步骤"
        return "Pass"

    async def prepare(self):

        self.message_queue = asyncio.Queue()
        await Broadcast.subscribe(self.message_queue)
        self.wait_event = asyncio.Event()

        self.run_book = {"SignIn": False, "PassCheck": False}

    async def main_task(self):
        """人工排查模式主逻辑"""

        # 初始化每日代理状态
        self.curdate = datetime.now(tz=UTC4).strftime("%Y-%m-%d")
        if self.cur_user_config.get("Data", "LastProxyDate") != self.curdate:
            await self.cur_user_config.set("Data", "LastProxyDate", self.curdate)
            await self.cur_user_config.set("Data", "ProxyTimes", 0)

        self.check_result = await self.check()
        if self.check_result != "Pass":
            if self.cur_user_item.status == "异常":
                await Config.send_websocket_message(
                    id=self.task_info.task_id,
                    type="Info",
                    data={
                        "Error": f"用户 {self.cur_user_item.name} 检查未通过: {self.check_result}"
                    },
                )
            return

        await self.prepare()

        logger.info(f"开始排查用户: {self.cur_user_uid}")
        self.cur_user_item.status = "运行"

        while True:

            try:
                self.script_info.log = "正在启动模拟器"
                emulator_info = await self.emulator_manager.open(
                    self.script_config.get("Emulator", "Index"),
                    STARRAIL_PACKAGE_NAME[self.cur_user_config.get("Info", "Server")],
                )
            except Exception as e:

                logger.exception(
                    f"用户: {self.cur_user_item.user_id} - 模拟器启动失败: {e}"
                )
                self.script_info.log = (
                    f"正在启动模拟器\n模拟器启动失败: {e}\n正在中止相关程序"
                )
                try:
                    await self.emulator_manager.close(
                        self.script_config.get("Emulator", "Index")
                    )
                except Exception as e:
                    logger.exception(f"关闭模拟器失败: {e}")

                uid = str(uuid.uuid4())
                await Config.send_websocket_message(
                    id=self.task_info.task_id,
                    type="Message",
                    data={
                        "message_id": uid,
                        "type": "Question",
                        "title": "操作提示",
                        "message": "模拟器启动失败, 是否重试？",
                        "options": ["是", "否"],
                    },
                )
                result = await self._wait_for_user_response(uid)
                if not result.get("data", {}).get("choice", False):
                    break
                continue

            self.script_info.log = (
                "正在启动模拟器\n模拟器已启动，正在登录「崩坏·星穹铁道」..."
            )
            if self.cur_user_config.get("Info", "Id") == "" or await login(
                emulator_info,
                STARRAIL_PACKAGE_NAME[self.cur_user_config.get("Info", "Server")],
                self.cur_user_config.get("Info", "Id"),
                self.cur_user_config.get("Info", "Password"),
            ):
                self.run_book["SignIn"] = True
                break
            else:
                logger.error(
                    f"用户: {self.cur_user_item.user_id} - 「崩坏·星穹铁道」登录失败"
                )
                self.script_info.log = "正在启动模拟器\n模拟器已启动，正在登录「崩坏·星穹铁道」...\n「崩坏·星穹铁道」登录失败\n正在中止相关程序"

                try:
                    await self.emulator_manager.close(
                        self.script_config.get("Emulator", "Index")
                    )
                except Exception as e:
                    logger.exception(f"关闭模拟器失败: {e}")

                uid = str(uuid.uuid4())
                await Config.send_websocket_message(
                    id=self.task_info.task_id,
                    type="Message",
                    data={
                        "message_id": uid,
                        "type": "Question",
                        "title": "操作提示",
                        "message": "未能正确登录到「崩坏·星穹铁道」, 是否重试？",
                        "options": ["是", "否"],
                    },
                )
                result = await self._wait_for_user_response(uid)
                if not result.get("data", {}).get("choice", False):
                    break

        if self.run_book["SignIn"]:

            try:
                await self.emulator_manager.setVisible(
                    self.script_config.get("Emulator", "Index"), True
                )
            except Exception as e:
                logger.exception(f"模拟器显示失败: {e}")
            uid = str(uuid.uuid4())
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Message",
                data={
                    "message_id": uid,
                    "type": "Question",
                    "title": "操作提示",
                    "message": "请检查用户代理情况, 该用户是否正确完成代理任务？",
                    "options": ["是", "否"],
                },
            )
            result = await self._wait_for_user_response(uid)
            if result.get("data", {}).get("choice", False):
                self.run_book["PassCheck"] = True

    async def _wait_for_user_response(self, message_id: str):
        """等待用户交互响应"""
        logger.info(f"等待客户端回应消息: {message_id}")
        while True:
            message = await self.message_queue.get()
            if message.get("id") == message_id and message.get("type") == "Response":
                self.message_queue.task_done()
                logger.success(f"收到客户端回应消息: {message_id}")
                return message
            else:
                self.message_queue.task_done()

    async def final_task(self):

        if self.check_result != "Pass":
            return

        if self.run_book["SignIn"] and self.run_book["PassCheck"]:
            logger.info(f"用户 {self.cur_user_uid} 通过人工排查")
            await self.cur_user_config.set("Data", "IfPassCheck", True)
            self.cur_user_item.status = "完成"
        else:
            logger.info(f"用户 {self.cur_user_uid} 未通过人工排查")
            await self.cur_user_config.set("Data", "IfPassCheck", False)
            self.cur_user_item.status = "异常"

    async def on_crash(self, e: Exception):
        self.cur_user_item.status = "异常"
        logger.exception(f"人工排查任务出现异常: {e}")
        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Info",
            data={"Error": f"人工排查任务出现异常: {e}"},
        )
