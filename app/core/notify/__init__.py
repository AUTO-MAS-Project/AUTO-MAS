"""Notify 核心组件：实现位于本包，入口创建并持有全局单例。"""

from .manager import NotificationManager

Notify = NotificationManager()

__all__ = ["Notify"]
