#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
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

"""Emulator 2.0：一条配置纳管多条模拟器路径。

与 `app.utils.emulator` 的关系：本包负责「设备号编排」「实例设置」与「带包启动」，
其余运行时（开关模拟器、显示/隐藏）仍然复用 `app.utils.emulator` 里的旧管理器。
带包启动之所以不复用，是因为两家原生的启动参数在模拟器已经在跑时会被整条吞掉，
见 `applaunch`。
"""

from importlib import import_module

# 更新引擎只用 avd 下的文件 / 网络工具；导入它不应顺带装配所有设备管理器与配置模型。
_LAZY_EXPORTS = {
    "AppLaunchMixin": (".applaunch", "AppLaunchMixin"),
    "AppLaunchResult": (".applaunch", "AppLaunchResult"),
    "DetectResult": (".detect", "DetectResult"),
    "DeviceUnavailableError": (".facade", "DeviceUnavailableError"),
    "Emulator2Manager": (".facade", "Emulator2Manager"),
    "LDPlayer14Manager": (".ldplayer14", "LDPlayer14Manager"),
    "PathRecord": (".slots", "PathRecord"),
    "SlotRecord": (".slots", "SlotRecord"),
    "SlotTable": (".slots", "SlotTable"),
    "dump_paths": (".facade", "dump_paths"),
    "ensure_app_running": (".applaunch", "ensure_app_running"),
    "is_package_foreground": (".applaunch", "is_package_foreground"),
    "is_package_missing": (".applaunch", "is_package_missing"),
    "load_paths": (".facade", "load_paths"),
    "make_path_id": (".slots", "make_path_id"),
    "probe_install_path": (".detect", "probe_install_path"),
}


def _get_public_export(name: str):
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module, attribute = _LAZY_EXPORTS[name]
    value = getattr(import_module(module, __name__), attribute)
    globals()[name] = value
    return value


__all__ = [
    "AppLaunchMixin",
    "AppLaunchResult",
    "DetectResult",
    "DeviceUnavailableError",
    "Emulator2Manager",
    "LDPlayer14Manager",
    "PathRecord",
    "SlotRecord",
    "SlotTable",
    "dump_paths",
    "ensure_app_running",
    "is_package_foreground",
    "is_package_missing",
    "load_paths",
    "make_path_id",
    "probe_install_path",
]


_SUBMODULES = {
    "facade": ".facade",
    "stability": ".stability",
    "ldplayer14": ".ldplayer14",
    "slots": ".slots",
    "vbox": ".vbox",
    "settings": ".settings",
    "master_mode": ".master_mode",
    "guard": ".guard",
    "applaunch": ".applaunch",
    "detect": ".detect",
    "adb": ".adb",
    "mumu6": ".mumu6",
    "avd": ".avd",
}


def __getattr__(name):
    if name in _SUBMODULES:
        from importlib import import_module

        value = import_module(_SUBMODULES[name], __name__)
        globals()[name] = value
        return value
    return _get_public_export(name)
