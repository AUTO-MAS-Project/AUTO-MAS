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


# 先完整初始化基础工具模块，避免 app.utils.emulator 与 app.models.config
# 之间既有循环导入在 config 初始化路径上被触发（原先由 broadcast 模块顺带完成）
import app.utils  # noqa: F401

from .config import Config
from .emulator_manager import EmulatorManager
from .history import HistoryStore, history_store
from .page_registry import (
    PageDeclaration,
    PageFacade,
    PageRegistry,
    page_registry,
    register_builtin_pages,
)

def __getattr__(name: str):
    if name == "MaaFWManager":
        from .maa_manager import MaaFWManager

        return MaaFWManager
    if name == "TaskManager":
        from .task_manager import TaskManager

        return TaskManager
    if name == "MainTimer":
        from .timer import MainTimer

        return MainTimer
    raise AttributeError(name)


__all__ = [
    "Config",
    "HistoryStore",
    "history_store",
    "MainTimer",
    "TaskManager",
    "EmulatorManager",
    "MaaFWManager",
    "PageDeclaration",
    "PageFacade",
    "PageRegistry",
    "page_registry",
    "register_builtin_pages",
]
