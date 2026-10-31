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

_MODULE_EXPORTS = {
    "config",
    "schema",
    "emulator",
    "task",
    "notification",
    "legacy_config",
}


def __getattr__(name: str):
    if name in _MODULE_EXPORTS:
        return import_module(f".{name}", __name__)
    if name.startswith("_"):
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    if name == "ConfigEntry":
        value = getattr(import_module("app.config"), name)
    else:
        # 保留旧包的显式导入兼容；普通子模块导入不再触发这些通配导出。
        for module_name in (".task", ".schema", ".emulator", ".config", "app.config"):
            module = import_module(module_name, __name__)
            exports = getattr(module, "__all__", None)
            if (exports is None or name in exports) and hasattr(module, name):
                value = getattr(module, name)
                break
        else:
            raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    globals()[name] = value
    return value


__all__ = ["ConfigEntry", "config", "schema", "emulator", "task"]
