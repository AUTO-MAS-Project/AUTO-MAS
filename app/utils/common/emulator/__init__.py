#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
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


from app.models.config import EmulatorConfig
from app.models.emulator import EmulatorRuntimePolicy

from .general import GeneralDeviceManager
from .ldplayer import LDManager
from .mumu import MumuManager
from .tools import search_all_emulators


def _build_emulator2_manager(
    config: EmulatorConfig, *, runtime_policy: EmulatorRuntimePolicy
):
    """Emulator 2.0 管理器的工厂。

    ``app.utils.emulator2`` 复用本包里的旧管理器实现（继承 ``LDManager``），
    在这里直接 import 它会形成导入环——谁先被导入谁就拿到半初始化的对方。
    表里的值只会被当成 ``EMULATOR_TYPE_BOOK[type](config, runtime_policy=...)`` 调用，
    所以放一个延迟导入的工厂函数即可，无需在模块加载期建立依赖。
    """
    from app.utils import emulator2 as _utils_emulator2

    return _utils_emulator2.Emulator2Manager(config, runtime_policy=runtime_policy)


EMULATOR_TYPE_BOOK = {
    "mumu": MumuManager,
    "ldplayer": LDManager,
    "general": GeneralDeviceManager,
    "emulator2": _build_emulator2_manager,
}

__all__ = [
    "MumuManager",
    "LDManager",
    "GeneralDeviceManager",
    "search_all_emulators",
    "EMULATOR_TYPE_BOOK",
]


def _get_public_export(name):
    raise AttributeError(name)


_SUBMODULES = {
    "ldplayer": ".ldplayer",
    "mumu": ".mumu",
    "tools": ".tools",
    "general": ".general",
}


def __getattr__(name):
    if name in _SUBMODULES:
        from importlib import import_module

        value = import_module(_SUBMODULES[name], __name__)
        globals()[name] = value
        return value
    return _get_public_export(name)
