#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

import uuid
from contextlib import suppress

from app.core import Config
from app.models.ConfigBase import MultipleConfig
from app.models.config import OkefConfig, OkefUserConfig
from app.models.task import ScriptItem, TaskExecuteBase, UserItem
from app.utils import ProcessManager, get_logger

from .AutoProxy import AutoProxyTask

logger = get_logger("OK-EF 调度器")

METHOD_BOOK: dict[str, type[AutoProxyTask]] = {
    "AutoProxy": AutoProxyTask,
}


class OkefManager(TaskExecuteBase):
    """OK-EF 控制器（ok-script 线）"""

    def __init__(self, script_info: ScriptItem):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.check_result = "-"
        self.script_config: OkefConfig | None = None
        self.user_config: MultipleConfig[OkefUserConfig] | None = None
        self.game_manager: ProcessManager | None = None

    async def check(self) -> str:
        if self.task_info.mode not in METHOD_BOOK:
            return "不支持的任务模式, 请检查任务配置！"

        script_uid = uuid.UUID(self.script_info.script_id)
        script_config = Config.ScriptConfig[script_uid]
        if not isinstance(script_config, OkefConfig):
            return "脚本配置类型错误, 不是 OK-EF 类型"

        if (not self.script_info.user_list) or (
            self.script_info.user_list
            and self.script_info.user_list[0].name == "暂未加载"
        ):
            self.script_info.user_list = [
                UserItem(user_id=str(uid), name=config.get("Info", "Name"), status="等待")
                for uid, config in script_config.UserData.items()
                if config.get("Info", "Status")
                and config.get("Info", "RemainedDay") != 0
            ]

        if not self.script_info.user_list:
            return "当前没有可执行的用户，请先添加并启用用户"

        return "Pass"

    async def prepare(self) -> None:
        script_uid = uuid.UUID(self.script_info.script_id)
        await Config.ScriptConfig[script_uid].lock()
        self.script_config = Config.ScriptConfig[script_uid]

        if not isinstance(self.script_config, OkefConfig):
            raise TypeError("脚本配置类型错误")

        self.user_config = MultipleConfig([OkefUserConfig])
        await self.user_config.load(await self.script_config.UserData.toDict())
        logger.success(f"{self.script_info.script_id} 已锁定，OK-EF 用户配置已提取")

        self.script_info.user_list = [
            UserItem(user_id=str(uid), name=config.get("Info", "Name"), status="等待")
            for uid, config in self.user_config.items()
            if config.get("Info", "Status")
            and config.get("Info", "RemainedDay") != 0
        ]

        self.game_manager = ProcessManager()

    async def main_task(self) -> None:
        self.check_result = await self.check()
        if self.check_result != "Pass":
            self.script_info.status = "异常"
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={"Error": self.check_result},
            )
            return

        await self.prepare()

        if self.script_config is None or self.user_config is None:
            raise RuntimeError("OK-EF 运行配置未初始化")

        method_cls = METHOD_BOOK[self.task_info.mode]
        for self.script_info.current_index in range(len(self.script_info.user_list)):
            task = method_cls(
                script_info=self.script_info,
                script_config=self.script_config,
                user_config=self.user_config,
                game_manager=self.game_manager,
            )

            sub_check = await task.check()
            if sub_check != "Pass":
                self.check_result = sub_check
                current_user = self.script_info.user_list[self.script_info.current_index]
                if current_user.status == "等待":
                    current_user.status = "异常"
                await Config.send_websocket_message(
                    id=self.task_info.task_id,
                    type="Info",
                    data={"Error": sub_check},
                )
                continue

            await self.spawn(task)

    async def final_task(self) -> None:
        script_uid = uuid.UUID(self.script_info.script_id)
        script_cfg = Config.ScriptConfig[script_uid]

        try:
            if script_cfg.is_locked:
                await script_cfg.unlock()

            if self.user_config is not None:
                await script_cfg.UserData.load(await self.user_config.toDict())
                await Config.ScriptConfig.save()

            if self.check_result != "Pass" and not any(
                user.status == "完成" for user in self.script_info.user_list
            ):
                self.script_info.status = "异常"
                return

            if any(user.status == "异常" for user in self.script_info.user_list):
                self.script_info.status = "异常"
            else:
                self.script_info.status = "完成"
        finally:
            if script_cfg.is_locked:
                with suppress(Exception):
                    await script_cfg.unlock()

    async def on_crash(self, e: Exception) -> None:
        self.script_info.status = "异常"
        logger.exception(f"OK-EF任务出现异常: {e}")

        try:
            script_uid = uuid.UUID(self.script_info.script_id)
            script_cfg = Config.ScriptConfig[script_uid]

            if script_cfg.is_locked:
                with suppress(Exception):
                    await script_cfg.unlock()

            if self.user_config is not None:
                await script_cfg.UserData.load(await self.user_config.toDict())
                await Config.ScriptConfig.save()
        except Exception:
            logger.exception("on_crash 写回 OK-EF UserConfig 失败，放弃本次状态变更")

        try:
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={"Error": f"OK-EF任务出现异常: {e}"},
            )
        except Exception as send_error:
            logger.exception(f"发送 OK-EF 调度器异常通知失败: {send_error}")
