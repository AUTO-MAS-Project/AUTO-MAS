"""L2 配置条目 ``ConfigEntry``：由若干 ConfigGroup 组成的单配置单元。"""

from __future__ import annotations

import asyncio
import inspect
import weakref
from pathlib import Path
from types import UnionType
from typing import (
    Any,
    ClassVar,
    Iterator,
    Literal,
    Self,
    Union,
    cast,
    get_args,
    get_origin,
)
from uuid import UUID

from pydantic import (
    BaseModel,
    Field,
    PrivateAttr,
    SerializationInfo,
    model_serializer,
    model_validator,
)
from pydantic_core.core_schema import SerializerFunctionWrapHandler

from app.utils.logger import get_logger

from ..errors import ConfigAggregateError, DeletedNodeError
from ..fields import (
    NestedCollectionMarker,
    RefDeleteAction,
    RefField,
    UiHintsMap,
    UiVisibility,
    UiVisibilitySpec,
    Virtual,
    is_reactive_model_field,
    is_trigger_model_field,
    is_virtual_model_field,
)
from ..fields.ann import strip_optional, unwrap_ann
from ..fields.encrypted import EncryptedValue
from ..fields.hints import (
    ComponentHint,
    OptionHint,
    UiTablesList,
    hint_for_field,
    migrate_legacy_fields,
    omit_masked_placeholders,
    visibility_spec_for_field,
)
from ..shortcuts import virtual_field
from ..signals import FieldChangeEvent
from .collection import ConfigCollection
from .group import ConfigGroup, ConfigTableColumn
from .manager import TransactionContext, config_manager
from .node import ConfigNode, ExportContext, NodeState, _ActivationState
from .staging import StagedOp, StageKind

logger = get_logger("配置激活")


class _RefReceiver:
    """单 ref 字段的目标失效接收者；包装与 deleted 守卫沿用统一信号机制。"""

    def __init__(
        self, entry: "ConfigEntry", group: str, field: str, spec: RefField
    ) -> None:
        self.__self__ = entry
        self._group = group
        self._field = field
        self._spec = spec

    async def __call__(self, sender: object, event: object) -> None:
        kind = getattr(event, "kind", None)
        if kind not in ("remove", "reload_type", "replace_type"):
            return
        entry = self.__self__
        group = entry.effective.__dict__.get(self._group)
        if not isinstance(group, ConfigGroup):
            return
        text = str(group.__dict__.get(self._field))
        if text in self._spec.allow_values:
            return
        try:
            uid = UUID(text)
        except ValueError:
            return
        if kind == "reload_type":
            if uid not in (getattr(event, "reloaded_uids", None) or ()):
                return
        elif str(uid) != str(getattr(event, "uid", "")):
            return
        if kind != "remove" and self._spec.normalize(uid) == uid:
            return
        if self._spec.on_delete == RefDeleteAction.RESTRICT:
            raise RuntimeError(
                f"ref {self._group}.{self._field} 处于 restrict，禁止使引用目标失效"
            )
        if self._spec.on_delete == RefDeleteAction.SET_DEFAULT:
            entry._stage(
                StagedOp.field_set(self._group, self._field, self._spec.default)
            )
            await entry.commit()
            return
        if self._spec.on_delete == RefDeleteAction.CASCADE:
            parent = entry.parent
            if not isinstance(parent, ConfigCollection):
                raise TypeError(
                    f"ref {self._group}.{self._field}: "
                    f"on_delete=CASCADE 仅适用于 Collection 成员 Entry"
                )
            parent.remove(entry.uid)
            await parent.commit()
            return
        if self._spec.on_delete == RefDeleteAction.CUSTOM:
            callback = self._spec.on_delete_callback
            if isinstance(callback, str):
                callback = getattr(entry, callback)
            result = callback(entry, event)  # type: ignore[misc]
            if inspect.isawaitable(result):
                await result


class ConfigEntry(ConfigNode):
    """L2 配置条目；文档形状 = 各 Group 字段顶层嵌套。"""

    # 类级规格（每子类独立）
    _cfg_group_fields: ClassVar[tuple[str, ...]] = ()
    _cfg_collection_fields: ClassVar[tuple[str, ...]] = ()
    _cfg_virtual_specs: ClassVar[dict[tuple[str, str], str]] = {}
    _cfg_trigger_specs: ClassVar[dict[tuple[str, str], str]] = {}
    # (group, field) → ("bool"|"literal", 触发值元组, 闲置值)
    _cfg_trigger_modes: ClassVar[
        dict[tuple[str, str], tuple[str, tuple[object, ...], object]]
    ] = {}
    _cfg_ref_specs: ClassVar[dict[tuple[str, str], RefField]] = {}
    _cfg_ui_hints: ClassVar[UiHintsMap] = {}
    _cfg_ui_tables: ClassVar[UiTablesList] = []
    _cfg_ui_visibility: ClassVar[dict[tuple[str, str | None], UiVisibilitySpec]] = {}

    @model_validator(mode="before")
    @classmethod
    def _prepare_input(cls, value: Any) -> Any:
        return omit_masked_placeholders(cls, migrate_legacy_fields(cls, value))

    class Ui(ConfigGroup):
        """前端组件提示虚拟组：``ui.hints`` / ``ui.tables``。"""

        hints: Virtual[UiHintsMap] = None
        tables: Virtual[UiTablesList] = None

    ui: Ui = Field(default_factory=Ui)

    # activate 后钉住的 ref 接收者；wrapped 由 receiver.__signal_wrappers__ 挂住
    _ref_receivers: list[object] = PrivateAttr(default_factory=list)

    def __init__(
        self,
        *,
        parent: ConfigNode | None = None,
        uid: UUID | str | None = None,
        payload: dict[str, Any] | None = None,
        file: Path | None = None,
        _activation: _ActivationState | None = None,
        **field_values: object,
    ) -> None:
        # 未激活导入（官方）：field_values 承接 model_validate 注入的字段（如 info=/data=），
        # 转发给 BaseModel 冷态填充（FastAPI Body）；热化仍走 activate，不在此完成。
        super().__init__(**field_values)
        self._parent_ref = weakref.ref(parent) if parent is not None else None
        if payload is not None and file is not None:
            raise ValueError("payload 与 file 互斥")
        # 登记前确定最终 UUID，激活只加载字段。
        if uid is not None:
            self._uid = uid if isinstance(uid, UUID) else UUID(uid)
        if file is not None:
            config_manager.register_root(self, file)
        self._pending_payload = payload
        if _activation is None and parent is not None:
            _activation = parent._activation
        self._activation = (
            _activation if _activation is not None and _activation.active else None
        )

    @classmethod
    def build(
        cls,
        *,
        parent: ConfigNode | None = None,
        uid: UUID | str | None = None,
        payload: dict[str, Any] | None = None,
        file: Path | None = None,
        **field_values: object,
    ) -> Self:
        """类型友好的构造入口。

        Pydantic 插件会为具体子类合成仅含模型字段的 ``__init__``，导致 ``uid`` /
        ``payload`` / ``file`` / ``parent`` 在类型检查中「不存在」。运行时仍可用
        ``Cls(...)``；需要完整构造参数且通过类型检查时请用 ``Cls.build(...)``。
        """
        self = object.__new__(cls)
        ConfigEntry.__init__(
            self,
            parent=parent,
            uid=uid,
            payload=payload,
            file=file,
            **cast("dict[str, Any]", field_values),
        )
        return self

    # ──────────────── 类级规格收集 ────────────────

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: object) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        group_fields: list[str] = []
        collection_fields: list[str] = []
        ref_specs: dict[tuple[str, str], RefField] = {}
        trigger_modes: dict[
            tuple[str, str], tuple[str, tuple[object, ...], object]
        ] = {}
        tables_by_cls: dict[type, list[str]] = {}
        ui_hints: UiHintsMap = {}
        ui_visibility: dict[tuple[str, str | None], UiVisibilitySpec] = {}

        for fname, finfo in cls.model_fields.items():
            ann = finfo.annotation
            origin = get_origin(ann) or ann
            if isinstance(ann, type) and issubclass(ann, ConfigGroup):
                group_fields.append(fname)
                if fname == "ui":
                    continue
                group_visibility = visibility_spec_for_field(finfo)
                if group_visibility is not None:
                    ui_visibility[(fname, None)] = group_visibility
                # 同一 ConfigTableColumn 子类的多个字段 = 一表多列
                if issubclass(ann, ConfigTableColumn) and ann is not ConfigTableColumn:
                    tables_by_cls.setdefault(ann, []).append(fname)
                group_hints: list[ComponentHint] = []
                for sub_name, sub_info in ann.model_fields.items():
                    key = (fname, sub_name)
                    refs = [
                        m
                        for m in getattr(sub_info, "metadata", ())
                        if isinstance(m, RefField)
                    ]
                    if len(refs) > 1:
                        raise TypeError(
                            f"{cls.__name__}.{fname}.{sub_name}: "
                            f"同一字段只能声明一个 ref()，收到 {len(refs)} 个"
                        )
                    if refs:
                        ref_specs[key] = refs[0]
                    if is_trigger_model_field(sub_info):
                        raw, _meta = unwrap_ann(sub_info.annotation)
                        raw = strip_optional(raw)
                        t_origin = get_origin(raw)
                        if t_origin is Union or t_origin is UnionType:
                            raise TypeError(
                                f"{cls.__name__}.{fname}.{sub_name}: "
                                "触发器须为 bool 或 Literal（可 | None），"
                                "禁止 bool 与 Literal 混用"
                            )
                        if raw is bool or t_origin is bool:
                            trigger_modes[key] = ("bool", (True,), False)
                        elif t_origin is Literal:
                            values = get_args(raw)
                            if not values:
                                raise TypeError(
                                    f"{cls.__name__}.{fname}.{sub_name}: "
                                    "Literal 触发器至少需要一个字面量"
                                )
                            trigger_modes[key] = ("literal", values, None)
                        else:
                            raise TypeError(
                                f"{cls.__name__}.{fname}.{sub_name}: "
                                f"触发器值类型须为 bool 或 Literal[...]，收到 {raw!r}"
                            )
                    vis = visibility_spec_for_field(sub_info)
                    if vis is not None:
                        if key in ui_visibility:
                            raise TypeError(
                                f"{cls.__name__}.{fname}.{sub_name}: UI 显隐重复声明"
                            )
                        ui_visibility[key] = vis
                    group_hints.append(
                        hint_for_field(
                            sub_name,
                            sub_info,
                            trigger_mode=trigger_modes.get(key),
                        )
                    )
                if group_hints:
                    ui_hints[fname] = group_hints
            elif isinstance(origin, type) and issubclass(origin, ConfigCollection):
                if not any(
                    isinstance(m, NestedCollectionMarker) for m in finfo.metadata
                ):
                    raise TypeError(
                        f"{cls.__name__}.{fname}: 嵌套 Collection 必须用 collection() 声明"
                    )
                collection_fields.append(fname)

        virtual_specs: dict[tuple[str, str], str] = {}
        trigger_specs: dict[tuple[str, str], str] = {}
        for attr_name in dir(cls):
            try:
                member = getattr(cls, attr_name)
            except AttributeError:
                continue
            vb = getattr(member, "__virtual_field_binding__", None)
            if vb is not None:
                key = (vb.group, vb.field_name)
                if key in virtual_specs:
                    raise TypeError(
                        f"{cls.__name__}: 虚拟字段 {vb.group}.{vb.field_name} "
                        f"重复绑定（{virtual_specs[key]!r} 与 {vb.getter!r}）"
                    )
                virtual_specs[key] = vb.getter
            tb = getattr(member, "__trigger_field_binding__", None)
            if tb is not None:
                key = (tb.group, tb.field_name)
                if key in trigger_specs:
                    raise TypeError(
                        f"{cls.__name__}: 触发器 {tb.group}.{tb.field_name} "
                        f"重复绑定（{trigger_specs[key]!r} 与 {tb.handler!r}）"
                    )
                trigger_specs[key] = tb.handler
            ub = getattr(member, "__ui_visibility_binding__", None)
            if ub is not None:
                key = (ub.group, ub.field_name)
                if key in ui_visibility:
                    raise TypeError(
                        f"{cls.__name__}.{ub.group}.{ub.field_name}: "
                        f"UI 显隐重复绑定（已有 {ui_visibility[key]!r}，又见 {ub.getter!r}）"
                    )
                ui_visibility[key] = ub.getter

        cls._cfg_group_fields = tuple(group_fields)
        cls._cfg_collection_fields = tuple(collection_fields)
        cls._cfg_ref_specs = ref_specs
        cls._cfg_virtual_specs = virtual_specs
        cls._cfg_trigger_specs = trigger_specs
        cls._cfg_trigger_modes = trigger_modes
        cls._cfg_ui_hints = ui_hints
        cls._cfg_ui_visibility = ui_visibility
        cls._cfg_ui_tables = [
            {
                "key": col_cls._table_key,
                "columns": columns,
                "rows": list(col_cls.model_fields.keys()),
                "transpose": bool(col_cls._table_transpose),
            }
            for col_cls, columns in tables_by_cls.items()
        ]

    def _ui_visibility(self, group: str, field: str | None = None) -> UiVisibility:
        """同步求显隐；组级隐藏、禁用作用于子项，掩码仅用于具体字段。"""
        group_visibility = (
            self._ui_visibility(group) if field is not None else UiVisibility.SHOW
        )
        if group_visibility == UiVisibility.HIDE:
            return UiVisibility.HIDE
        spec = type(self)._cfg_ui_visibility.get((group, field))
        if spec is None:
            return group_visibility
        if isinstance(spec, UiVisibility):
            result = spec
        else:
            result = spec(self)
            if inspect.isawaitable(result):
                raise TypeError("UI 显隐仅支持同步函数")
            if not isinstance(result, UiVisibility):
                raise TypeError(
                    f"UI 显隐方法 {spec!r} 须返回 UiVisibility，收到 {type(result).__name__}"
                )
        if field is None and result == UiVisibility.MASKED:
            raise TypeError("MASKED 须声明在具体配置字段上")
        if result == UiVisibility.SHOW and group_visibility == UiVisibility.DISABLE:
            return UiVisibility.DISABLE
        return result

    @virtual_field("ui.hints")
    def _get_ui_hints(self) -> UiHintsMap:
        """类级底板 + 显隐、editable、ref 动态选项；上锁时全部 editable=false。"""
        out: UiHintsMap = {}
        locked = self.is_locked
        virtuals = type(self)._cfg_virtual_specs
        for gname, hints in type(self)._cfg_ui_hints.items():
            filtered: list[ComponentHint] = []
            for hint in hints:
                fname = str(hint.get("field", ""))
                vis = self._ui_visibility(gname, fname)
                if vis == UiVisibility.HIDE:
                    continue
                item = dict(hint)
                # DISABLE / 虚拟 → 不可改；SHOW 默认可改；上锁再全量只读
                item["editable"] = (
                    False
                    if locked
                    or vis == UiVisibility.DISABLE
                    or self._ui_visibility(gname) == UiVisibility.DISABLE
                    or (gname, fname) in virtuals
                    else True
                )
                item["masked"] = vis == UiVisibility.MASKED
                spec = type(self)._cfg_ref_specs.get((gname, fname))
                if spec is not None:
                    options: list[OptionHint] = [
                        {"value": value}
                        for value in dict.fromkeys((spec.default, *spec.allow_values))
                    ]
                    seen = {option["value"] for option in options}
                    target = config_manager.get_collection(spec.target)
                    for uid, target_entry in target.items():
                        value = str(uid)
                        if value in seen or not spec.accepts(target_entry):
                            continue
                        option: OptionHint = {"value": value}
                        if spec.display_field is not None:
                            display: object = target_entry
                            for part in spec.display_field.split("."):
                                if (
                                    not isinstance(display, BaseModel)
                                    or part not in type(display).model_fields
                                ):
                                    raise ValueError(
                                        f"ref {gname}.{fname}: 目标 "
                                        f"{type(target_entry).__name__} 不存在展示字段 "
                                        f"{spec.display_field!r}"
                                    )
                                display = getattr(display, part)
                                if display is None:
                                    break
                            label = "" if display is None else str(display)
                            option["label"] = label or value
                        options.append(option)
                        seen.add(value)
                    item["options"] = options
                filtered.append(item)  # type: ignore[arg-type]
            if filtered:
                out[gname] = filtered
        return out

    @virtual_field("ui.tables")
    def _get_ui_tables(self) -> UiTablesList:
        """按当前显隐过滤表格列与行；不修改类级布局声明。"""
        out: UiTablesList = []
        for table in type(self)._cfg_ui_tables:
            columns = [
                group
                for group in table["columns"]
                if any(
                    self._ui_visibility(group, row) != UiVisibility.HIDE
                    for row in table["rows"]
                )
            ]
            if not columns:
                continue
            rows = [
                row
                for row in table["rows"]
                if any(
                    self._ui_visibility(group, row) != UiVisibility.HIDE
                    for group in columns
                )
            ]
            out.append({**table, "columns": columns, "rows": rows})
        return out

    # ──────────────── 构造后挂载 ────────────────

    def model_post_init(self, __context: object) -> None:
        for gname in self._cfg_group_fields:
            group = cast(ConfigGroup, self.__dict__[gname])
            object.__setattr__(group, "_entry", self)
            object.__setattr__(group, "_group", gname)
        # 嵌套 Collection：default_factory 无 parent；此处绑 parent（避免重建）
        for cname in self._cfg_collection_fields:
            col = cast(ConfigCollection[ConfigNode], self.__dict__[cname])
            if col.parent is None:
                col._parent_ref = weakref.ref(self)

    async def _commit_op(self, op: StagedOp) -> None:
        if op.kind != StageKind.FIELD_SET:
            raise TypeError(f"Entry 不支持: {op.kind.value}")
        assert op.group is not None and op.field is not None
        use_init = self.activation_state == NodeState.INITIALIZING
        async with config_manager.transaction():
            self._build_workspace()
            group = getattr(self.effective, op.group)
            old = group.__dict__.get(op.field)
            group.__pydantic_validator__.validate_assignment(
                group, op.field, op.value, context={"entry": self}
            )
            new = group.__dict__.get(op.field)
            if use_init or old != new:
                await type(self).send(
                    sender=self,
                    event=FieldChangeEvent(
                        kind="init_set" if use_init else "set",
                        node=self,
                        group=op.group,
                        field=op.field,
                        value=(
                            new.plaintext() if isinstance(new, EncryptedValue) else new
                        ),
                        old_value=(
                            old.plaintext() if isinstance(old, EncryptedValue) else old
                        ),
                    ),
                )
            if self._current_staged():
                raise RuntimeError(
                    "信号回调须在返回前 commit 当次 stage，"
                    f"残留 {len(self._current_staged())} 条"
                )

    # ──────────────── 读路径 ────────────────

    def _resolve_field(self, group: str, field: str) -> object:
        if self.deleted:
            raise DeletedNodeError(self.uid)
        if (group, field) in type(self)._cfg_virtual_specs:
            return getattr(self, type(self)._cfg_virtual_specs[(group, field)])()
        tmode = type(self)._cfg_trigger_modes.get((group, field))
        if tmode is not None:
            return tmode[2]
        stored = getattr(self.effective, group).__dict__.get(field)
        if isinstance(stored, EncryptedValue):
            return stored.plaintext()
        return stored

    def _dispatch_trigger(self, group: str, field: str, value: object = True) -> None:
        if not self._activation_ready:
            raise ValueError("配置尚未完成激活，无法触发操作")
        if self.deleted:
            raise DeletedNodeError(self.uid)
        handler = getattr(self, type(self)._cfg_trigger_specs[(group, field)])
        # bool：无额外参；Literal：传入触发值
        result = (
            handler()
            if type(self)._cfg_trigger_modes[(group, field)][0] == "bool"
            else handler(value)
        )
        if inspect.isawaitable(result):
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            coro = (
                result
                if inspect.iscoroutine(result)
                else asyncio.wait_for(result, timeout=None)
            )
            if loop is not None:
                loop.create_task(coro)
            else:
                asyncio.run(coro)

    # ──────────────── 更新 ────────────────

    async def update(self, other: Self, *, check_visibility: bool = True) -> None:
        """用同类冷态 Entry 的 Group 字段更新本实例，自动 ``commit``；失败 ``raise ConfigAggregateError``。

        - 仅同步 ``_cfg_group_fields``（含触发器；跳过虚拟字段与 **未赋值** 字段），**不**改嵌套 Collection / 子 Node。
        - 未赋值判定：``other`` / 各 Group 的 ``model_fields_set``（FastAPI Body 部分字段可直接 ``await cfg.update(body)``）。
        - ``check_visibility``：默认 ``True``，按 UI 显隐跳过 ``HIDE`` / ``DISABLE``
          字段 —— 前端传参必须走这条，否则用户能改到界面上不给改的项。
          程序内部调用传 ``False`` 可全量写入传入字段（如订阅期回写、迁移、
          插件自身的批量落配置）；此时**仅**跳过虚拟字段与未赋值字段，
          这两类与显隐无关：前者无存储、后者调用方压根没打算改。
        """
        if type(other) is not type(self):
            raise TypeError(
                f"update 须为同类 Entry，收到 {type(other).__name__}，"
                f"期望 {type(self).__name__}"
            )
        if self.activation_state != NodeState.ACTIVE:
            raise ValueError("须先 activate")

        errors: list[Exception] = []
        other_set = other.model_fields_set
        for gname in self._cfg_group_fields:
            if gname not in other_set:
                continue
            src = other.__dict__.get(gname)
            dst = self.__dict__.get(gname)
            if not isinstance(src, ConfigGroup) or not isinstance(dst, ConfigGroup):
                continue
            src_set = src.model_fields_set
            for fname, finfo in type(dst).model_fields.items():
                if is_virtual_model_field(finfo) or fname not in src_set:
                    continue
                # hide / disable：跳过（与前端不可改契约对齐；求值用热态 self）
                if check_visibility:
                    vis = self._ui_visibility(gname, fname)
                    if vis in (UiVisibility.HIDE, UiVisibility.DISABLE) or (
                        self._ui_visibility(gname) == UiVisibility.DISABLE
                    ):
                        continue
                try:
                    setattr(dst, fname, src.__dict__.get(fname))
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)
        try:
            await self.commit()
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
        if errors:
            raise ConfigAggregateError(errors)

    # ──────────────── 激活 ────────────────

    async def _activate_from_payload(
        self, payload: dict[str, Any], *, regenerate_uuids: bool = False
    ) -> None:
        payload = omit_masked_placeholders(
            type(self), migrate_legacy_fields(type(self), payload or {})
        )
        activation = self._activation
        errors = (
            await self._try_fast_fields(payload)
            if activation is not None and activation.fast_init
            else await self._activate_fields(payload)
        )

        # 嵌套 Collection：标准 activate（pending_payload）
        for cname in self._cfg_collection_fields:
            col = cast(ConfigCollection[ConfigNode], self.__dict__[cname])
            if col.activation_state != NodeState.INACTIVE:
                continue
            nested = payload.get(cname)
            if isinstance(nested, dict):
                col._pending_payload = cast(dict[str, Any], nested)
            try:
                await col.activate(regenerate_uuids=regenerate_uuids)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        # ref 外键：每字段订一次；只钉 receiver（wrapped 挂在 receiver.__signal_wrappers__）
        self._ref_receivers.clear()
        for (group_name, field_name), spec in type(self)._cfg_ref_specs.items():
            try:
                if spec.on_delete == RefDeleteAction.CASCADE:
                    parent = self.parent
                    if not isinstance(parent, ConfigCollection):
                        raise TypeError(
                            f"ref {group_name}.{field_name}: "
                            f"on_delete=CASCADE 仅适用于 Collection 成员 Entry"
                        )
                # 目标集合必须已登记（未登记 → LookupError）
                target = config_manager.get_collection(spec.target)
                receiver = _RefReceiver(self, group_name, field_name, spec)
                for kind in ("remove", "reload_type", "replace_type"):
                    type(target)._connect_impl(
                        receiver,
                        phase="runtime",
                        kind=kind,
                        group=None,
                        field=None,
                        sender=target,
                    )
                self._ref_receivers.append(receiver)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        if errors:
            raise ConfigAggregateError(errors)

    async def _try_fast_fields(self, payload: dict[str, Any]) -> list[Exception]:
        """字段共用局部事务；失败后在边界外恢复逐字段流程。"""
        failed: Exception | None = None
        try:
            async with config_manager.transaction(new_boundary=True):
                try:
                    await self._activate_fields(payload, fail_fast=True)
                except Exception as exc:
                    failed = exc
                    raise
        except Exception as exc:
            # 提交和清理错误不属于可重试的字段错误。
            if exc is not failed:
                raise
            logger.debug(f"快速赋值退出，回退逐字段初始化：{type(exc).__name__}")
        else:
            return []
        # 共享边界已完整撤销；从首字段重试，每字段重新建立独立回退边界。
        return await self._activate_fields(payload)

    async def _activate_fields(
        self, payload: dict[str, Any], *, fail_fast: bool = False
    ) -> list[Exception]:
        errors: list[Exception] = []
        # 保持逐字段校验与即时 Init 信号，仅共享快速赋值的工作区。
        for gname in self._cfg_group_fields:
            group = cast(ConfigGroup, self.__dict__[gname])
            group_values = payload.get(gname)
            if not isinstance(group_values, dict):
                group_values = {}
            for field_name, fld in type(group).model_fields.items():
                if is_reactive_model_field(fld):
                    continue
                if field_name in group_values:
                    value = group_values[field_name]
                else:
                    value = group.__dict__.get(field_name)
                    # 复用冷态默认值；加密值仍经密文重走校验链。
                    if isinstance(value, EncryptedValue):
                        value = value.ciphertext()
                try:
                    async with config_manager.transaction(new_boundary=not fail_fast):
                        setattr(group, field_name, value)
                        await self.commit()
                        if fail_fast:
                            ctx = config_manager.current
                            assert ctx is not None
                            config_manager._check_staged(ctx)
                except Exception as exc:  # noqa: BLE001
                    if fail_fast:
                        raise
                    errors.append(exc)
        return errors

    # ──────────────── 工作区 ────────────────

    def _make_workspace_shell(self, source: ConfigNode) -> ConfigEntry:
        src = cast(ConfigEntry, source)
        ws = src.model_copy()
        ws._staged_by_owner = weakref.WeakKeyDictionary()
        ws._workspace = {}
        ws._is_workspace = True
        src_data = src.__dict__
        live_data = self.__dict__
        for gname in self._cfg_group_fields:
            src_g = cast(ConfigGroup, src_data[gname])
            # TODO(R11): 可变字段仍只支持整字段赋值；浅复制不保护原地修改。
            dup = src_g.model_copy()
            object.__setattr__(dup, "_entry", self)
            object.__setattr__(dup, "_group", gname)
            object.__setattr__(ws, gname, dup)
        for cname in self._cfg_collection_fields:
            object.__setattr__(ws, cname, live_data[cname])
        return ws

    def _COMMIT(self, ctx: TransactionContext) -> None:
        source = self._workspace.pop(ctx.scope_id, None)
        if source is None:
            return
        target = self
        if ctx.parent is not None:
            parent = self._workspace.get(ctx.parent.scope_id)
            if parent is None:
                self._workspace[ctx.parent.scope_id] = self._make_workspace_shell(
                    source
                )
                return
            target = cast(ConfigEntry, parent)
        # 逐字段回填，保留 live 及父工作区的分组身份。
        for gname in self._cfg_group_fields:
            group = cast(ConfigGroup, target.__dict__[gname])
            values = source.__dict__[gname].__dict__
            for fname in type(group).model_fields:
                if not fname.startswith("_"):
                    object.__setattr__(group, fname, values.get(fname))
        target._deleted = source._deleted
        target._activation_state = source._activation_state
        target._activation = source._activation
        target._pending_payload = source._pending_payload

    # ──────────────── 迭代与导出 ────────────────

    def iter_children(self) -> Iterator[ConfigNode]:
        for cname in self._cfg_collection_fields:
            yield cast(ConfigCollection[ConfigNode], self.__dict__[cname])

    # ──────────────── 导出（官方 model_serializer）────────────────

    @model_serializer(mode="wrap")
    def _serialize(
        self,
        handler: SerializerFunctionWrapHandler,
        info: SerializationInfo,
    ) -> dict[str, Any]:
        """Entry 文档：各 Group + 嵌套 Collection；persist 跳过 ``ui``。

        不调用 ``handler(self)``：避免把运行时 PrivateAttr / 非文档字段带出；
        嵌套导出统一 ``model_dump(mode=…, context=ctx)``。
        ``mode=python`` 与 audience 正交：仍导出各组，不做 UI 裁剪（由 Group 侧处理）。
        """
        _ = handler
        dump_mode = info.mode if info.mode in ("json", "python") else "json"
        if dump_mode == "python":
            # 内部代理：各组 / 嵌套 Collection 原样 python dump，不套 audience
            out_py: dict[str, Any] = {}
            for gname in self._cfg_group_fields:
                out_py[gname] = cast(ConfigGroup, self.__dict__[gname]).model_dump(
                    mode="python"
                )
            for cname in self._cfg_collection_fields:
                out_py[cname] = cast(
                    ConfigCollection[ConfigNode], self.__dict__[cname]
                ).model_dump(mode="python")
            return out_py
        ctx = ExportContext.from_dump(info.context)
        out: dict[str, Any] = {}
        for gname in self._cfg_group_fields:
            if gname == "ui" and ctx.audience != "api":
                continue
            if (
                ctx.audience == "api"
                and self._ui_visibility(gname) == UiVisibility.HIDE
            ):
                continue
            values = cast(ConfigGroup, self.__dict__[gname]).model_dump(
                mode=dump_mode, context=ctx
            )
            if ctx.audience != "api" or values:
                out[gname] = values
        for cname in self._cfg_collection_fields:
            out[cname] = cast(
                ConfigCollection[ConfigNode], self.__dict__[cname]
            ).model_dump(mode=dump_mode, context=ctx)
        return out
