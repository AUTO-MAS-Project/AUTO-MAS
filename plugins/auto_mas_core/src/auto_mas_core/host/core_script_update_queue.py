"""[兼容旧专项] 临时复用旧 manager 的脚本更新入口。

TODO(脚本更新迁移)：安装与恢复后续统一迁入 L2；旧专项完成迁移后删除此宿主桥接。
"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.core.script_update_queue import *  # noqa: F403 - SDK 整包静态再导出，复用宿主自身的公开符号声明。
else:

    def __getattr__(name: str) -> Any:
        """按需从宿主 app.core.script_update_queue 取得同名能力，使插件通过 SDK 入口复用宿主实现。"""
        return getattr(import_module("app.core.script_update_queue"), name)
