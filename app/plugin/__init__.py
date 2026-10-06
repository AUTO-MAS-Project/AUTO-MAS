"""AUTO-MAS 插件实现基础（``app.plugin``）。

提供基类、异常、发现/uv/级联/市场等积木；全局 i18n 服务位于 ``app.core.i18n``，插件单例位于 ``app.core.plugin_manager.Plugin``。
其它业务模块不要依赖本包内部编排，只依赖 core 入口（测试与 ``auto_mas_core`` 再导出除外）。
"""

from __future__ import annotations

from .base import (
    BasePlugin,
    ExtensionPlugin,
    GameAdapterPlugin,
    GameControl,
    GameTypeDecl,
    ScriptAdapterPlugin,
    ScriptTypeDecl,
)
from .errors import (
    CascadeResult,
    DisableCheckFailure,
    PluginOpResult,
    PlanDiff,
    PluginBusyError,
    PluginError,
    PluginNotFoundError,
    PluginOperationError,
    PluginPrecheckError,
    PluginStateError,
    PrecheckOk,
    VersionConflict,
)
from .http import plugin_route
from .types import (
    CORE_PLUGIN_NAME,
    MARKET_GATE_TAG,
    PLUGIN_ATTR,
    PLUGIN_API_VERSION,
    LifecycleContext,
    PluginState,
)

__all__ = [
    "BasePlugin",
    "CascadeResult",
    "CORE_PLUGIN_NAME",
    "DisableCheckFailure",
    "ExtensionPlugin",
    "GameAdapterPlugin",
    "GameControl",
    "GameTypeDecl",
    "LifecycleContext",
    "MARKET_GATE_TAG",
    "PLUGIN_ATTR",
    "PLUGIN_API_VERSION",
    "PluginOpResult",
    "PlanDiff",
    "PluginBusyError",
    "PluginError",
    "PluginNotFoundError",
    "PluginOperationError",
    "PluginPrecheckError",
    "PluginState",
    "PluginStateError",
    "PrecheckOk",
    "ScriptAdapterPlugin",
    "ScriptTypeDecl",
    "VersionConflict",
    "plugin_route",
]
