"""专项运行使用的窗口检测和桌面分身进程上下文。"""

from app.utils.common.process.manager import has_process_window
from app.utils.common.process.session import desktop_process_target

__all__ = ["desktop_process_target", "has_process_window"]
