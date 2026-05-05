#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

# ── 核心上下文 ──
from .cache_store import JsonPluginCache, PluginCacheManager
from .config_store import PluginConfigStore
from .context import PluginConfigProxy, PluginContext, PluginEventFacade, RuntimeFacade, ServiceFacade
from .fields import PluginField
from .runtime_api import RuntimeAPI

# ── 生命周期 ──
from .lifecycle import OPTIONAL_LIFECYCLE_METHODS, REQUIRED_LIFECYCLE_METHODS, PluginLifecycle
from .lifecycle_hooks import (
    LIFECYCLE_HOOK_ATTR,
    LifecycleHookRegistry,
    LifecycleHookSpec,
    PluginDefinitionError,
    get_lifecycle_hooks,
    hook,
    inject_before_prepare,
    inject_check,
    inject_final_task,
    inject_main_task,
    inject_on_crash,
    inject_prepare,
    replace_check,
    replace_final_task,
    replace_main_task,
    replace_on_crash,
    replace_prepare,
)

# ── 分组 API ──
from .event import *  # noqa: F401,F403
from .log import *  # noqa: F401,F403
from .script import *  # noqa: F401,F403

# ── 加载 / 管理 ──
from .loader import PluginLoader, PluginRecord
from .manager import PluginManager
from .pypi_site import (
    ENTRY_POINT_GROUPS,
    ensure_pypi_site_packages_on_syspath,
    get_pypi_root,
    get_pypi_site_packages_dir,
    iter_plugin_entry_points,
)

# ── 服务 ──
from .server import (
    PluginHttpRequest,
    PluginHttpResponse,
    PluginServerFacade,
    PluginServerRegistry,
    PluginWebSocketSession,
    plugin_server,
)
from .service_registry import ServiceRegistry
from .service_spec import ServiceSpec

__all__ = [
    # 核心上下文
    "PluginContext",
    "PluginConfigProxy",
    "PluginEventFacade",
    "RuntimeFacade",
    "ServiceFacade",
    "PluginCacheManager",
    "JsonPluginCache",
    "PluginConfigStore",
    "PluginField",
    "RuntimeAPI",
    # 生命周期
    "PluginLifecycle",
    "REQUIRED_LIFECYCLE_METHODS",
    "OPTIONAL_LIFECYCLE_METHODS",
    "LifecycleHookSpec",
    "LifecycleHookRegistry",
    "PluginDefinitionError",
    "LIFECYCLE_HOOK_ATTR",
    "get_lifecycle_hooks",
    "hook",
    "inject_check",
    "inject_before_prepare",
    "inject_prepare",
    "inject_main_task",
    "inject_final_task",
    "inject_on_crash",
    "replace_check",
    "replace_prepare",
    "replace_main_task",
    "replace_final_task",
    "replace_on_crash",
    # 事件 (from .event)
    "EventBus",
    "on_event",
    "EventSubscription",
    "PluginEventFactory",
    "EVENT_CONTRACT_VERSION",
    "EVENT_DISPATCH_MODEL",
    "CORE_SOURCE_PREFIX",
    "PluginEventNames",
    "SCRIPT_LIFECYCLE_EVENTS",
    "EventScope",
    "EventErrorPolicy",
    "is_script_event",
    "is_valid_source",
    # 日志 (from .log)
    "LogContext",
    "LogPipeline",
    "LogMonitorAdapter",
    "LogHandlerSpec",
    "LogFacade",
    "LOG_HANDLER_ATTR",
    "on_log",
    "get_log_handlers",
    # 脚本 (from .script)
    "TaskContext",
    "PluginScriptManager",
    "PluginAutoProxyTask",
    "PluginManualReviewTask",
    "PluginScriptConfigTask",
    "register_script_type",
    # 加载 / 管理
    "PluginLoader",
    "PluginRecord",
    "PluginManager",
    "ENTRY_POINT_GROUPS",
    "get_pypi_root",
    "get_pypi_site_packages_dir",
    "ensure_pypi_site_packages_on_syspath",
    "iter_plugin_entry_points",
    # 服务
    "ServiceRegistry",
    "ServiceSpec",
    "PluginHttpRequest",
    "PluginHttpResponse",
    "PluginServerFacade",
    "PluginServerRegistry",
    "PluginWebSocketSession",
    "plugin_server",
]
