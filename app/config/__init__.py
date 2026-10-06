"""AUTO-MAS 配置基类（统一 Node 抽象、配置文档、冷/热态、blinker 信号）。

由原 ``config_framework_v2`` 迁入 ``app.config``；设计规格见仓库根 ``配置基类.md``。
"""

from __future__ import annotations

from .core.collection import CollectionOrderItem, ConfigCollection
from .core.entry import ConfigEntry
from .core.group import ConfigGroup, ConfigTableColumn
from .core.manager import ConfigManager, RootRecord, TransactionContext, config_manager
from .core.node import ConfigNode, ExportContext, LockTicket, NodeState
from .core.staging import StageKind, StagedOp
from .errors import (
    ConfigAggregateError,
    ConfigError,
    ConfigErrorList,
    ConfigRemoveRejected,
    DeletedNodeError,
)
from .fields import (
    EncryptedMarker,
    EncryptedValue,
    ComponentHint,
    LegacyMarker,
    OnDeleteCallback,
    OptionHint,
    RefDeleteAction,
    RefField,
    Select,
    TableHint,
    Trigger,
    TriggerDecl,
    UiHintMarker,
    UiHintsMap,
    UiTablesList,
    UiVisibility,
    Virtual,
    encrypted,
    is_encrypted_model_field,
    legacy,
    select,
    ui,
)
from .shortcuts import collection, ref, trigger_field, ui_visibility, virtual_field
from .signals import CollectionChangeEvent, FieldChangeEvent
from .types import (
    CliArgumentListString,
    CliArgumentString,
    ExecutablePath,
    FilePath,
    FolderPath,
    JsonDictString,
    JsonListString,
    KeyboardKeyString,
    LoosePath,
    ScriptRootPath,
    UrlString,
    WindowsNameString,
    tz,
)

__all__ = [
    # 核心
    "ConfigNode",
    "LockTicket",
    "NodeState",
    "ConfigEntry",
    "ConfigCollection",
    "ConfigGroup",
    "ConfigTableColumn",
    "ConfigManager",
    "config_manager",
    "CollectionOrderItem",
    "TransactionContext",
    "RootRecord",
    # 字段
    "Virtual",
    "Trigger",
    "TriggerDecl",
    "RefField",
    "RefDeleteAction",
    "OnDeleteCallback",
    "Select",
    "ComponentHint",
    "OptionHint",
    "TableHint",
    "UiHintsMap",
    "UiTablesList",
    "UiHintMarker",
    "UiVisibility",
    "LegacyMarker",
    "ui",
    "select",
    "legacy",
    # 加密
    "EncryptedValue",
    "EncryptedMarker",
    "encrypted",
    "is_encrypted_model_field",
    # 信号
    "FieldChangeEvent",
    "CollectionChangeEvent",
    "StageKind",
    "StagedOp",
    # 装饰器 / 工厂
    "ref",
    "collection",
    "virtual_field",
    "trigger_field",
    "ui_visibility",
    # 导出
    "ExportContext",
    # 内置类型
    "FilePath",
    "FolderPath",
    "ScriptRootPath",
    "ExecutablePath",
    "LoosePath",
    "JsonDictString",
    "JsonListString",
    "KeyboardKeyString",
    "WindowsNameString",
    "CliArgumentString",
    "CliArgumentListString",
    "UrlString",
    "tz",
    # 异常
    "ConfigError",
    "ConfigAggregateError",
    "ConfigRemoveRejected",
    "DeletedNodeError",
    "ConfigErrorList",
]
