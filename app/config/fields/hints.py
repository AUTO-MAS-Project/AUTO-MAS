"""UI / Select / Legacy 字段注解与 hint 推导。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path
from types import UnionType
from typing import Literal, Union, TypedDict, get_args, get_origin

from annotated_types import Ge, Gt, Le, Lt

from .ann import strip_optional, unwrap_ann
from .encrypted import EncryptedMarker
from .ref import RefField


class UiVisibility(str, Enum):
    """字段 UI 显隐三态。"""

    SHOW = "show"
    HIDE = "hide"
    DISABLE = "disable"


class OptionHint(TypedDict):
    """select 选项（仅 value；展示文案由前端 i18n）。"""

    value: str


class ComponentHint(TypedDict, total=False):
    """单字段 UI 组件提示（无文案/宽度）。"""

    field: str
    component: str
    secret: bool
    editable: bool
    format: str | None
    path_kind: str | None
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


def legacy(*, group: str, name: str) -> LegacyMarker:
    """标记字段的旧文档位置，激活时旧值回退写入新位置。"""
    return LegacyMarker(group=group, name=name)


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
    if hint.get("component") == "input":
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

    # ── 预设路径/URL（靠类型名 / 校验函数名探测 Annotated 别名）──
    type_name = getattr(base, "__name__", "") or str(base)
    probe = f"{type_name} {repr(base)} {' '.join(repr(m) for m in meta)}"
    if "FilePath" in probe or "_validate_file_path" in probe:
        hint["component"] = "path"
        hint["path_kind"] = "file"
    elif "ExecutablePath" in probe or "_validate_executable_path" in probe:
        hint["component"] = "path"
        hint["path_kind"] = "file"
    elif (
        "FolderPath" in probe
        or "_validate_folder_path" in probe
        or "ScriptRootPath" in probe
        or "_validate_script_root_path" in probe
    ):
        hint["component"] = "path"
        hint["path_kind"] = "folder"
    elif "LoosePath" in probe or "_validate_loose_path" in probe:
        hint["component"] = "path"
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
