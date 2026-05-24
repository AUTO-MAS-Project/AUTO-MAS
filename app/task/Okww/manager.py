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

from pathlib import Path

from app.core import Config, EmulatorManager
from app.models.task import TaskExecuteBase, ScriptItem, UserItem
from app.models.config import OkwwConfig, OkwwUserConfig
from app.models.ConfigBase import MultipleConfig
from app.models.emulator import DeviceBase
from app.utils import get_logger, ProcessManager

from .AutoProxy import AutoProxyTask
from .ScriptConfig import ScriptConfigTask

logger = get_logger("OK-WW 调度器")

METHOD_BOOK: dict[str, type[AutoProxyTask | ScriptConfigTask]] = {
    "AutoProxy": AutoProxyTask,
    "ScriptConfig": ScriptConfigTask,
}


class OkwwManager(TaskExecuteBase):
    """OK-WW 控制器（ok-script 线）"""

    def __init__(self, script_info: ScriptItem):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.check_result = "-"

    async def check(self) -> str:
        if self.task_info.mode not in METHOD_BOOK:
            return "不支持的任务模式, 请检查任务配置！"

        if not isinstance(Config.ScriptConfig[uuid.UUID(self.script_info.script_id)], OkwwConfig):
            return "脚本配置类型错误, 不是 OK-WW 类型"

        # 复用通用脚本的基本校验：配置会话写盘（ConfigFile）存在性
        if self.task_info.mode == "AutoProxy":
            script_uid = uuid.UUID(self.script_info.script_id)
            if (not self.script_info.user_list) or (
                self.script_info.user_list
                and self.script_info.user_list[0].name == "暂未加载"
            ):
                self.script_info.user_list = [
                    UserItem(user_id=str(uid), name=config.get("Info", "Name"), status="等待")
                    for uid, config in Config.ScriptConfig[script_uid].UserData.items()
                    if config.get("Info", "Status")
                ]
            if not self.script_info.user_list:
                return "当前没有可执行的用户，请先添加并启用用户"
            user_uid = uuid.UUID(self.script_info.user_list[self.script_info.current_index].user_id)
            user_cfg = Config.ScriptConfig[script_uid].UserData[user_uid]
            mode = str(user_cfg.get("Info", "Mode") or "简洁")
            config_owner = "Default" if mode == "简洁" else str(user_uid)
            if not (
                Path.cwd() / f"data/{script_uid}/{config_owner}/ConfigFile"
            ).exists():
                if mode == "简洁":
                    return "未找到共享的 OK-WW 配置文件，请先在脚本页完成「配置 ok-ww」步骤"
                return "未找到用户的 OK-WW 配置文件，请先在用户配置页完成「配置 ok-ww」步骤"

        return "Pass"

    async def prepare(self):
        self.script_config = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]
        self.user_config = self.script_config.UserData

        if not isinstance(self.script_config, OkwwConfig):
            raise TypeError("脚本配置类型错误")
        if not isinstance(self.user_config, MultipleConfig):
            raise TypeError("用户配置类型错误")

        # 构建用户列表：ScriptConfig 模式使用 task_info.user_id（Default 或具体用户），AutoProxy 模式遍历脚本用户
        if self.task_info.mode == "ScriptConfig":
            self.script_info.user_list = [
                UserItem(user_id=self.task_info.user_id or "Default", name="", status="等待")
            ]
        else:
            self.script_info.user_list = [
                UserItem(user_id=str(uid), name=config.get("Info", "Name"), status="等待")
                for uid, config in self.user_config.items()
                if config.get("Info", "Status")
            ]

        # 启动与收尾解耦：Enabled=由 MAS 拉起游戏；CloseOnFinish=由 MAS 结束游戏（可单独开启）
        self.game_manager: ProcessManager | DeviceBase | None = None
        if self.script_config.get("Game", "Enabled") or self.script_config.get(
            "Game", "CloseOnFinish"
        ):
            if self.script_config.get("Game", "Type") == "Emulator":
                self.game_manager = EmulatorManager()
            elif self.script_config.get("Game", "Type") == "Client":
                self.game_manager = ProcessManager()

    async def main_task(self):
        await self.prepare()

        method_cls = METHOD_BOOK[self.task_info.mode]
        method = method_cls(
            script_info=self.script_info,
            script_config=self.script_config,  # type: ignore[arg-type]
            user_config=self.user_config,  # type: ignore[arg-type]
            game_manager=self.game_manager,
        )

        self.check_result = await method.check()
        if self.check_result != "Pass":
            self.script_info.status = "异常"
            await Config.send_websocket_message(
                id=self.task_info.task_id, type="Info", data={"Error": self.check_result}
            )
            return

        await self.spawn(method)

    async def final_task(self):
        if self.check_result != "Pass":
            self.script_info.status = "异常"
            return

        await Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].unlock()

        if self.task_info.mode == "AutoProxy":
            await Config.ScriptConfig[
                uuid.UUID(self.script_info.script_id)
            ].UserData.load(await self.user_config.toDict())

        self.script_info.status = "完成"

    async def on_crash(self, e: Exception):
        self.script_info.status = "异常"
        logger.exception(f"OK-WW任务出现异常: {e}")
        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Info",
            data={"Error": f"OK-WW任务出现异常: {e}"},
        )

