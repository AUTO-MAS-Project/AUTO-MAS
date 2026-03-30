from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from collections.abc import Callable, Coroutine
from typing import Any, ClassVar, cast

from pydantic import BaseModel, ConfigDict, PrivateAttr

from .base import (
    MultipleConfig,
    backup_legacy_config_if_needed,
    dump_toml,
    load_config_with_legacy_migration,
)
from .types import _EncryptedFieldMarker, decrypt_encrypted_string


SaveMethod = Callable[[], Coroutine[Any, Any, None]]
Slot = Callable[[Any], Any] | Callable[[Any], Coroutine[Any, Any, Any]]


def _default_save_methods() -> list[SaveMethod]:
    return []


def _default_bindings() -> dict[tuple[str, str], list[Slot]]:
    return {}


def _normalize_mapping(value: Any) -> dict[str, Any]:
    """将任意映射值规范化为 `dict[str, Any]`。"""

    if not isinstance(value, dict):
        return {}
    mapping = cast(dict[object, Any], value)
    return {str(key): item for key, item in mapping.items()}


def _is_encrypted_field(group_model: BaseModel, field_name: str) -> bool:
    """判断字段是否为对外需要自动解密的字符串字段。"""

    field = type(group_model).model_fields.get(field_name)
    if field is None:
        return False
    return any(isinstance(item, _EncryptedFieldMarker) for item in field.metadata)


def _export_group_model(group_model: BaseModel, if_decrypt: bool) -> dict[str, Any]:
    """将分组模型导出为字典，并按需解密加密字段。"""

    data: dict[str, Any] = {}

    for field_name in type(group_model).model_fields:
        value = getattr(group_model, field_name)

        if isinstance(value, BaseModel):
            data[field_name] = _export_group_model(value, if_decrypt)
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
    _file: Path | None = PrivateAttr(default=None)
    _is_locked: bool = PrivateAttr(default=False)
    _save_methods: list[SaveMethod] = PrivateAttr(default_factory=_default_save_methods)
    _bindings: dict[tuple[str, str], list[Slot]] = PrivateAttr(
        default_factory=_default_bindings
    )

    @property
    def file(self) -> Path | None:
        return self._file

    @property
    def is_locked(self) -> bool:
        return self._is_locked

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
        return value

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
            data[group_name] = _export_group_model(group_model, if_decrypt)

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

        old_value = getattr(group_model, name)
        value = self._normalize_value(group, name, value)

        default_group = type(group_model)()
        try:
            setattr(group_model, name, value)
        except Exception:
            setattr(group_model, name, getattr(default_group, name))

        new_value = getattr(group_model, name)
        if old_value != new_value:
            await self._emit_bindings(group, name, new_value)

        if self._file:
            await self.save()

        if self._save_methods:
            await asyncio.gather(*(_() for _ in self._save_methods))

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
            if inspect.iscoroutinefunction(slot):
                await slot(value)
            else:
                slot(value)

    async def save(self) -> None:
        if not self._file:
            raise ValueError("文件路径未设置, 请先调用 `connect` 方法连接配置文件")

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
