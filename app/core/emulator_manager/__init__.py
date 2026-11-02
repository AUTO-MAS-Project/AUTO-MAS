"""EmulatorManager 核心组件：实现位于本包，入口创建并持有全局单例。"""

from .manager import _EmulatorManager

EmulatorManager = _EmulatorManager()

__all__ = ["EmulatorManager"]
