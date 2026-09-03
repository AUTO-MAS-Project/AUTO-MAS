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

    def _write_one_dragon_config(self) -> None:
        """用户独立配置模式下，把该用户组开关写入一条龙配置并载入 BetterGI。"""
        if not self.use_mas_config:
            return
        target = self._target_user_config()
        if target is None:
            return
        one_dragon.write_user_one_dragon(
            self.root_path,
            self.script_info.script_id,
            self.cur_user_item.user_id,
            str(target.get("Task", "OneDragonConfigName") or ""),
            list(target.get("OneDragon", "Groups") or []),
            custom_groups=one_dragon.parse_custom_groups(
                target.get("OneDragon", "CustomGroups") or ""
            ),
            manage_custom_groups=bool(target.get("OneDragon", "IfUseCustomGroups")),
        )

    def _snapshot_one_dragon_config(self) -> None:
        """把 BetterGI 现有的一条龙配置回读为 per-user 副本（捕获 GUI 中改的设置）。

        独立模式下 ``write_user_one_dragon`` 物化到 MAS 槽位，用户在 BGI GUI 里编辑的就是
        槽位，故读取源改为槽位名，per-user 缓存 key 仍是用户所选名。
        """
        if not self.use_mas_config:
            return
        target = self._target_user_config()
        if target is None:
            return
        config_name = str(target.get("Task", "OneDragonConfigName") or "")
        read_name = (
            one_dragon.launch_slot_name()
            if one_dragon.launch_slot_name()
            != one_dragon.resolve_config_name(config_name)
            else config_name
        )
        one_dragon.snapshot_user_one_dragon(
            self.root_path,
            self.script_info.script_id,
            self.cur_user_item.user_id,
            config_name,
            read_name=read_name,
        )

    async def main_task(self) -> None:
        await self._kill_processes()
        logger.info(f"启动 BetterGI 设置: {self.exe_path}")
        self.cur_user_item.status = "运行"
        # 用户独立配置：先把该用户的一条龙配置载入 BetterGI，再打开 GUI 供其修改
        self._write_one_dragon_config()
        # 仅当 MAS 自身未提权时才走 runas 触发 UAC；已提权时子进程自动继承
        await self.process_manager.open_process(self.exe_path, elevated=not IS_ELEVATED)
        await self.wait_event.wait()

    async def final_task(self) -> None:
        self.wait_event.set()
        await self._kill_processes()
        if not self.crashed:
            # 用户独立配置：回读 BetterGI 现有配置，保存 GUI 中修改的设置
            self._snapshot_one_dragon_config()
            logger.success("BetterGI 直控配置已由脚本原生 GUI 保存")
            self.cur_user_item.status = "完成"
        # 快照已固化到 per-user 副本，删除 MAS 运行时槽位，避免残留到 BGI GUI
        if self.use_mas_config:
            with suppress(Exception):
                one_dragon.remove_one_dragon_slot(self.root_path)

    async def on_crash(self, e: Exception) -> None:
        self.crashed = True
        self.cur_user_item.status = "异常"
        logger.opt(exception=True).warning(f"BetterGI 设置任务出现异常: {e}")
        with suppress(Exception):
            await self._kill_processes()
        # 异常退出也先快照（固化 GUI 中已保存的编辑）再清理 MAS 运行时槽位，避免残留与丢编辑
        if self.use_mas_config:
            with suppress(Exception):
                self._snapshot_one_dragon_config()
            with suppress(Exception):
                one_dragon.remove_one_dragon_slot(self.root_path)
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
