"""Config 核心组件：实现位于本包，入口创建并持有全局单例。"""

from .manager import AppConfig

Config = AppConfig()

__all__ = ["Config"]
