"""引用字段、虚拟字段、触发器字段等配置元数据定义。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Annotated, Protocol
from uuid import UUID

from pydantic import GetCoreSchemaHandler, ValidationInfo
from pydantic.fields import FieldInfo
from pydantic_core import core_schema

from ..core.node import ConfigNode, NodeState
from .ann import unwrap_ann

if TYPE_CHECKING:
    from ..core.entry import ConfigEntry
    from ..signals import CollectionChangeEvent

# ──────────────────────────── ref 外键 ────────────────────────────


class RefDeleteAction(str, Enum):
    """引用目标被删除时的处理策略。"""

    RESTRICT = "restrict"
    SET_DEFAULT = "set_default"
    CASCADE = "cascade"
    CUSTOM = "custom"


class OnDeleteCallback(Protocol):
    def __call__(
        self, entry: "ConfigEntry", event: "CollectionChangeEvent"
    ) -> object: ...


@dataclass(frozen=True)
class RefField:
    """声明式 UUID 外键引用字段 metadata；同时是 pydantic 字段 validator。

    ``target`` 为 ref 池逻辑名，须经 ``manager.register_collection`` 登记。
    冷态仅 coerce 为 str；热态查表归一为 ``UUID | str``（命中为 ``UUID``，
    无效回落 ``default``）。字段注解须写 ``UUID | str``。
    ``entry_types`` 按 isinstance 限制目标类型，接受子类；空元组表示不限制。
    ``display_field`` 是 UI 选项展示字段的点号路径，例如 ``Info.Name``。
    ``on_delete`` 统一处理目标删除或类型变更后不再兼容导致的引用失效。
    """

    target: str
    default: str = "-"
    allow_values: tuple[str, ...] = ()
    entry_types: tuple[type[ConfigNode], ...] = ()
    display_field: str | None = None
    on_delete: RefDeleteAction = RefDeleteAction.SET_DEFAULT
    on_delete_callback: OnDeleteCallback | str | None = None

    def __post_init__(self) -> None:
        if any(
            not isinstance(entry_type, type) or not issubclass(entry_type, ConfigNode)
            for entry_type in self.entry_types
        ):
            raise TypeError("ref entry_types 须为配置类")
        if self.display_field is not None and (
            not isinstance(self.display_field, str)
            or any(
                not part.isidentifier() or part.startswith("_")
                for part in self.display_field.split(".")
            )
        ):
            raise ValueError("ref display_field 须为公开字段的点号路径")
        if self.on_delete == RefDeleteAction.CUSTOM and self.on_delete_callback is None:
            raise ValueError("on_delete='custom' 时必须提供 on_delete_callback")
        if (
            self.on_delete != RefDeleteAction.CUSTOM
            and self.on_delete_callback is not None
        ):
            raise ValueError("on_delete_callback 仅在 on_delete='custom' 时有效")

    def accepts(self, entry: ConfigNode) -> bool:
        """校验、事件重校验及 UI 选项共用的目标类型判定。"""
        return not self.entry_types or isinstance(entry, self.entry_types)

    def normalize(self, value: object) -> UUID | str:
        """热态归一：无效 ref 回落 default。"""
        from ..core.manager import config_manager

        text = "" if value is None else str(value)
        if text in self.allow_values:
            return text
        try:
            uid = UUID(text)
        except (ValueError, AttributeError):
            return self.default
        col = config_manager.get_collection(self.target)  # 未登记 → LookupError
        entry = col.get(uid)
        if entry is None or not self.accepts(entry):
            return self.default
        return uid

    def __get_pydantic_core_schema__(
        self, source: object, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        inner = handler(source)
        spec = self

        def validate(value: object, info: ValidationInfo) -> UUID | str:
            text = "" if value is None else str(value)
            entry = (info.context or {}).get("entry")
            if entry is None or entry.activation_state == NodeState.INACTIVE:
                return text
            return spec.normalize(text)

        return core_schema.with_info_after_validator_function(validate, inner)


# ──────────────────────────── virtual ────────────────────────────


class VirtualFieldGetter(Protocol):
    def __call__(self, owner: "ConfigEntry") -> object: ...


class VirtualDecl:
    """``Virtual[T]`` 类型桩标记；须与 ``@virtual_field`` 配对。"""


type Virtual[T] = Annotated[T | None, VirtualDecl()]
"""响应式虚拟字段类型桩（允许 ``None`` 默认值；须配 ``@virtual_field``）。

Example::

    class Info(ConfigGroup):
        status: Virtual[str] = None
"""


def is_virtual_model_field(model_field: FieldInfo) -> bool:
    meta = list(getattr(model_field, "metadata", ())) + list(
        unwrap_ann(getattr(model_field, "annotation", None))[1]
    )
    return any(isinstance(m, VirtualDecl) for m in meta)


# ──────────────────────────── trigger ────────────────────────────


class TriggerDecl:
    """``Trigger`` 类型桩标记；须与 ``@trigger_field`` 配对。"""


Trigger = Annotated[bool, TriggerDecl()]
"""响应式触发器类型桩（bool；读恒 ``False``，置 ``True`` 执行一次；须配 ``@trigger_field``）。

Literal 多按钮写法（与 bool **不混用**）::

    action: Annotated[Literal["a", "b"] | None, TriggerDecl()] = None
    # 读/API 闲置为 None；写入字面量触发，handler(value)
"""


def is_trigger_model_field(model_field: FieldInfo) -> bool:
    meta = list(getattr(model_field, "metadata", ())) + list(
        unwrap_ann(getattr(model_field, "annotation", None))[1]
    )
    return any(isinstance(m, TriggerDecl) for m in meta)


def is_reactive_model_field(model_field: FieldInfo) -> bool:
    """响应式字段：虚拟 / 触发器（不参与 activate 热化与默认落盘）。"""
    return is_virtual_model_field(model_field) or is_trigger_model_field(model_field)


# ──────────────────────────── 路径解析与注册绑定 ────────────────────────────


def parse_field_path(path: str) -> tuple[str, str]:
    """解析 ``'<group>.<field>'`` 挂载路径。"""
    parts = path.split(".", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(f"字段挂载路径必须是 '<group>.<field>' 格式: {path!r}")
    return parts[0], parts[1]


@dataclass(frozen=True)
class NestedCollectionMarker:
    """``collection()`` 打在 FieldInfo.metadata 上的标记；Entry 类定义期校验用。"""


@dataclass(frozen=True)
class VirtualFieldBinding:
    group: str
    field_name: str
    getter: str


@dataclass(frozen=True)
class TriggerFieldBinding:
    group: str
    field_name: str
    handler: str
