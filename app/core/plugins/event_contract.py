#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

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
    """
    判断给定事件名是否属于脚本生命周期标准事件集合。

    Args:
        event (str): 待判断的事件名。

    Returns:
        bool: 若事件名属于标准脚本生命周期事件则返回 True，否则返回 False。
    """
    return event in SCRIPT_LIFECYCLE_EVENTS


def is_valid_source(source: object) -> bool:
    """
    校验事件来源字符串是否满足基础格式约束。

    Args:
        source (str): 事件来源字符串，建议使用点分格式（例如 core.task_manager）。

    Returns:
        bool: 来源格式合法返回 True，否则返回 False。
    """
    if not isinstance(source, str):
        return False

    value = source.strip()
    if not value:
        return False

    return "." in value
