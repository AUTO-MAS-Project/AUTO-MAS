"""任务管理核心组件；调度及周期策略在本包实现。"""

from .manager import _TaskManager

TaskManager = _TaskManager()

__all__ = ["TaskManager"]
