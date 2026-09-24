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

import asyncio
from contextlib import suppress

from app.core.ws import Publisher, protocol
from app.models.schema import WSTaskNoticeData
from app.models.task import ScriptItem, TaskExecuteBase
from app.utils import ProcessManager, get_logger

from .AutoProxy import ensure_launcher_auto_start, kill_project_processes
from .project import OkScriptProject

logger = get_logger("OkScript 原生界面")


class ScriptConfigTask(TaskExecuteBase):
    """无参数打开 ok-script 项目的原生界面，供用户修改项目自己的设置。

    配置来源是「直接使用项目原生配置」：会话前后都不下发、不回写，项目界面里保存的
    设置就是运行时使用的设置。会话由前端遮罩的「保存并关闭」结束，结束时关闭项目。
    """

    def __init__(self, script_info: ScriptItem, project: OkScriptProject):
        super().__init__()
        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")
        self.task_info = script_info.task_info
        self.script_info = script_info
        self.project = project
        self.cur_user_item = self.script_info.user_list[self.script_info.current_index]
        self.process_manager = ProcessManager()
        self.wait_event = asyncio.Event()
        self.crashed = False

    async def main_task(self) -> None:
        await self._kill_processes()
        ensure_launcher_auto_start(self.project)
        logger.info(f"打开 {self.project.app_name} 原生界面: {self.project.exe_path}")
        self.cur_user_item.status = "运行"
        await self.process_manager.open_process(self.project.exe_path)
        await self.wait_event.wait()

    async def final_task(self) -> None:
        self.wait_event.set()
        await self._kill_processes()
        if not self.crashed:
            logger.success(
                f"{self.project.app_name} 原生界面已关闭，设置由项目自行保存"
            )
            self.cur_user_item.status = "完成"

    async def on_crash(self, e: Exception) -> None:
        self.crashed = True
        self.cur_user_item.status = "异常"
        logger.opt(exception=True).warning(f"打开原生界面出现异常: {e}")
        with suppress(Exception):
            await self._kill_processes()
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(
                level="error",
                message=f"打开 {self.project.app_name} 原生界面出现异常: {e}",
            ),
        )

    async def _kill_processes(self) -> None:
        await kill_project_processes(self.project, self.process_manager)
