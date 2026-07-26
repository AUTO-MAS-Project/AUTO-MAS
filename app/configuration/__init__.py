"""AUTO-MAS 原生配置框架 v2。

基于 config_framework_v2 参考实现，提供：
- ConfigNode / ConfigEntry / ConfigCollection / ConfigGroup 统一抽象
- 事务与工作区（COW）
- blinker 信号模型
- Wire 格式（TOML）持久化
- DPAPI 加密字段
- Pydantic 2.11+ 集成

环境变量：
    AUTO_MAS_CONFIG_V2_MODE=off|shadow|canary|authoritative
"""

from __future__ import annotations

import os

# Config v2 模式
CONFIG_V2_MODE_OFF = "off"
CONFIG_V2_MODE_SHADOW = "shadow"
CONFIG_V2_MODE_CANARY = "canary"
CONFIG_V2_MODE_AUTHORITATIVE = "authoritative"

_CONFIG_V2_MODES = (
    CONFIG_V2_MODE_OFF,
    CONFIG_V2_MODE_SHADOW,
    CONFIG_V2_MODE_CANARY,
    CONFIG_V2_MODE_AUTHORITATIVE,
)

CONFIG_V2_MODE: str = os.getenv(
    "AUTO_MAS_CONFIG_V2_MODE",
    CONFIG_V2_MODE_AUTHORITATIVE,
)
if CONFIG_V2_MODE not in _CONFIG_V2_MODES:
    CONFIG_V2_MODE = CONFIG_V2_MODE_AUTHORITATIVE


class ConfigV2AuthoritativeUnavailableError(RuntimeError):
    """Deprecated compatibility error retained for external imports."""


def assert_config_v2_startup_mode_ready(mode: str | None = None) -> None:
    """Validate the selected startup mode.

    All four modes remain available for controlled rollback and diagnostics.
    The default authoritative mode is backed by the eight native production
    roots and no longer needs a feature-readiness exception.
    """

    effective_mode = CONFIG_V2_MODE if mode is None else mode
    if effective_mode not in _CONFIG_V2_MODES:
        raise ValueError(
            f"unsupported Config v2 startup mode: {effective_mode!r}"
        )


# 从 v2 子包导出核心 API
from .v2.collection import ConfigCollection
from .v2.encrypted import (
    EncryptedMarker,
    EncryptedMigrationOutcome,
    EncryptedValue,
    encrypted,
    is_encrypted_model_field,
)
from .v2.entry import ConfigEntry
from .v2.errors import (
    ConfigAggregateError,
    ConfigError,
    ConfigErrorList,
    DeletedNodeError,
    EncryptedValueError,
)
from .v2.fields import (
    RefDeleteAction,
    RefField,
    Trigger,
    Virtual,
)
from .v2.group import ConfigGroup
from .v2.manager import ConfigManager, RootRecord, TransactionContext, config_manager
from .v2.node import ConfigNode
from .v2.node_state import NodeState
from .v2.shortcuts import collection, ref, trigger_field, virtual_field
from .v2.signals import (
    AfterCommitObserverReport,
    CollectionChangeEvent,
    FieldChangeEvent,
    ObserverCallbackResult,
)
from .v2.staging import StageKind, StagedOp
from .v2.wire import (
    CollectionOrderItem,
    ExportContext,
    WireDict,
    read_wire_toml,
    serialize_wire_toml,
    write_wire_toml,
)

__all__ = [
    # 模式
    "CONFIG_V2_MODE",
    "CONFIG_V2_MODE_OFF",
    "CONFIG_V2_MODE_SHADOW",
    "CONFIG_V2_MODE_CANARY",
    "CONFIG_V2_MODE_AUTHORITATIVE",
    "ConfigV2AuthoritativeUnavailableError",
    "assert_config_v2_startup_mode_ready",
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
    "WireDict",
    "read_wire_toml",
    "serialize_wire_toml",
    "write_wire_toml",
    # 异常
    "ConfigError",
    "ConfigAggregateError",
    "DeletedNodeError",
    "EncryptedValueError",
    "ConfigErrorList",
]
