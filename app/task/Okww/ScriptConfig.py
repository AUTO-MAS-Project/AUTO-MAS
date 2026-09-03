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

import asyncio
import shutil
import uuid
from contextlib import suppress
from pathlib import Path

from app.core.ws import Publisher, protocol
from app.models.config import OkwwConfig, OkwwUserConfig
from app.models.ConfigBase import MultipleConfig
from app.models.schema import WSTaskNoticeData
from app.models.task import ScriptItem, TaskExecuteBase
from app.services import System
from app.utils import ProcessManager, get_logger

from .AutoProxy import (
    _OKWW_REL_CONFIG_DIR,
    _OKWW_REL_EXE,
    _OKWW_REL_PYTHONW,
    _configure_okww_launcher,
    _okww_config_mode,
    _okww_mas_config_dir,
    _update_json,
)

logger = get_logger("OK-WW 脚本设置")


class ScriptConfigTask(TaskExecuteBase):
    """无参数启动 OK-WW 本体，供用户修改程序设置。"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: OkwwConfig,
        user_config: MultipleConfig[OkwwUserConfig],
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
        self.exe_path = self.root_path / _OKWW_REL_EXE
        self.script_config_path = self.root_path / _OKWW_REL_CONFIG_DIR
        target_user_id = self.cur_user_item.user_id
        mode = "脚本"
        self.resource: str | None = None
        if target_user_id != "Default":
            target_user_config = self.user_config[uuid.UUID(target_user_id)]
            mode = _okww_config_mode(target_user_config.get("Info", "Mode"))
            self.resource = str(target_user_config.get("Info", "Resource"))
        self.use_mas_config = mode != "直控"
        self.mas_config_dir = (
            _okww_mas_config_dir(self.script_info.script_id, target_user_id, mode)
            if self.use_mas_config
            else None
        )

    async def main_task(self) -> None:
        await self._kill_processes()
        _configure_okww_launcher(self.root_path, self.resource)
        if (
            self.use_mas_config
            and self.mas_config_dir
            and self.mas_config_dir.is_dir()
            and any(item.is_file() for item in self.mas_config_dir.rglob("*"))
        ):
            temporary_path = self.script_config_path.with_name(
                self.script_config_path.name + ".tmp"
            )
            shutil.rmtree(temporary_path, ignore_errors=True)
            shutil.copytree(self.mas_config_dir, temporary_path)
            shutil.rmtree(self.script_config_path, ignore_errors=True)
            temporary_path.rename(self.script_config_path)
        logger.info(f"启动 OK-WW 设置: {self.exe_path}")
        self.cur_user_item.status = "运行"
        await self.process_manager.open_process(self.exe_path)
        await self.wait_event.wait()

    async def final_task(self) -> None:
        self.wait_event.set()
        await self._kill_processes()
        if not self.crashed and self.use_mas_config and self.mas_config_dir:
            _configure_okww_launcher(self.root_path, self.resource)
            if not self.script_config_path.is_dir():
                raise FileNotFoundError(
                    "未找到 OK-WW 配置目录，请先在 OK-WW 中保存设置"
                )
            _update_json(
                self.script_config_path / "Basic Options.json",
                {"Exit App when Game Exits": True},
            )
            temporary_path = self.mas_config_dir.with_name(
                self.mas_config_dir.name + ".tmp"
            )
            shutil.rmtree(temporary_path, ignore_errors=True)
            temporary_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(self.script_config_path, temporary_path)
            shutil.rmtree(self.mas_config_dir, ignore_errors=True)
            temporary_path.rename(self.mas_config_dir)
            logger.success(f"OK-WW 配置已保存到: {self.mas_config_dir}")
            self.cur_user_item.status = "完成"
        elif not self.crashed:
            logger.success("OK-WW 直控配置已由脚本原生 GUI 保存")
            self.cur_user_item.status = "完成"

    async def on_crash(self, e: Exception) -> None:
        self.crashed = True
        self.cur_user_item.status = "异常"
        logger.opt(exception=True).warning(f"OK-WW 设置任务出现异常: {e}")
        with suppress(Exception):
            await self._kill_processes()
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(
                level="error", message=f"OK-WW 设置任务出现异常: {e}"
            ),
        )

    async def _kill_processes(self) -> None:
        try:
            await self.process_manager.kill()
        except Exception as e:
            logger.opt(exception=True).warning(f"通过进程管理器中止 OK-WW 失败: {e}")

        for path in (self.exe_path, self.root_path / _OKWW_REL_PYTHONW):
            try:
                await System.kill_process(path)
            except Exception as e:
                logger.opt(exception=True).warning(f"中止 OK-WW 进程失败 ({path}): {e}")
