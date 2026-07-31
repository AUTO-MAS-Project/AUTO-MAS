"""UI / Select / Legacy 字段注解与 hint 推导。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal, TypedDict, get_args, get_origin

from annotated_types import Ge, Gt, Le, Lt

from .encrypted import EncryptedMarker
from .ref import RefField, TriggerDecl, VirtualDecl


class OptionHint(TypedDict):
    """select 选项（仅 value；展示文案由前端 i18n）。"""

    value: str


class ComponentHint(TypedDict, total=False):
    """单字段 UI 组件提示（无文案/宽度）。"""

    field: str
    component: str
    secret: bool
    readonly: bool
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


type UiHintsMap = dict[str, list[ComponentHint]]
"""``{group_name: [ComponentHint, ...]}``。"""


@dataclass(frozen=True)
class UiHintMarker:
    """覆盖 UI 推导的注解标记。"""

    widget: str | None = None
    format: str | None = None
    deps: tuple[str, ...] = ()
    secret: bool = False
    readonly: bool = False


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
    readonly: bool = False,
) -> UiHintMarker:
    """生成 UI 覆盖标记，置于 ``Annotated`` 内。"""
    return UiHintMarker(
        widget=widget,
        format=format,
        deps=tuple(deps or ()),
        secret=secret,
        readonly=readonly,
    )


def select(*, endpoint: str | None = None, ordered: bool = False) -> Select:
    """生成 select 标记（等价于 ``Select(...)``）。"""
    return Select(endpoint=endpoint, ordered=ordered)


def legacy(*, group: str, name: str) -> LegacyMarker:
    """标记字段的旧 Wire 位置，激活时旧值回退写入新位置。"""
    return LegacyMarker(group=group, name=name)


def _unwrap_annotated(ann: object) -> tuple[object, list[object]]:
    """剥 ``Annotated``，返回 ``(base, metadata)``。"""
    origin = get_origin(ann)
    args = get_args(ann)
    if origin is Annotated and args:
        return args[0], list(args[1:])
    return ann, []


def _type_name(base: object) -> str:
    return getattr(base, "__name__", "") or str(base)


def build_ui_hints(entry_cls: type) -> UiHintsMap:
    """从 Entry 类推导 ``{group: [ComponentHint, ...]}``（无文案/宽度）。"""
    hints: UiHintsMap = {}
    for gname, gfield in getattr(entry_cls, "model_fields", {}).items():
        if gname == "ui":
            continue
        group_cls = gfield.annotation
        if group_cls is None or not hasattr(group_cls, "model_fields"):
            continue
        group_hints: list[ComponentHint] = []
        for fname, ffield in group_cls.model_fields.items():
            hint: ComponentHint = {"field": fname, "component": "input"}
            base, meta = _unwrap_annotated(ffield.annotation)
            meta = meta + list(getattr(ffield, "metadata", ()) or ())

            # ── Annotated / 框架标记优先 ──
            for m in meta:
                if isinstance(m, TriggerDecl):
                    hint["component"] = "button"
                elif isinstance(m, VirtualDecl):
                    hint["readonly"] = True
                elif isinstance(m, RefField):
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
                    if m.readonly:
                        hint["readonly"] = True
                elif isinstance(m, (Ge, Gt)):
                    hint["min"] = getattr(m, "ge", None) or getattr(m, "gt", None)
                elif isinstance(m, (Le, Lt)):
                    hint["max"] = getattr(m, "le", None) or getattr(m, "lt", None)

            # ── Python / Literal 类型推导 ──
            if hint.get("component") == "input":
                borigin = get_origin(base)
                if base is bool or borigin is bool:
                    hint["component"] = "switch"
                elif base is int or borigin is int:
                    hint["component"] = "number"
                elif borigin is Literal:
                    hint["component"] = "select"
                    hint["options"] = [{"value": str(v)} for v in get_args(base)]
                    hint["multiple"] = False
                elif borigin is list:
                    inner = get_args(base)[0] if get_args(base) else str
                    if get_origin(inner) is Literal:
                        hint["component"] = "select"
                        hint["options"] = [
                            {"value": str(v)} for v in get_args(inner)
                        ]
                        hint["multiple"] = True

            # ── 预设路径/时间/URL（Pydantic 常把别名展开为 str + BeforeValidator）──
            type_name = _type_name(base)
            meta_repr = " ".join(repr(m) for m in meta)
            probe = f"{type_name} {repr(base)} {meta_repr}"
            if "FilePath" in probe or "_validate_file_path" in probe:
                hint["component"] = "path"
                hint["path_kind"] = "file"
            elif "EmulatorPath" in probe or "_validate_emulator_path" in probe:
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
            elif "HHMMString" in probe or "_validate_hhmm_string" in probe:
                hint["component"] = "time"
            elif "UrlString" in probe or "_validate_url_string" in probe:
                if hint.get("component") == "input":
                    hint["format"] = hint.get("format") or "url"

            if get_origin(base) is list and "multiple" not in hint:
                hint["multiple"] = True
            if hint.get("component") == "select" and "multiple" not in hint:
                hint["multiple"] = get_origin(base) is list

            group_hints.append(hint)
        if group_hints:
            hints[gname] = group_hints
    return hints


def iter_legacy_markers(field_info: object) -> list[LegacyMarker]:
    """收集字段上的 ``LegacyMarker``（含 Annotated 元数据）。"""
    ann = getattr(field_info, "annotation", None)
    _, meta = _unwrap_annotated(ann)
    meta = meta + list(getattr(field_info, "metadata", ()) or ())
    return [m for m in meta if isinstance(m, LegacyMarker)]
