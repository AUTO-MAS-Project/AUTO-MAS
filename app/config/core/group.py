"""L3 配置分组：嵌套在 ConfigEntry 内的字段块（如 info、data）。

``__getattribute__`` / ``__setattr__`` 按字段类型分流：

- 普通 / ref / 内置类型：读经 ``entry._resolve_field``，写经 ``entry`` 框架链。
- 加密字段：内存 ``EncryptedValue``，读 unwrap 为明文。
- 虚拟字段：只读；运行时计算。
- 触发器字段：bool 闲置 ``False`` / 写 ``True`` 触发；Literal 闲置 ``None`` / 写字面量触发并传参。
- ``date``：若入参为 ``datetime``，先按目标时区转换再存为 ``date``（``datetime`` 字段不做时区强制）。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, ClassVar, TYPE_CHECKING, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    SerializationInfo,
    ValidationInfo,
    field_validator,
    model_serializer,
)
from pydantic_core.core_schema import SerializerFunctionWrapHandler

from ..fields import (
    is_trigger_model_field,
    is_virtual_model_field,
)
from ..fields.ann import strip_optional, unwrap_ann
from ..fields.hints import UiVisibility
from ..types import TzMarker
from .manager import config_manager
from .node import ExportContext, NodeState
from .staging import StagedOp
from app.utils.constants import UTC8

if TYPE_CHECKING:
    from .entry import ConfigEntry


class ConfigGroup(BaseModel):
    """L3 配置分组。"""

    model_config = ConfigDict(validate_assignment=True, validate_default=True)

    @field_validator("*", mode="before")
    @classmethod
    def _date_from_datetime_tz(cls, value: object, info: ValidationInfo) -> object:
        """``date`` 字段收到 ``datetime`` 时：先强制目标时区，再取 ``.date()``。

        未激活赋值同样走 ``validate_assignment(..., context={"entry": entry})``，本校验器会生效；
        冷态 ``model_validate`` 无 entry context 时回退 ``UTC8``。
        """
        if not isinstance(value, datetime):
            return value
        name = info.field_name
        if not name or name not in cls.model_fields:
            return value
        field = cls.model_fields[name]
        base, meta = unwrap_ann(field.annotation)
        base = strip_optional(base)
        # 仅 date 字段（datetime 是 date 子类，须排除）
        if not (
            base is date
            or (
                isinstance(base, type)
                and issubclass(base, date)
                and not issubclass(base, datetime)
            )
        ):
            return value
        if value.tzinfo is None:
            return value.date()
        # aware：需转目标时区再取 date（跨时区可能跨日）
        meta = list(meta) + list(getattr(field, "metadata", ()) or ())
        marker = next((m for m in meta if isinstance(m, TzMarker)), None)
        if marker is not None:
            target = marker.tz
        else:
            ctx = info.context if isinstance(info.context, dict) else None
            entry = ctx.get("entry") if ctx else None
            target = type(entry).timezone if entry is not None else UTC8
        return value.astimezone(target).date()

    # ── 读路径 ──

    def __getattribute__(self, name: str) -> object:
        cls: type[ConfigGroup] = object.__getattribute__(self, "__class__")
        fields = cls.model_fields
        if name.startswith("_") or name not in fields:
            return object.__getattribute__(self, name)

        state: dict[str, object] = object.__getattribute__(self, "__dict__")
        entry = state.get("_entry")
        group = state.get("_group")
        if entry is None or group is None:
            raise RuntimeError(f"配置分组 {cls.__name__} 未绑定所属 ConfigEntry")

        entry = cast("ConfigEntry", entry)
        assert isinstance(group, str)
        return entry._resolve_field(group, name)

    # ── 写路径 ──

    def __setattr__(self, name: str, value: object) -> None:
        fields = type(self).model_fields
        if name.startswith("_") or name not in fields:
            return super().__setattr__(name, value)

        field = fields[name]
        state: dict[str, object] = object.__getattribute__(self, "__dict__")
        entry = state.get("_entry")
        group = state.get("_group")
        if entry is None or group is None:
            raise RuntimeError(
                f"配置分组 {type(self).__name__} 未绑定所属 ConfigEntry"
            )

        entry = cast("ConfigEntry", entry)
        assert isinstance(group, str)

        if is_virtual_model_field(field):
            raise AttributeError(f"虚拟字段 {group}.{name} 只读")

        if is_trigger_model_field(field):
            if (group, name) not in type(entry)._cfg_trigger_specs:
                raise AttributeError(f"触发器 {group}.{name} 须经 @trigger_field 注册")
            # 与 entry.update 一致：HIDE/DISABLE 不接受开闸
            if entry._ui_visibility(group, name) in (
                UiVisibility.HIDE,
                UiVisibility.DISABLE,
            ):
                return
            mode, allowed, _idle = type(entry)._cfg_trigger_modes[(group, name)]
            if mode == "bool":
                if not isinstance(value, bool):
                    raise TypeError(f"触发器 {name} 仅接受 bool 类型")
                if value:
                    entry._dispatch_trigger(group, name, True)
                return
            # Literal：None 空操作；字面量触发并传参
            if value is None:
                return
            if value not in allowed:
                raise TypeError(
                    f"触发器 {name} 仅接受 {allowed!r} 或 None，收到 {value!r}"
                )
            entry._dispatch_trigger(group, name, value)
            return

        if config_manager.in_transaction and entry._workspace is not None:
            if getattr(entry._workspace, group, None) is self:
                self.__pydantic_validator__.validate_assignment(
                    self, name, value, context={"entry": entry}
                )
                return
            if (
                config_manager.in_init_transaction
                and entry._workspace._workspace is not None
                and getattr(entry._workspace._workspace, group, None) is self
            ):
                self.__pydantic_validator__.validate_assignment(
                    self, name, value, context={"entry": entry}
                )
                return

        if entry.activation_state == NodeState.INACTIVE:
            # 未激活：纯 pydantic 校验直写（无事务 / 信号）；带 entry 以便时区
            self.__pydantic_validator__.validate_assignment(
                self, name, value, context={"entry": entry}
            )
            return

        entry._stage(StagedOp.field_set(group, name, value))

    # ── 导出：官方 model_serializer ────────────────

    @model_serializer(mode="wrap")
    def _serialize(
        self,
        handler: SerializerFunctionWrapHandler,
        info: SerializationInfo,
    ) -> dict[str, Any]:
        """普通字段走 handler；virtual / trigger / UI hide 按 audience（python 模式跳过）。"""
        data = cast(dict[str, Any], handler(self))
        # mode=python：与 audience 正交，不做响应式注入 / UI 裁剪
        if info.mode == "python":
            return data
        ctx = ExportContext.from_dump(info.context)
        state = object.__getattribute__(self, "__dict__")
        entry = cast("ConfigEntry | None", state.get("_entry"))
        group_name = state.get("_group")
        include_reactive = ctx.audience == "api"
        for name, field in type(self).model_fields.items():
            # api：尊重 hide（含普通字段与响应式）
            if (
                ctx.audience == "api"
                and entry is not None
                and isinstance(group_name, str)
                and entry._ui_visibility(group_name, name) == UiVisibility.HIDE
            ):
                data.pop(name, None)
                continue
            if is_virtual_model_field(field):
                if (
                    not include_reactive
                    or entry is None
                    or not isinstance(group_name, str)
                ):
                    data.pop(name, None)
                else:
                    data[name] = entry._resolve_field(group_name, name)
            elif is_trigger_model_field(field):
                if not include_reactive:
                    data.pop(name, None)
                else:
                    idle: object = False
                    if entry is not None and isinstance(group_name, str):
                        tmode = type(entry)._cfg_trigger_modes.get((group_name, name))
                        if tmode is not None:
                            idle = tmode[2]
                    data[name] = idle
        return data


class ConfigTableColumn(ConfigGroup):
    """表格列基类。同一子类在 Entry 上的多个字段 = 一表多列。

    - ``_table_key``：i18n 键片段；标题文案由前端解析，可为 ``None``（无标题）。
    - ``_table_transpose``：为 ``True`` 时 UI 行列转置展示。
    """

    _table_key: ClassVar[str | None] = None
    _table_transpose: ClassVar[bool] = False
