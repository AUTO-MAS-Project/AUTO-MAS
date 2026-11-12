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

from contextlib import suppress
from pathlib import Path

from app.core import Publisher
from app.core.ws import protocol
from app.models.config import OkwwConfig
from app.models.schema import WSTaskNoticeData
from app.models.task import ScriptItem, TaskExecuteBase
from app.task.proxy_helpers import push_dispatch_log
from app.utils import get_logger

from .tools.game_update import update_game_via_launcher

logger = get_logger("OK-WW 鸣潮更新")


class WuwaUpdateTask(TaskExecuteBase):
    """脚本配置页「检查更新」手动触发的一次鸣潮官方更新。

    TODO(插件迁移，#1845)：存量维护执行、结果、日志与取消暂不改造，待插件统一迁移。

    与代理任务共用官方启动器更新流程；仅更新资源，不进入游戏。
    检查失败明确报错，不把旧接口的版本相同当成已更新。
    """

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: OkwwConfig,
    ):
        super().__init__()
        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")
        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.cur_user_item = self.script_info.user_list[self.script_info.current_index]

    async def _push_dispatch_log(self, line: str) -> None:
        """向调度台追加流程日志（赋值 script_info.log 会触发 WebSocket 推送）。"""

        await push_dispatch_log(self.script_info, line)

    async def main_task(self) -> None:
        await self.cur_user_item.set_state(status="运行")
        launcher = Path(str(self.script_config.Game.Path or "").strip())
        if not launcher.is_file():
            raise RuntimeError("请先在托管配置中导入有效的鸣潮官方启动器")

        await update_game_via_launcher(
            launcher,
            client_path=self.script_config.Game.ClientPath,
            on_progress=self._push_dispatch_log,
        )
        await self.cur_user_item.set_state(status="完成")

    async def final_task(self) -> None:
        """一次性更新任务不持有需要释放的资源，结果状态由 main_task / on_crash 落定。"""

    async def on_crash(self, e: Exception) -> None:
        await self.cur_user_item.set_state(status="异常")
        logger.opt(exception=True).warning(f"鸣潮更新任务出现异常: {e}")
        with suppress(Exception):
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(level="error", message=f"鸣潮更新失败: {e}"),
            )
