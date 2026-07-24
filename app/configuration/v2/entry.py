"""L2 配置条目 ``ConfigEntry``：由若干 ConfigGroup 组成的单配置单元。"""

from __future__ import annotations

import asyncio
import copy
import inspect
import weakref
from collections.abc import Mapping
from pathlib import Path
from typing import ClassVar, Iterator, Self, cast, get_origin
from uuid import UUID

from pydantic import PrivateAttr

from .collection import ConfigCollection
from .encrypted import EncryptedValue, is_encrypted_model_field
from .errors import ConfigAggregateError, DeletedNodeError, EncryptedValueError
from .fields import (
    NestedCollectionMarker,
    RefDeleteAction,
    RefField,
    is_reactive_model_field,
)
from .group import ConfigGroup
from .manager import config_manager
from .node import ConfigNode, NodeState
from .signals import FieldChangeEvent
from .staging import StageKind, StagedOp
from .wire import ExportContext, WireDict


class _RefRemoveReceiver:
    """单 ref 字段的 Collection.remove 接收者；``__self__`` 供 deleted 守卫。"""

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
        # Ref integrity must observe the same transaction workspace as the
        # collection removal.  Reading the live entry here would allow a
        # staged B -> A change and deletion of A to bypass RESTRICT, while a
        # staged A -> default change could be rejected incorrectly.
        group = entry.effective.__dict__.get(self._group)
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

    # activate 后钉住 ref 接收者；框架 signal registry 仅弱引用 receiver。
    # 保留目标集合是为了最终释放时不再依赖全局 registry（registry 此时可能已
    # 注销），并让断连精确对应最初 connect 的 sender。
    _ref_receivers: list[tuple[ConfigCollection, _RefRemoveReceiver]] = PrivateAttr(
        default_factory=list
    )

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
        # Identity must be final before registry lookup.  Registering the
        # random PrivateAttr default first would leave the requested uid
        # unregistered and could also hide a real uid conflict.
        if uid is not None:
            self._uid = uid if isinstance(uid, UUID) else UUID(uid)
        if file is not None:
            if not self.is_root:
                raise ValueError("仅根节点可 file=")
            config_manager.register_root(self, file)
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

    # ──────────────── 构造后挂载 ────────────────

    def model_post_init(self, __context: object) -> None:
        for gname in self._cfg_group_fields:
            group = cast(ConfigGroup, self.__dict__[gname])
            object.__setattr__(group, "_entry", self)
            object.__setattr__(group, "_group", gname)
        # 嵌套 Collection：default_factory 无 parent；此处绑 parent（避免重建）
        for cname in self._cfg_collection_fields:
            col = cast(ConfigCollection, self.__dict__[cname])
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
            field_info = type(group).model_fields[op.field]
            is_encrypted = is_encrypted_model_field(field_info)
            try:
                setattr(group, op.field, op.value)
            except Exception:
                if is_encrypted:
                    # Pydantic validation errors retain their input object.
                    # Never keep a secret-bearing exception in an aggregate
                    # error or expose it through the caller-facing message.
                    raise EncryptedValueError(
                        "encrypted configuration field validation failed: "
                        f"{op.group}.{op.field}"
                    ) from None
                raise
            new = group.__dict__.get(op.field)
            if is_encrypted and isinstance(old, EncryptedValue) and isinstance(
                new, EncryptedValue
            ):
                # DPAPI uses randomized ciphertext, so equal plaintexts can
                # legitimately have different persisted bytes. Compare via
                # EncryptedValue's non-exporting plaintext equality instead.
                changed = old != new
            else:
                changed = old != new
            if use_init or changed:
                event = FieldChangeEvent(
                    kind="init_set" if use_init else "set",
                    node=self,
                    group=op.group,
                    field=op.field,
                    changed=changed,
                    encrypted=is_encrypted,
                    # Events are observations, not mutation handles into the
                    # transaction workspace.  A receiver may mutate these
                    # snapshots without changing live or staged config state.
                    value=None if is_encrypted else copy.deepcopy(new),
                    old_value=None if is_encrypted else copy.deepcopy(old),
                )
                if not use_init:
                    # Local import avoids a module cycle while keeping the v2
                    # package independent from the core-owned WS publisher.
                    from ..runtime import enqueue_field_change

                    await enqueue_field_change(event)
                await type(self).emit_change(
                    sender=self,
                    event=event,
                )
            staged_count = len(self._current_staged_ops())
            if staged_count:
                raise RuntimeError(
                    "信号回调须在返回前 commit 当次 stage，"
                    f"残留 {staged_count} 条"
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
        if isinstance(stored, (list, dict, set, bytearray)):
            # Configuration mutation must always travel through whole-value
            # assignment + stage/commit, including while the node is locked.
            return copy.deepcopy(stored)
        return stored

    def get(self, group: str, field: str) -> object:
        """Read one logical field through the native Config v2 access path.

        Host services use this small API when a group/field pair arrives from
        a transport payload.  It deliberately resolves virtual and encrypted
        fields through the same path as attribute access and does not depend
        on the removed legacy ``ConfigBase`` implementation.
        """

        group_value = getattr(self.effective, group)
        if not isinstance(group_value, ConfigGroup):
            raise TypeError(f"{group} 不是 ConfigGroup")
        if field not in type(group_value).model_fields:
            raise AttributeError(f"{type(self).__name__}.{group}.{field}")
        return self._resolve_field(group, field)

    async def set(self, group: str, field: str, value: object) -> None:
        """Atomically validate and commit one native Config v2 field."""

        await self.set_many({group: {field: value}})

    async def set_many(
        self,
        changes: Mapping[str, Mapping[str, object]],
    ) -> None:
        """Validate and commit a transport update as one transaction.

        Every path is checked before staging starts.  Runtime value validation,
        signals and durable persistence then run in the single native commit;
        one bad value rolls back the complete request.
        """

        resolved: list[tuple[ConfigGroup, str, object]] = []
        for group, fields in changes.items():
            if not isinstance(group, str):
                raise TypeError("配置分组名称必须是字符串")
            if not isinstance(fields, Mapping):
                raise TypeError(f"{group} 必须是字段映射")
            group_value = getattr(self.effective, group)
            if not isinstance(group_value, ConfigGroup):
                raise TypeError(f"{group} 不是 ConfigGroup")
            for field, value in fields.items():
                if not isinstance(field, str):
                    raise TypeError(f"{group} 的字段名称必须是字符串")
                if field not in type(group_value).model_fields:
                    raise AttributeError(f"{type(self).__name__}.{group}.{field}")
                resolved.append((group_value, field, value))

        for group_value, field, value in resolved:
            setattr(group_value, field, value)
        await self.commit()

    async def toDict(  # noqa: N802 - temporary stable host transport surface
        self,
        if_decrypt: bool = True,
        regenerate_uuids: bool = False,
    ) -> WireDict:
        """Export an entry for existing host/API consumers.

        The object is still a native ``ConfigEntry`` and persistence always
        uses ``to_dict(if_decrypt=False)`` through the generation coordinator.
        UUID regeneration belongs to collection-copy orchestration and is
        therefore rejected here instead of silently producing duplicate child
        identities.
        """

        if regenerate_uuids:
            raise ValueError(
                "Config v2 entry UUID regeneration must use collection copy"
            )
        return await self.to_dict(
            if_decrypt=if_decrypt,
            include_reactive=if_decrypt,
        )

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
        """原子更新普通 Group 字段，不执行 trigger 或修改子节点。"""
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

        staged_ops = self._current_staged_ops(create=True)
        staged_start = len(staged_ops)
        try:
            async with config_manager.transaction():
                async with config_manager.node_commit(self):
                    for gname in self._cfg_group_fields:
                        if gname not in other.model_fields_set:
                            continue
                        src = other.__dict__.get(gname)
                        dst = self.__dict__.get(gname)
                        if not isinstance(src, ConfigGroup) or not isinstance(
                            dst, ConfigGroup
                        ):
                            continue
                        for fname, finfo in type(dst).model_fields.items():
                            if fname not in src.model_fields_set:
                                continue
                            if is_reactive_model_field(finfo):
                                continue
                            value = src.__dict__.get(fname)
                            is_encrypted = is_encrypted_model_field(finfo)
                            if is_encrypted and isinstance(value, EncryptedValue):
                                # The encrypted marker validates the logical
                                # string before wrapping it again.  Feeding an
                                # EncryptedValue into that inner str schema is
                                # invalid even though the source model itself
                                # is valid.
                                value = value.plaintext()
                            try:
                                setattr(dst, fname, value)
                            except Exception:
                                if is_encrypted:
                                    raise EncryptedValueError(
                                        "encrypted configuration field validation failed: "
                                        f"{gname}.{fname}"
                                    ) from None
                                raise
                    await self.commit()
        except Exception as exc:
            current_ops = self._current_staged_ops()
            del current_ops[staged_start:]
            if isinstance(exc, ConfigAggregateError):
                raise
            raise ConfigAggregateError([exc]) from exc

    # ──────────────── 激活 ────────────────

    def _validate_activation_payload_shape(self, payload: WireDict) -> None:
        """Reject unknown/lossy native-v2 paths before opening init workspaces."""
        allowed_top = set(self._cfg_group_fields) | set(self._cfg_collection_fields)
        unknown_paths = [f"$.{key}" for key in set(payload) - allowed_top]

        for group_name in self._cfg_group_fields:
            if group_name not in payload:
                continue
            group_values = payload[group_name]
            if not isinstance(group_values, dict):
                raise TypeError(f"$.{group_name} must be a table")
            group = cast(ConfigGroup, self.__dict__[group_name])
            persistent_fields = {
                name
                for name, field in type(group).model_fields.items()
                if not is_reactive_model_field(field)
            }
            unknown_paths.extend(
                f"$.{group_name}.{field_name}"
                for field_name in set(group_values) - persistent_fields
            )

        for collection_name in self._cfg_collection_fields:
            if collection_name in payload and not isinstance(
                payload[collection_name], dict
            ):
                raise TypeError(f"$.{collection_name} must be a table")

        if unknown_paths:
            raise ValueError(
                "unknown configuration paths: " + ", ".join(sorted(unknown_paths))
            )

    async def _activate_from_payload(self, payload: WireDict) -> None:
        payload = payload or {}
        self._validate_activation_payload_shape(payload)
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
                value = (
                    group_values[field_name]
                    if field_name in group_values
                    else group.__dict__.get(field_name)
                )
                try:
                    setattr(group, field_name, value)
                    await self.commit()
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)

        # 嵌套 Collection：标准 activate（pending_wire）
        for cname in self._cfg_collection_fields:
            col = cast(ConfigCollection, self.__dict__[cname])
            if col.activation_state != NodeState.INACTIVE:
                continue
            nested = payload.get(cname)
            if isinstance(nested, dict):
                col._pending_wire = cast(WireDict, nested)
            try:
                await col.activate()
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        # ref 外键：每字段订一次；receiver 由 Entry 钉住，wrapper 由框架 registry 管理。
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
                    role="validator",
                    phase="runtime",
                    group=None,
                    field=None,
                    sender=target,
                )
                self._ref_receivers.append((target, receiver))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        if errors:
            raise ConfigAggregateError(errors)

    def _disconnect_ref_receivers(self, *, clear: bool = True) -> None:
        """释放本 Entry 的 ref 订阅。

        保存的 target/receiver 对使最终释放不依赖 ``ConfigManager`` 的
        collection registry。删除路径在事务内只断开 signal workspace，而不能
        清空 live receiver 所有权；事务回滚时仍需它保持旧订阅可达。
        """

        if clear and config_manager.in_transaction:
            raise RuntimeError("活动配置事务中不可最终释放 ref receiver")
        subscriptions = self._ref_receivers
        for target, receiver in reversed(subscriptions):
            type(target)._disconnect_impl(
                receiver,
                role="validator",
                phase="runtime",
                group=None,
                field=None,
                sender=target,
            )
        if clear:
            self._ref_receivers = []

    async def _delete(self) -> None:
        """先在事务 signal workspace 断连，再执行可回滚的软删除。"""

        if not self.deleted:
            self._disconnect_ref_receivers(clear=False)
        await super()._delete()

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
            yield cast(ConfigCollection, self.__dict__[cname])

    def _export_wire(self, ctx: ExportContext) -> WireDict:
        """Wire export from committed state or the owner transaction workspace."""
        source = cast(
            ConfigEntry,
            self.effective if ctx.include_staged else self,
        )
        out: WireDict = {}
        for gname in self._cfg_group_fields:
            out[gname] = cast(
                ConfigGroup,
                source.__dict__[gname],
            ).model_dump(context=ctx)
        for cname in self._cfg_collection_fields:
            out[cname] = cast(
                ConfigCollection,
                source.__dict__[cname],
            )._export_wire(ctx)
        return out
