"""L3 配置分组：嵌套在 ConfigEntry 内的字段块（如 info、data）。

``__getattribute__`` / ``__setattr__`` 按字段类型分流：

- 普通 / ref / 内置类型：读经 ``entry._resolve_field``，写经 ``entry`` 框架链。
- 加密字段：内存 ``EncryptedValue``，读 unwrap 为明文。
- 虚拟字段：只读；运行时计算。
- 触发器字段：读取空闲或操作 UUID，按三态命令派发。
- 日期时间：Pydantic 校验后统一存为 UTC；属性读取按预设转换，序列化直接导出存储值。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, ClassVar, cast
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    PrivateAttr,
    SerializationInfo,
    field_validator,
    model_serializer,
)
from pydantic_core.core_schema import SerializerFunctionWrapHandler

from app.utils import UTC8

from ..fields import (
    is_trigger_model_field,
    is_virtual_model_field,
)
from ..fields.hints import UI_MASKED_VALUE, UiVisibility
from ..fields.ref import validate_trigger_command
from ..types import TzMarker
from .node import ExportContext, NodeState
from .staging import StagedOp

if TYPE_CHECKING:
    from .entry import ConfigEntry


class ConfigGroup(BaseModel):
    """L3 配置分组。"""

    model_config = ConfigDict(validate_assignment=True, validate_default=True)
    _trigger_uids: dict[str, UUID] = PrivateAttr(default_factory=dict)

    @field_validator("*", mode="after")
    @classmethod
    def _utc_storage(cls, value: object) -> object:
        """无时区输入视为 UTC；不依赖所属配置、字段顺序或读取预设。"""
        if not isinstance(value, datetime):
            return value
        try:
            return (
                value.replace(tzinfo=timezone.utc)
                if value.utcoffset() is None
                else value.astimezone(timezone.utc)
            )
        except OverflowError as exc:
            raise ValueError("日期时间转为 UTC 后超出范围") from exc

    def _read_zone(self, name: str) -> timezone:
        """解析字段的读取预设；无声明时使用来源框架的 UTC+8 默认值。"""
        markers = [
            marker
            for marker in type(self).model_fields[name].metadata
            if isinstance(marker, TzMarker)
        ]
        if len(markers) > 1:
            raise ValueError("同一字段不能声明多个读取时区")
        return markers[0].resolve(self) if markers else UTC8

    # ── 读路径 ──

    # 可变字段只支持复制、修改后整字段赋值并 commit，不支持 append、下标赋值等原地修改。
    # TODO(R11): 后续统一处理读取引用泄漏及嵌套可变值隔离；当前原地修改会绕过
    # 锁、校验、信号和事务回滚，不能视为受配置框架保护的写入。
    def __getattribute__(self, name: str) -> object:
        if name.startswith("_"):
            return object.__getattribute__(self, name)
        cls: type[ConfigGroup] = object.__getattribute__(self, "__class__")
        fields = cls.model_fields
        if name not in fields:
            return object.__getattribute__(self, name)

        state: dict[str, object] = object.__getattribute__(self, "__dict__")
        entry = state.get("_entry")
        group = state.get("_group")
        if entry is None or group is None:
            value = None if is_trigger_model_field(fields[name]) else state.get(name)
        else:
            value = cast("ConfigEntry", entry)._resolve_field(str(group), name)
        if isinstance(value, datetime):
            try:
                return value.astimezone(self._read_zone(name))
            except OverflowError as exc:
                raise ValueError("日期时间转为读取时区后超出范围") from exc
        return value

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
            return super().__setattr__(name, value)

        entry = cast("ConfigEntry", entry)
        assert isinstance(group, str)

        if is_virtual_model_field(field):
            raise AttributeError(f"虚拟字段 {group}.{name} 只读")

        if is_trigger_model_field(field):
            entry._apply_trigger_field(group, name, validate_trigger_command(value))
            return

        workspace = entry.effective
        if workspace is not entry and workspace.__dict__.get(group) is self:
            entry._require_write_access()
            # 父层引用也只能写本边界，不能绕过局部回退直接修改父壳。
            entry._build_workspace()
            target = entry.effective.__dict__[group]
            target.__pydantic_validator__.validate_assignment(
                target, name, value, context={"entry": entry}
            )
            return

        if entry.activation_state == NodeState.INACTIVE:
            entry._require_write_access()
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
        state = object.__getattribute__(self, "__dict__")
        entry = cast("ConfigEntry | None", state.get("_entry"))
        group_name = state.get("_group")
        # 按当前对象的存储值序列化，不把整个分组隐式切换到工作区。
        data = cast(dict[str, Any], handler(self))
        # mode=python：与 audience 正交，不做响应式注入 / UI 裁剪
        if info.mode == "python":
            return data
        ctx = ExportContext.from_dump(info.context)
        include_reactive = ctx.audience == "api"
        for name, field in type(self).model_fields.items():
            if ctx.audience == "api":
                visibility = (
                    entry._ui_visibility(group_name, name)
                    if entry is not None and isinstance(group_name, str)
                    else UiVisibility.SHOW
                )
                if visibility == UiVisibility.MASKED:
                    data[name] = UI_MASKED_VALUE
                    continue
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
                    value = (
                        entry._resolve_field(group_name, name)
                        if entry is not None and isinstance(group_name, str)
                        else None
                    )
                    data[name] = str(value) if isinstance(value, UUID) else None
        return data


class ConfigTableColumn(ConfigGroup):
    """表格列基类。同一子类在 Entry 上的多个字段 = 一表多列。

    - ``_table_key``：i18n 键片段；标题文案由前端解析，可为 ``None``（无标题）。
    - ``_table_transpose``：为 ``True`` 时 UI 行列转置展示。
    """

    _table_key: ClassVar[str | None] = None
    _table_transpose: ClassVar[bool] = False
