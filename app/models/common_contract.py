from __future__ import annotations

from collections.abc import Iterable, Mapping
from functools import lru_cache
import re
from types import UnionType
from typing import (
    Annotated,
    Any,
    Generic,
    TypeAlias,
    TypeVar,
    Union,
    cast,
    get_args,
    get_origin,
)

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    create_model,
    model_validator,
)

from app.core.config.fields import VirtualField
from app.core.config.pydantic import PydanticConfigBase


ModelT = TypeVar("ModelT", bound=BaseModel)
MapKeyT = TypeVar("MapKeyT")
IndexT = TypeVar("IndexT")
DataT = TypeVar("DataT")
RawModelSource: TypeAlias = Mapping[str, Any] | BaseModel


class ApiModel(BaseModel):
    """API Contract 的统一基线。"""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        populate_by_name=True,
        validate_by_alias=True,
    )

    @staticmethod
    def _to_snake(name: str) -> str:
        normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
        normalized = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", normalized)
        return normalized.replace("-", "_").lower()

    @model_validator(mode="before")
    @classmethod
    def _normalize_input_keys(cls, data: Any) -> Any:
        if not isinstance(data, Mapping):
            return data

        normalized: dict[str, Any] = {}
        field_names = cls.model_fields.keys()
        raw_mapping = cast(Mapping[object, Any], data)
        for raw_key, value in raw_mapping.items():
            key = str(raw_key)
            if key in field_names:
                normalized[key] = value
                continue

            snake_key = cls._to_snake(key)
            if snake_key in field_names and snake_key not in normalized:
                normalized[snake_key] = value
                continue

            normalized[key] = value

        return normalized


class OutBase(ApiModel):
    code: int = Field(default=200, description="状态码")
    status: str = Field(default="success", description="操作状态")
    message: str = Field(default="操作成功", description="操作消息")


class InfoOut(OutBase):
    data: dict[str, Any] = Field(..., description="收到的服务器数据")


class ComboBoxItem(ApiModel):
    label: str = Field(..., description="展示值")
    value: str | None = Field(..., description="实际值")


class ComboBoxOut(OutBase):
    data: list[ComboBoxItem] = Field(..., description="下拉框选项")


class ResourceCollectionOut(OutBase, Generic[IndexT, DataT]):
    index: list[IndexT] = Field(..., description="资源索引列表")
    data: dict[str, DataT] = Field(..., description="资源数据字典")


class ResourceItemOut(OutBase, Generic[DataT]):
    data: DataT = Field(..., description="资源数据")


class ResourceCreateOut(ResourceItemOut[DataT], Generic[DataT]):
    id: str = Field(..., description="新创建资源的唯一 ID")


class IndexOrderPatch(ApiModel):
    index_list: list[str] = Field(
        ...,
        validation_alias=AliasChoices("index_list", "indexList"),
        serialization_alias="indexList",
        description="按新顺序排列的资源 ID 列表",
    )


def _annotate(annotation: Any, metadata: tuple[object, ...]) -> Any:
    if not metadata:
        return annotation
    return cast(Any, Annotated)[(annotation, *metadata)]


def _make_optional(annotation: Any) -> Any:
    origin = get_origin(annotation)
    if origin in (Union, UnionType) and type(None) in get_args(annotation):
        return annotation
    return annotation | None


def _clone_field_annotation(
    field_info: Any,
    annotation: Any,
    *,
    keep_virtual: bool,
) -> Any:
    metadata = tuple(
        item
        for item in field_info.metadata
        if keep_virtual or not isinstance(item, VirtualField)
    )
    field_kwargs: dict[str, Any] = {}
    if field_info.description is not None:
        field_kwargs["description"] = field_info.description
    if field_info.validation_alias is not None:
        field_kwargs["validation_alias"] = field_info.validation_alias
    if field_info.serialization_alias is not None:
        field_kwargs["serialization_alias"] = field_info.serialization_alias
    if field_info.alias is not None:
        field_kwargs["alias"] = field_info.alias
    if field_info.json_schema_extra is not None:
        field_kwargs["json_schema_extra"] = field_info.json_schema_extra
    if field_info.discriminator is not None:
        field_kwargs["discriminator"] = field_info.discriminator
    if field_kwargs:
        metadata = (*metadata, Field(**field_kwargs))
    return _annotate(annotation, metadata)


def _model_field_definitions(
    model_cls: type[BaseModel],
    *,
    optional_fields: bool,
    keep_virtual: bool,
) -> dict[str, tuple[Any, Any]]:
    field_definitions: dict[str, tuple[Any, Any]] = {}

    for field_name, field_info in model_cls.model_fields.items():
        if not keep_virtual and any(
            isinstance(item, VirtualField) for item in field_info.metadata
        ):
            continue

        annotation = field_info.annotation
        if optional_fields:
            annotation = _make_optional(annotation)

        annotated = _clone_field_annotation(
            field_info,
            annotation,
            keep_virtual=keep_virtual,
        )

        if optional_fields:
            default = Field(default=None, description=field_info.description)
        elif field_info.default_factory is not None:
            default = Field(
                default_factory=field_info.default_factory,
                description=field_info.description,
            )
        elif field_info.is_required():
            default = ...
        else:
            default = Field(
                default=field_info.default, description=field_info.description
            )

        field_definitions[field_name] = (annotated, default)

    return field_definitions


@lru_cache(maxsize=None)
def derive_group_read_model(
    group_cls: type[BaseModel],
    *,
    model_name: str,
) -> type[ApiModel]:
    return create_model(
        model_name,
        __base__=ApiModel,
        **cast(
            dict[str, Any],
            _model_field_definitions(
                group_cls,
                optional_fields=False,
                keep_virtual=True,
            ),
        ),
    )


@lru_cache(maxsize=None)
def derive_group_patch_model(
    group_cls: type[BaseModel],
    *,
    model_name: str,
) -> type[ApiModel]:
    return create_model(
        model_name,
        __base__=ApiModel,
        **cast(
            dict[str, Any],
            _model_field_definitions(
                group_cls,
                optional_fields=True,
                keep_virtual=False,
            ),
        ),
    )


@lru_cache(maxsize=None)
def derive_config_read_model(
    config_cls: type[PydanticConfigBase],
    *,
    model_name: str,
    include_groups: tuple[str, ...] | None = None,
) -> type[ApiModel]:
    field_definitions: dict[str, tuple[Any, Any]] = {}

    allowed_groups = set(include_groups) if include_groups is not None else None
    for group_name, field_info in config_cls.model_fields.items():
        if allowed_groups is not None and group_name not in allowed_groups:
            continue
        group_cls = field_info.annotation
        if not isinstance(group_cls, type) or not issubclass(group_cls, BaseModel):
            continue
        group_model = derive_group_read_model(
            group_cls,
            model_name=f"{model_name}{group_name}",
        )
        field_definitions[group_name] = (
            group_model,
            Field(default_factory=group_model, description=field_info.description),
        )

    return create_model(
        model_name,
        __base__=ApiModel,
        **cast(dict[str, Any], field_definitions),
    )


@lru_cache(maxsize=None)
def derive_config_patch_model(
    config_cls: type[PydanticConfigBase],
    *,
    model_name: str,
    include_groups: tuple[str, ...] | None = None,
) -> type[ApiModel]:
    field_definitions: dict[str, tuple[Any, Any]] = {}

    allowed_groups = set(include_groups) if include_groups is not None else None
    for group_name, field_info in config_cls.model_fields.items():
        if allowed_groups is not None and group_name not in allowed_groups:
            continue
        group_cls = field_info.annotation
        if not isinstance(group_cls, type) or not issubclass(group_cls, BaseModel):
            continue
        group_model = derive_group_patch_model(
            group_cls,
            model_name=f"{model_name}{group_name}",
        )
        field_definitions[group_name] = (
            group_model | None,
            Field(default=None, description=field_info.description),
        )

    return create_model(
        model_name,
        __base__=ApiModel,
        **cast(dict[str, Any], field_definitions),
    )


def derive_config_contracts(
    config_cls: type[PydanticConfigBase],
    *,
    read_name: str,
    patch_name: str,
    include_groups: tuple[str, ...] | None = None,
) -> tuple[type[ApiModel], type[ApiModel]]:
    return (
        derive_config_read_model(
            config_cls,
            model_name=read_name,
            include_groups=include_groups,
        ),
        derive_config_patch_model(
            config_cls,
            model_name=patch_name,
            include_groups=include_groups,
        ),
    )


def _normalize_source(raw: RawModelSource | None) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, BaseModel):
        return raw.model_dump()
    return dict(raw)


def _project_value(annotation: Any, value: Any) -> Any:
    if value is None:
        return None

    origin = get_origin(annotation)

    if origin is None:
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            return _project_model_data(annotation, value)
        return value

    if origin in (Union, UnionType):
        for candidate in (arg for arg in get_args(annotation) if arg is not type(None)):
            try:
                projected = _project_value(candidate, value)
                if isinstance(candidate, type) and issubclass(candidate, BaseModel):
                    candidate.model_validate(projected)
                return projected
            except Exception:
                continue
        return value

    if origin in (list, set, frozenset):
        item_annotation = get_args(annotation)[0] if get_args(annotation) else Any
        if not isinstance(value, (list, tuple, set, frozenset)):
            return value

        iterable_value = cast(
            list[Any] | tuple[Any, ...] | set[Any] | frozenset[Any], value
        )
        items = [_project_value(item_annotation, item) for item in iterable_value]
        if origin is set:
            return set(items)
        if origin is frozenset:
            return frozenset(items)
        return items

    if origin is tuple:
        if not isinstance(value, (list, tuple)):
            return value

        tuple_value = cast(list[Any] | tuple[Any, ...], value)
        item_annotations = get_args(annotation)
        if len(item_annotations) == 2 and item_annotations[1] is Ellipsis:
            return tuple(
                _project_value(item_annotations[0], item) for item in tuple_value
            )

        return tuple(
            _project_value(item_annotation, item)
            for item_annotation, item in zip(item_annotations, tuple_value)
        )

    if origin in (dict, Mapping):
        key_annotation, value_annotation = (
            get_args(annotation) if get_args(annotation) else (Any, Any)
        )
        if not isinstance(value, Mapping):
            return value

        mapping_value = cast(Mapping[Any, Any], value)
        return {
            _project_value(key_annotation, key): _project_value(value_annotation, item)
            for key, item in mapping_value.items()
        }

    return value


def _project_model_data(
    model_cls: type[BaseModel],
    raw: RawModelSource | None,
    include_keys: Iterable[str] | None = None,
) -> dict[str, Any]:
    source = _normalize_source(raw)
    field_names = include_keys or model_cls.model_fields.keys()

    projected: dict[str, Any] = {}
    for name in field_names:
        field = model_cls.model_fields.get(name)
        if field is None:
            continue

        source_value: Any | None = None
        has_value = False
        if name in source:
            source_value = source[name]
            has_value = True
        else:
            if field.alias is not None and field.alias in source:
                source_value = source[field.alias]
                has_value = True
            elif field.validation_alias is not None:
                alias = field.validation_alias
                if isinstance(alias, str) and alias in source:
                    source_value = source[alias]
                    has_value = True
                elif isinstance(alias, AliasChoices):
                    for candidate in alias.choices:
                        if isinstance(candidate, str) and candidate in source:
                            source_value = source[candidate]
                            has_value = True
                            break

        if not has_value:
            continue

        projected[name] = _project_value(field.annotation, source_value)

    return projected


def project_model(
    model_cls: type[ModelT],
    raw: RawModelSource | None,
    include_keys: Iterable[str] | None = None,
) -> ModelT:
    """把运行期字典投影为声明过字段的 Contract 模型。"""

    return model_cls.model_validate(_project_model_data(model_cls, raw, include_keys))


def project_model_list(
    model_cls: type[ModelT],
    raw_list: Iterable[RawModelSource] | None,
    include_keys: Iterable[str] | None = None,
) -> list[ModelT]:
    if raw_list is None:
        return []

    projected_items: list[ModelT] = []
    for raw_item in raw_list:
        projected_items.append(
            project_model(model_cls, raw_item, include_keys=include_keys)
        )
    return projected_items


def project_model_map(
    model_cls: type[ModelT],
    raw_map: Mapping[MapKeyT, RawModelSource] | None,
    include_keys: Iterable[str] | None = None,
) -> dict[MapKeyT, ModelT]:
    if raw_map is None:
        return {}

    projected_map: dict[MapKeyT, ModelT] = {}
    for key, raw_item in raw_map.items():
        projected_map[key] = project_model(
            model_cls, raw_item, include_keys=include_keys
        )
    return projected_map


__all__ = [
    "ApiModel",
    "OutBase",
    "InfoOut",
    "ComboBoxItem",
    "ComboBoxOut",
    "ResourceCollectionOut",
    "ResourceItemOut",
    "ResourceCreateOut",
    "IndexOrderPatch",
    "derive_group_read_model",
    "derive_group_patch_model",
    "derive_config_read_model",
    "derive_config_patch_model",
    "derive_config_contracts",
    "project_model",
    "project_model_list",
    "project_model_map",
]
