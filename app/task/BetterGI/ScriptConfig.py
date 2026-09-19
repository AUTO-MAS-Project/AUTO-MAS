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

from app.core.ws import Publisher, protocol
from app.models.config import BetterGIConfig, BetterGIUserConfig
from app.models.ConfigBase import MultipleConfig
from app.models.schema import WSTaskNoticeData
from app.models.task import ScriptItem, TaskExecuteBase
from app.services import System
from app.task.proxy_helpers import CONFIG_SOURCE_DIRECT, read_config_source
from app.utils import ProcessManager, get_logger
from app.utils.platform import IS_ELEVATED

from .AutoProxy import _BGI_REL_EXE, _BGI_UNKILLABLE_HINT, _wait_bgi_exit
from .tools import one_dragon

logger = get_logger("BetterGI 脚本设置")


class ScriptConfigTask(TaskExecuteBase):
    """无参数启动 BetterGI 本体，供用户修改程序设置（原生 GUI 直控）。"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: BetterGIConfig,
        user_config: MultipleConfig[BetterGIUserConfig],
        *,
        view_only: bool = False,
    ):
        super().__init__()
        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")
        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config
        # view_only=True 时为查看会话（如「查看历史备份」）：只读打开 BetterGI
        # 查看原生配置（BGI GUI 即原生，所见即备份）。BetterGI 配置会话本就
        # 无参打开、无基线注入/无回写（任务配置以 MAS 前端为准），viewOnly
        # 与配置会话共享同一打开路径，无需额外分支
        self.view_only = view_only
        self.cur_user_item = self.script_info.user_list[self.script_info.current_index]
        # 脚本级配置（"Default"）强制使用 MAS 配置；真实用户按配置来源决定。
        self.use_mas_config = True
        if self.cur_user_item.user_id != "Default":
            user_config = self.user_config[uuid.UUID(self.cur_user_item.user_id)]
            # 直控来源 = 用 BGI 原生配置，MAS 不接管（与 AutoProxy 同口径）
            mode = read_config_source(user_config)
            self.use_mas_config = mode != CONFIG_SOURCE_DIRECT
        self.process_manager = ProcessManager()
        self.wait_event = asyncio.Event()
        self.crashed = False
        self.root_path = Path(self.script_config.get("Info", "RootPath"))
        self.exe_path = self.root_path / _BGI_REL_EXE

    def _cleanup_leftover_slot(self) -> None:
        """清理上一轮残留的 MAS 运行时槽位/物化组（若存在；安全幂等，不误删用户文件）。"""
        if not self.use_mas_config:
            return
        with suppress(Exception):
            # 按用户短 id 前缀扫描删除历史残留物化组（只命中 MAS-{短id}-自定义配置组*，不碰 BGI 本体）
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
        if not await self._kill_processes():
            # 本任务只负责把 BGI 界面开起来，结束时若关不掉它会一直留着（且 MAS 管不了它），
            # 下次任务带参启动会被这个单实例吞掉 → 任务卡住、游戏不启动。故必须明确告知用户。
            logger.warning(f"BetterGI 设置界面未能自动关闭：{_BGI_UNKILLABLE_HINT}")
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(level="warning", message=_BGI_UNKILLABLE_HINT),
            )
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
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(
                level="error", message=f"BetterGI 设置任务出现异常: {e}"
            ),
        )

    async def _kill_processes(self) -> bool:
        """中止 BetterGI 进程。

        Returns:
            bool: 已确认无 BetterGI 残留时返回 True；仍有实例存活（MAS 无权终止它，常见于
                BGI 由 MAS 以管理员权限启动而 MAS 未提权）时返回 False。
        """
        try:
            await self.process_manager.kill()
        except Exception as e:
            logger.opt(exception=True).warning(f"通过进程管理器中止 BetterGI 失败: {e}")

        try:
            await System.kill_process(self.exe_path)
        except Exception as e:
            logger.opt(exception=True).warning(f"中止 BetterGI 进程失败: {e}")

        remaining = await _wait_bgi_exit()
        if remaining:
            logger.warning(
                f"BetterGI 进程仍存活（PID: {remaining}）：{_BGI_UNKILLABLE_HINT}"
            )
            return False
        return True
