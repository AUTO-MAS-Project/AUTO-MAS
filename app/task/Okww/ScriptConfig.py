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
import shlex
from pathlib import Path

from app.core import Config
from app.models.task import TaskExecuteBase, ScriptItem
from app.models.ConfigBase import MultipleConfig
from app.models.config import OkwwConfig, OkwwUserConfig
from app.models.emulator import DeviceBase
from app.services import System
from app.utils import get_logger, ProcessManager

from .config_io import deploy_mas_config_to_script, mas_config_dir, mas_config_ready, pull_script_config_to_mas

logger = get_logger("OK-WW 脚本设置")


class ScriptConfigTask(TaskExecuteBase):
    """OK-WW 配置会话：拉起 ok-ww.exe（不带 -t/-e），由用户在 GUI 内保存 configs"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: OkwwConfig,
        user_config: MultipleConfig[OkwwUserConfig],
        game_manager: ProcessManager | DeviceBase | None,
    ):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config
        self.game_manager = game_manager
        self.cur_user_item = self.script_info.user_list[self.script_info.current_index]

    async def check(self) -> str:
        if not Path(self.script_config.get("Info", "RootPath")).exists():
            return "OK-WW 根目录不存在，请检查脚本根目录"
        if not Path(self.script_config.get("Script", "ScriptPath")).exists():
            return "OK-WW 可执行文件不存在，请检查主程序路径"
        return "Pass"

    async def main_task(self):
        self.okww_process_manager = ProcessManager()
        self.wait_event = asyncio.Event()

        config_owner = self.task_info.user_id or "Default"
        mas_dir = mas_config_dir(self.script_info.script_id, config_owner)
        if mas_config_ready(mas_dir):
            deploy_mas_config_to_script(
                self.script_config, self.script_info.script_id, config_owner
            )

        exe = Path(self.script_config.get("Script", "ScriptPath"))

        # 仅附加用户填写的额外参数（不带 -t/-e）
        extra_args = []
        raw_extra = str(self.script_config.get("Script", "Arguments")).strip()
        if raw_extra:
            extra_args.extend(shlex.split(raw_extra, posix=False))

        await System.kill_process(exe)
        logger.info(f"启动 OK-WW 配置会话: {exe} {' '.join(extra_args)}")
        await self.okww_process_manager.open_process(exe, *extra_args)

        # 等待前端 stopTask 结束会话
        self.wait_event.clear()
        await self.wait_event.wait()

    async def _kill_okww_processes(self) -> None:
        """结束 ok-ww.exe 及其 pythonw 子进程（与 AutoProxy 收尾一致）"""
        if hasattr(self, "okww_process_manager"):
            try:
                await self.okww_process_manager.kill()
            except Exception:
                pass

        exe = Path(self.script_config.get("Script", "ScriptPath"))
        try:
            await System.kill_process(exe)
        except Exception:
            pass

        root = Path(self.script_config.get("Info", "RootPath"))
        track_exe = str(self.script_config.get("Script", "TrackProcessExe") or "").strip()
        if not track_exe and root:
            track_exe = str(root / "data/apps/ok-ww/python/pythonw.exe")
        if track_exe:
            try:
                await System.kill_process(Path(track_exe))
            except Exception:
                pass

    async def final_task(self):
        if hasattr(self, "wait_event"):
            self.wait_event.set()
        await self._kill_okww_processes()
        config_owner = self.task_info.user_id or "Default"
        pull_script_config_to_mas(
            self.script_config, self.script_info.script_id, config_owner
        )

    async def on_crash(self, e: Exception):
        logger.exception(f"OK-WW 配置任务出现异常: {e}")
        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Info",
            data={"Error": f"OK-WW 配置任务出现异常: {e}"},
        )
        if hasattr(self, "wait_event"):
            self.wait_event.set()

