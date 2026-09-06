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
import uuid
from contextlib import suppress
from pathlib import Path

from app.core import Config
from app.models.config import BetterGIConfig, BetterGIUserConfig
from app.models.ConfigBase import MultipleConfig
from app.models.task import ScriptItem, TaskExecuteBase
from app.services import System
from app.utils import ProcessManager, get_logger
from app.utils.platform import IS_ELEVATED

from .AutoProxy import _BGI_REL_EXE
from .tools import one_dragon

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
        # 脚本级配置（"Default"）强制独立配置；真实用户读 IfUseMasConfig
        self.use_mas_config = True
        if self.cur_user_item.user_id != "Default":
            self.use_mas_config = bool(
                self.user_config[uuid.UUID(self.cur_user_item.user_id)].get(
                    "Info", "IfUseMasConfig"
                )
            )
        self.process_manager = ProcessManager()
        self.wait_event = asyncio.Event()
        self.crashed = False
        self.root_path = Path(self.script_config.get("Info", "RootPath"))
        self.exe_path = self.root_path / _BGI_REL_EXE

    def _target_user_config(self) -> BetterGIUserConfig | None:
        """返回当前会话对应的用户配置；脚本级（"Default"）返回 None。"""
        if self.cur_user_item.user_id == "Default":
            return None
        return self.user_config[uuid.UUID(self.cur_user_item.user_id)]

    def _cleanup_leftover_slot(self) -> None:
        """清理上一轮残留的 MAS 运行时槽位/物化组（若存在；安全幂等，不误删用户文件）。"""
        if not self.use_mas_config:
            return
        with suppress(Exception):
            # 按用户短 id 前缀扫描删除历史残留物化组（只命中 MAS-{短id}-*，不碰 BGI 本体）
            one_dragon.cleanup_leftover_mas_groups(
                self.root_path, self.script_info.script_id, self.cur_user_item.user_id
            )
        with suppress(Exception):
            # 仅删除确由 MAS 写入的槽位（owner/backup 标记校验在函数内）
            one_dragon.remove_one_dragon_slot(
                self.root_path, self.script_info.script_id
            )

    async def main_task(self) -> None:
        await self._kill_processes()
        logger.info(f"启动 BetterGI 设置: {self.exe_path}")
        self.cur_user_item.status = "运行"
        # 任务配置以 MAS 前端为准：GUI 直控只打开 BGI 供查看游戏/程序环境，
        # 不再预置一条龙槽位，也不在结束后回读（MAS 前端是唯一编辑入口）。
        self._cleanup_leftover_slot()
        # 仅当 MAS 自身未提权时才走 runas 触发 UAC；已提权时子进程自动继承
        await self.process_manager.open_process(
            self.exe_path,
            elevated=self.script_config.get("Run", "UseAdmin") and not IS_ELEVATED,
        )
        await self.wait_event.wait()

    async def final_task(self) -> None:
        self.wait_event.set()
        await self._kill_processes()
        if not self.crashed:
            logger.success("BetterGI 直控配置已打开（任务配置请以 MAS 前端为准）")
            self.cur_user_item.status = "完成"
        self._cleanup_leftover_slot()

    async def on_crash(self, e: Exception) -> None:
        self.crashed = True
        self.cur_user_item.status = "异常"
        logger.opt(exception=True).warning(f"BetterGI 设置任务出现异常: {e}")
        with suppress(Exception):
            await self._kill_processes()
        self._cleanup_leftover_slot()
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
