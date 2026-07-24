#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

"""Public plugin-host surface with opt-in imports.

Historically this package re-exported every plugin subsystem eagerly.  That
made a harmless ``import app.plugins`` instantiate script-adapter and legacy
configuration dependencies before the runtime had selected Config v2.  Keep
the public names and import semantics intact, but resolve each named export
only when a caller explicitly asks for it.

The mapping deliberately points at the existing grouping modules (``event``,
``log`` and ``script``) rather than bypassing them to their leaves.  That
preserves each public symbol's previous import closure; it only removes the
unrequested closures from package initialization.
"""

from importlib import import_module


_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    # 核心上下文
    "PluginContext": ("context", "PluginContext"),
    "PluginConfigProxy": ("context", "PluginConfigProxy"),
    "PluginEventFacade": ("context", "PluginEventFacade"),
    "RuntimeFacade": ("context", "RuntimeFacade"),
    "ServiceFacade": ("context", "ServiceFacade"),
    "PluginCacheManager": ("cache_store", "PluginCacheManager"),
    "JsonPluginCache": ("cache_store", "JsonPluginCache"),
    "PluginConfigStore": ("config_store", "PluginConfigStore"),
    "PluginField": ("fields", "PluginField"),
    "RuntimeAPI": ("runtime_api", "RuntimeAPI"),
    # 生命周期
    "PluginLifecycle": ("lifecycle", "PluginLifecycle"),
    "REQUIRED_LIFECYCLE_METHODS": ("lifecycle", "REQUIRED_LIFECYCLE_METHODS"),
    "OPTIONAL_LIFECYCLE_METHODS": ("lifecycle", "OPTIONAL_LIFECYCLE_METHODS"),
    "LifecycleHookSpec": ("lifecycle_hooks", "LifecycleHookSpec"),
    "LifecycleHookRegistry": ("lifecycle_hooks", "LifecycleHookRegistry"),
    "PluginDefinitionError": ("lifecycle_hooks", "PluginDefinitionError"),
    "LIFECYCLE_HOOK_ATTR": ("lifecycle_hooks", "LIFECYCLE_HOOK_ATTR"),
    "get_lifecycle_hooks": ("lifecycle_hooks", "get_lifecycle_hooks"),
    "hook": ("lifecycle_hooks", "hook"),
    "inject_check": ("lifecycle_hooks", "inject_check"),
    "inject_before_prepare": ("lifecycle_hooks", "inject_before_prepare"),
    "inject_prepare": ("lifecycle_hooks", "inject_prepare"),
    "inject_main_task": ("lifecycle_hooks", "inject_main_task"),
    "inject_final_task": ("lifecycle_hooks", "inject_final_task"),
    "inject_on_crash": ("lifecycle_hooks", "inject_on_crash"),
    "replace_check": ("lifecycle_hooks", "replace_check"),
    "replace_prepare": ("lifecycle_hooks", "replace_prepare"),
    "replace_main_task": ("lifecycle_hooks", "replace_main_task"),
    "replace_final_task": ("lifecycle_hooks", "replace_final_task"),
    "replace_on_crash": ("lifecycle_hooks", "replace_on_crash"),
    # 事件 / 日志 / 脚本分组 API
    "EventBus": ("event", "EventBus"),
    "on_event": ("event", "on_event"),
    "EventSubscription": ("event", "EventSubscription"),
    "PluginEventFactory": ("event", "PluginEventFactory"),
    "EVENT_CONTRACT_VERSION": ("event", "EVENT_CONTRACT_VERSION"),
    "EVENT_DISPATCH_MODEL": ("event", "EVENT_DISPATCH_MODEL"),
    "CORE_SOURCE_PREFIX": ("event", "CORE_SOURCE_PREFIX"),
    "PluginEventNames": ("event", "PluginEventNames"),
    "SCRIPT_LIFECYCLE_EVENTS": ("event", "SCRIPT_LIFECYCLE_EVENTS"),
    "EventScope": ("event", "EventScope"),
    "EventErrorPolicy": ("event", "EventErrorPolicy"),
    "is_script_event": ("event", "is_script_event"),
    "is_valid_source": ("event", "is_valid_source"),
    "LogContext": ("log", "LogContext"),
    "LogPipeline": ("log", "LogPipeline"),
    "LogMonitorAdapter": ("log", "LogMonitorAdapter"),
    "LogHandlerSpec": ("log", "LogHandlerSpec"),
    "LogFacade": ("log", "LogFacade"),
    "LOG_HANDLER_ATTR": ("log", "LOG_HANDLER_ATTR"),
    "on_log": ("log", "on_log"),
    "get_log_handlers": ("log", "get_log_handlers"),
    "TaskContext": ("script", "TaskContext"),
    "PluginScriptManager": ("script", "PluginScriptManager"),
    "PluginAutoProxyTask": ("script", "PluginAutoProxyTask"),
    "PluginManualReviewTask": ("script", "PluginManualReviewTask"),
    "PluginScriptConfigTask": ("script", "PluginScriptConfigTask"),
    "register_script_type": ("script", "register_script_type"),
    "ScriptAdapterRuntime": ("script", "ScriptAdapterRuntime"),
    "ScriptAdapterHooks": ("script", "ScriptAdapterHooks"),
    "ScriptAdapterDefinition": ("script", "ScriptAdapterDefinition"),
    "BaseAdapterManager": ("script", "BaseAdapterManager"),
    "ScriptAdapterPlugin": ("script", "ScriptAdapterPlugin"),
    "ScriptConfigWorkspace": ("script_adapter", "ScriptConfigWorkspace"),
    "ScriptConfigStore": ("script_config_store", "ScriptConfigStore"),
    # Schema 工具
    "SchemaDecorationContext": ("schema_utils", "SchemaDecorationContext"),
    "SchemaOptionsProviderContext": ("schema_utils", "SchemaOptionsProviderContext"),
    "find_schema_group": ("schema_utils", "find_schema_group"),
    "find_schema_field": ("schema_utils", "find_schema_field"),
    "set_schema_group_label": ("schema_utils", "set_schema_group_label"),
    "set_schema_field_label": ("schema_utils", "set_schema_field_label"),
    "set_schema_field_options": ("schema_utils", "set_schema_field_options"),
    "set_schema_field_state": ("schema_utils", "set_schema_field_state"),
    "append_schema_field": ("schema_utils", "append_schema_field"),
    # 加载 / 管理
    "PluginLoader": ("loader", "PluginLoader"),
    "PluginRecord": ("loader", "PluginRecord"),
    "PluginManager": ("manager", "PluginManager"),
    "ENTRY_POINT_GROUPS": ("pypi_site", "ENTRY_POINT_GROUPS"),
    "get_pypi_root": ("pypi_site", "get_pypi_root"),
    "get_pypi_site_packages_dir": ("pypi_site", "get_pypi_site_packages_dir"),
    "ensure_pypi_site_packages_on_syspath": (
        "pypi_site",
        "ensure_pypi_site_packages_on_syspath",
    ),
    "iter_plugin_entry_points": ("pypi_site", "iter_plugin_entry_points"),
    # 服务
    "ServiceRegistry": ("service_registry", "ServiceRegistry"),
    "ServiceSpec": ("service_spec", "ServiceSpec"),
    "PluginHttpRequest": ("server", "PluginHttpRequest"),
    "PluginHttpResponse": ("server", "PluginHttpResponse"),
    "PluginServerFacade": ("server", "PluginServerFacade"),
    "PluginServerRegistry": ("server", "PluginServerRegistry"),
    "PluginWebSocketSession": ("server", "PluginWebSocketSession"),
    "plugin_server": ("server", "plugin_server"),
}

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
    "ScriptAdapterRuntime",
    "ScriptAdapterHooks",
    "ScriptAdapterDefinition",
    "BaseAdapterManager",
    "ScriptAdapterPlugin",
    "ScriptConfigWorkspace",
    "ScriptConfigStore",
    # Schema 工具
    "SchemaDecorationContext",
    "SchemaOptionsProviderContext",
    "find_schema_group",
    "find_schema_field",
    "set_schema_group_label",
    "set_schema_field_label",
    "set_schema_field_options",
    "set_schema_field_state",
    "append_schema_field",
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


def __getattr__(name: str) -> object:
    """Resolve a documented public symbol without eager package imports."""

    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError as error:
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        ) from error

    module = import_module(f".{module_name}", __name__)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Expose documented lazy exports to introspection tools."""

    return sorted(set(globals()) | set(__all__))
