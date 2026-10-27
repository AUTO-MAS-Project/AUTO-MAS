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


"""按能力分发的平台工具入口；导入根包不装配桌面或可选依赖。"""

import sys
from importlib import import_module

_LAZY_EXPORTS = {
    "SIGN_MODE_REGEX": (".common.LogPatternExtractor", "SIGN_MODE_REGEX"),
    "SIGN_MODE_SPLIT": (".common.LogPatternExtractor", "SIGN_MODE_SPLIT"),
    "get_game_day_tz": (".common.constants", "get_game_day_tz"),
    "game_now": (".common.constants", "game_now"),
    "normalize_base_source": (".common.constants", "normalize_base_source"),
    "LOG_TYPE_ERROR": (".common.LogPatternExtractor", "LOG_TYPE_ERROR"),
    "LOG_TYPE_NORMAL": (".common.LogPatternExtractor", "LOG_TYPE_NORMAL"),
    "UnsupportedPlatformError": (".common.errors", "UnsupportedPlatformError"),
    "LogMonitor": (".common.LogMonitor", "LogMonitor"),
    "strptime": (".common.LogMonitor", "strptime"),
    "ProcessManager": (".common.process", "ProcessManager"),
    "ProcessRunner": (".common.process", "ProcessRunner"),
    "ProcessInfo": (".common.process", "ProcessInfo"),
    "ProcessResult": (".common.process", "ProcessResult"),
    "is_process_running": (".common.process", "is_process_running"),
    "is_process_alive": (".common.process", "is_process_alive"),
    "RegexMatcher": (".common.LogPatternExtractor", "RegexMatcher"),
    "MultiLineAggregator": (".common.LogPatternExtractor", "MultiLineAggregator"),
    "compile_regex": (".common.LogPatternExtractor", "compile_regex"),
    "load_patterns": (".common.LogPatternExtractor", "load_patterns"),
    "apply_patterns": (".common.LogPatternExtractor", "apply_patterns"),
    "flush_patterns": (".common.LogPatternExtractor", "flush_patterns"),
    "debug_pattern": (".common.LogPatternExtractor", "debug_pattern"),
    "LogSignMatcher": (".common.LogPatternExtractor", "LogSignMatcher"),
    "compile_log_signs": (".common.LogPatternExtractor", "compile_log_signs"),
    "MumuManager": (".common.emulator", "MumuManager"),
    "LDManager": (".common.emulator", "LDManager"),
    "search_all_emulators": (".common.emulator", "search_all_emulators"),
    "EMULATOR_TYPE_BOOK": (".common.emulator", "EMULATOR_TYPE_BOOK"),
    "decode_bytes": (".common.tools", "decode_bytes"),
    "busy_wait": (".common.tools", "busy_wait"),
    "WebSocketClient": (".common.websocket", "WebSocketClient"),
    "MirrorChyanError": (".common.mirrorchyan", "MirrorChyanError"),
    "compare_mirrorchyan_versions": (
        ".common.mirrorchyan",
        "compare_mirrorchyan_versions",
    ),
    "IS_WINDOWS": ("host", "IS_WINDOWS"),
    "IS_ELEVATED": ("host", "IS_ELEVATED"),
    "is_admin": ("host", "is_admin"),
    "is_long_path_supported": ("host", "is_long_path_supported"),
    "get_logger": (".common.logger", "get_logger"),
    "resource_path": (".common.paths", "resource_path"),
    "is_supervised": (".common.supervision", "is_supervised"),
    "should_preserve_backend": (".common.supervision", "should_preserve_backend"),
    "dpapi_encrypt": (".common.security", "dpapi_encrypt"),
    "dpapi_decrypt": (".common.security", "dpapi_decrypt"),
    "looks_like_dpapi_blob": (".common.security", "looks_like_dpapi_blob"),
    "format_exception_reason": (".common.security", "format_exception_reason"),
    "sanitize_log_message": (".common.security", "sanitize_log_message"),
    "UTC4": (".common.constants", "UTC4"),
    "UTC8": (".common.constants", "UTC8"),
    "TYPE_BOOK": (".common.constants", "TYPE_BOOK"),
    "PLAN_CONSUMER_VALUES": (".common.constants", "PLAN_CONSUMER_VALUES"),
    "MSS_TRIBULATION_STAGES": (".common.constants", "MSS_TRIBULATION_STAGES"),
    "MSS_DEFAULT_TRIBULATION_STAGE": (
        ".common.constants",
        "MSS_DEFAULT_TRIBULATION_STAGE",
    ),
    "MAAEND_RUN_MOOD_BOOK": (".common.constants", "MAAEND_RUN_MOOD_BOOK"),
    "MAAEND_DELIVERY_TASK": (".common.constants", "MAAEND_DELIVERY_TASK"),
    "MAAEND_AUTO_COLLECT_TASK": (".common.constants", "MAAEND_AUTO_COLLECT_TASK"),
    "MAAEND_DELIVERY_COMMISSION_SOURCES": (
        ".common.constants",
        "MAAEND_DELIVERY_COMMISSION_SOURCES",
    ),
    "MAAEND_AUTO_COLLECT_MODES": (".common.constants", "MAAEND_AUTO_COLLECT_MODES"),
    "MAA_STAGE_KEY": (".common.constants", "MAA_STAGE_KEY"),
    "ARKNIGHTS_GAME_DAY_TZ": (".common.constants", "ARKNIGHTS_GAME_DAY_TZ"),
    "MAAEND_SANITY_TASK_LABELS": (".common.constants", "MAAEND_SANITY_TASK_LABELS"),
    "MAAEND_SANITY_TASK_DETAIL_LABELS": (
        ".common.constants",
        "MAAEND_SANITY_TASK_DETAIL_LABELS",
    ),
    "MAAEND_SANITY_TASK_TYPES": (".common.constants", "MAAEND_SANITY_TASK_TYPES"),
    "MAAEND_AUTO_ESSENCE_MENUS": (".common.constants", "MAAEND_AUTO_ESSENCE_MENUS"),
    "MAAEND_PROTOCOL_SPACE_TASK_OPTIONS": (
        ".common.constants",
        "MAAEND_PROTOCOL_SPACE_TASK_OPTIONS",
    ),
    "MAAEND_STAGE_WITH_AB": (".common.constants", "MAAEND_STAGE_WITH_AB"),
    "MAAEND_TASK_GROUPS": (".common.constants", "MAAEND_TASK_GROUPS"),
    "MAAEND_TASKS": (".common.constants", "MAAEND_TASKS"),
    "MAAEND_SANITY_TASK_DEFAULTS": (".common.constants", "MAAEND_SANITY_TASK_DEFAULTS"),
    "MAAEND_INVENTORY_TARGET_DEFAULTS": (
        ".common.constants",
        "MAAEND_INVENTORY_TARGET_DEFAULTS",
    ),
    "MAAEND_SANITY_TASK_FIELDS": (".common.constants", "MAAEND_SANITY_TASK_FIELDS"),
    "ENDFIELD_SERVER_PRESETS": (".common.constants", "ENDFIELD_SERVER_PRESETS"),
    "EMULATOR_PATH_BOOK": (".common.constants", "EMULATOR_PATH_BOOK"),
    "RESOURCE_STAGE_INFO": (".common.constants", "RESOURCE_STAGE_INFO"),
    "MATERIALS_MAP": (".common.constants", "MATERIALS_MAP"),
    "STARRAIL_PACKAGE_NAME": (".common.constants", "STARRAIL_PACKAGE_NAME"),
    "STARRAIL_CN_UPDATE_LINK_URL": (".common.constants", "STARRAIL_CN_UPDATE_LINK_URL"),
    "STARRAIL_UPDATE_LINK_SERVER": (".common.constants", "STARRAIL_UPDATE_LINK_SERVER"),
    "STARRAIL_STAGE_BOOK": (".common.constants", "STARRAIL_STAGE_BOOK"),
    "TIME_FIELDS": (".common.constants", "TIME_FIELDS"),
    "RESERVED_NAMES": (".common.constants", "RESERVED_NAMES"),
    "ILLEGAL_CHARS": (".common.constants", "ILLEGAL_CHARS"),
    "KEYBOARD_KEYS": (".common.constants", "KEYBOARD_KEYS"),
    "MIRROR_ERROR_INFO": (".common.constants", "MIRROR_ERROR_INFO"),
    "DEFAULT_DATETIME": (".common.constants", "DEFAULT_DATETIME"),
    "SKLAND_SM_CONFIG": (".common.constants", "SKLAND_SM_CONFIG"),
    "BROWSER_ENV": (".common.constants", "BROWSER_ENV"),
    "DES_RULE": (".common.constants", "DES_RULE"),
    "ANSI_ESCAPE_RE": (".common.constants", "ANSI_ESCAPE_RE"),
    "TASK_MODE_ZH": (".common.constants", "TASK_MODE_ZH"),
    "APPDATA_PATH": (".common.constants", "APPDATA_PATH"),
    "FORBIDDEN_PATH_PREFIXES": (".common.constants", "FORBIDDEN_PATH_PREFIXES"),
    "FORBIDDEN_PATH_EXACT": (".common.constants", "FORBIDDEN_PATH_EXACT"),
    "EMULATOR_SPLASH_ADS_PATH_BOOK": (
        ".common.constants",
        "EMULATOR_SPLASH_ADS_PATH_BOOK",
    ),
    "CYCLE_DATETIME_FORMAT": (".common.constants", "CYCLE_DATETIME_FORMAT"),
    "CYCLE_EMPTY_TIME": (".common.constants", "CYCLE_EMPTY_TIME"),
    "BASE_SHARED": (".common.constants", "BASE_SHARED"),
    "BASE_INDEPENDENT": (".common.constants", "BASE_INDEPENDENT"),
    "BASE_NATIVE": (".common.constants", "BASE_NATIVE"),
    "LEGACY_BASE_SOURCES": (".common.constants", "LEGACY_BASE_SOURCES"),
    "BASE_SOURCE_LABELS": (".common.constants", "BASE_SOURCE_LABELS"),
}
_COMMON_MODULES = {
    "update_native": ".common.update_native",
    "emulator_native": ".common.emulator_native",
    "registry": ".common.registry",
    "audio": ".common.audio",
    "update_files": ".common.update_files",
    "exception": ".common.exception",
    "config_restore": ".common.config_restore",
    "window": ".common.window",
    "paths": ".common.paths",
    "mirrorchyan": ".common.mirrorchyan",
    "host": ".common.host",
    "hpatchz": ".common.hpatchz",
    "tools": ".common.tools",
    "security": ".common.security",
    "constants": ".common.constants",
    "io": ".common.io",
    "game_apk": ".common.game_apk",
    "notification_render": ".common.notification_render",
    "process_runner": ".common.process_runner",
    "config_archive": ".common.config_archive",
    "logger": ".common.logger",
    "display": ".common.display",
    "fluxdown_cli": ".common.fluxdown_cli",
    "supervision": ".common.supervision",
    "community": ".common.community",
    "secret": ".common.secret",
    "config_document": ".common.config_document",
    "LogMonitor": ".common.LogMonitor",
    "environment": ".common.environment",
    "notification_template": ".common.notification_template",
    "process": ".common.process",
    "errors": ".common.errors",
    "process_platform": ".common.process_platform",
    "LogPatternExtractor": ".common.LogPatternExtractor",
    "game_update": ".common.game_update",
    "vdd": ".common.vdd",
    "websocket": ".common.websocket",
    "emulator": ".common.emulator",
    "emulator2": ".common.emulator2",
    "OCR": ".common.OCR",
    "i18n": ".common.i18n",
    "expression": ".common.expression",
    "notification": ".common.notification",
}
_PLATFORM_MODULES = {
    "win32": {
        "update_native": ".windows.update_native",
        "emulator_native": ".windows.emulator_native",
        "registry": ".windows.registry",
        "host": ".windows.host",
        "window": ".windows.window",
        "display": ".windows.display",
        "secret": ".windows.secret",
        "audio": ".windows.audio",
        "vdd": ".windows.vdd",
        "process_platform": ".windows.process",
        "notification": ".windows.notification",
    },
    "darwin": {},
    "linux": {},
}


def __getattr__(name: str):
    if name in _LAZY_EXPORTS:
        module, attribute = _LAZY_EXPORTS[name]
        value = getattr(
            __getattr__(module)
            if not module.startswith(".")
            else import_module(module, __name__),
            attribute,
        )
    else:
        target = _PLATFORM_MODULES.get(sys.platform, {}).get(
            name
        ) or _COMMON_MODULES.get(name)
        if target is None:
            if not any(name in entries for entries in _PLATFORM_MODULES.values()):
                raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
            value = import_module(".common.dummy", __name__).create_dummy(name)
        else:
            value = import_module(target, __name__)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))


class LazyProxy:
    """惰性代理：首次属性访问时才导入真实对象，避免初始化期间的循环导入。

    与模块级 __getattr__ 不同，它绑定为一个真实的模块全局名，因此函数内的
    裸全局名引用（LOAD_GLOBAL）也能正常解析；同时转发属性读写，保证
    ``Config.xxx = yyy`` 这类赋值落到真实对象上。
    """

    def __init__(self, module: str, name: str) -> None:
        object.__setattr__(self, "_module", module)
        object.__setattr__(self, "_name", name)
        object.__setattr__(self, "_obj", None)

    def _resolve(self):
        obj = self.__dict__["_obj"]
        if obj is None:
            from importlib import import_module

            obj = getattr(import_module(self._module), self._name)
            object.__setattr__(self, "_obj", obj)
        return obj

    def __getattr__(self, attr: str):
        return getattr(self._resolve(), attr)

    def __setattr__(self, attr: str, value) -> None:
        setattr(self._resolve(), attr, value)


__all__ = list(dict.fromkeys([*_LAZY_EXPORTS, *_COMMON_MODULES, "LazyProxy"]))
