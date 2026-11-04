"""Config 核心组件：实现位于本包，入口创建并持有全局单例。"""

from app.utils.common.startup_timing import startup_stage

with startup_stage("后端/配置管理模块导入"):
    from .manager import AppConfig

with startup_stage("后端/配置单例构造"):
    Config = AppConfig()

__all__ = ["Config"]
