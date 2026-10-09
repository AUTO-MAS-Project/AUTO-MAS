#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""脚本配置页「检查更新」的手动入口：一次终末地 PC 客户端差量更新。

走 `tools/game_update.ensure_game_updated` 这条判定链；与自动前置门的区别只在怎么用
那四个状态——自动流程对「判不了」放行 `Skipped`，这里要如实告诉用户没查出结论。

这里说的是**游戏客户端**。`update_takeover.py` 接管的是 MaaEnd 程序自身的更新。
"""

from contextlib import suppress
from pathlib import Path

from app.core.ws import Publisher, protocol
from app.models.config import MaaEndConfig
from app.models.schema import WSTaskNoticeData
from app.models.task import ScriptItem, TaskExecuteBase
from app.task.proxy_helpers import push_dispatch_log
from app.utils import get_logger

from .tools.game_update import ensure_game_updated

logger = get_logger("终末地客户端更新")


class EndfieldUpdateTask(TaskExecuteBase):
    """手动触发的一次客户端更新，不持有需要跨轮保留的资源。

    Args:
        script_info: 已绑定 `task_info` 的脚本项；结论写进它的调度台日志。
        script_config: 该脚本的 MaaEnd 配置，只用 `Game.Path` 与
            `Game.UpdateTimeLimit`。
    """

    def __init__(self, script_info: ScriptItem, script_config: MaaEndConfig):
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
        self.cur_user_item.status = "运行"
        game_exe = Path(str(self.script_config.get("Game", "Path") or "").strip())

        # 不看 Game.IfAutoUpdate：那是自动门的开关，用户当面点下按钮即为授权。
        result = await ensure_game_updated(
            game_exe,
            time_limit_minutes=int(self.script_config.get("Game", "UpdateTimeLimit")),
            progress=self._push_dispatch_log,
            entry="手动",
        )
        # 结论先落进日志再抛：toast 三秒就没了，弹窗里这一行才是留下的那份
        await self._push_dispatch_log(result.message)
        if result.status == "Skipped":
            # Skipped 是「本轮没做这件事」，不是失败
            self.cur_user_item.status = "跳过"
            return
        if result.status == "NeedManualUpdate":
            raise RuntimeError(result.message)
        self.cur_user_item.status = "完成"

    async def final_task(self) -> None:
        """一次性更新任务不持有需要释放的资源；脚本配置锁归调度器。"""

    async def on_crash(self, e: Exception) -> None:
        self.cur_user_item.status = "异常"
        logger.opt(exception=True).warning(f"终末地客户端手动更新失败: {e}")
        with suppress(Exception):
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                # 只推原因本身；「终末地更新失败: 」这层前缀由前端词表加，两边都加会说两遍
                data=WSTaskNoticeData(level="error", message=f"{e}"),
            )
