"""插件运行时公共常量与记录类型。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

CORE_PLUGIN_NAME = "auto_mas_core"
CORE_DISTRIBUTION_NAME = "auto_mas_core"
MARKET_GATE_TAG = "auto-mas-plugin"
PLUGIN_ID_TAG_PREFIX = "auto-mas-id:"
# 包顶层 ``__init__.py`` 固定入口符号（取代 entry-points）
PLUGIN_ATTR = "PLUGIN"
PLUGIN_API_VERSION = "6"


class PluginState(str, Enum):
    """插件状态：稳态含未加载 / 干净禁用启用 / 两档故障；另五过渡。"""

    UNLOADED = "unloaded"
    DISABLED = "disabled"
    ENABLED = "enabled"
    FAULT_LOAD = "fault_load"
    FAULT_RUNTIME = "fault_runtime"
    LOADING = "loading"
    ENABLING = "enabling"
    RELOADING = "reloading"
    DISABLING = "disabling"
    UNLOADING = "unloading"


class PluginCodeDrift(str, Enum):
    """插件发现结果与注册表之间的差异状态。"""

    NORMAL = "normal"
    NEEDS_RELOAD = "needs_reload"
    PACKAGE_REMOVED = "package_removed"


class LifecycleContext(str, Enum):
    """写在 PluginRecord 上的生命周期语境（Manager 写入）。"""

    IDLE = ""
    NORMAL = "normal"
    RELOAD = "reload"
    RELOAD_CASCADE = "reload_cascade"
    # 卸载本项内嵌 disable；适配类型表动作与 normal 相同
    UNLOAD = "unload"


@dataclass(frozen=True)
class SourceChange:
    """单个本地插件工程根的变更。"""

    local_dir: str
    code_touched: bool = False


@dataclass(frozen=True)
class SourcesChangedPayload:
    """源码监视防抖后的插件目录变更。"""

    changes: tuple[SourceChange, ...]
