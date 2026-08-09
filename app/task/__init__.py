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

from importlib import import_module
from typing import Any

__all__ = [
    "MaaManager",
    "SrcManager",
    "GeneralManager",
    "MaaEndManager",
]

_LAZY_EXPORTS = {
    "MaaManager": ("app.task.MAA.manager", "MaaManager"),
    "SrcManager": ("app.task.SRC.manager", "SrcManager"),
    "GeneralManager": ("app.task.general.manager", "GeneralManager"),
    "MaaEndManager": ("app.task.MaaEnd.manager", "MaaEndManager"),
}


def __getattr__(name: str) -> Any:
    """按需导出任务管理器，避免包初始化时触发环形导入。"""

    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)

    module_path, attr_name = target
    module = import_module(module_path)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
