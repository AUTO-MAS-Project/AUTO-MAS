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
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""奇想盒直控配置：无参数拉起 whimbox_app.exe，用户在原生 GUI 修改设置。

MAS 不预置不回读（BetterGI「GUI 直控只打开本体」同款先例）；会话进入/退出
各归档一次 config.json（通用恢复池 snapshot，指纹去重），捕捉用户经 app 的
原生修改前后态，作为跨会话恢复锚点。
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from pathlib import Path

from app.core.ws import Publisher, protocol
from app.models.config import WhimboxConfig, WhimboxUserConfig
from app.models.ConfigBase import MultipleConfig
from app.models.schema import WSTaskNoticeData
from app.models.task import ScriptItem, TaskExecuteBase
from app.services import System
from app.task.proxy_helpers import push_dispatch_log
from app.utils import ProcessInfo, ProcessManager, get_logger
from app.utils.platform import IS_ELEVATED

from .tools.upstream import APP_EXE_NAME, WheelAssetsConfigSurface

logger = get_logger("奇想盒 脚本设置")


class ScriptConfigTask(TaskExecuteBase):
    """无参数启动奇想盒 app，供用户修改程序设置（原生 GUI 直控）。"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: WhimboxConfig,
        user_config: MultipleConfig[WhimboxUserConfig],
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
        self.root_path = Path(str(self.script_config.get("Info", "RootPath") or ""))
        self.exe_path = self.root_path / APP_EXE_NAME
        self.target_process = ProcessInfo(
            name=APP_EXE_NAME, exe=str(self.exe_path), cmdline=None
        )
        self.config_surface = WheelAssetsConfigSurface(self.root_path)

    async def main_task(self) -> None:
        self.cur_user_item.status = "运行"
        # 会话进入时归档（捕捉「用户在 app 内修改前」的原生配置态）
        with suppress(Exception):
            self.config_surface.snapshot_entry()
        await push_dispatch_log(self.script_info, "启动奇想盒 app（直控配置）")
        # 仅当 MAS 自身未提权时才走 runas 触发 UAC；已提权时子进程自动继承
        await self.process_manager.open_process(
            self.exe_path,
            elevated=bool(self.script_config.get("Run", "UseAdmin"))
            and not IS_ELEVATED,
            target_process=self.target_process,
        )
        await self.wait_event.wait()

    async def final_task(self) -> None:
        self.wait_event.set()
        await self._kill_processes()
        # 会话退出时归档（固化用户在 app 中已保存的编辑，作为恢复锚点）
        with suppress(Exception):
            self.config_surface.snapshot_entry()
        if not self.crashed:
            logger.success("奇想盒直控配置会话已结束")
            self.cur_user_item.status = "完成"

    async def on_crash(self, e: Exception) -> None:
        self.crashed = True
        self.cur_user_item.status = "异常"
        logger.opt(exception=True).warning(f"奇想盒设置任务出现异常: {e}")
        with suppress(Exception):
            await self._kill_processes()
        # 异常退出也先归档（固化 GUI 中已保存的编辑）
        with suppress(Exception):
            self.config_surface.snapshot_entry()
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(
                level="error", message=f"奇想盒设置任务出现异常: {e}"
            ),
        )

    async def _kill_processes(self) -> None:
        try:
            await self.process_manager.kill()
        except Exception as e:
            logger.opt(exception=True).warning(f"通过进程管理器中止奇想盒失败: {e}")

        try:
            await System.kill_process(self.exe_path)
        except Exception as e:
            logger.opt(exception=True).warning(f"中止奇想盒进程失败: {e}")
