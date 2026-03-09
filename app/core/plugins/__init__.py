#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

from .context import PluginContext
from .event_bus import EventBus
from .loader import PluginLoader, PluginRecord
from .manager import PluginManager

__all__ = [
    "PluginContext",
    "EventBus",
    "PluginLoader",
    "PluginRecord",
    "PluginManager",
]
