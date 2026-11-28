"""真实宿主模块 app.utils 的 SDK 导出。"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.utils import *  # noqa: F403 - SDK 整包静态再导出，复用宿主自身的公开符号声明。
    from app.utils.common.log.patterns import match_log_signs as match_log_signs
    from app.utils.common.log.sources import LogSource as LogSource
else:

    def __getattr__(name: str) -> Any:
        """按需从宿主 app.utils 取得同名能力，使插件通过 SDK 入口复用宿主实现。"""
        if name == "LogSource":
            return import_module("app.utils.common.log.sources").LogSource
        if name == "match_log_signs":
            return import_module("app.utils.common.log.patterns").match_log_signs
        return getattr(import_module("app.utils"), name)
