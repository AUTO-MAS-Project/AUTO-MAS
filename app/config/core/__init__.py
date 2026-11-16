"""配置框架运行时核心：Node / Entry / Collection / Manager / Staging。"""

from __future__ import annotations

# 加载顺序在此固定：manager 先建立单例，再加载 node；node 定义完成后
# 导入 signals，最后加载依赖它们的 collection / group / entry。
# 子模块导入可正常排序，本入口的顺序不可调整。
# isort: off
from .manager import (
    ConfigManager,
    PersistenceFailure,
    RootRecord,
    TransactionContext,
    config_manager,
)
from .node import ConfigNode, LockTicket, NodeState
from .collection import ConfigCollection, RemoveGuard
from .group import ConfigGroup, ConfigTableColumn
from .entry import ConfigEntry
from .staging import StagedOp, StageKind
# isort: on

__all__ = [
    "ConfigCollection",
    "ConfigEntry",
    "ConfigGroup",
    "ConfigTableColumn",
    "ConfigManager",
    "ConfigNode",
    "LockTicket",
    "NodeState",
    "RemoveGuard",
    "RootRecord",
    "PersistenceFailure",
    "StageKind",
    "StagedOp",
    "TransactionContext",
    "config_manager",
]
