"""AUTO-MAS 配置基类（统一 Node 抽象、Wire 文档、冷/热态、blinker 信号）。

由原 ``config_framework_v2`` 迁入 ``app.config``；设计规格见仓库根 ``配置基类.md``。
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from app.utils.io import read_toml, write_toml

from .core.collection import ConfigCollection
from .core.entry import ConfigEntry
from .core.group import ConfigGroup
from .core.manager import ConfigManager, RootRecord, TransactionContext, config_manager
from .core.node import ConfigNode, NodeState
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
    Trigger,
    UiHintMarker,
    UiHintsMap,
    Virtual,
    encrypted,
    is_encrypted_model_field,
    legacy,
    select,
    ui,
)
from .shortcuts import collection, ref, trigger_field, virtual_field
from .signals import CollectionChangeEvent, FieldChangeEvent
from .types import (
    CliArgumentListString,
    CliArgumentString,
    EmulatorPath,
    FilePath,
    FolderPath,
    HHMMString,
    JsonDictString,
    JsonListString,
    KeyboardKeyString,
    LoosePath,
    ScriptRootPath,
    UrlString,
    WindowsNameString,
    YmdHmString,
    YmdHmsString,
    YmdString,
)
from .wire import CollectionOrderItem, ExportContext, WireDict, to_tomlable


def read_wire_toml(path: Path) -> WireDict:
    """兼容入口：解析 TOML → Wire dict（委托 ``app.utils.io.read_toml``）。"""
    return read_toml(path)


def write_wire_toml(path: Path, payload: WireDict) -> None:
    """兼容入口：Wire dict → TOML（经 ``to_tomlable`` + ``app.utils.io.write_toml``）。"""
    write_toml(path, cast(WireDict, to_tomlable(payload)))


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
    "Select",
    "ComponentHint",
    "OptionHint",
    "UiHintsMap",
    "UiHintMarker",
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
    # Wire
    "ExportContext",
    "WireDict",
    "to_tomlable",
    "read_wire_toml",
    "write_wire_toml",
    # 内置类型
    "FilePath",
    "FolderPath",
    "ScriptRootPath",
    "EmulatorPath",
    "LoosePath",
    "HHMMString",
    "JsonDictString",
    "JsonListString",
    "KeyboardKeyString",
    "WindowsNameString",
    "CliArgumentString",
    "CliArgumentListString",
    "UrlString",
    "YmdHmString",
    "YmdHmsString",
    "YmdString",
    # 异常
    "ConfigError",
    "ConfigAggregateError",
    "ConfigRemoveRejected",
    "DeletedNodeError",
    "ConfigErrorList",
]
