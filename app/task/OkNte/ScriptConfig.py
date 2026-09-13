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
import shutil
from contextlib import suppress
from pathlib import Path

from app.core.ws import Publisher, protocol
from app.models.config import OkNteConfig, OkNteUserConfig
from app.models.ConfigBase import MultipleConfig
from app.models.schema import WSTaskNoticeData
from app.models.task import ScriptItem, TaskExecuteBase
from app.services import System
from app.utils import ProcessManager, get_logger
from app.utils.io import replace_dir

from .tools.backup_archive import archive_mas_runtime_backup

logger = get_logger("OK-NTE 脚本设置")


class ScriptConfigTask(TaskExecuteBase):
    """拉起 OK-NTE 原生 GUI；用户会话把 MAS 侧配置下发到读取目录，关闭回写。

    view_only=True 时为查看会话：只读预览（如「查看历史备份」）——用户级
    会话下发的 MAS 目录即刚恢复的备份（所见即备份），脚本级会话跳过下发
    （原生目录即备份）；结束不回写 MAS 配置，原生目录由 manager 的任务前
    快照还原（临时注入，看完还原）。
    """

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: OkNteConfig,
        user_config: MultipleConfig[OkNteUserConfig],
        game_manager: ProcessManager | None,
        view_only: bool = False,
    ):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config
        self.game_manager = game_manager
        # 查看会话：只读预览（如「查看历史备份」），结束不回写 MAS 配置
        self.view_only = view_only
        self.cur_user_item = self.script_info.user_list[self.script_info.current_index]
        self.oknte_process_manager: ProcessManager = ProcessManager()
        self.wait_event: asyncio.Event = asyncio.Event()
        self.script_root_path: Path = Path(self.script_config.get("Info", "RootPath"))
        self.script_exe_path: Path = Path(
            self.script_config.get("Script", "ScriptPath")
        )
        self.script_config_path: Path = Path(
            self.script_config.get("Script", "ConfigPath")
        )
        self.mas_config_dir: Path = (
            Path.cwd()
            / "data"
            / self.script_info.script_id
            / self.cur_user_item.user_id
            / "ConfigFile"
        )

    async def check(self) -> str:
        return "Pass"

    async def prepare(self) -> None:
        self.oknte_process_manager = ProcessManager()
        self.wait_event = asyncio.Event()

    async def main_task(self) -> None:
        await self.prepare()
        await self.set_oknte()

        logger.info(f"启动 OK-NTE GUI 配置进程: {self.script_exe_path}")
        self.cur_user_item.status = "运行"
        self.wait_event.clear()
        await self.oknte_process_manager.open_process(self.script_exe_path)
        await self.wait_event.wait()

    async def set_oknte(self) -> None:
        """将 AUTO-MAS 侧用户配置下发到 OK-NTE GUI 读取目录。

        查看会话（view_only）的脚本级入口跳过下发——原生目录就是刚恢复的
        备份；用户级入口照常下发（MAS 目录即备份内容，下发是查看的必经
        复制，GUI 所见即备份）。
        """

        logger.info(f"开始配置 OK-NTE GUI: 设置脚本 {self.cur_user_item.user_id}")
        await self._kill_oknte_process()

        # 下发前归档 MAS 用户配置（下发源；指纹去重，失败不阻断会话）——
        # MAS 目录缺失时 GUI 会直接改原生配置、final_task 还会回写覆盖 MAS 目录。
        # native 池由 manager.prepare 在任务级一次性归档，此处不重复
        archive_mas_runtime_backup(
            self.script_info.script_id, self.cur_user_item.user_id
        )

        # 查看会话的脚本级入口：原生目录即所选备份，跳过下发
        if self.view_only and self.cur_user_item.user_id == "Default":
            logger.info("OK-NTE 查看会话跳过配置下发: 原生目录即所选备份")
            return

        if not self.mas_config_dir.exists() or not any(self.mas_config_dir.iterdir()):
            logger.info("未找到用户级 OK-NTE 配置，使用脚本当前配置启动 GUI")
            return

        if self.script_config.get("Script", "ConfigPathMode") == "Folder":
            replace_dir(self.mas_config_dir, self.script_config_path)
        elif self.script_config.get("Script", "ConfigPathMode") == "File":
            src_file = self.mas_config_dir / self.script_config_path.name
            if src_file.exists():
                self.script_config_path.parent.mkdir(parents=True, exist_ok=True)
                tmp_file = self.script_config_path.with_name(
                    self.script_config_path.name + ".tmp"
                )
                shutil.copy(src_file, tmp_file)
                tmp_file.replace(self.script_config_path)

        logger.success(f"OK-NTE GUI 配置已加载: {self.cur_user_item.user_id}")

    async def final_task(self) -> None:
        await self._kill_oknte_process()

        # 查看会话：只读预览，不把原生目录回写 MAS 配置（原生现场由 manager
        # 的任务前快照还原）；GUI 内的改动一律丢弃
        if self.view_only:
            logger.success("OK-NTE 查看结束（只读，不回写配置）")
            self.cur_user_item.status = "完成"
            return

        self.mas_config_dir.parent.mkdir(parents=True, exist_ok=True)
        if self.script_config.get("Script", "ConfigPathMode") == "Folder":
            if not self.script_config_path.exists():
                raise FileNotFoundError(
                    "未找到 OK-NTE 配置目录，请在 GUI 中保存后再点击保存配置"
                )

            replace_dir(self.script_config_path, self.mas_config_dir)
            logger.success(f"OK-NTE 配置已保存到: {self.mas_config_dir}")
        elif self.script_config.get("Script", "ConfigPathMode") == "File":
            if not self.script_config_path.exists():
                raise FileNotFoundError(
                    "未找到 OK-NTE 配置文件，请在 GUI 中保存后再点击保存配置"
                )

            self.mas_config_dir.mkdir(parents=True, exist_ok=True)
            tmp_file = self.mas_config_dir / (self.script_config_path.name + ".tmp")
            shutil.copy(self.script_config_path, tmp_file)
            tmp_file.replace(self.mas_config_dir / self.script_config_path.name)
            logger.success(
                f"OK-NTE 配置已保存到: {self.mas_config_dir / self.script_config_path.name}"
            )

        self.cur_user_item.status = "完成"

    async def on_crash(self, e: Exception) -> None:
        self.cur_user_item.status = "异常"
        logger.opt(exception=True).warning(f"OK-NTE GUI 配置任务出现异常: {e}")
        with suppress(Exception):
            await self._kill_oknte_process()
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(
                level="error", message=f"OK-NTE GUI 配置任务出现异常: {e}"
            ),
        )

    async def _kill_oknte_process(self) -> None:
        try:
            await self.oknte_process_manager.kill()
        except Exception as e:
            logger.opt(exception=True).warning(
                f"通过进程管理器中止 OK-NTE GUI 进程失败: {e}"
            )

        try:
            await System.kill_process(self.script_exe_path)
        except Exception as e:
            logger.opt(exception=True).warning(f"中止 OK-NTE 主进程失败: {e}")

        track_exe = str(
            self.script_config.get("Script", "TrackProcessExe") or ""
        ).strip()
        if not track_exe:
            track_exe = str(
                self.script_root_path / "data/apps/ok-nte/python/pythonw.exe"
            )
        if track_exe:
            try:
                await System.kill_process(Path(track_exe))
            except Exception as e:
                logger.opt(exception=True).warning(f"中止 OK-NTE 追踪进程失败: {e}")
