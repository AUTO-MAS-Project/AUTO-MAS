"""L3 配置分组：嵌套在 ConfigEntry 内的字段块（如 info、data）。

``__getattribute__`` / ``__setattr__`` 按字段类型分流：

- 普通 / ref / 内置类型：读经 ``entry._resolve_field``，写经 ``entry`` 框架链。
- 加密字段：内存 ``EncryptedValue``，读 unwrap 为明文。
- 虚拟字段：只读；运行时计算。
- 触发器字段：仅 bool；读恒 ``False``，``True`` 执行一次 handler。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Literal, cast

from pydantic import BaseModel, ConfigDict, model_validator
from pydantic.main import IncEx

from .encrypted import is_encrypted_model_field, protect_encrypted_input
from .fields import (
    is_trigger_model_field,
    is_virtual_model_field,
)
from .manager import config_manager
from .node import NodeState
from .staging import StagedOp
from .wire import ExportContext, WireDict

if TYPE_CHECKING:
    from .entry import ConfigEntry


class ConfigGroup(BaseModel):
    """L3 配置分组。"""

    model_config = ConfigDict(
        validate_assignment=True,
        validate_default=True,
        hide_input_in_errors=True,
        extra="forbid",
    )

    @model_validator(mode="before")
    @classmethod
    def _protect_encrypted_transport_inputs(cls, value: object) -> object:
        """Keep secret-bearing request input out of Pydantic/FastAPI errors."""
        if not isinstance(value, dict):
            return value
        protected = dict(value)
        for name, field in cls.model_fields.items():
            if name in protected and is_encrypted_model_field(field):
                protected[name] = protect_encrypted_input(protected[name])
        return protected

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
            if not isinstance(value, bool):
                raise TypeError(f"触发器 {name} 仅接受 bool 类型")
            if value:
                entry._dispatch_trigger(group, name)
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
            # 未激活：纯 pydantic 校验直写（无事务 / 信号）
            self.__pydantic_validator__.validate_assignment(self, name, value)
            return

        entry._stage(StagedOp.field_set(group, name, value))

    def model_dump(
        self,
        *,
        mode: Literal["json", "python"] | str = "python",
        include: IncEx | None = None,
        exclude: IncEx | None = None,
        context: object | None = None,
        by_alias: bool | None = None,
        exclude_unset: bool = False,
        exclude_defaults: bool = False,
        exclude_none: bool = False,
        round_trip: bool = False,
        warnings: bool | Literal["none", "warn", "error"] = True,
        serialize_as_any: bool = False,
        fallback: Callable[[object], object] | None = None,
    ) -> WireDict:
        data = cast(
            WireDict,
            super().model_dump(
                mode=mode,
                include=include,
                exclude=exclude,
                context=context,
                by_alias=by_alias,
                exclude_unset=exclude_unset,
                exclude_defaults=exclude_defaults,
                exclude_none=exclude_none,
                round_trip=round_trip,
                warnings=warnings,
                serialize_as_any=serialize_as_any,
                fallback=fallback,
            ),
        )
        ctx = context if isinstance(context, ExportContext) else ExportContext()
        state = object.__getattribute__(self, "__dict__")
        entry = cast("ConfigEntry | None", state.get("_entry"))
        group_name = state.get("_group")
        for name, field in type(self).model_fields.items():
            if is_virtual_model_field(field):
                if (
                    not ctx.include_reactive
                    or entry is None
                    or not isinstance(group_name, str)
                ):
                    data.pop(name, None)
                else:
                    data[name] = entry._resolve_field(group_name, name)
            elif is_trigger_model_field(field):
                if not ctx.include_reactive:
                    data.pop(name, None)
                else:
                    data[name] = False
        return data
