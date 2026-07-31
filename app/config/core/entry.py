"""L2 配置条目 ``ConfigEntry``：由若干 ConfigGroup 组成的单配置单元。"""

from __future__ import annotations

import asyncio
import inspect
import weakref
from pathlib import Path
from typing import Annotated, ClassVar, Iterator, Self, cast, get_args, get_origin
from uuid import UUID

from pydantic import Field, PrivateAttr

from .collection import ConfigCollection
from ..fields.encrypted import EncryptedValue
from ..errors import ConfigAggregateError, DeletedNodeError
from ..fields import (
    NestedCollectionMarker,
    RefDeleteAction,
    RefField,
    UiHintsMap,
    Virtual,
    is_reactive_model_field,
    is_virtual_model_field,
)
from ..fields.hints import LegacyMarker, build_ui_hints
from ..shortcuts import virtual_field
from .group import ConfigGroup
from .manager import config_manager
from .node import ConfigNode, NodeState
from ..signals import FieldChangeEvent
from .staging import StageKind, StagedOp
from ..wire import ExportContext, WireDict


class _RefRemoveReceiver:
    """单 ref 字段的 Collection.remove 接收者；可挂 ``__signal_wrappers__``，``__self__`` 供 deleted 守卫。"""

    def __init__(
        self, entry: "ConfigEntry", group: str, field: str, spec: RefField
    ) -> None:
        self.__self__ = entry
        self._group = group
        self._field = field
        self._spec = spec

    async def __call__(self, sender: object, event: object) -> None:
        if getattr(event, "kind", None) != "remove":
            return
        entry = self.__self__
        group = entry.__dict__.get(self._group)
        if not isinstance(group, ConfigGroup):
            return
        if str(group.__dict__.get(self._field)) != str(getattr(event, "uid", "")):
            return
        if self._spec.on_delete == RefDeleteAction.RESTRICT:
            raise RuntimeError(
                f"ref {self._group}.{self._field} 处于 restrict，禁止删除目标"
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
    """L2 配置条目；Wire 形状 = 各 Group 字段顶层嵌套。"""

    # 类级规格（每子类独立）
    _cfg_group_fields: ClassVar[tuple[str, ...]] = ()
    _cfg_collection_fields: ClassVar[tuple[str, ...]] = ()
    _cfg_virtual_specs: ClassVar[dict[tuple[str, str], str]] = {}
    _cfg_trigger_specs: ClassVar[dict[tuple[str, str], str]] = {}
    _cfg_ref_specs: ClassVar[dict[tuple[str, str], RefField]] = {}
    _cfg_ui_hints: ClassVar[UiHintsMap] = {}

    class Ui(ConfigGroup):
        """前端组件提示虚拟组：``ui.hints``。"""

        hints: Virtual[UiHintsMap] = None

    ui: Ui = Field(default_factory=Ui)

    # activate 后钉住的 ref 接收者（bound method）；wrapped 由 receiver.__signal_wrappers__ 挂住
    _ref_receivers: list[object] = PrivateAttr(default_factory=list)

    def __init__(
        self,
        *,
        parent: ConfigNode | None = None,
        uid: UUID | str | None = None,
        wire: WireDict | None = None,
        file: Path | None = None,
        **field_values: object,
    ) -> None:
        # field_values 承接 pydantic model_validate 注入的字段（如 info=/data=），
        # 转发给 BaseModel 以完成冷态字段填充（FastAPI Body 必需）。
        super().__init__(**field_values)
        self._parent_ref = weakref.ref(parent) if parent is not None else None
        if wire is not None and file is not None:
            raise ValueError("wire 与 file 互斥")
        if file is not None:
            if not self.is_root:
                raise ValueError("仅根节点可 file=")
            config_manager.register_root(self, file)
        if uid is not None:
            self._uid = uid if isinstance(uid, UUID) else UUID(uid)
        self._pending_wire = wire

    @classmethod
    def build(
        cls,
        *,
        parent: ConfigNode | None = None,
        uid: UUID | str | None = None,
        wire: WireDict | None = None,
        file: Path | None = None,
        **field_values: object,
    ) -> Self:
        """类型友好的构造入口。

        Pydantic 插件会为具体子类合成仅含模型字段的 ``__init__``，导致 ``uid`` /
        ``wire`` / ``file`` / ``parent`` 在类型检查中「不存在」。运行时仍可用
        ``Cls(...)``；需要完整构造参数且通过类型检查时请用 ``Cls.build(...)``。
        """
        self = object.__new__(cls)
        ConfigEntry.__init__(
            self, parent=parent, uid=uid, wire=wire, file=file, **field_values
        )
        return self

    # ──────────────── 类级规格收集 ────────────────

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: object) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        group_fields: list[str] = []
        collection_fields: list[str] = []
        ref_specs: dict[tuple[str, str], RefField] = {}

        for fname, finfo in cls.model_fields.items():
            ann = finfo.annotation
            origin = get_origin(ann) or ann
            if isinstance(ann, type) and issubclass(ann, ConfigGroup):
                group_fields.append(fname)
                for sub_name, sub_info in ann.model_fields.items():
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
                        ref_specs[(fname, sub_name)] = refs[0]
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

        cls._cfg_group_fields = tuple(group_fields)
        cls._cfg_collection_fields = tuple(collection_fields)
        cls._cfg_ref_specs = ref_specs
        cls._cfg_virtual_specs = virtual_specs
        cls._cfg_trigger_specs = trigger_specs
        cls._cfg_ui_hints = build_ui_hints(cls)

    @virtual_field("ui.hints")
    def _get_ui_hints(self) -> UiHintsMap:
        return type(self)._cfg_ui_hints

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
        async with (
            config_manager.init_transaction()
            if use_init
            else config_manager.transaction()
        ):
            (self._build_init_workspace if use_init else self._build_workspace)()
            group = getattr(self.effective, op.group)
            old = group.__dict__.get(op.field)
            setattr(group, op.field, op.value)
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
            if self._staged_ops:
                raise RuntimeError(
                    "信号回调须在返回前 commit 当次 stage，"
                    f"残留 {len(self._staged_ops)} 条"
                )

    # ──────────────── 读路径 ────────────────

    def _resolve_field(self, group: str, field: str) -> object:
        if self.deleted:
            raise DeletedNodeError(self.uid)
        if (group, field) in type(self)._cfg_virtual_specs:
            return getattr(self, type(self)._cfg_virtual_specs[(group, field)])()
        if (group, field) in type(self)._cfg_trigger_specs:
            return False
        stored = getattr(self.effective, group).__dict__.get(field)
        if isinstance(stored, EncryptedValue):
            return stored.plaintext()
        return stored

    def _dispatch_trigger(self, group: str, field: str) -> None:
        result = getattr(self, type(self)._cfg_trigger_specs[(group, field)])()
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

    async def update(self, other: Self) -> None:
        """用同类冷态 Entry 的 Group 字段更新本实例，自动 ``commit``；失败 ``raise ConfigAggregateError``。

        - 仅同步 ``_cfg_group_fields``（含触发器；跳过虚拟字段与 **未赋值** 字段），**不**改嵌套 Collection / 子 Node。
        - 未赋值判定：``other`` / 各 Group 的 ``model_fields_set``（FastAPI Body 部分字段可直接 ``await cfg.update(body)``）。
        """
        if type(other) is not type(self):
            raise TypeError(
                f"update 须为同类 Entry，收到 {type(other).__name__}，"
                f"期望 {type(self).__name__}"
            )
        if self.activation_state != NodeState.ACTIVE:
            raise ValueError("须先 activate")
        if self.is_locked:
            raise RuntimeError("已锁定，不可 update")
        if self.deleted:
            raise DeletedNodeError(self.uid)

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

    async def _activate_from_payload(self, payload: WireDict) -> None:
        payload = payload or {}
        errors: list[Exception] = []

        # Group 字段热化：与 Collection 相同 — 赋值 stage + commit（commit_op 内切 init 事务）
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
                    # 空 payload 时复用已构造默认值；EncryptedValue 需经密文再入校验链
                    if isinstance(value, EncryptedValue):
                        value = value.ciphertext()
                    ann = fld.annotation
                    meta = list(getattr(fld, "metadata", ()) or ())
                    if get_origin(ann) is Annotated:
                        meta = list(get_args(ann)[1:]) + meta
                    for marker in meta:
                        if isinstance(marker, LegacyMarker):
                            old_group = payload.get(marker.group)
                            if isinstance(old_group, dict) and marker.name in old_group:
                                value = old_group[marker.name]
                                break
                try:
                    setattr(group, field_name, value)
                    await self.commit()
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)

        # 嵌套 Collection：标准 activate（pending_wire）
        for cname in self._cfg_collection_fields:
            col = cast(ConfigCollection[ConfigNode], self.__dict__[cname])
            if col.activation_state != NodeState.INACTIVE:
                continue
            nested = payload.get(cname)
            if isinstance(nested, dict):
                col._pending_wire = cast(WireDict, nested)
            try:
                await col.activate()
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
                receiver = _RefRemoveReceiver(self, group_name, field_name, spec)
                type(target)._connect_impl(
                    receiver,
                    phase="runtime",
                    kind="remove",
                    group=None,
                    field=None,
                    sender=target,
                )
                self._ref_receivers.append(receiver)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        if errors:
            raise ConfigAggregateError(errors)

    # ──────────────── 工作区 ────────────────

    def _make_workspace_shell(self, *, init: bool = False) -> "ConfigEntry":
        if init:
            assert self._workspace is not None
            src = cast(ConfigEntry, self._workspace)
        else:
            src = self
        ws = src.model_copy()
        ws._workspace = None
        ws._deleted = src._deleted
        ws._activation_state = src._activation_state
        ws._pending_wire = src._pending_wire
        ws._is_workspace = True
        for gname in self._cfg_group_fields:
            src_g = cast(ConfigGroup, src.__dict__[gname])
            dup = src_g.model_copy()
            object.__setattr__(dup, "_entry", self)
            object.__setattr__(dup, "_group", gname)
            object.__setattr__(ws, gname, dup)
        for cname in self._cfg_collection_fields:
            object.__setattr__(ws, cname, self.__dict__[cname])
        return ws

    def _COMMIT(self) -> None:
        if self._workspace is None:
            return
        for gname in self._cfg_group_fields:
            live = cast(ConfigGroup, self.__dict__[gname])
            staged = cast(ConfigGroup, self._workspace.__dict__[gname])
            for fname in type(live).model_fields:
                if fname.startswith("_"):
                    continue
                object.__setattr__(live, fname, staged.__dict__.get(fname))
        self._deleted = self._workspace._deleted
        self._activation_state = self._workspace._activation_state
        self._pending_wire = self._workspace._pending_wire
        self._workspace = None

    def _COMMIT_init(self) -> None:
        if self._workspace is None or self._workspace._workspace is None:
            return
        init = self._workspace._workspace
        for gname in self._cfg_group_fields:
            dst = cast(ConfigGroup, self._workspace.__dict__[gname])
            src = cast(ConfigGroup, init.__dict__[gname])
            for fname in type(dst).model_fields:
                if fname.startswith("_"):
                    continue
                object.__setattr__(dst, fname, src.__dict__.get(fname))
        self._workspace._deleted = init._deleted
        self._workspace._activation_state = init._activation_state
        self._workspace._pending_wire = init._pending_wire
        self._workspace._workspace = None

    # ──────────────── 迭代与导出 ────────────────

    def iter_children(self) -> Iterator[ConfigNode]:
        for cname in self._cfg_collection_fields:
            yield cast(ConfigCollection[ConfigNode], self.__dict__[cname])

    def _export_wire(self, ctx: ExportContext) -> WireDict:
        """Wire 导出：读已提交 ``self``，不经 ``effective``（事务 ws）。"""
        out: WireDict = {}
        for gname in self._cfg_group_fields:
            if gname == "ui" and not ctx.include_reactive:
                continue
            out[gname] = cast(ConfigGroup, self.__dict__[gname]).model_dump(context=ctx)
        for cname in self._cfg_collection_fields:
            out[cname] = cast(
                ConfigCollection[ConfigNode], self.__dict__[cname]
            )._export_wire(ctx)
        return out
