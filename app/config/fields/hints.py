"""UI / Select / Legacy 字段注解与 hint 推导。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path
from types import UnionType
from typing import Any, Literal, NotRequired, TypedDict, Union, get_args, get_origin

from annotated_types import Ge, Gt, Le, Lt

from ..types import PathKind, PathPolicy
from .ann import strip_optional, unwrap_ann
from .encrypted import EncryptedMarker
from .ref import RefField, is_reactive_model_field


class UiVisibility(str, Enum):
    """字段 UI 显隐与读写方式。"""

    SHOW = "show"
    HIDE = "hide"
    DISABLE = "disable"
    MASKED = "masked"


UI_MASKED_VALUE = "__AUTO_MAS_CONFIG_MASKED__"
"""API 掩码字段的保留占位符；原样提交表示不修改现值。"""


class OptionHint(TypedDict):
    """select 选项；ref 可携带展示字段的 label，其余文案由前端 i18n。"""

    value: str
    label: NotRequired[str]


class ComponentHint(TypedDict, total=False):
    """单字段 UI 组件提示（无文案/宽度）。"""

    field: str
    component: str
    secret: bool
    editable: bool
    masked: bool
    format: str | None
    path_kind: PathKind | None
    path_extensions: list[str]
    path_must_exist: bool
    min: float | None
    max: float | None
    options: list[OptionHint] | None
    multiple: bool
    ordered: bool
    endpoint: str | None
    deps: list[str] | None
    widget: str | None


class TableHint(TypedDict):
    """表格布局提示（标题文案由前端按 ``key`` 取 i18n）。"""

    key: str | None
    columns: list[str]
    rows: list[str]
    transpose: bool


type UiHintsMap = dict[str, list[ComponentHint]]
"""``{group_name: [ComponentHint, ...]}``。"""

type UiTablesList = list[TableHint]
"""Entry 上由同列 Group 类聚合得到的表格声明列表。"""

# 类级显隐规格：常量 Enum，或同步可调用
type UiVisibilitySpec = UiVisibility | Callable[..., UiVisibility]


@dataclass(frozen=True)
class UiVisibilityBinding:
    """``@ui_visibility("group.field")`` 绑定到 Entry 同步方法。"""

    group: str
    field_name: str
    getter: Callable[..., UiVisibility]


@dataclass(frozen=True)
class UiHintMarker:
    """覆盖 UI 推导的注解标记。"""

    widget: str | None = None
    format: str | None = None
    deps: tuple[str, ...] = ()
    secret: bool = False
    visibility: UiVisibility | Callable[..., UiVisibility] | None = None


@dataclass(frozen=True)
class Select:
    """select 注解：与 ``encrypted()`` 同级。"""

    endpoint: str | None = None
    ordered: bool = False


@dataclass(frozen=True)
class LegacyMarker:
    """旧字段位置迁移标记。"""

    group: str
    name: str
    convert: Callable[[Any], Any] | None = None


def ui(
    *,
    widget: str | None = None,
    format: str | None = None,
    deps: list[str] | None = None,
    secret: bool = False,
    visibility: UiVisibility | Callable[..., UiVisibility] | None = None,
) -> UiHintMarker:
    """生成 UI 覆盖标记，置于 ``Annotated`` 内。

    ``visibility`` 可为 ``UiVisibility`` 常量，或返回该枚举的**同步**方法引用。
    """
    return UiHintMarker(
        widget=widget,
        format=format,
        deps=tuple(deps or ()),
        secret=secret,
        visibility=visibility,
    )


def select(*, endpoint: str | None = None, ordered: bool = False) -> Select:
    """生成 select 标记（等价于 ``Select(...)``）。"""
    return Select(endpoint=endpoint, ordered=ordered)


def legacy(
    *, group: str, name: str, convert: Callable[[Any], Any] | None = None
) -> LegacyMarker:
    """标记字段的旧文档位置，激活时旧值回退写入新位置。"""
    return LegacyMarker(group=group, name=name, convert=convert)


def migrate_legacy_fields(entry_type: type, payload: Any) -> Any:
    """按唯一的 legacy 声明搬移旧字段；显式提供的新字段始终优先。"""
    if not isinstance(payload, dict):
        return payload
    result = dict(payload)
    for group_name in entry_type._cfg_group_fields:
        group_type = entry_type.model_fields[group_name].annotation
        values = result.get(group_name, {})
        if not isinstance(values, dict):
            continue
        migrated = dict(values)
        for name, field in group_type.model_fields.items():
            for marker in field.metadata:
                if not isinstance(marker, LegacyMarker):
                    continue
                old_group = payload.get(marker.group)
                if not isinstance(old_group, dict) or marker.name not in old_group:
                    continue
                if name not in migrated:
                    value = old_group[marker.name]
                    migrated[name] = marker.convert(value) if marker.convert else value
                if (marker.group, marker.name) != (group_name, name):
                    old_group_field = entry_type.model_fields.get(marker.group)
                    old_field = (
                        old_group_field.annotation.model_fields.get(marker.name)
                        if old_group_field is not None
                        else None
                    )
                    if old_field is not None and not is_reactive_model_field(old_field):
                        # 仍正式声明的旧字段保留其值；只有兼容入口才被消费。
                        continue
                    # 只删除兼容入口；不原地改动调用方传入的数据。
                    current = result.get(marker.group)
                    if isinstance(current, dict):
                        current = dict(current)
                        current.pop(marker.name, None)
                        if current or marker.group in entry_type._cfg_group_fields:
                            result[marker.group] = current
                        else:
                            result.pop(marker.group, None)
                    if marker.group == group_name:
                        migrated.pop(marker.name, None)
        if migrated or group_name in payload:
            result[group_name] = migrated
    return result


def omit_masked_placeholders(entry_type: type, payload: Any) -> Any:
    """移除 UI 掩码回传值，避免其进入加密、类型校验或持久化。"""
    if not isinstance(payload, dict):
        return payload
    result = dict(payload)
    for (group, name), visibility in entry_type._cfg_ui_visibility.items():
        if name is None or not (
            visibility == UiVisibility.MASKED or callable(visibility)
        ):
            continue
        values = result.get(group)
        if isinstance(values, dict) and values.get(name) == UI_MASKED_VALUE:
            values = dict(values)
            values.pop(name)
            result[group] = values
    return result


def visibility_spec_for_field(field_info: object) -> UiVisibilitySpec | None:
    """从 Group 子字段 ``ui(visibility=…)`` 提取显隐规格；无则 ``None``。"""
    ann = getattr(field_info, "annotation", None)
    _, meta = unwrap_ann(ann)
    meta = list(meta) + list(getattr(field_info, "metadata", ()) or ())
    for m in meta:
        if not isinstance(m, UiHintMarker) or m.visibility is None:
            continue
        vis = m.visibility
        if isinstance(vis, UiVisibility) or callable(vis):
            return vis
        raise TypeError(
            f"ui(visibility=) 仅接受 UiVisibility 或同步可调用，收到 {type(vis).__name__}"
        )
    return None


def hint_for_field(
    fname: str,
    field_info: object,
    *,
    trigger_mode: tuple[str, tuple[object, ...], object] | None = None,
) -> ComponentHint:
    """单字段 ``ComponentHint``（无 ``editable``；显隐在实例 ``_get_ui_hints`` 叠加）。"""
    hint: ComponentHint = {"field": fname, "component": "input"}
    ann = getattr(field_info, "annotation", None)
    base, meta = unwrap_ann(ann)
    meta = list(meta) + list(getattr(field_info, "metadata", ()) or ())
    base = strip_optional(base)

    if trigger_mode is not None:
        mode, values, _idle = trigger_mode
        if mode == "literal":
            hint["component"] = "dropdown-button"
            hint["options"] = [{"value": str(v)} for v in values]
        else:
            hint["component"] = "button"

    # ── Annotated / 框架标记优先 ──
    for m in meta:
        if isinstance(m, RefField):
            hint["component"] = "ref-select"
        elif isinstance(m, EncryptedMarker):
            hint["secret"] = True
            hint["format"] = "password"
        elif isinstance(m, Select):
            hint["component"] = "select"
            if m.endpoint:
                hint["endpoint"] = m.endpoint
            if m.ordered:
                hint["ordered"] = True
        elif isinstance(m, UiHintMarker):
            if m.widget:
                hint["widget"] = m.widget
                hint["component"] = m.widget
            if m.format:
                hint["format"] = m.format
            if m.deps:
                hint["deps"] = list(m.deps)
            if m.secret:
                hint["secret"] = True
        elif isinstance(m, (Ge, Gt)):
            hint["min"] = getattr(m, "ge", None) or getattr(m, "gt", None)
        elif isinstance(m, (Le, Lt)):
            hint["max"] = getattr(m, "le", None) or getattr(m, "lt", None)

    # ── Python / Literal / Enum 类型推导 ──
    # 无 endpoint 的 select 仍从 Literal / Enum 推导静态选项；有 endpoint 时由接口供值。
    infer_static_options = hint.get("component") == "input" or (
        hint.get("component") == "select" and not hint.get("endpoint")
    )
    if infer_static_options:
        borigin = get_origin(base)
        type_candidates: list[object] = [base]
        if borigin is Union or borigin is UnionType:
            type_candidates = [a for a in get_args(base) if a is not type(None)]

        enum_cls: type[Enum] | None = None
        for cand in type_candidates:
            if isinstance(cand, type) and issubclass(cand, Enum):
                enum_cls = cand
                break

        if base is bool or borigin is bool:
            hint["component"] = "switch"
        elif base is int or borigin is int:
            hint["component"] = "number"
        elif base is time or (isinstance(base, type) and issubclass(base, time)):
            hint["component"] = "time"
            hint["format"] = hint.get("format") or "hm"
        elif base is datetime or (
            isinstance(base, type) and issubclass(base, datetime)
        ):
            fmt = hint.get("format") or "hms"
            if fmt == "hm":
                hint["component"] = "time"
                hint["format"] = "hm"
            elif fmt == "date":
                hint["component"] = "date"
                hint["format"] = "date"
            else:
                hint["component"] = "datetime"
                hint["format"] = fmt
        elif base is date or (
            isinstance(base, type)
            and issubclass(base, date)
            and not issubclass(base, datetime)
        ):
            hint["component"] = "date"
            hint["format"] = hint.get("format") or "date"
        elif enum_cls is not None:
            hint["component"] = "select"
            hint["options"] = [{"value": str(m.value)} for m in enum_cls]
            hint["multiple"] = False
        elif borigin is Literal:
            hint["component"] = "select"
            hint["options"] = [{"value": str(v)} for v in get_args(base)]
            hint["multiple"] = False
        elif borigin is list:
            inner = get_args(base)[0] if get_args(base) else str
            if isinstance(inner, type) and issubclass(inner, Enum):
                hint["component"] = "select"
                hint["options"] = [{"value": str(m.value)} for m in inner]
                hint["multiple"] = True
            elif get_origin(inner) is Literal:
                hint["component"] = "select"
                hint["options"] = [{"value": str(v)} for v in get_args(inner)]
                hint["multiple"] = True

    # ── 路径声明直接提供选择提示，不向 UI 暴露阻止目录；URL 沿用预设识别 ──
    type_name = getattr(base, "__name__", "") or str(base)
    probe = f"{type_name} {repr(base)} {' '.join(repr(m) for m in meta)}"
    path_spec = next((m for m in meta if isinstance(m, PathPolicy)), None)
    if path_spec is not None:
        hint["component"] = "path"
        hint["path_kind"] = path_spec.kind
        hint["path_must_exist"] = path_spec.must_exist
        if path_spec.kind != "folder":
            hint["path_extensions"] = list(path_spec.extensions)
    elif base is Path or (isinstance(base, type) and issubclass(base, Path)):
        if hint.get("component") == "input":
            hint["component"] = "path"
    elif "UrlString" in probe or "_validate_url_string" in probe:
        if hint.get("component") == "input":
            hint["format"] = hint.get("format") or "url"

    if get_origin(base) is list and "multiple" not in hint:
        hint["multiple"] = True
    if hint.get("component") == "select" and "multiple" not in hint:
        hint["multiple"] = get_origin(base) is list

    return hint
