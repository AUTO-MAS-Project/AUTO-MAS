"""服务统一入口：静态引用契约或共享实现，运行时按能力选择并缓存。"""

import sys
from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.common.config_center.errors import (
        ConfigCenterError as ConfigCenterError,
    )

    from .common import config_center as config_center
    from .common import custom_script as custom_script
    from .common import endfield_launcher as endfield_launcher
    from .common import game_maintenance as game_maintenance
    from .common import gi_updater as gi_updater
    from .common import maa_capture as maa_capture
    from .common import maa_copilot as maa_copilot
    from .common import obs_replay as obs_replay
    from .common import system as system
    from .common import telemetry as telemetry
    from .common import update as update
    from .common import wuthering_waves as wuthering_waves
    from .common.config_center import ConfigCenter as ConfigCenter
    from .common.custom_script import execute_script_task as execute_script_task
    from .common.maa_capture import capture_adb as capture_adb
    from .common.maa_capture import capture_win32 as capture_win32
    from .common.system import System as System
    from .contracts.custom_script import ScriptCommandAPI
    from .contracts.power import PowerController
    from .contracts.startup import StartupManager

    power: PowerController
    startup: StartupManager
    custom_script_native: ScriptCommandAPI

_LAZY_EXPORTS = {
    "capture_adb": (".common.maa_capture", "capture_adb"),
    "capture_win32": (".common.maa_capture", "capture_win32"),
    "execute_script_task": (".common.custom_script", "execute_script_task"),
    "ConfigCenter": (".common.config_center", "ConfigCenter"),
    "ConfigCenterError": (".common.config_center.errors", "ConfigCenterError"),
    "System": (".common.system", "System"),
}
_COMMON_MODULES = {
    "maa_capture": ".common.maa_capture",
    "custom_script_native": ".common.custom_script.native",
    "config_center": ".common.config_center",
    "custom_script": ".common.custom_script",
    "endfield_launcher": ".common.endfield_launcher",
    "game_maintenance": ".common.game_maintenance",
    "maa_copilot": ".common.maa_copilot",
    "obs_replay": ".common.obs_replay",
    "system": ".common.system",
    "telemetry": ".common.telemetry",
    "update": ".common.update",
    "wuthering_waves": ".common.wuthering_waves",
    "gi_updater": ".common.gi_updater",
    "power": ".unsupported.power",
    "startup": ".unsupported.startup",
}
_PLATFORM_MODULES: dict[str, dict[str, str]] = {
    "win32": {
        "power": ".windows.power",
        "startup": ".windows.startup",
        "custom_script_native": ".windows.custom_script_native",
    },
    "darwin": {},
    "linux": {},
}


def __getattr__(name: str):
    if name in _LAZY_EXPORTS:
        module_name, attribute = _LAZY_EXPORTS[name]
        value = getattr(import_module(module_name, __name__), attribute)
    else:
        module_name = _PLATFORM_MODULES.get(sys.platform, {}).get(
            name
        ) or _COMMON_MODULES.get(name)
        if module_name is None:
            raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
        value = import_module(module_name, __name__)
        if name in {"power", "startup"}:
            value = getattr(value, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))


__all__ = [
    "maa_capture",
    "capture_adb",
    "capture_win32",
    "execute_script_task",
    "custom_script_native",
    "ConfigCenter",
    "ConfigCenterError",
    "System",
    "config_center",
    "custom_script",
    "endfield_launcher",
    "game_maintenance",
    "maa_copilot",
    "obs_replay",
    "system",
    "telemetry",
    "update",
    "wuthering_waves",
    "gi_updater",
    "power",
    "startup",
]
