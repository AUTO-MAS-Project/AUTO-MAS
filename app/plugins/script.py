"""脚本类型系统公共 API — 分组 re-export 模块。"""

from .script_base import (
    PluginAutoProxyTask,
    PluginManualReviewTask,
    PluginScriptConfigTask,
    PluginScriptManager,
    TaskContext,
    register_script_type,
)
from .script_adapter import (
    BaseAdapterManager,
    ScriptAdapterDefinition,
    ScriptAdapterHooks,
    ScriptAdapterPlugin,
    ScriptAdapterRuntime,
)

__all__ = [
    "TaskContext",
    "PluginScriptManager",
    "PluginAutoProxyTask",
    "PluginManualReviewTask",
    "PluginScriptConfigTask",
    "register_script_type",
    "ScriptAdapterRuntime",
    "ScriptAdapterHooks",
    "ScriptAdapterDefinition",
    "BaseAdapterManager",
    "ScriptAdapterPlugin",
]
