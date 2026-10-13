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

"""L2 下传给 L3 的任务级只读快照。运行期事实源仍是 ``TaskItem`` 树。"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.models.task import TaskMode, TaskTriggerSource

__all__ = ["TaskContext"]


@dataclass(frozen=True)
class TaskContext:
    """从 ``TaskItem.info`` 拍下的不可变审计快照。"""

    task_id: UUID
    trigger_source: TaskTriggerSource
    mode: TaskMode
    queue_id: str | None
    script_id: str | None
    user_id: str | None
