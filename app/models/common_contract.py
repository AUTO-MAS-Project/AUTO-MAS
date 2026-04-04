from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import UnionType
from typing import Any, TypeAlias, TypeVar, Union, cast, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field


ModelT = TypeVar("ModelT", bound=BaseModel)
MapKeyT = TypeVar("MapKeyT")
RawModelSource: TypeAlias = Mapping[str, Any] | BaseModel


class ApiModel(BaseModel):
    """API Contract 的统一基线。"""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


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

        iterable_value = cast(list[Any] | tuple[Any, ...] | set[Any] | frozenset[Any], value)
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
            return tuple(_project_value(item_annotations[0], item) for item in tuple_value)

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
            _project_value(key_annotation, key): _project_value(
                value_annotation, item
            )
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
        if field is None or name not in source:
            continue
        projected[name] = _project_value(field.annotation, source[name])

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
    "project_model",
    "project_model_list",
    "project_model_map",
]
