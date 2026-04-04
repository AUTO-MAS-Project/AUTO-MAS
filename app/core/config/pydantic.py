from __future__ import annotations

import asyncio
import inspect
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from collections.abc import Callable, Coroutine
from collections.abc import AsyncIterator
from typing import Any, ClassVar, TypeVar, cast

from pydantic import BaseModel, ConfigDict, PrivateAttr

from .base import (
    MultipleConfig,
    MultipleConfigDeleteEvent,
    backup_legacy_config_if_needed,
    dump_toml,
    load_config_with_legacy_migration,
)
from .fields import RefField, VirtualField
from .types import EncryptedFieldMarker, decrypt_encrypted_string


SaveMethod = Callable[[], Coroutine[Any, Any, None]]
Slot = Callable[[Any], Any] | Callable[[Any], Coroutine[Any, Any, Any]]


def _default_save_methods() -> list[SaveMethod]:
    return []


def _default_bindings() -> dict[tuple[str, str], list[Slot]]:
    return {}


def _default_pending_bindings() -> dict[tuple[str, str], Any]:
    return {}


def _default_registered_ref_targets() -> set[str]:
    return set()


def _normalize_mapping(value: Any) -> dict[str, Any]:
    """将任意映射值规范化为 `dict[str, Any]`。"""

    if not isinstance(value, dict):
        return {}
    mapping = cast(dict[object, Any], value)
    return {str(key): item for key, item in mapping.items()}


FieldMarkerT = TypeVar("FieldMarkerT")


def _get_field_marker(
    group_model: BaseModel, field_name: str, marker_type: type[FieldMarkerT]
) -> FieldMarkerT | None:
    """获取字段上声明的特定元数据。"""

    field = type(group_model).model_fields.get(field_name)
    if field is None:
        return None

    for marker in field.metadata:
        if isinstance(marker, marker_type):
            return marker

    return None


def _is_encrypted_field(group_model: BaseModel, field_name: str) -> bool:
    """判断字段是否为对外需要自动解密的字符串字段。"""

    return _get_field_marker(group_model, field_name, EncryptedFieldMarker) is not None


def _export_group_model(
    owner: "PydanticConfigBase",
    group_name: str,
    group_model: BaseModel,
    if_decrypt: bool,
) -> dict[str, Any]:
    """将分组模型导出为字典，并按需解密加密字段。"""

    data: dict[str, Any] = {}

    for field_name in type(group_model).model_fields:
        virtual_field = _get_field_marker(group_model, field_name, VirtualField)
        if virtual_field is not None:
            data[field_name] = owner.get_virtual_value(
                group_name, field_name, virtual_field
            )
            continue

        value = getattr(group_model, field_name)

        if isinstance(value, BaseModel):
            data[field_name] = _export_group_model(owner, field_name, value, if_decrypt)
            continue

        if if_decrypt and _is_encrypted_field(group_model, field_name):
            data[field_name] = decrypt_encrypted_string(str(value))
            continue

        data[field_name] = value

    return data


class PydanticConfigBase(BaseModel):
    """基于 pydantic v2 的配置基类，兼容旧版 ConfigBase 常用接口。"""

    model_config = ConfigDict(extra="allow", validate_assignment=True)

    LEGACY_FIELD_MAP: ClassVar[dict[tuple[str, str], tuple[str, str]]] = {}
    related_config: ClassVar[dict[str, MultipleConfig[Any]]] = {}
    _file: Path | None = PrivateAttr(default=None)
    _is_locked: bool = PrivateAttr(default=False)
    _save_methods: list[SaveMethod] = PrivateAttr(default_factory=_default_save_methods)
    _bindings: dict[tuple[str, str], list[Slot]] = PrivateAttr(
        default_factory=_default_bindings
    )
    _transaction_depth: int = PrivateAttr(default=0)
    _pending_save: bool = PrivateAttr(default=False)
    _pending_sync: bool = PrivateAttr(default=False)
    _pending_bindings: dict[tuple[str, str], Any] = PrivateAttr(
        default_factory=_default_pending_bindings
    )
    _registered_ref_targets: set[str] = PrivateAttr(
        default_factory=_default_registered_ref_targets
    )
    _owner_collection: MultipleConfig[Any] | None = PrivateAttr(default=None)
    _owner_uid: uuid.UUID | None = PrivateAttr(default=None)

    @property
    def file(self) -> Path | None:
        return self._file

    @property
    def is_locked(self) -> bool:
        return self._is_locked

    def model_post_init(self, __context: Any) -> None:
        self._register_ref_bindings()

    def _multiple_config_index(self) -> dict[str, MultipleConfig[Any]]:
        result: dict[str, MultipleConfig[Any]] = {}
        for name, value in self.__dict__.items():
            if isinstance(value, MultipleConfig):
                result[name] = value
        return result

    def _group_index(self) -> dict[str, BaseModel]:
        result: dict[str, BaseModel] = {}
        for name in type(self).model_fields:
            value = getattr(self, name, None)
            if isinstance(value, BaseModel):
                result[name] = value
        return result

    def _normalize_value(self, group: str, name: str, value: Any) -> Any:
        ref_field = self._get_ref_field(group, name)
        if ref_field is not None:
            return self._normalize_ref_value(ref_field, value)
        return value

    def _bind_owner_collection(
        self, collection: MultipleConfig[Any], uid: uuid.UUID
    ) -> None:
        """记录当前配置项所属容器。"""

        self._owner_collection = collection
        self._owner_uid = uid

    def bind_owner_collection(
        self, collection: MultipleConfig[Any], uid: uuid.UUID
    ) -> None:
        """公开所属容器绑定入口，供 `MultipleConfig` 调用。"""

        self._bind_owner_collection(collection, uid)

    def _resolve_related_collection(self, target: str) -> MultipleConfig[Any] | None:
        value = getattr(self, target, None)
        if isinstance(value, MultipleConfig):
            return cast(MultipleConfig[Any], value)

        target_collection = type(self).related_config.get(target)
        if isinstance(target_collection, MultipleConfig):
            return target_collection

        return None

    def _get_ref_field(self, group: str, name: str) -> RefField | None:
        group_model = self._group_index().get(group)
        if group_model is None:
            return None
        return _get_field_marker(group_model, name, RefField)

    def _get_virtual_field(self, group: str, name: str) -> VirtualField | None:
        group_model = self._group_index().get(group)
        if group_model is None:
            return None
        return _get_field_marker(group_model, name, VirtualField)

    def _iter_ref_fields(self):
        for group_name, group_model in self._group_index().items():
            for field_name in type(group_model).model_fields:
                ref_field = _get_field_marker(group_model, field_name, RefField)
                if ref_field is not None:
                    yield group_name, field_name, ref_field

    def _iter_virtual_dependents(self, dependency: tuple[str, str]):
        for group_name, group_model in self._group_index().items():
            for field_name in type(group_model).model_fields:
                virtual_field = _get_field_marker(group_model, field_name, VirtualField)
                if virtual_field is None:
                    continue
                if dependency in virtual_field.depends_on:
                    yield group_name, field_name, virtual_field

    def _get_virtual_value(
        self, group: str, name: str, spec: VirtualField | None = None
    ) -> Any:
        spec = spec or self._get_virtual_field(group, name)
        if spec is None:
            raise AttributeError(f"配置项 '{group}.{name}' 不是虚拟字段")

        getter = spec.getter
        if isinstance(getter, str):
            result = getattr(self, getter)()
        else:
            result = getter(self)

        if inspect.isawaitable(result):
            raise TypeError(f"虚拟配置项 '{group}.{name}' 的 getter 不能是异步方法")

        return result

    def get_virtual_value(
        self, group: str, name: str, spec: VirtualField | None = None
    ) -> Any:
        """公开只读虚拟值访问入口，便于模块内辅助函数调用。"""

        return self._get_virtual_value(group, name, spec)

    async def _set_virtual_value(self, group: str, name: str, value: Any) -> None:
        spec = self._get_virtual_field(group, name)
        if spec is None:
            raise AttributeError(f"配置项 '{group}.{name}' 不是虚拟字段")
        if spec.setter is None:
            raise ValueError(f"虚拟配置项 '{group}.{name}' 为只读")

        setter = spec.setter
        if isinstance(setter, str):
            result = getattr(self, setter)(value)
        else:
            result = setter(self, value)

        if inspect.isawaitable(result):
            await result

    def _normalize_ref_value(self, spec: RefField, value: Any) -> Any:
        if value in spec.allow_values:
            return value
        if value == spec.default:
            return spec.default

        text = value if isinstance(value, str) else str(value)
        try:
            uid = uuid.UUID(text)
        except (TypeError, ValueError):
            return spec.default

        target_collection = self._resolve_related_collection(spec.target)
        if target_collection is None or uid not in target_collection:
            return spec.default

        return str(uid)

    def _display_name(self) -> str:
        info_model = self._group_index().get("Info")
        if info_model is not None and hasattr(info_model, "Name"):
            name = getattr(info_model, "Name")
            if isinstance(name, str) and name:
                return name
        if self._owner_uid is not None:
            return str(self._owner_uid)
        return type(self).__name__

    def _register_ref_bindings(self) -> None:
        for _, _, ref_field in self._iter_ref_fields():
            if ref_field.target in self._registered_ref_targets:
                continue

            target_collection = self._resolve_related_collection(ref_field.target)
            if target_collection is None:
                continue

            target_collection.bind_before_del(self._on_related_config_deleted)
            self._registered_ref_targets.add(ref_field.target)

    async def _on_related_config_deleted(
        self, event: MultipleConfigDeleteEvent[Any]
    ) -> None:
        matched_fields: list[tuple[str, str, RefField]] = []

        for group_name, field_name, ref_field in self._iter_ref_fields():
            target_collection = self._resolve_related_collection(ref_field.target)
            if target_collection is not event.collection:
                continue

            group_model = self._group_index().get(group_name)
            if group_model is None:
                continue

            if getattr(group_model, field_name) != str(event.uid):
                continue

            matched_fields.append((group_name, field_name, ref_field))

        if not matched_fields:
            return

        for group_name, field_name, ref_field in matched_fields:
            action = ref_field.on_delete

            if action == "restrict":
                raise RuntimeError(
                    f"{self._display_name()} 正在引用 {event.uid}, 无法删除"
                )

            if self.is_locked:
                raise RuntimeError(
                    f"{self._display_name()} 正在引用 {event.uid} 且已锁定, 无法删除"
                )

            if action == "set_default":
                await self.set(group_name, field_name, ref_field.default)
                continue

            if action == "cascade":
                if self._owner_collection is None or self._owner_uid is None:
                    raise RuntimeError(
                        f"{self._display_name()} 缺少所属容器信息, 无法级联删除"
                    )
                await self._owner_collection.remove(self._owner_uid)
                return

            if action == "custom":
                callback = ref_field.on_delete_callback
                if callback is None:
                    raise RuntimeError(
                        f"{group_name}.{field_name} 未声明自定义删除回调"
                    )

                if isinstance(callback, str):
                    result = getattr(self, callback)(event)
                else:
                    result = callback(self, event)

                if inspect.isawaitable(result):
                    await result
                continue

            raise ValueError(f"不支持的引用删除策略: {action}")

    async def _queue_binding(self, group: str, name: str, value: Any) -> None:
        self._pending_bindings[(group, name)] = value
        if self._transaction_depth == 0:
            await self._flush_pending_bindings()

    async def _flush_pending_bindings(self) -> None:
        while self._pending_bindings:
            pending_items = list(self._pending_bindings.items())
            self._pending_bindings.clear()
            for (group, name), value in pending_items:
                await self._emit_bindings(group, name, value)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["PydanticConfigBase"]:
        """开启一个延迟保存事务。"""

        self._transaction_depth += 1
        try:
            yield self
        finally:
            self._transaction_depth -= 1
            if self._transaction_depth == 0:
                await self._flush_pending_changes()

    async def _flush_pending_changes(self) -> None:
        await self._flush_pending_bindings()

        if self._pending_save and self._file:
            self._pending_save = False
            self._file.parent.mkdir(parents=True, exist_ok=True)
            self._file.write_text(
                dump_toml(await self.toDict(if_decrypt=False)),
                encoding="utf-8",
            )

        if self._pending_sync:
            self._pending_sync = False
            if self._save_methods:
                await asyncio.gather(*(_() for _ in self._save_methods))

    async def connect(self, path: Path) -> None:
        if path.suffix != ".toml":
            raise ValueError("配置文件必须是扩展名为 '.toml' 的 TOML 文件")

        if self._is_locked:
            raise ValueError("配置已锁定, 无法修改")

        self._file = path

        if not self._file.exists():
            self._file.parent.mkdir(parents=True, exist_ok=True)
            self._file.touch()

        data, legacy_file = load_config_with_legacy_migration(self._file)
        await self.load(data)
        await self.add_save_method(self.save)
        backup_legacy_config_if_needed(self._file, legacy_file)

    async def add_save_method(self, save_method: SaveMethod) -> None:
        if save_method != self.save and save_method not in self._save_methods:
            self._save_methods.append(save_method)

        for sub_config in self._multiple_config_index().values():
            await sub_config.add_save_method(save_method)

    async def load(self, data: dict[str, Any]) -> None:
        if self._is_locked:
            raise ValueError("配置已锁定, 无法修改")

        raw: dict[str, Any] = dict(data)

        sub_configs = _normalize_mapping(raw.pop("SubConfigsInfo", {}))

        for name, sub_config in self._multiple_config_index().items():
            data_for_sub = sub_configs.get(name)
            if isinstance(data_for_sub, dict):
                await sub_config.load(_normalize_mapping(data_for_sub))

        for group_name, group_model in self._group_index().items():
            group_data = _normalize_mapping(raw.get(group_name, {}))

            default_group = type(group_model)()
            for field_name in list(type(group_model).model_fields.keys()):
                if self._get_virtual_field(group_name, field_name) is not None:
                    continue

                candidate: Any = None
                has_value = False

                if field_name in group_data:
                    candidate = group_data[field_name]
                    has_value = True
                else:
                    legacy = self.LEGACY_FIELD_MAP.get((group_name, field_name))
                    if legacy is not None:
                        legacy_group, legacy_name = legacy
                        legacy_data = _normalize_mapping(raw.get(legacy_group, {}))
                        if legacy_name in legacy_data:
                            candidate = legacy_data[legacy_name]
                            has_value = True

                if not has_value:
                    continue

                candidate = self._normalize_value(group_name, field_name, candidate)
                try:
                    setattr(group_model, field_name, candidate)
                except Exception:
                    setattr(group_model, field_name, getattr(default_group, field_name))

        if self._file:
            await self.save()

        if self._save_methods:
            await asyncio.gather(*(_() for _ in self._save_methods))

    async def toDict(
        self, if_decrypt: bool = True, regenerate_uuids: bool = False
    ) -> dict[str, Any]:
        data: dict[str, Any] = {}

        for group_name, group_model in self._group_index().items():
            data[group_name] = _export_group_model(
                self, group_name, group_model, if_decrypt
            )

        for name, item in self._multiple_config_index().items():
            if "SubConfigsInfo" not in data:
                data["SubConfigsInfo"] = {}
            data["SubConfigsInfo"][name] = await item.toDict(
                if_decrypt, regenerate_uuids
            )

        return data

    def get(self, group: str, name: str) -> Any:
        group_model = self._group_index().get(group)
        if group_model is None or not hasattr(group_model, name):
            raise AttributeError(f"配置项 '{group}.{name}' 不存在")

        virtual_field = self._get_virtual_field(group, name)
        if virtual_field is not None:
            return self._get_virtual_value(group, name, virtual_field)

        value = getattr(group_model, name)
        if _is_encrypted_field(group_model, name):
            return decrypt_encrypted_string(str(value))
        return value

    async def set(self, group: str, name: str, value: Any) -> None:
        group_model = self._group_index().get(group)
        if group_model is None or not hasattr(group_model, name):
            raise AttributeError(f"配置项 '{group}.{name}' 不存在")

        if self._is_locked:
            raise ValueError("配置已锁定, 无法修改")

        virtual_field = self._get_virtual_field(group, name)
        if virtual_field is not None:
            await self._set_virtual_value(group, name, value)
            return

        old_value = getattr(group_model, name)
        virtual_old_values = {
            (virtual_group, virtual_name): self._get_virtual_value(
                virtual_group, virtual_name, virtual_field
            )
            for virtual_group, virtual_name, virtual_field in self._iter_virtual_dependents(
                (group, name)
            )
        }
        value = self._normalize_value(group, name, value)

        default_group = type(group_model)()
        try:
            setattr(group_model, name, value)
        except Exception:
            setattr(group_model, name, getattr(default_group, name))

        new_value = getattr(group_model, name)
        if old_value != new_value:
            await self._queue_binding(group, name, new_value)

        for (virtual_group, virtual_name), old_virtual_value in virtual_old_values.items():
            new_virtual_value = self.get(virtual_group, virtual_name)
            if old_virtual_value != new_virtual_value:
                await self._queue_binding(
                    virtual_group, virtual_name, new_virtual_value
                )

        if self._file:
            await self.save()

        if self._transaction_depth > 0:
            self._pending_sync = self._pending_sync or bool(self._save_methods)
        elif self._save_methods:
            await asyncio.gather(*(_() for _ in self._save_methods))

    async def set_many(self, values: dict[str, dict[str, Any]]) -> None:
        """批量更新多个配置项。"""

        async with self.transaction():
            for group, items in values.items():
                for name, value in items.items():
                    await self.set(group, name, value)

    def bind(self, group: str, name: str, slot: Slot) -> None:
        group_model = self._group_index().get(group)
        if group_model is None or not hasattr(group_model, name):
            raise AttributeError(f"配置项 '{group}.{name}' 不存在")

        if self._is_locked:
            raise ValueError("配置已锁定, 无法修改")

        key = (group, name)
        if key not in self._bindings:
            self._bindings[key] = []
        if slot not in self._bindings[key]:
            self._bindings[key].append(slot)

    def unbind(self, group: str, name: str, slot: Slot) -> None:
        group_model = self._group_index().get(group)
        if group_model is None or not hasattr(group_model, name):
            raise AttributeError(f"配置项 '{group}.{name}' 不存在")

        if self._is_locked:
            raise ValueError("配置已锁定, 无法修改")

        key = (group, name)
        if key in self._bindings and slot in self._bindings[key]:
            self._bindings[key].remove(slot)

    async def _emit_bindings(self, group: str, name: str, value: Any) -> None:
        key = (group, name)
        slots = self._bindings.get(key)
        if slots is None:
            return
        for slot in slots:
            result = slot(value)
            if inspect.isawaitable(result):
                await result

    async def save(self) -> None:
        if not self._file:
            raise ValueError("文件路径未设置, 请先调用 `connect` 方法连接配置文件")

        if self._transaction_depth > 0:
            self._pending_save = True
            return

        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(
            dump_toml(await self.toDict(if_decrypt=False)),
            encoding="utf-8",
        )

    async def lock(self) -> None:
        self._is_locked = True
        for config in self._multiple_config_index().values():
            await config.lock()

    async def unlock(self) -> None:
        self._is_locked = False
        for config in self._multiple_config_index().values():
            await config.unlock()
