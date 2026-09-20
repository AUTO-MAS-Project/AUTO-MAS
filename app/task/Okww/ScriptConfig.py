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
from app.utils.io import mark_native_config_injected, swap_in_dir

from .AutoProxy import (
    _OKWW_REL_CONFIG_DIR,
    _OKWW_REL_EXE,
    _OKWW_REL_PYTHONW,
    _configure_okww_launcher,
    _okww_config_mode,
    _okww_mas_config_dir,
)
from .tools.backup_archive import (
    archive_mas_runtime_backup,
    owner_for_mode,
    read_overlay_values,
)

logger = get_logger("OK-WW 脚本设置")


class ScriptConfigTask(TaskExecuteBase):
    """无参数启动 OK-WW 本体，供用户修改程序设置。

    view_only=True 时为查看会话：只读预览（如「查看历史备份」）——用户级
    会话下发的 MAS 目录即刚恢复的备份（所见即备份），脚本级会话跳过下发
    （原生目录即备份）；结束不回写 MAS 配置，原生目录由 manager 的任务前
    快照还原（临时注入，看完还原）。
    """

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: OkwwConfig,
        user_config: MultipleConfig[OkwwUserConfig],
        view_only: bool = False,
    ):
        super().__init__()
        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")
        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config
        # 查看会话：只读预览（如「查看历史备份」），结束不回写 MAS 配置
        self.view_only = view_only
        self.cur_user_item = self.script_info.user_list[self.script_info.current_index]
        self.process_manager = ProcessManager()
        self.wait_event = asyncio.Event()
        self.crashed = False
        self.root_path = Path(self.script_config.get("Info", "RootPath"))
        self.exe_path = self.root_path / _OKWW_REL_EXE
        self.script_config_path = self.root_path / _OKWW_REL_CONFIG_DIR
        target_user_id = self.cur_user_item.user_id
        mode = "脚本"
        if target_user_id != "Default":
            target_user_config = self.user_config[uuid.UUID(target_user_id)]
            mode = _okww_config_mode(target_user_config.get("Info", "Mode"))
        self.use_mas_config = mode != "直控"
        # MAS 配置目录 owner（脚本态共享 Default、用户态独立目录；直控无 MAS 配置）
        self.mas_owner = (
            owner_for_mode(mode, target_user_id) if self.use_mas_config else None
        )
        # 本会话涉及用户的覆盖层字段（脚本级 Default 入口无单一用户，不带侧车）
        self.mas_overlay = (
            read_overlay_values(self.user_config[uuid.UUID(target_user_id)])
            if self.use_mas_config and target_user_id != "Default"
            else None
        )
        self.mas_config_dir = (
            _okww_mas_config_dir(self.script_info.script_id, target_user_id, mode)
            if self.use_mas_config
            else None
        )

    async def main_task(self) -> None:
        await self._kill_processes()
        _configure_okww_launcher(self.root_path)

        # 下发前归档 MAS 配置到用户池（下发源，会话保存会覆盖它；指纹去重，
        # 失败不阻断会话）。native 池由 manager.prepare 在任务级一次性归档
        if self.use_mas_config and self.mas_owner and self.mas_config_dir:
            archive_mas_runtime_backup(
                self.script_info.script_id,
                self.cur_user_item.user_id,
                self.mas_config_dir,
                overlay=self.mas_overlay,
                # 备份标注来源：tri_state 池跨来源恢复靠它切回
                mode="用户" if self.mas_owner == self.cur_user_item.user_id else "脚本",
            )

        # 查看会话的脚本级入口：原生目录即所选备份，跳过下发
        if self.view_only and self.cur_user_item.user_id == "Default":
            logger.info("OK-WW 查看会话跳过配置下发: 原生目录即所选备份")
        elif (
            self.use_mas_config
            and self.mas_config_dir
            and self.mas_config_dir.is_dir()
            and any(item.is_file() for item in self.mas_config_dir.rglob("*"))
        ):
            swap_in_dir(self.mas_config_dir, self.script_config_path)
            mark_native_config_injected(
                Path.cwd() / f"data/{self.script_info.script_id}/Temp",
                self.script_config_path,
                script_id=self.script_info.script_id,
            )
        logger.info(f"启动 OK-WW 设置: {self.exe_path}")
        self.cur_user_item.status = "运行"
        await self.process_manager.open_process(self.exe_path)
        await self.wait_event.wait()

    async def final_task(self) -> None:
        self.wait_event.set()
        await self._kill_processes()

        # 查看会话：只读预览，不把原生目录回写 MAS 配置（原生现场由 manager
        # 的任务前快照还原）；GUI 内的改动一律丢弃
        if self.view_only:
            logger.success("OK-WW 查看结束（只读，不回写配置）")
            self.cur_user_item.status = "完成"
            return

        if not self.crashed and self.use_mas_config and self.mas_config_dir:
            _configure_okww_launcher(self.root_path)
            if not self.script_config_path.is_dir():
                raise FileNotFoundError(
                    "未找到 OK-WW 配置目录，请先在 OK-WW 中保存设置"
                )
            # 不在这里注入 Basic Options.json：它是运行期 overlay 值，写入后
            # 随即随整目录回写进 base，而配置会话没有还原路径——会把这个非面板
            # 字段永久固化进 base。运行期由 AutoProxy._apply_mas_overrides 覆盖，
            # 任务结束由整目录快照还原，base 只保留用户在 ok-ww GUI 里的设置。
            self.mas_config_dir.parent.mkdir(parents=True, exist_ok=True)
            swap_in_dir(self.script_config_path, self.mas_config_dir)
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
