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


"""模型包的惰性兼容导出。

导入 ``app.models.schema`` 不应顺带实例化旧 ConfigBase 配置图。旧版包级
导出仍按需解析，供尚未迁移的外部插件使用。
"""

from __future__ import annotations

from importlib import import_module
from typing import Any


_SUBMODULE_EXPORTS = {
    "config": "config",
    "schema": "schema",
    "emulator": "emulator",
    "task": "task",
}
_SAFE_SYMBOL_MODULES = ("schema", "emulator", "task")

# Do not probe the legacy modules for arbitrary attribute names.  ``hasattr``
# used to import both modules for every miss, making a harmless capability
# check such as ``getattr(app.models, "unknown", None)`` instantiate the old
# ConfigBase graph.  The names below retain the supported package-level
# compatibility surface while keeping unknown lookups side-effect free.
_LEGACY_SYMBOL_MODULES = {
    **dict.fromkeys(
        (
            "configure_config_save_observer",
            "ValidatorBase",
            "StringValidator",
            "RangeValidator",
            "OptionsValidator",
            "MultipleOptionsValidator",
            "UUIDValidator",
            "MultipleUIDValidator",
            "DateTimeValidator",
            "JSONValidator",
            "EncryptedConfigValueError",
            "EncryptedValueNormalization",
            "EncryptValidator",
            "EncryptedValidator",
            "EncryptedJSONValidator",
            "VirtualConfigValidator",
            "BoolValidator",
            "FileValidator",
            "FolderValidator",
            "ScriptRootPathValidator",
            "EmulatorPathValidator",
            "UserNameValidator",
            "KeyValidator",
            "URLValidator",
            "ArgumentValidator",
            "AdvancedArgumentValidator",
            "ConfigItem",
            "ConfigBase",
            "MultipleConfig",
        ),
        "ConfigBase",
    ),
    **dict.fromkeys(
        (
            "init_maaend_task_config",
            "EmulatorConfig",
            "Webhook",
            "QueueItem",
            "TimeSet",
            "QueueConfig",
            "MaaUserConfig",
            "MaaConfig",
            "MaaEndUserConfig",
            "MaaEndConfig",
            "SrcUserConfig",
            "SrcConfig",
            "M9AUserConfig",
            "M9AConfig",
            "MaaFWUserConfig",
            "MaaFWConfig",
            "MaaPlanConfig",
            "GeneralUserConfig",
            "OkwwUserConfig",
            "GeneralConfig",
            "OkwwConfig",
            "GameSignAccountGroup",
            "ToolsConfig",
            "PluginConfig",
            "GlobalConfig",
            "CLASS_BOOK",
        ),
        "config",
    ),
}


def __getattr__(name: str) -> Any:
    module_name = _SUBMODULE_EXPORTS.get(name)
    if module_name is not None:
        value = import_module(f"{__name__}.{module_name}")
        globals()[name] = value
        return value

    legacy_module = _LEGACY_SYMBOL_MODULES.get(name)
    if legacy_module is not None:
        module = import_module(f"{__name__}.{legacy_module}")
        value = getattr(module, name)
        globals()[name] = value
        return value

    for candidate in _SAFE_SYMBOL_MODULES:
        module = import_module(f"{__name__}.{candidate}")
        if name in module.__dict__:
            value = module.__dict__[name]
            globals()[name] = value
            return value

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))


__all__ = ["ConfigBase", "config", "schema", "emulator", "task"]
