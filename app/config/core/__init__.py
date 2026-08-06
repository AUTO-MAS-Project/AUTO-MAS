"""配置框架运行时核心：Node / Entry / Collection / Manager / Staging。"""

from __future__ import annotations

from .collection import ConfigCollection, RemoveGuard
from .entry import ConfigEntry
from .group import ConfigGroup
from .manager import ConfigManager, RootRecord, TransactionContext, config_manager
from .node import ConfigNode, LockTicket, NodeState
from .staging import StageKind, StagedOp

__all__ = [
    "ConfigCollection",
    "ConfigEntry",
    "ConfigGroup",
    "ConfigManager",
    "ConfigNode",
    "LockTicket",
    "NodeState",
    "RemoveGuard",
    "RootRecord",
    "StageKind",
    "StagedOp",
    "TransactionContext",
    "config_manager",
]
