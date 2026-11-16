"""进程管理、执行及平台后端；导入子模块不装配其他能力。"""

from .operations import (
    is_process_running as is_process_running,
)
from .operations import (
    is_process_stopped as is_process_stopped,
)
from .operations import (
    kill_process as kill_process,
)
from .operations import (
    kill_process_by_pid as kill_process_by_pid,
)
