"""AUTO-MAS 配置框架 v2（统一 Node 抽象、Wire 文档、冷/热态、blinker 信号）。

设计规格见仓库根 ``配置基类.md``。
"""

from __future__ import annotations

from .collection import CollectionOrderItem, ConfigCollection
from .encrypted import (
    EncryptedMarker,
    EncryptedMigrationOutcome,
    EncryptedValue,
    encrypted,
    is_encrypted_model_field,
)
from .entry import ConfigEntry
from .errors import (
    ConfigAggregateError,
    ConfigError,
    ConfigErrorList,
    DeletedNodeError,
    EncryptedValueError,
)
from .fields import (
    OnDeleteCallback,
    RefDeleteAction,
    RefField,
    Trigger,
    Virtual,
)
from .group import ConfigGroup
from .manager import ConfigManager, RootRecord, TransactionContext, config_manager
from .node import ConfigNode
from .node_state import NodeState
from .shortcuts import collection, ref, trigger_field, virtual_field
from .signals import (
    AfterCommitObserverReport,
    CollectionChangeEvent,
    FieldChangeEvent,
    ObserverCallbackResult,
)
from .staging import StageKind, StagedOp
from .support.constants import DEFAULT_FILE_PATH
from .types import (
    DayCount,
    FilePath,
    HHMMString,
    JsonDictString,
    JsonListString,
    KeyboardKeyString,
    NonNegativeInt,
    PositiveInt,
    UrlString,
    YmdHmsString,
    YmdHmString,
    YmdString,
)
from .wire import ExportContext, read_wire_toml, serialize_wire_toml, write_wire_toml

__all__ = [
    # 核心
    "ConfigNode",
    "NodeState",
    "ConfigEntry",
    "ConfigCollection",
    "ConfigGroup",
    "ConfigManager",
    "config_manager",
    "CollectionOrderItem",
    "TransactionContext",
    "RootRecord",
    # 字段
    "Virtual",
    "Trigger",
    "RefField",
    "RefDeleteAction",
    "OnDeleteCallback",
    # 加密
    "EncryptedValue",
    "EncryptedMarker",
    "EncryptedMigrationOutcome",
    "encrypted",
    "is_encrypted_model_field",
    # 信号
    "FieldChangeEvent",
    "CollectionChangeEvent",
    "ObserverCallbackResult",
    "AfterCommitObserverReport",
    "StageKind",
    "StagedOp",
    # 装饰器 / 工厂
    "ref",
    "collection",
    "virtual_field",
    "trigger_field",
    # Wire
    "ExportContext",
    "read_wire_toml",
    "serialize_wire_toml",
    "write_wire_toml",
    # 内置类型
    "DayCount",
    "FilePath",
    "DEFAULT_FILE_PATH",
    "HHMMString",
    "JsonDictString",
    "JsonListString",
    "KeyboardKeyString",
    "NonNegativeInt",
    "PositiveInt",
    "UrlString",
    "YmdHmString",
    "YmdHmsString",
    "YmdString",
    # 异常
    "ConfigError",
    "ConfigAggregateError",
    "DeletedNodeError",
    "EncryptedValueError",
    "ConfigErrorList",
]
