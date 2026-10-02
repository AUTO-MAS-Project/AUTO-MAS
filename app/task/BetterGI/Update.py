#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

import uuid
from contextlib import suppress

from app.core.ws import Publisher, protocol
from app.models.config import BetterGIConfig, BetterGIUserConfig
from app.models.ConfigBase import MultipleConfig
from app.models.schema import WSTaskNoticeData
from app.models.task import ScriptItem, TaskExecuteBase
from app.task.proxy_helpers import push_dispatch_log
from app.utils import get_logger

from .tools.game_update import ensure_game_updated

logger = get_logger("原神更新 BetterGI")


class BetterGIUpdateTask(TaskExecuteBase):
    """脚本配置页「检查更新」手动触发的一次原神客户端增量更新。

    与代理任务启动前的自动更新共用 :func:`ensure_game_updated` 的检查与落盘
    逻辑；手动入口下无法自动完成的情况一律抛错（用户主动发起，不应像自动
    流程那样静默放行）。
    """

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: BetterGIConfig,
        user_config: MultipleConfig[BetterGIUserConfig],
        user_id: str,
    ):
        super().__init__()
        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")
        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config
        self.user_id = user_id
        self.cur_user_item = self.script_info.user_list[self.script_info.current_index]

    async def _push_dispatch_log(self, line: str) -> None:
        """向调度台追加流程日志（赋值 script_info.log 会触发 WebSocket 推送）。"""

        await push_dispatch_log(self.script_info, line)

    async def main_task(self) -> None:
        self.cur_user_item.status = "运行"
        user_config = self.user_config[uuid.UUID(self.user_id)]
        await self._push_dispatch_log("正在检查原神客户端更新...")
        # manual=True 时凡不能自动完成的情况都会抛错，走到这里即已完成或无需更新
        await ensure_game_updated(
            self.script_config,
            user_config,
            on_log=self._push_dispatch_log,
            manual=True,
        )
        self.cur_user_item.status = "完成"

    async def final_task(self) -> None:
        """一次性更新任务不持有需要释放的资源，结果状态由 main_task / on_crash 落定。"""

    async def on_crash(self, e: Exception) -> None:
        self.cur_user_item.status = "异常"
        logger.opt(exception=True).warning(f"原神更新任务出现异常: {e}")
        with suppress(Exception):
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                # 只推原因本身；「原神更新失败: 」这层前缀由前端词表加，两边都加会说两遍
                data=WSTaskNoticeData(level="error", message=f"{e}"),
            )
