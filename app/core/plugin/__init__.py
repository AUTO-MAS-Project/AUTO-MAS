"""插件核心组件；本包创建并持有唯一的宿主插件管理器。"""

from .manager import _PluginManager

Plugin = _PluginManager()

__all__ = ["Plugin"]
