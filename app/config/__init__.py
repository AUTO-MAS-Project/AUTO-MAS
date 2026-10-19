"""AUTO-MAS 配置基类（统一 Node 抽象、配置文档、冷/热态、blinker 信号）。

由原 ``config_framework_v2`` 迁入 ``app.config``；设计规格见仓库根 ``配置基类.md``。
"""

from __future__ import annotations

# 配置包统一加载入口：异常 → core（内部先 manager / node / signals）
# → 字段元数据与内置类型 → 快捷声明。直接导入子模块也会先经过此入口。
# 保留依赖顺序，避免自动排序把 signals 提前到 ConfigNode 定义之前。
# isort: off
from .errors import (
    ConfigAggregateError,
    ConfigError,
    ConfigErrorList,
    ConfigRemoveRejected,
    ConfigPersistenceError,
    DeletedNodeError,
)
from .core.manager import (
    ConfigManager,
    PersistenceFailure,
    RootRecord,
    TransactionContext,
    config_manager,
)
from .core.node import ConfigNode, ExportContext, LockTicket, NodeState
from .signals import CollectionChangeEvent, FieldChangeEvent
from .core.collection import CollectionOrderItem, ConfigCollection
from .core.group import ConfigGroup, ConfigTableColumn
from .core.entry import ConfigEntry
from .core.staging import StagedOp, StageKind
from .fields import (
    UI_MASKED_VALUE,
    ComponentHint,
    EncryptedMarker,
    EncryptedValue,
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
from .types import (
    STANDARD_BLOCKED_DIRS,
    SYSTEM_BLOCKED_DIRS,
    CliArgumentListString,
    CliArgumentString,
    ExecutablePath,
    FilePath,
    FolderPath,
    JsonDictString,
    JsonListString,
    KeyboardKeyString,
    LoosePath,
    PathBlockPreset,
    PathKind,
    PathPolicy,
    ScriptRootPath,
    UrlString,
    WindowsNameString,
    path_policy,
    tz,
)
from .shortcuts import collection, ref, trigger_field, ui_visibility, virtual_field
# isort: on

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
    "PersistenceFailure",
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
    "UI_MASKED_VALUE",
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
    "PathKind",
    "PathPolicy",
    "PathBlockPreset",
    "STANDARD_BLOCKED_DIRS",
    "SYSTEM_BLOCKED_DIRS",
    "JsonDictString",
    "JsonListString",
    "KeyboardKeyString",
    "WindowsNameString",
    "CliArgumentString",
    "CliArgumentListString",
    "UrlString",
    "tz",
    "path_policy",
    # 异常
    "ConfigError",
    "ConfigAggregateError",
    "ConfigRemoveRejected",
    "ConfigPersistenceError",
    "DeletedNodeError",
    "ConfigErrorList",
]
