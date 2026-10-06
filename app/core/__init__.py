#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


# 先完整初始化基础工具模块，避免 utils 与 app.models.config
# 之间既有循环导入在 config 初始化路径上被触发（原先由 broadcast 模块顺带完成）
import app.utils  # 副作用导入：初始化工具模块，打破循环导入 # noqa: F401  # type: ignore[reportUnusedImport]
from importlib import import_module
from typing import TYPE_CHECKING

from .config import Config

if TYPE_CHECKING:  # 仅供类型检查；运行时由下方 __getattr__ 延迟解析
    from .game_manager import GameManager
    from .history import HistoryStore, history_store
    from .maa_manager import MaaFWManager
    from .plugin_manager import Plugin
    from .task_dispatcher import TaskDispatcher
    from .timer import MainTimer

# 其余核心单例在导入期即触碰 Config 或插件运行时，延迟到首次访问再解析，避免循环导入
_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "GameManager": (".game_manager", "GameManager"),
    "HistoryStore": (".history", "HistoryStore"),
    "history_store": (".history", "history_store"),
    "MaaFWManager": (".maa_manager", "MaaFWManager"),
    "MainTimer": (".timer", "MainTimer"),
    "Plugin": (".plugin_manager", "Plugin"),
    "TaskDispatcher": (".task_dispatcher", "TaskDispatcher"),
}


def __getattr__(name: str) -> object:
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = _LAZY_EXPORTS[name]
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value


__all__ = [
    "Config",
    "GameManager",
    "HistoryStore",
    "history_store",
    "MaaFWManager",
    "MainTimer",
    "Plugin",
    "TaskDispatcher",
]
