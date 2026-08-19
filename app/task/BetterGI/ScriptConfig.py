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

import asyncio
from contextlib import suppress
from pathlib import Path

from app.core import Config
from app.models.ConfigBase import MultipleConfig
from app.models.config import BetterGIConfig, BetterGIUserConfig
from app.models.task import ScriptItem, TaskExecuteBase
from app.services import System
from app.utils import ProcessManager, get_logger

from .AutoProxy import _BGI_REL_EXE

logger = get_logger("BetterGI 脚本设置")


class ScriptConfigTask(TaskExecuteBase):
    """无参数启动 BetterGI 本体，供用户修改程序设置（原生 GUI 直控）。"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: BetterGIConfig,
        user_config: MultipleConfig[BetterGIUserConfig],
    ):
        super().__init__()
        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")
        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config
        self.cur_user_item = self.script_info.user_list[self.script_info.current_index]
        self.process_manager = ProcessManager()
        self.wait_event = asyncio.Event()
        self.crashed = False
        self.root_path = Path(self.script_config.get("Info", "RootPath"))
        self.exe_path = self.root_path / _BGI_REL_EXE

    async def main_task(self) -> None:
        await self._kill_processes()
        logger.info(f"启动 BetterGI 设置: {self.exe_path}")
        self.cur_user_item.status = "运行"
        await self.process_manager.open_process(self.exe_path)
        await self.wait_event.wait()

    async def final_task(self) -> None:
        self.wait_event.set()
        await self._kill_processes()
        if not self.crashed:
            logger.success("BetterGI 直控配置已由脚本原生 GUI 保存")
            self.cur_user_item.status = "完成"

    async def on_crash(self, e: Exception) -> None:
        self.crashed = True
        self.cur_user_item.status = "异常"
        logger.opt(exception=True).warning(f"BetterGI 设置任务出现异常: {e}")
        with suppress(Exception):
            await self._kill_processes()
        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Info",
            data={"Error": f"BetterGI 设置任务出现异常: {e}"},
        )

    async def _kill_processes(self) -> None:
        try:
            await self.process_manager.kill()
        except Exception as e:
            logger.opt(exception=True).warning(f"通过进程管理器中止 BetterGI 失败: {e}")

        try:
            await System.kill_process(self.exe_path)
        except Exception as e:
            logger.opt(exception=True).warning(f"中止 BetterGI 进程失败: {e}")
