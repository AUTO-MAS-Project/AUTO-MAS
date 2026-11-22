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
#   Contact: DLmaster_361@163.com

"""MFW 账号任务更新：全局选项兼容与密码准备。"""

import asyncio
from typing import Any

from app.config import ConfigEntry

from .option_secrets import prepare_user_task_snapshot


async def prepare_user_update(
    script: ConfigEntry, user: ConfigEntry, *, data: dict[str, Any]
) -> None:
    """原地准备快照补丁；配置的 stage/commit 留在调用 Task。"""
    task_data = data.get("Task")
    if not isinstance(task_data, dict) or "TaskSnapshot" not in task_data:
        return

    # 双写全局选项，再加密任务和全局表里的密码（M9A 先收归受管任务，见 M9A/config_hooks）。
    task_data["TaskSnapshot"] = await asyncio.to_thread(
        prepare_user_task_snapshot,
        script_id=str(script.uid),
        script_config=script,
        snapshot=task_data["TaskSnapshot"],
    )
