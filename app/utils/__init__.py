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
from typing import TYPE_CHECKING

# 静态检查显式声明导出；运行时仍由下方入口按需加载。
if TYPE_CHECKING:
    from .common import OCR as OCR
    from .common import LogPatternExtractor as LogPatternExtractor
    from .common import community as community
    from .common import config_archive as config_archive
    from .common import config_document as config_document
    from .common import config_restore as config_restore
    from .common import constants as constants
    from .common import emulator as emulator
    from .common import emulator2 as emulator2
    from .common import environment as environment
    from .common import errors as errors
    from .common import exception as exception
    from .common import expression as expression
    from .common import fluxdown_cli as fluxdown_cli
    from .common import game_apk as game_apk
    from .common import game_update as game_update
    from .common import hpatchz as hpatchz
    from .common import i18n as i18n
    from .common import io as io
    from .common import logger as logger
    from .common import mirrorchyan as mirrorchyan
    from .common import notification_render as notification_render
    from .common import notification_template as notification_template
    from .common import paths as paths
    from .common import process as process
    from .common import process_runner as process_runner
    from .common import security as security
    from .common import supervision as supervision
    from .common import tools as tools
    from .common import update_files as update_files
    from .common import websocket as websocket
    from .common.constants import ANSI_ESCAPE_RE as ANSI_ESCAPE_RE
    from .common.constants import APPDATA_PATH as APPDATA_PATH
    from .common.constants import ARKNIGHTS_GAME_DAY_TZ as ARKNIGHTS_GAME_DAY_TZ
    from .common.constants import BASE_INDEPENDENT as BASE_INDEPENDENT
    from .common.constants import BASE_NATIVE as BASE_NATIVE
    from .common.constants import BASE_SHARED as BASE_SHARED
    from .common.constants import BASE_SOURCE_LABELS as BASE_SOURCE_LABELS
    from .common.constants import BROWSER_ENV as BROWSER_ENV
    from .common.constants import CYCLE_DATETIME_FORMAT as CYCLE_DATETIME_FORMAT
    from .common.constants import CYCLE_EMPTY_TIME as CYCLE_EMPTY_TIME
    from .common.constants import DEFAULT_DATETIME as DEFAULT_DATETIME
    from .common.constants import DES_RULE as DES_RULE
    from .common.constants import EMULATOR_PATH_BOOK as EMULATOR_PATH_BOOK
    from .common.constants import (
        EMULATOR_SPLASH_ADS_PATH_BOOK as EMULATOR_SPLASH_ADS_PATH_BOOK,
    )
    from .common.constants import ENDFIELD_SERVER_PRESETS as ENDFIELD_SERVER_PRESETS
    from .common.constants import FORBIDDEN_PATH_EXACT as FORBIDDEN_PATH_EXACT
    from .common.constants import FORBIDDEN_PATH_PREFIXES as FORBIDDEN_PATH_PREFIXES
    from .common.constants import ILLEGAL_CHARS as ILLEGAL_CHARS
    from .common.constants import KEYBOARD_KEYS as KEYBOARD_KEYS
    from .common.constants import LEGACY_BASE_SOURCES as LEGACY_BASE_SOURCES
    from .common.constants import MAA_STAGE_KEY as MAA_STAGE_KEY
    from .common.constants import MAAEND_AUTO_COLLECT_MODES as MAAEND_AUTO_COLLECT_MODES
    from .common.constants import MAAEND_AUTO_COLLECT_TASK as MAAEND_AUTO_COLLECT_TASK
    from .common.constants import MAAEND_AUTO_ESSENCE_MENUS as MAAEND_AUTO_ESSENCE_MENUS
    from .common.constants import (
        MAAEND_DELIVERY_COMMISSION_SOURCES as MAAEND_DELIVERY_COMMISSION_SOURCES,
    )
    from .common.constants import MAAEND_DELIVERY_TASK as MAAEND_DELIVERY_TASK
    from .common.constants import (
        MAAEND_INVENTORY_TARGET_DEFAULTS as MAAEND_INVENTORY_TARGET_DEFAULTS,
    )
    from .common.constants import (
        MAAEND_PROTOCOL_SPACE_TASK_OPTIONS as MAAEND_PROTOCOL_SPACE_TASK_OPTIONS,
    )
    from .common.constants import MAAEND_RUN_MOOD_BOOK as MAAEND_RUN_MOOD_BOOK
    from .common.constants import (
        MAAEND_SANITY_TASK_DEFAULTS as MAAEND_SANITY_TASK_DEFAULTS,
    )
    from .common.constants import (
        MAAEND_SANITY_TASK_DETAIL_LABELS as MAAEND_SANITY_TASK_DETAIL_LABELS,
    )
    from .common.constants import MAAEND_SANITY_TASK_FIELDS as MAAEND_SANITY_TASK_FIELDS
    from .common.constants import MAAEND_SANITY_TASK_LABELS as MAAEND_SANITY_TASK_LABELS
    from .common.constants import MAAEND_SANITY_TASK_TYPES as MAAEND_SANITY_TASK_TYPES
    from .common.constants import MAAEND_STAGE_WITH_AB as MAAEND_STAGE_WITH_AB
    from .common.constants import MAAEND_TASK_GROUPS as MAAEND_TASK_GROUPS
    from .common.constants import MAAEND_TASKS as MAAEND_TASKS
    from .common.constants import MATERIALS_MAP as MATERIALS_MAP
    from .common.constants import MIRROR_ERROR_INFO as MIRROR_ERROR_INFO
    from .common.constants import (
        MSS_DEFAULT_TRIBULATION_STAGE as MSS_DEFAULT_TRIBULATION_STAGE,
    )
    from .common.constants import MSS_TRIBULATION_STAGES as MSS_TRIBULATION_STAGES
    from .common.constants import PLAN_CONSUMER_VALUES as PLAN_CONSUMER_VALUES
    from .common.constants import RESERVED_NAMES as RESERVED_NAMES
    from .common.constants import RESOURCE_STAGE_INFO as RESOURCE_STAGE_INFO
    from .common.constants import SKLAND_SM_CONFIG as SKLAND_SM_CONFIG
    from .common.constants import (
        STARRAIL_CN_UPDATE_LINK_URL as STARRAIL_CN_UPDATE_LINK_URL,
    )
    from .common.constants import STARRAIL_PACKAGE_NAME as STARRAIL_PACKAGE_NAME
    from .common.constants import STARRAIL_STAGE_BOOK as STARRAIL_STAGE_BOOK
    from .common.constants import (
        STARRAIL_UPDATE_LINK_SERVER as STARRAIL_UPDATE_LINK_SERVER,
    )
    from .common.constants import TASK_MODE_ZH as TASK_MODE_ZH
    from .common.constants import TIME_FIELDS as TIME_FIELDS
    from .common.constants import TYPE_BOOK as TYPE_BOOK
    from .common.constants import UTC4 as UTC4
    from .common.constants import UTC8 as UTC8
    from .common.constants import game_now as game_now
    from .common.constants import get_game_day_tz as get_game_day_tz
    from .common.constants import normalize_base_source as normalize_base_source
    from .common.emulator import EMULATOR_TYPE_BOOK as EMULATOR_TYPE_BOOK
    from .common.emulator import LDManager as LDManager
    from .common.emulator import MumuManager as MumuManager
    from .common.emulator import search_all_emulators as search_all_emulators
    from .common.errors import UnsupportedPlatformError as UnsupportedPlatformError
    from .common.logger import get_logger as get_logger
    from .common.LogMonitor import LogMonitor as LogMonitor
    from .common.LogMonitor import strptime as strptime
    from .common.LogPatternExtractor import LOG_TYPE_ERROR as LOG_TYPE_ERROR
    from .common.LogPatternExtractor import LOG_TYPE_NORMAL as LOG_TYPE_NORMAL
    from .common.LogPatternExtractor import SIGN_MODE_REGEX as SIGN_MODE_REGEX
    from .common.LogPatternExtractor import SIGN_MODE_SPLIT as SIGN_MODE_SPLIT
    from .common.LogPatternExtractor import LogSignMatcher as LogSignMatcher
    from .common.LogPatternExtractor import MultiLineAggregator as MultiLineAggregator
    from .common.LogPatternExtractor import RegexMatcher as RegexMatcher
    from .common.LogPatternExtractor import apply_patterns as apply_patterns
    from .common.LogPatternExtractor import compile_log_signs as compile_log_signs
    from .common.LogPatternExtractor import compile_regex as compile_regex
    from .common.LogPatternExtractor import debug_pattern as debug_pattern
    from .common.LogPatternExtractor import flush_patterns as flush_patterns
    from .common.LogPatternExtractor import load_patterns as load_patterns
    from .common.mirrorchyan import MirrorChyanError as MirrorChyanError
    from .common.mirrorchyan import (
        compare_mirrorchyan_versions as compare_mirrorchyan_versions,
    )
    from .common.paths import resource_path as resource_path
    from .common.process import ProcessInfo as ProcessInfo
    from .common.process import ProcessManager as ProcessManager
    from .common.process import ProcessResult as ProcessResult
    from .common.process import ProcessRunner as ProcessRunner
    from .common.process import is_process_alive as is_process_alive
    from .common.process import is_process_running as is_process_running
    from .common.security import dpapi_decrypt as dpapi_decrypt
    from .common.security import dpapi_encrypt as dpapi_encrypt
    from .common.security import format_exception_reason as format_exception_reason
    from .common.security import looks_like_dpapi_blob as looks_like_dpapi_blob
    from .common.security import sanitize_log_message as sanitize_log_message
    from .common.supervision import is_supervised as is_supervised
    from .common.supervision import should_preserve_backend as should_preserve_backend
    from .common.tools import busy_wait as busy_wait
    from .common.tools import decode_bytes as decode_bytes
    from .common.websocket import WebSocketClient as WebSocketClient

    if sys.platform == "win32":
        from .windows import audio as audio
        from .windows import display as display
        from .windows import emulator_native as emulator_native
        from .windows import host as host
        from .windows import notification as notification
        from .windows import process as process_platform
        from .windows import registry as registry
        from .windows import secret as secret
        from .windows import update_native as update_native
        from .windows import vdd as vdd
        from .windows import window as window
        from .windows.host import IS_ELEVATED as IS_ELEVATED
        from .windows.host import IS_WINDOWS as IS_WINDOWS
        from .windows.host import is_admin as is_admin
        from .windows.host import is_long_path_supported as is_long_path_supported
    else:
        from .common import audio as audio
        from .common import display as display
        from .common import emulator_native as emulator_native
        from .common import host as host
        from .common import notification as notification
        from .common import process_platform as process_platform
        from .common import registry as registry
        from .common import secret as secret
        from .common import update_native as update_native
        from .common import vdd as vdd
        from .common import window as window
        from .common.host import IS_ELEVATED as IS_ELEVATED
        from .common.host import IS_WINDOWS as IS_WINDOWS
        from .common.host import is_admin as is_admin
        from .common.host import is_long_path_supported as is_long_path_supported

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


__all__ = [
    "SIGN_MODE_REGEX",
    "SIGN_MODE_SPLIT",
    "get_game_day_tz",
    "game_now",
    "normalize_base_source",
    "LOG_TYPE_ERROR",
    "LOG_TYPE_NORMAL",
    "UnsupportedPlatformError",
    "LogMonitor",
    "strptime",
    "ProcessManager",
    "ProcessRunner",
    "ProcessInfo",
    "ProcessResult",
    "is_process_running",
    "is_process_alive",
    "RegexMatcher",
    "MultiLineAggregator",
    "compile_regex",
    "load_patterns",
    "apply_patterns",
    "flush_patterns",
    "debug_pattern",
    "LogSignMatcher",
    "compile_log_signs",
    "MumuManager",
    "LDManager",
    "search_all_emulators",
    "EMULATOR_TYPE_BOOK",
    "decode_bytes",
    "busy_wait",
    "WebSocketClient",
    "MirrorChyanError",
    "compare_mirrorchyan_versions",
    "IS_WINDOWS",
    "IS_ELEVATED",
    "is_admin",
    "is_long_path_supported",
    "get_logger",
    "resource_path",
    "is_supervised",
    "should_preserve_backend",
    "dpapi_encrypt",
    "dpapi_decrypt",
    "looks_like_dpapi_blob",
    "format_exception_reason",
    "sanitize_log_message",
    "UTC4",
    "UTC8",
    "TYPE_BOOK",
    "PLAN_CONSUMER_VALUES",
    "MSS_TRIBULATION_STAGES",
    "MSS_DEFAULT_TRIBULATION_STAGE",
    "MAAEND_RUN_MOOD_BOOK",
    "MAAEND_DELIVERY_TASK",
    "MAAEND_AUTO_COLLECT_TASK",
    "MAAEND_DELIVERY_COMMISSION_SOURCES",
    "MAAEND_AUTO_COLLECT_MODES",
    "MAA_STAGE_KEY",
    "ARKNIGHTS_GAME_DAY_TZ",
    "MAAEND_SANITY_TASK_LABELS",
    "MAAEND_SANITY_TASK_DETAIL_LABELS",
    "MAAEND_SANITY_TASK_TYPES",
    "MAAEND_AUTO_ESSENCE_MENUS",
    "MAAEND_PROTOCOL_SPACE_TASK_OPTIONS",
    "MAAEND_STAGE_WITH_AB",
    "MAAEND_TASK_GROUPS",
    "MAAEND_TASKS",
    "MAAEND_SANITY_TASK_DEFAULTS",
    "MAAEND_INVENTORY_TARGET_DEFAULTS",
    "MAAEND_SANITY_TASK_FIELDS",
    "ENDFIELD_SERVER_PRESETS",
    "EMULATOR_PATH_BOOK",
    "RESOURCE_STAGE_INFO",
    "MATERIALS_MAP",
    "STARRAIL_PACKAGE_NAME",
    "STARRAIL_CN_UPDATE_LINK_URL",
    "STARRAIL_UPDATE_LINK_SERVER",
    "STARRAIL_STAGE_BOOK",
    "TIME_FIELDS",
    "RESERVED_NAMES",
    "ILLEGAL_CHARS",
    "KEYBOARD_KEYS",
    "MIRROR_ERROR_INFO",
    "DEFAULT_DATETIME",
    "SKLAND_SM_CONFIG",
    "BROWSER_ENV",
    "DES_RULE",
    "ANSI_ESCAPE_RE",
    "TASK_MODE_ZH",
    "APPDATA_PATH",
    "FORBIDDEN_PATH_PREFIXES",
    "FORBIDDEN_PATH_EXACT",
    "EMULATOR_SPLASH_ADS_PATH_BOOK",
    "CYCLE_DATETIME_FORMAT",
    "CYCLE_EMPTY_TIME",
    "BASE_SHARED",
    "BASE_INDEPENDENT",
    "BASE_NATIVE",
    "LEGACY_BASE_SOURCES",
    "BASE_SOURCE_LABELS",
    "update_native",
    "emulator_native",
    "registry",
    "audio",
    "update_files",
    "exception",
    "config_restore",
    "window",
    "paths",
    "mirrorchyan",
    "host",
    "hpatchz",
    "tools",
    "security",
    "constants",
    "io",
    "game_apk",
    "notification_render",
    "process_runner",
    "config_archive",
    "logger",
    "display",
    "fluxdown_cli",
    "supervision",
    "community",
    "secret",
    "config_document",
    "environment",
    "notification_template",
    "process",
    "errors",
    "process_platform",
    "LogPatternExtractor",
    "game_update",
    "vdd",
    "websocket",
    "emulator",
    "emulator2",
    "OCR",
    "i18n",
    "expression",
    "notification",
    "LazyProxy",
]
