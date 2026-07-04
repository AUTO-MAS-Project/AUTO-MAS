"""事件系统公共 API — 分组 re-export 模块。"""

from .decorators import EventSubscription, on_event
from .event_bus import EventBus
from .event_contract import (
    CORE_SOURCE_PREFIX,
    EVENT_CONTRACT_VERSION,
    EVENT_DISPATCH_MODEL,
    EventErrorPolicy,
    EventScope,
    PluginEventNames,
    SCRIPT_LIFECYCLE_EVENTS,
    is_script_event,
    is_valid_source,
)
from .event_factory import PluginEventFactory

__all__ = [
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
]
