"""Wire 文档形状：JSON / TOML / ``model_dump`` 同一逻辑结构。

- Collection Wire：``{ "order": [{uid, type}, …], "data": { "<uuid>": <EntryWire>, … } }``
- Entry Wire：各 Group 字段名顶层嵌套 dict

落盘 IO 走 ``app.utils.io``；本模块统一文档类型、接口契约派生与 TOML 可写归一。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    ClassVar,
    Literal,
    TypeVar,
    Union,
    cast,
)
from uuid import UUID

from annotated_types import BaseMetadata
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    create_model,
    model_serializer,
    model_validator,
)
from pydantic._internal._forward_ref import PydanticRecursiveRef

from .fields import is_trigger_model_field, is_virtual_model_field, unwrap_ann
from .fields.hints import (
    UI_MASKED_VALUE,
    UiVisibility,
    migrate_legacy_fields,
    omit_masked_placeholders,
    visibility_spec_for_field,
)
from .types import PathPolicy

if TYPE_CHECKING:
    from .core.entry import ConfigEntry


class ConfigPayload[T: BaseModel](BaseModel):
    """配置接口投影的类型入口；运行时仍复用缓存的纯契约模型。

    与原生配置类型分开标注，避免把路径等内存类型误当作接口类型。
    泛型参数只指定字段来源，不复制字段声明，也不激活配置。
    """

    _contract_mode: ClassVar[Literal["input", "output"]] = "output"
    _contract_extra: ClassVar[Literal["ignore", "forbid"]] = "ignore"

    @classmethod
    def __class_getitem__(
        cls, typevar_values: Any
    ) -> type[BaseModel] | PydanticRecursiveRef:
        if isinstance(typevar_values, TypeVar):
            # Pydantic 支持 TypeVar 实参，但其签名只声明了具体类型。
            specialize = cast(
                Callable[[TypeVar], type[BaseModel] | PydanticRecursiveRef],
                super().__class_getitem__,
            )
            return specialize(typevar_values)
        entry = (
            typevar_values[0] if isinstance(typevar_values, tuple) else typevar_values
        )
        return config_contract(
            entry, mode=cls._contract_mode, extra=cls._contract_extra
        )


class ConfigInput[T: BaseModel](ConfigPayload[T]):
    """保留未提供字段的配置更新投影。"""

    _contract_mode = "input"


class StrictConfigInput[T: BaseModel](ConfigInput[T]):
    """拒绝未知字段的配置更新投影。"""

    _contract_extra = "forbid"


type WireScalar = str | int | float | bool
"""Wire 叶子标量。"""

type WireValue = WireScalar | None | dict[str, Any] | list[Any]
"""Wire 单值；嵌套 dict/list 用 ``Any``，便于 ``to_dict`` 多层下标。"""

type WireDict = dict[str, Any]
"""Wire 顶层或 Entry 级 dict。"""


@dataclass
class ExportContext:
    """``_export_wire`` 导出上下文：控制解密与是否携带响应式字段。"""

    if_decrypt: bool = False
    """False → 密文；True → 明文。"""

    include_reactive: bool = False
    """是否携带响应式字段（virtual / trigger）。"""


class CollectionOrderItem(BaseModel):
    """Collection 索引项：``{ uid, type }``。"""

    uid: UUID
    type: str  # Entry 子类名，如 "ExampleQueue"


@lru_cache(maxsize=None)
def config_group_contract(
    group_type: type[BaseModel],
    *,
    name: str,
    mode: Literal["input", "output"] = "output",
    extra: Literal["ignore", "forbid"] = "ignore",
    entry_type: type[ConfigEntry] | None = None,
    group: str | None = None,
) -> type[BaseModel]:
    """从分组字段派生无运行时状态的接口模型，不执行配置激活或字段校正。"""
    fields = {}
    for key, field in group_type.model_fields.items():
        if is_trigger_model_field(field):
            continue
        visibility = (
            entry_type._cfg_ui_visibility.get((group, key))
            if entry_type is not None and group is not None
            else visibility_spec_for_field(field)
        )
        if visibility == UiVisibility.HIDE or (
            mode == "input" and visibility == UiVisibility.DISABLE
        ):
            continue
        annotation, _metadata = unwrap_ann(field.annotation)
        if any(isinstance(m, PathPolicy) for m in (*_metadata, *field.metadata)):
            annotation = str
        constraints = tuple(m for m in field.metadata if isinstance(m, BaseMetadata))
        if constraints:
            annotation = Annotated[annotation, *constraints]
        if annotation is list:
            annotation = list[JsonValue]
        elif annotation is dict:
            annotation = dict[str, JsonValue]
        readonly = is_virtual_model_field(field) or visibility == UiVisibility.DISABLE
        schema_extra: dict[str, Any] = {"readOnly": True} if readonly else {}
        if mode == "output":
            if visibility == UiVisibility.MASKED:
                annotation = Literal[UI_MASKED_VALUE]
            elif callable(visibility):
                annotation = Union[annotation, Literal[UI_MASKED_VALUE]]
        fields[key] = (
            Union[annotation, None],
            Field(
                default=None,
                description=field.description,
                discriminator=field.discriminator,
                json_schema_extra=schema_extra or None,
            ),
        )

    def serialize_present(self, handler):
        values = handler(self)
        if mode == "output":
            return {
                key: value
                for key, value in values.items()
                if key in self.model_fields_set
            }
        return values

    return create_model(
        name,
        __config__=ConfigDict(extra=extra),
        __module__=__name__,
        __validators__={
            "serialize_present": model_serializer(mode="wrap")(serialize_present)
        },
        **fields,
    )


def config_contract(
    entry_type: type[ConfigEntry],
    *,
    mode: Literal["input", "output"] = "output",
    include_collections: bool = False,
    extra: Literal["ignore", "forbid"] = "ignore",
) -> type[BaseModel]:
    """按同一份配置声明派生接口契约，显式归一默认参数后命中同一缓存。"""
    return _config_contract(
        entry_type, mode=mode, include_collections=include_collections, extra=extra
    )


@lru_cache(maxsize=None)
def _config_contract(
    entry_type: type[ConfigEntry],
    *,
    mode: Literal["input", "output"],
    include_collections: bool,
    extra: Literal["ignore", "forbid"],
) -> type[BaseModel]:
    suffix = "Input" if mode == "input" else ""
    name = entry_type.__name__ + ("Document" if include_collections else "") + suffix
    fields = {}
    for group in entry_type._cfg_group_fields:
        if group == "ui":
            continue
        field = entry_type.model_fields[group]
        visibility = visibility_spec_for_field(field)
        if visibility == UiVisibility.HIDE or (
            mode == "input" and visibility == UiVisibility.DISABLE
        ):
            continue
        group_type = field.annotation
        contract = config_group_contract(
            group_type,
            name=f"{entry_type.__name__}_{group}{suffix}",
            mode=mode,
            extra=extra,
            entry_type=entry_type,
            group=group,
        )
        if not contract.model_fields:
            continue
        fields[group] = (
            Union[contract, None],
            Field(
                default=None,
                description=field.description,
                json_schema_extra={"readOnly": True}
                if visibility == UiVisibility.DISABLE
                else None,
            ),
        )
    if include_collections and mode == "output":
        for key in entry_type._cfg_collection_fields:
            collection = entry_type.model_fields[key].get_default(
                call_default_factory=True
            )
            members: list[type[BaseModel]] = [
                config_contract(t, include_collections=True)
                for t in collection._entry_types.values()
            ]
            if not members:
                raise TypeError(f"配置集合未登记成员类型：{entry_type.__name__}.{key}")
            item_type = Union[tuple(members)] if len(members) > 1 else members[0]
            document = create_model(
                f"{entry_type.__name__}_{key}Collection",
                order=(list[CollectionOrderItem], Field(default_factory=list)),
                data=(dict[str, item_type], Field(default_factory=dict)),
                __module__=__name__,
            )
            fields[key] = (document, Field(default_factory=document))

    def prepare_input(value):
        if mode == "input":
            return omit_masked_placeholders(
                entry_type, migrate_legacy_fields(entry_type, value)
            )
        return value

    def serialize_present(self, handler):
        values = handler(self)
        if mode == "output":
            return {
                key: value
                for key, value in values.items()
                if key in self.model_fields_set
            }
        return values

    validators: dict[str, Any] = {
        "prepare_input": model_validator(mode="before")(prepare_input),
        "serialize_present": model_serializer(mode="wrap")(serialize_present),
    }
    return create_model(
        name,
        __config__=ConfigDict(extra=extra),
        __module__=__name__,
        __validators__=validators,
        **fields,
    )


def to_tomlable(value: object) -> object:
    """将 Wire 值归一为 TOML 可写形态（去 None、UUID/Path → str）。"""
    if isinstance(value, dict):
        out: dict[str, object] = {}
        for k, v in value.items():
            if v is None:
                continue
            key = str(k) if isinstance(k, UUID) else k
            out[str(key)] = to_tomlable(v)
        return out
    if isinstance(value, list):
        return [to_tomlable(v) for v in value if v is not None]
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    return value
