"""MaaFW 第一层·外部运行：把 interface.json 映射成外壳自己的实例配置。

不加载项目 DLL，而是写项目外壳能识别的配置文件后裸启动外壳。本包只负责
「生成配置 dict」的纯逻辑，不写文件、不删实例、不起进程。
"""

from .mfaavalonia import (
    CONTROLLER_TYPE_CODES,
    TASK_ENTRY_SEPARATOR,
    InstanceOrchestration,
    UnknownControllerTypeError,
    build_current_tasks,
    build_instance_config,
    build_option_entries,
    build_task_items,
    resolve_controller_code,
)
from .models import ShellMappingError, TaskSelection
from .profile import (
    SHELL_LOG_PROFILES,
    ShellLogProfile,
    get_shell_log_profile,
    pick_latest_mxu_log,
    resolve_log_relpath,
)
from .mxu import (
    append_instance,
    build_instance_entry,
    build_interface_task_snapshot,
    build_task_entries,
    build_task_entry,
    default_instance_id,
)
from .shell import ShellFamily, detect_shell_family

__all__ = [
    "CONTROLLER_TYPE_CODES",
    "SHELL_LOG_PROFILES",
    "TASK_ENTRY_SEPARATOR",
    "InstanceOrchestration",
    "ShellFamily",
    "ShellLogProfile",
    "ShellMappingError",
    "TaskSelection",
    "UnknownControllerTypeError",
    "append_instance",
    "build_current_tasks",
    "build_instance_config",
    "build_instance_entry",
    "build_interface_task_snapshot",
    "build_option_entries",
    "build_task_entries",
    "build_task_entry",
    "build_task_items",
    "default_instance_id",
    "detect_shell_family",
    "get_shell_log_profile",
    "pick_latest_mxu_log",
    "resolve_controller_code",
    "resolve_log_relpath",
]
