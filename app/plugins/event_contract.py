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

from typing import Final, Literal


EVENT_CONTRACT_VERSION: Final[str] = "1"
"""插件事件契约版本。"""

EVENT_DISPATCH_MODEL: Final[str] = "async"
"""插件事件分发模型：固定为异步并发分发。"""

EventScope = Literal["global", "instance"]
"""事件作用域：global 表示全局广播，instance 表示实例内广播。"""

EventErrorPolicy = Literal["continue", "raise"]
"""事件错误策略：continue 表示继续分发，raise 表示抛出异常。"""

CORE_SOURCE_PREFIX: Final[str] = "core."
"""约定的核心事件来源前缀。"""


class PluginEventNames:
    """插件系统约定的标准事件名。"""

    TASK_START: Final[str] = "task.start"
    TASK_PROGRESS: Final[str] = "task.progress"
    TASK_LOG: Final[str] = "task.log"
    TASK_EXIT: Final[str] = "task.exit"

    SCRIPT_START: Final[str] = "script.start"
    SCRIPT_SUCCESS: Final[str] = "script.success"
    SCRIPT_ERROR: Final[str] = "script.error"
    SCRIPT_CANCELLED: Final[str] = "script.cancelled"
    SCRIPT_EXIT: Final[str] = "script.exit"


SCRIPT_LIFECYCLE_EVENTS: Final[set[str]] = {
    PluginEventNames.SCRIPT_START,
    PluginEventNames.SCRIPT_SUCCESS,
    PluginEventNames.SCRIPT_ERROR,
    PluginEventNames.SCRIPT_CANCELLED,
    PluginEventNames.SCRIPT_EXIT,
}
"""脚本生命周期标准事件集合。"""


def is_script_event(event: str) -> bool:
    return event in SCRIPT_LIFECYCLE_EVENTS


def is_valid_source(source: str) -> bool:
    if not isinstance(source, str):
        return False
    value = source.strip()
    if not value:
        return False
    return "." in value
