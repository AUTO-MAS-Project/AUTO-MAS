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

"""任务传参件：非法组合错误、"是否选中"口径与队列取数。

真值表本身不在这里 —— 展开是各层任务自己的活，分别落在
``ScriptExpander.expand_scripts``（§5.4）与 ``UserExpander.expand_users``（§5.5）。
本模块只放派发层与两层展开都要用的共用件：``queue_script_ids`` 被派发层判合法性
与脚本展开层取顺序两处用到，``is_selected`` 是三处共同的"选中"判定。
"""

from __future__ import annotations

from uuid import UUID

__all__ = ["ExpandError", "is_selected", "queue_script_ids"]


class ExpandError(ValueError):
    """非法的队列 / 脚本 / 用户组合。"""


def is_selected(value: str | None) -> bool:
    """判断调度参数是否真的选中了目标（空串与 ``-`` 都算未选）。"""
    return bool(value and str(value).strip() not in {"", "-"})


def queue_script_ids(queue_id: str | None) -> list[str]:
    """读取队列内已选脚本的 uid 顺序；未选队列时返回空列表。

    派发层建任务前要拿它判参数合法性，脚本展开层展开时再拿一次，故公开。
    """
    from app.core import Config

    if not is_selected(queue_id):
        return []
    queue = Config.queues[UUID(str(queue_id))]
    return [
        item.info.script_id
        for item in queue.items.values()
        if is_selected(item.info.script_id)
    ]
