#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

from .context import PluginContext, PluginConfigProxy, RuntimeFacade, PluginEventFacade, ServiceFacade
from .cache_store import PluginCacheManager, JsonPluginCache
from .config_store import PluginConfigStore
from .event_bus import EventBus
from .event_contract import (
    EVENT_CONTRACT_VERSION,
    EVENT_DISPATCH_MODEL,
    CORE_SOURCE_PREFIX,
    PluginEventNames,
    SCRIPT_LIFECYCLE_EVENTS,
    EventScope,
    EventErrorPolicy,
    is_script_event,
    is_valid_source,
)
from .decorators import on_event, EventSubscription
from .event_factory import PluginEventFactory
from .fields import PluginField
from .lifecycle_hooks import (
    LifecycleHookSpec,
    LifecycleHookRegistry,
    PluginDefinitionError,
    LIFECYCLE_HOOK_ATTR,
    get_lifecycle_hooks,
    inject_check,
    inject_before_prepare,
    inject_prepare,
    inject_main_task,
    inject_final_task,
    inject_on_crash,
    replace_check,
    replace_prepare,
    replace_main_task,
    replace_final_task,
    replace_on_crash,
)
from .log_pipeline import (
    LogContext,
    LogPipeline,
    LogMonitorAdapter,
    LogHandlerSpec,
    LogFacade,
    LOG_HANDLER_ATTR,
    on_log_line,
    get_log_handlers,
)
from .loader import PluginLoader, PluginRecord
from .manager import PluginManager
from .pypi_site import (
    ENTRY_POINT_GROUPS,
    ensure_pypi_site_packages_on_syspath,
    get_pypi_root,
    get_pypi_site_packages_dir,
    iter_plugin_entry_points,
)
from .runtime_api import RuntimeAPI
from .script_base import (
    TaskContext,
    PluginScriptManager,
    PluginAutoProxyTask,
    PluginManualReviewTask,
    PluginScriptConfigTask,
    register_script_type,
)
from .service_registry import ServiceRegistry
from .service_spec import ServiceSpec
from .server import (
    PluginHttpRequest,
    PluginHttpResponse,
    PluginServerFacade,
    PluginServerRegistry,
    PluginWebSocketSession,
    plugin_server,
)
from .lifecycle import (
    PluginLifecycle,
    REQUIRED_LIFECYCLE_METHODS,
    OPTIONAL_LIFECYCLE_METHODS,
)

__all__ = [
    "PluginContext",
    "PluginConfigProxy",
    "PluginEventFacade",
    "RuntimeFacade",
    "ServiceFacade",
    "PluginCacheManager",
    "JsonPluginCache",
    "PluginConfigStore",
    "EventBus",
    "EVENT_CONTRACT_VERSION",
    "EVENT_DISPATCH_MODEL",
    "CORE_SOURCE_PREFIX",
    "PluginEventNames",
    "SCRIPT_LIFECYCLE_EVENTS",
    "EventScope",
    "EventErrorPolicy",
    "is_script_event",
    "is_valid_source",
    "on_event",
    "EventSubscription",
    "PluginEventFactory",
    "PluginField",
    "LifecycleHookSpec",
    "LifecycleHookRegistry",
    "PluginDefinitionError",
    "LIFECYCLE_HOOK_ATTR",
    "get_lifecycle_hooks",
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
    "LogContext",
    "LogPipeline",
    "LogMonitorAdapter",
    "LogHandlerSpec",
    "LogFacade",
    "LOG_HANDLER_ATTR",
    "on_log_line",
    "get_log_handlers",
    "PluginLoader",
    "PluginRecord",
    "RuntimeAPI",
    "TaskContext",
    "PluginScriptManager",
    "PluginAutoProxyTask",
    "PluginManualReviewTask",
    "PluginScriptConfigTask",
    "register_script_type",
    "ServiceRegistry",
    "ServiceSpec",
    "PluginHttpRequest",
    "PluginHttpResponse",
    "PluginServerFacade",
    "PluginServerRegistry",
    "PluginWebSocketSession",
    "plugin_server",
    "PluginLifecycle",
    "REQUIRED_LIFECYCLE_METHODS",
    "OPTIONAL_LIFECYCLE_METHODS",
    "PluginManager",
    "ENTRY_POINT_GROUPS",
    "get_pypi_root",
    "get_pypi_site_packages_dir",
    "ensure_pypi_site_packages_on_syspath",
    "iter_plugin_entry_points",
]
