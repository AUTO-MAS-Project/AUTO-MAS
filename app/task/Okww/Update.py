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

import asyncio
from contextlib import suppress
from pathlib import Path

from app.core import Config
from app.core.ws import Publisher, protocol
from app.models.schema import WSTaskNoticeData
from app.models.config import OkwwConfig
from app.models.task import ScriptItem, TaskExecuteBase
from app.services.wuthering_waves import check_wuthering_waves_update
from app.services.wuthering_waves_updater import update_wuthering_waves
from app.utils import get_logger

logger = get_logger("OK-WW 鸣潮更新")


class WuwaUpdateTask(TaskExecuteBase):
    """脚本配置页「检查更新」手动触发的一次鸣潮官方更新。

    与代理任务内的自动更新共用同一套检查与下载逻辑；手动入口下
    检查失败直接报错（用户主动发起，不应像自动流程那样放行）。
    """

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: OkwwConfig,
        resource: str,
    ):
        super().__init__()
        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")
        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.resource = resource
        self.cur_user_item = self.script_info.user_list[self.script_info.current_index]

    async def _push_dispatch_log(self, line: str) -> None:
        """向调度台追加流程日志（赋值 script_info.log 会触发 WebSocket 推送）。"""

        prev = self.script_info.log
        self.script_info.log = f"{prev}\n{line}" if prev else line
        await asyncio.sleep(0)

    async def main_task(self) -> None:
        self.cur_user_item.status = "运行"
        launcher = Path(str(self.script_config.get("Game", "Path") or "").strip())
        if not launcher.is_file():
            raise RuntimeError("请先在脚本配置中导入有效的鸣潮官方启动器")

        await self._push_dispatch_log(f"正在检查 {self.resource} 鸣潮更新...")
        try:
            update_info = await check_wuthering_waves_update(launcher, self.resource)
        except Exception as e:
            raise RuntimeError(f"鸣潮更新检查失败: {e}") from e

        if not update_info.update_available:
            await self._push_dispatch_log(
                f"鸣潮已是最新版本: {update_info.release_version}"
            )
            self.cur_user_item.status = "完成"
            return

        await self._push_dispatch_log(
            f"鸣潮需更新: {update_info.current_version}"
            f" -> {update_info.release_version}"
        )
        limit_gb = int(self.script_config.get("Game", "UpdateFullSyncLimit") or 0)
        await update_wuthering_waves(
            update_info.install_dir,
            self.resource,
            update_info.current_version,
            on_progress=self._push_dispatch_log,
            full_sync_limit=max(limit_gb, 1) * 1024**3,
        )
        self.cur_user_item.status = "完成"

    async def final_task(self) -> None:
        pass

    async def on_crash(self, e: Exception) -> None:
        self.cur_user_item.status = "异常"
        logger.opt(exception=True).warning(f"鸣潮更新任务出现异常: {e}")
        with suppress(Exception):
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(level="error", message=f"鸣潮更新失败: {e}"),
            )
