#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

from typing import Final


EVENT_CONTRACT_VERSION: Final[str] = "1"
"""插件事件契约版本。"""

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
    """判断事件是否属于脚本生命周期标准事件。"""
    return event in SCRIPT_LIFECYCLE_EVENTS


def is_valid_source(source: str) -> bool:
    """校验事件来源字符串格式。

    约束：
    - 非空字符串
    - 建议使用点分格式（如 core.task_manager）
    """
    if not isinstance(source, str):
        return False

    value = source.strip()
    if not value:
        return False

    return "." in value
