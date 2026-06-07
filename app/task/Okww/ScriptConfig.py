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
import shutil
from pathlib import Path

from app.core import Config
from app.models.task import TaskExecuteBase, ScriptItem
from app.models.ConfigBase import MultipleConfig
from app.models.config import OkwwConfig, OkwwUserConfig
from app.services import System
from app.utils import get_logger, ProcessManager

logger = get_logger("OK-WW 脚本设置")


class ScriptConfigTask(TaskExecuteBase):
    """OK-WW 配置会话：拉起 ok-ww.exe（不带 -t/-e），由用户在 GUI 内保存 configs"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: OkwwConfig,
        user_config: MultipleConfig[OkwwUserConfig],
        game_manager: ProcessManager | None,
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
        if not Path(self.script_config.get("Script", "ScriptPath")).is_file():
            return "请设置ok-ww脚本路径"
        return "Pass"

    async def main_task(self):
        self.okww_process_manager = ProcessManager()
        self.wait_event = asyncio.Event()

        self.script_config_path = Path(self.script_config.get("Script", "ConfigPath"))
        config_owner = self.task_info.user_id or "Default"
        mas_config_dir = (
            Path.cwd()
            / f"data/{self.script_info.script_id}/{config_owner}/ConfigFile"
        )
        if mas_config_dir.exists():
            if self.script_config.get("Script", "ConfigPathMode") == "Folder":
                shutil.copytree(
                    mas_config_dir, self.script_config_path, dirs_exist_ok=True
                )
            elif self.script_config.get("Script", "ConfigPathMode") == "File":
                shutil.copy(
                    mas_config_dir / self.script_config_path.name,
                    self.script_config_path,
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
            except Exception as e:
                logger.exception(f"通过进程管理器中止 OK-WW 配置进程失败: {e}")

        exe = Path(self.script_config.get("Script", "ScriptPath"))
        try:
            await System.kill_process(exe)
        except Exception as e:
            logger.exception(f"中止 OK-WW 配置主进程失败: {e}")

        root = Path(self.script_config.get("Info", "RootPath"))
        track_exe = str(self.script_config.get("Script", "TrackProcessExe") or "").strip()
        if not track_exe and root:
            track_exe = str(root / "data/apps/ok-ww/python/pythonw.exe")
        if track_exe:
            try:
                await System.kill_process(Path(track_exe))
            except Exception as e:
                logger.exception(f"中止 OK-WW 配置追踪进程失败: {e}")

    async def final_task(self):
        if hasattr(self, "wait_event"):
            self.wait_event.set()
        await self._kill_okww_processes()

        config_owner = self.task_info.user_id or "Default"
        mas_config_dir = (
            Path.cwd()
            / f"data/{self.script_info.script_id}/{config_owner}/ConfigFile"
        )
        if self.script_config.get("Script", "ConfigPathMode") == "Folder":
            if not self.script_config_path.is_dir():
                raise FileNotFoundError("未找到 ok-ww 配置目录，请先在 ok-ww 中完成配置保存")
        elif self.script_config.get("Script", "ConfigPathMode") == "File":
            if not self.script_config_path.is_file():
                raise FileNotFoundError("未找到 ok-ww 配置文件，请先在 ok-ww 中完成配置保存")

        shutil.rmtree(mas_config_dir, ignore_errors=True)
        mas_config_dir.mkdir(parents=True, exist_ok=True)
        if self.script_config.get("Script", "ConfigPathMode") == "Folder":
            shutil.copytree(
                self.script_config_path, mas_config_dir, dirs_exist_ok=True
            )
        elif self.script_config.get("Script", "ConfigPathMode") == "File":
            shutil.copy(
                self.script_config_path,
                mas_config_dir / self.script_config_path.name,
            )
        logger.success(
            f"OK-WW 配置已保存到: {mas_config_dir}"
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
