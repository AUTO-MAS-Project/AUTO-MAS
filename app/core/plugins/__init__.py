#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

from .context import PluginContext, PluginConfigProxy, RuntimeFacade, PluginEventFacade
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
    "PluginLoader",
    "PluginRecord",
    "RuntimeAPI",
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
