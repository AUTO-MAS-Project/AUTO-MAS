#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
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
import shlex
import shutil
import uuid
from pathlib import Path

from app.config import ConfigCollection
from app.core import Publisher
from app.core.ws import protocol
from app.models.config import GeneralConfig, GeneralUserConfig
from app.models.emulator import DeviceBase
from app.models.schema import WSTaskNoticeData
from app.models.task import ScriptItem, TaskExecuteBase
from app.services import System
from app.task.proxy_helpers import (
    CONFIG_BASE_NATIVE,
    CONFIG_BASE_SHARED,
    read_config_base,
)
from app.utils import ProcessManager, get_logger
from app.utils import io as _utils_io

logger = get_logger("通用脚本设置")


class ScriptConfigTask(TaskExecuteBase):
    """脚本设置模式"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: GeneralConfig,
        user_config: ConfigCollection[GeneralUserConfig],
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
        self.config_base = CONFIG_BASE_SHARED
        self.use_mas_config = True
        if self.cur_user_item.user_id != "Default":
            selected_user = self.user_config[uuid.UUID(self.cur_user_item.user_id)]
            self.config_base = read_config_base(selected_user)
            # 原生来源=不写；shared/independent 来源都写面板值（见 AutoProxy 同款说明）
            self.use_mas_config = self.config_base != CONFIG_BASE_NATIVE

    async def prepare(self):

        self.general_process_manager = ProcessManager()
        self.wait_event = asyncio.Event()

        script_path = self.script_config.Script.ScriptPath
        if script_path is None:
            raise ValueError("ScriptPath未配置，请检查路径设置")
        self.script_path = script_path

        arguments_list = []
        path_list = []

        for argument in [
            part.strip()
            for part in str(self.script_config.Script.Arguments).split("|")
            if part.strip()
        ]:
            arg_parts = [
                part.strip() for part in argument.split("%", 1) if part.strip()
            ]

            path_list.append(
                (
                    self.script_path / arg_parts[0]
                    if len(arg_parts) > 1
                    else self.script_path
                ).resolve()
            )
            arguments_list.append(shlex.split(arg_parts[-1]))

        self.script_arguments = arguments_list[0] if len(arguments_list) > 0 else []
        self.script_set_exe_path = (
            path_list[1] if len(path_list) > 1 else self.script_path
        )
        self.script_set_arguments = arguments_list[1] if len(arguments_list) > 1 else []
        script_config_path = self.script_config.Script.ConfigPath
        if script_config_path is None:
            raise ValueError("ConfigPath未配置，请检查路径设置")
        self.script_config_path = script_config_path

    async def main_task(self):

        await self.prepare()

        await self.set_general()
        # 创建通用脚本任务
        logger.info(
            f"运行脚本任务: {self.script_set_exe_path}, 参数: {self.script_set_arguments}"
        )
        await self.general_process_manager.open_process(
            self.script_set_exe_path, *self.script_set_arguments
        )

        # 等待用户完成配置
        self.wait_event.clear()
        await self.wait_event.wait()

    async def set_general(self) -> None:
        """配置通用脚本运行参数"""

        logger.info(f"开始配置脚本运行参数: 脚本设置 {self.cur_user_item.user_id}")

        await System.kill_process(self.script_set_exe_path)

        # 查看会话的脚本级入口：原生配置即所选备份，跳过下发（用户级为目录
        # 副本型，强制照常下发——GUI 所见即备份，不受原生来源门控影响）
        if self.task_info.view_only and self.cur_user_item.user_id == "Default":
            logger.info("通用脚本查看会话跳过配置下发: 原生配置即所选备份")
            return

        if not self.use_mas_config and not self.task_info.view_only:
            logger.info("脚本原生配置：跳过写入脚本配置")
            return

        # 下发前归档 MAS 配置到用户池（下发源，会话保存会覆盖它；指纹去重，
        # 失败不阻断会话）。General 的 ConfigFile 恒按用户，无 owner 解耦；
        # 查看会话的 ConfigFile 即刚恢复的备份，无需再归档
        if not self.task_info.view_only:
            from .tools.backup_archive import archive_mas_runtime_backup

            archive_mas_runtime_backup(
                self.script_info.script_id,
                self.cur_user_item.user_id,
                Path.cwd()
                / f"data/{self.script_info.script_id}/{self.cur_user_item.user_id}/ConfigFile",
            )

        if (
            self.script_config.Script.ConfigPathMode == "Folder"
            and (
                Path.cwd()
                / f"data/{self.script_info.script_id}/{self.cur_user_item.user_id}/ConfigFile"
            ).exists()
        ):
            _utils_io.swap_in_dir(
                Path.cwd()
                / f"data/{self.script_info.script_id}/{self.cur_user_item.user_id}/ConfigFile",
                self.script_config_path,
            )
            _utils_io.mark_native_config_injected(
                Path.cwd() / f"data/{self.script_info.script_id}/Temp",
                self.script_config_path,
                script_id=self.script_info.script_id,
            )
        elif (
            self.script_config.Script.ConfigPathMode == "File"
            and (
                Path.cwd()
                / f"data/{self.script_info.script_id}/{self.cur_user_item.user_id}/ConfigFile"
                / self.script_config_path.name
            ).exists()
        ):
            shutil.copy(
                Path.cwd()
                / f"data/{self.script_info.script_id}/{self.cur_user_item.user_id}/ConfigFile"
                / self.script_config_path.name,
                self.script_config_path,
            )

        logger.success(f"MAA运行参数配置完成: 设置脚本 {self.cur_user_item.user_id}")

    async def final_task(self):

        await self.general_process_manager.kill()
        await System.kill_process(self.script_set_exe_path)
        del self.general_process_manager

        # 查看会话：只读预览，不把 GUI 内的改动回写 MAS 配置副本（原生配置
        # 现场由 manager 的任务前快照还原）
        if self.task_info.view_only:
            logger.success("通用脚本查看结束（只读，不回写配置）")
            self.cur_user_item.status = "完成"
            return

        if not self.use_mas_config:
            logger.info("脚本原生来源配置：跳过回写用户独立配置")
            return

        # 源是用户自己填的脚本配置位置，可能压根不存在（路径填错、脚本还没生成过
        # 配置）。先判再动：不能先把 MAS 侧副本清掉再抛 FileNotFoundError，那会让
        # 用户以为配置丢了。
        if not self.script_config_path.exists():
            logger.warning(
                f"跳过配置回写: 脚本配置路径不存在 {self.script_config_path}"
            )
            return

        shutil.rmtree(
            Path.cwd()
            / f"data/{self.script_info.script_id}/{self.cur_user_item.user_id}/ConfigFile",
            ignore_errors=True,
        )
        (
            Path.cwd()
            / f"data/{self.script_info.script_id}/{self.cur_user_item.user_id}/ConfigFile"
        ).mkdir(parents=True, exist_ok=True)
        if self.script_config.Script.ConfigPathMode == "Folder":
            shutil.copytree(
                self.script_config_path,
                Path.cwd()
                / f"data/{self.script_info.script_id}/{self.cur_user_item.user_id}/ConfigFile",
                dirs_exist_ok=True,
            )
            logger.success(
                f"通用脚本配置已保存到: {Path.cwd() / f'data/{self.script_info.script_id}/{self.cur_user_item.user_id}/ConfigFile'}"
            )
        elif self.script_config.Script.ConfigPathMode == "File":
            shutil.copy(
                self.script_config_path,
                Path.cwd()
                / f"data/{self.script_info.script_id}/{self.cur_user_item.user_id}/ConfigFile"
                / self.script_config_path.name,
            )
            logger.success(
                f"通用脚本配置已保存到: {Path.cwd() / f'data/{self.script_info.script_id}/{self.cur_user_item.user_id}/ConfigFile' / self.script_config_path.name}"
            )

    async def on_crash(self, e: Exception):
        self.cur_user_item.status = "异常"
        logger.opt(exception=True).warning(f"脚本设置任务出现异常: {e}")
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level="error", message=f"脚本设置任务出现异常: {e}"),
        )
