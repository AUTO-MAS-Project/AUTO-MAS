#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

from .context import PluginContext
from .cache_store import PluginCacheManager, JsonPluginCache
from .config_store import PluginConfigStore
from .event_bus import EventBus
from .event_contract import (
    EVENT_CONTRACT_VERSION,
    CORE_SOURCE_PREFIX,
    PluginEventNames,
    SCRIPT_LIFECYCLE_EVENTS,
    is_script_event,
    is_valid_source,
)
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

__all__ = [
    "PluginContext",
    "PluginCacheManager",
    "JsonPluginCache",
    "PluginConfigStore",
    "EventBus",
    "EVENT_CONTRACT_VERSION",
    "CORE_SOURCE_PREFIX",
    "PluginEventNames",
    "SCRIPT_LIFECYCLE_EVENTS",
    "is_script_event",
    "is_valid_source",
    "PluginEventFactory",
    "PluginLoader",
    "PluginRecord",
    "RuntimeAPI",
    "PluginManager",
    "ENTRY_POINT_GROUPS",
    "get_pypi_root",
    "get_pypi_site_packages_dir",
    "ensure_pypi_site_packages_on_syspath",
    "iter_plugin_entry_points",
]
