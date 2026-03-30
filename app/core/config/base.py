#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


from __future__ import annotations

import asyncio
import inspect
import json
import tomllib
import uuid
import weakref
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any, Generic, Protocol, TypeVar


PRIMARY_CONFIG_SUFFIX = ".toml"
LEGACY_CONFIG_SUFFIX = ".json"


def _toml_key(key: str) -> str:
    """生成兼容 UUID 等特殊字符的 TOML 键名。"""

    return json.dumps(str(key), ensure_ascii=False)


def _toml_path(path: tuple[str, ...]) -> str:
    """生成 TOML 表头路径。"""

    return ".".join(_toml_key(part) for part in path)


def _toml_scalar(value: Any) -> str:
    """序列化 TOML 标量值。"""

    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if value is None:
        return '""'
    return json.dumps(str(value), ensure_ascii=False)


def _toml_inline(value: Any) -> str:
    """序列化内联 TOML 值，支持数组和内联表。"""

    if isinstance(value, dict):
        items = ", ".join(
            f"{_toml_key(str(key))} = {_toml_inline(item)}"
            for key, item in value.items()
        )
        return "{ " + items + " }"
    if isinstance(value, list):
        return "[" + ", ".join(_toml_inline(item) for item in value) + "]"
    return _toml_scalar(value)


def dump_toml(data: dict[str, Any]) -> str:
    """公共 TOML 序列化入口。"""

    lines: list[str] = []

    def emit_table(path: tuple[str, ...], obj: dict[str, Any]) -> None:
        scalars: list[tuple[str, Any]] = []
        children: list[tuple[str, dict[str, Any]]] = []

        for key, value in obj.items():
            if isinstance(value, dict):
                children.append((str(key), value))
            else:
                scalars.append((str(key), value))

        if path:
            lines.append(f"[{_toml_path(path)}]")

        for key, value in scalars:
            lines.append(f"{_toml_key(key)} = {_toml_inline(value)}")

        if scalars and children:
            lines.append("")

        for index, (key, child) in enumerate(children):
            emit_table((*path, key), child)
            if index != len(children) - 1:
                lines.append("")

    emit_table((), data)
    content = "\n".join(lines).strip()
    return f"{content}\n" if content else ""


def _load_json_config(path: Path) -> dict[str, Any]:
    raw_text = path.read_text(encoding="utf-8")
    if raw_text.strip() == "":
        return {}

    loaded = json.loads(raw_text)
    return loaded if isinstance(loaded, dict) else {}


def _load_toml_config(path: Path) -> dict[str, Any]:
    raw_text = path.read_text(encoding="utf-8")
    if raw_text.strip() == "":
        return {}

    loaded = tomllib.loads(raw_text)
    return loaded if isinstance(loaded, dict) else {}


def _load_config_with_legacy_migration(path: Path) -> tuple[dict[str, Any], Path | None]:
    legacy_json_file = path.with_suffix(LEGACY_CONFIG_SUFFIX)

    if legacy_json_file.exists() and (not path.exists() or path.stat().st_size == 0):
        try:
            return _load_json_config(legacy_json_file), legacy_json_file
        except json.JSONDecodeError:
            return {}, legacy_json_file

    if not path.exists():
        return {}, legacy_json_file if legacy_json_file.exists() else None

    try:
        return _load_toml_config(path), legacy_json_file if legacy_json_file.exists() else None
    except tomllib.TOMLDecodeError:
        if legacy_json_file.exists():
            with suppress(json.JSONDecodeError):
                return _load_json_config(legacy_json_file), legacy_json_file
        return {}, legacy_json_file if legacy_json_file.exists() else None


def _backup_legacy_config_if_needed(
    current_file: Path, legacy_file: Path | None
) -> None:
    if legacy_file is None or not legacy_file.exists():
        return
    if not current_file.exists() or current_file.stat().st_size == 0:
        return

    legacy_backup = legacy_file.with_suffix(f"{legacy_file.suffix}.bak")
    if not legacy_backup.exists():
        legacy_file.replace(legacy_backup)


def load_config_with_legacy_migration(
    path: Path,
) -> tuple[dict[str, Any], Path | None]:
    """公开的兼容加载入口，供其他模块调用。"""

    return _load_config_with_legacy_migration(path)


def backup_legacy_config_if_needed(
    current_file: Path, legacy_file: Path | None
) -> None:
    """公开的旧版配置备份入口，供其他模块调用。"""

    _backup_legacy_config_if_needed(current_file, legacy_file)


class _ConfigLike(Protocol):
    @property
    def is_locked(self) -> bool: ...

    async def add_save_method(
        self, save_method: Callable[[], Coroutine[Any, Any, None]]
    ) -> None: ...

    async def load(self, data: dict[str, Any]) -> None: ...

    async def toDict(
        self, if_decrypt: bool = True, regenerate_uuids: bool = False
    ) -> dict[str, Any]: ...

    async def lock(self) -> None: ...

    async def unlock(self) -> None: ...


T = TypeVar("T", bound=_ConfigLike)


CollectionEventSlot = Callable[[Any], Any] | Callable[[Any], Coroutine[Any, Any, Any]]


@dataclass(slots=True)
class MultipleConfigAddEvent(Generic[T]):
    """新增配置项事件。"""

    collection: "MultipleConfig[T]"
    uid: uuid.UUID
    config: T


@dataclass(slots=True)
class MultipleConfigDeleteEvent(Generic[T]):
    """删除配置项事件。"""

    collection: "MultipleConfig[T]"
    uid: uuid.UUID
    config: T


@dataclass(slots=True)
class MultipleConfigReorderEvent(Generic[T]):
    """重排配置项事件。"""

    collection: "MultipleConfig[T]"
    order: list[uuid.UUID]


def _callback_identity(callback: CollectionEventSlot) -> object:
    """生成回调唯一标识。"""

    if inspect.ismethod(callback) and getattr(callback, "__self__", None) is not None:
        return (id(callback.__self__), callback.__func__)
    return callback


@dataclass(slots=True)
class _WeakCallbackSlot:
    """容器事件弱引用回调槽。"""

    identity: object
    callback: CollectionEventSlot | None = None
    weak_method: weakref.WeakMethod[Any] | None = None

    @classmethod
    def build(cls, callback: CollectionEventSlot) -> "_WeakCallbackSlot":
        if inspect.ismethod(callback) and getattr(callback, "__self__", None) is not None:
            return cls(
                identity=_callback_identity(callback),
                weak_method=weakref.WeakMethod(callback),
            )
        return cls(identity=_callback_identity(callback), callback=callback)

    def resolve(self) -> CollectionEventSlot | None:
        if self.weak_method is not None:
            resolved = self.weak_method()
            if resolved is None:
                return None
            return resolved
        return self.callback


async def _emit_collection_slots(
    slots: list[_WeakCallbackSlot], event: Any
) -> None:
    """依次触发容器事件回调，并清理失效弱引用。"""

    alive_slots: list[_WeakCallbackSlot] = []

    for slot in slots:
        callback = slot.resolve()
        if callback is None:
            continue

        alive_slots.append(slot)
        result = callback(event)
        if inspect.isawaitable(result):
            await result

    slots[:] = alive_slots


class MultipleConfig(Generic[T]):
    """
    多配置项管理类。

    负责管理同一类或同一组配置实例，并统一提供加载、保存、增删改序等接口。
    """

    def __init__(self, sub_config_type: list[type[T]]):
        if not sub_config_type:
            raise ValueError("子配置项类型列表不能为空")

        self.sub_config_type: dict[str, type[T]] = {
            config_type.__name__: config_type for config_type in sub_config_type
        }
        self.file: Path | None = None
        self.order: list[uuid.UUID] = []
        self.data: dict[uuid.UUID, T] = {}
        self.is_locked = False
        self._save_methods: list[Callable[[], Coroutine[Any, Any, None]]] = []
        self._transaction_depth = 0
        self._pending_save = False
        self._pending_sync = False
        self._on_add_slots: list[_WeakCallbackSlot] = []
        self._on_before_del_slots: list[_WeakCallbackSlot] = []
        self._on_del_slots: list[_WeakCallbackSlot] = []
        self._on_reorder_slots: list[_WeakCallbackSlot] = []

    def __getitem__(self, key: uuid.UUID) -> T:
        if key not in self.data:
            raise KeyError(f"配置项 '{key}' 不存在")
        return self.data[key]

    def __contains__(self, key: uuid.UUID) -> bool:
        return key in self.data

    def __len__(self) -> int:
        return len(self.data)

    def __repr__(self) -> str:
        return (
            "MultipleConfig("
            f"items={len(self.data)}, "
            f"types={list(self.sub_config_type.keys())}"
            ")"
        )

    def __str__(self) -> str:
        return f"MultipleConfig with {len(self.data)} items"

    async def connect(self, path: Path) -> None:
        """将运行期配置连接到指定 TOML 文件。"""

        if path.suffix != PRIMARY_CONFIG_SUFFIX:
            raise ValueError("配置文件必须是带有 '.toml' 扩展名的 TOML 文件。")

        if self.is_locked:
            raise ValueError("配置已锁定, 无法修改")

        self.file = path

        if not self.file.exists():
            self.file.parent.mkdir(parents=True, exist_ok=True)
            self.file.touch()

        data, legacy_file = _load_config_with_legacy_migration(self.file)
        await self.load(data)
        await self.add_save_method(self.save)
        _backup_legacy_config_if_needed(self.file, legacy_file)

    async def add_save_method(
        self, save_method: Callable[[], Coroutine[Any, Any, None]]
    ) -> None:
        """为当前管理器及其子配置添加级联保存方法。"""

        if save_method != self.save and save_method not in self._save_methods:
            self._save_methods.append(save_method)

        for sub_config in self.data.values():
            await sub_config.add_save_method(save_method)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["MultipleConfig[T]"]:
        """开启一个延迟保存事务。"""

        self._transaction_depth += 1
        try:
            yield self
        finally:
            self._transaction_depth -= 1
            if self._transaction_depth == 0:
                await self._flush_pending_changes()

    async def _flush_pending_changes(self) -> None:
        """提交事务期间累积的保存请求。"""

        if self._pending_save and self.file:
            self._pending_save = False
            self.file.parent.mkdir(parents=True, exist_ok=True)
            self.file.write_text(
                dump_toml(await self.toDict(if_decrypt=False)),
                encoding="utf-8",
            )

        if self._pending_sync:
            self._pending_sync = False
            if self._save_methods:
                await asyncio.gather(*(_() for _ in self._save_methods))

    async def load(self, data: dict[str, Any]) -> None:
        """从字典加载多实例配置数据。"""

        if self.is_locked:
            raise ValueError("配置已锁定, 无法修改")

        self.order = []
        self.data = {}

        instances = data.get("instances")
        if not isinstance(instances, list):
            return

        for instance in instances:
            if not isinstance(instance, dict):
                continue

            uid_str = instance.get("uid")
            type_name = instance.get("type")
            if not isinstance(uid_str, str) or not isinstance(type_name, str):
                continue
            if type_name not in self.sub_config_type:
                continue

            instance_data = data.get(uid_str)
            if not isinstance(instance_data, dict):
                continue

            try:
                uid = uuid.UUID(uid_str)
            except (TypeError, ValueError):
                continue

            config = self.sub_config_type[type_name]()
            if hasattr(config, "_bind_owner_collection"):
                config._bind_owner_collection(self, uid)
            self.order.append(uid)
            self.data[uid] = config
            await config.load(instance_data)

        if self.file:
            await self.save()

        if self._save_methods:
            await asyncio.gather(*(_() for _ in self._save_methods))

    async def toDict(
        self, if_decrypt: bool = True, regenerate_uuids: bool = False
    ) -> dict[str, Any]:
        """将全部子配置序列化为统一字典结构。"""

        uuid_book: dict[uuid.UUID, uuid.UUID] = {
            uid: uuid.uuid4() if regenerate_uuids else uid for uid in self.order
        }

        data: dict[str, Any] = {
            "instances": [
                {"uid": str(uuid_book[uid]), "type": type(self.data[uid]).__name__}
                for uid in self.order
            ]
        }

        for uid, config in self.items():
            data[str(uuid_book[uid])] = await config.toDict(
                if_decrypt, regenerate_uuids
            )

        return data

    async def get(self, uid: uuid.UUID) -> dict[str, Any]:
        """获取指定 UID 的单个配置。"""

        if uid not in self.data:
            raise ValueError(f"配置项 '{uid}' 不存在。")

        data: dict[str, Any] = {
            "instances": [
                {"uid": str(current_uid), "type": type(self.data[current_uid]).__name__}
                for current_uid in self.order
                if current_uid == uid
            ]
        }
        data[str(uid)] = await self.data[uid].toDict()
        return data

    async def save(self) -> None:
        """保存当前多实例配置。"""

        if not self.file:
            raise ValueError("文件路径未设置, 请先调用 `connect` 方法连接配置文件")

        if self._transaction_depth > 0:
            self._pending_save = True
            return

        self.file.parent.mkdir(parents=True, exist_ok=True)
        self.file.write_text(
            dump_toml(await self.toDict(if_decrypt=False)),
            encoding="utf-8",
        )

    async def add(self, config_type: type[T]) -> tuple[uuid.UUID, T]:
        """新增一个指定类型的子配置实例。"""

        if config_type not in self.sub_config_type.values():
            raise ValueError(f"配置类型 {config_type.__name__} 不被允许")
        if self.is_locked:
            raise ValueError("配置已锁定, 无法修改")

        uid = uuid.uuid4()
        config = config_type()
        if hasattr(config, "_bind_owner_collection"):
            config._bind_owner_collection(self, uid)
        self.order.append(uid)
        self.data[uid] = config

        for save_method in self._save_methods:
            await config.add_save_method(save_method)

        if self.file:
            await config.add_save_method(self.save)
            await self.save()

        if self._transaction_depth > 0:
            self._pending_sync = self._pending_sync or bool(self._save_methods)
        elif self._save_methods:
            await asyncio.gather(*(_() for _ in self._save_methods))

        await _emit_collection_slots(
            self._on_add_slots, MultipleConfigAddEvent(self, uid, config)
        )

        return uid, config

    async def remove(self, uid: uuid.UUID) -> None:
        """移除一个子配置实例。"""

        if self.is_locked:
            raise ValueError("配置已锁定, 无法修改")
        if uid not in self.data:
            raise ValueError(f"配置项 '{uid}' 不存在")
        if self.data[uid].is_locked:
            raise ValueError(f"配置项 '{uid}' 已锁定, 无法移除")

        config = self.data[uid]
        await _emit_collection_slots(
            self._on_before_del_slots, MultipleConfigDeleteEvent(self, uid, config)
        )

        self.data.pop(uid)
        self.order.remove(uid)

        if self.file:
            await self.save()

        if self._transaction_depth > 0:
            self._pending_sync = self._pending_sync or bool(self._save_methods)
        elif self._save_methods:
            await asyncio.gather(*(_() for _ in self._save_methods))

        await _emit_collection_slots(
            self._on_del_slots, MultipleConfigDeleteEvent(self, uid, config)
        )

    async def setOrder(self, order: list[uuid.UUID]) -> None:  # noqa: N802
        """设置子配置实例顺序。"""

        if set(order) != set(self.data.keys()):
            raise ValueError("顺序与当前配置项不匹配")
        if self.is_locked:
            raise ValueError("配置已锁定, 无法修改")

        self.order = order

        if self.file:
            await self.save()

        if self._transaction_depth > 0:
            self._pending_sync = self._pending_sync or bool(self._save_methods)
        elif self._save_methods:
            await asyncio.gather(*(_() for _ in self._save_methods))

        await _emit_collection_slots(
            self._on_reorder_slots, MultipleConfigReorderEvent(self, list(order))
        )

    async def lock(self) -> None:
        """锁定当前管理器及全部子配置。"""

        self.is_locked = True
        for item in self.values():
            await item.lock()

    async def unlock(self) -> None:
        """解锁当前管理器及全部子配置。"""

        self.is_locked = False
        for item in self.values():
            await item.unlock()

    def keys(self):
        """返回全部 UID。"""

        return iter(tuple(self.order))

    def values(self):
        """按顺序返回全部子配置实例。"""

        if not self.data:
            return iter(())
        order_snapshot = tuple(self.order)
        return iter(tuple(self.data[uid] for uid in order_snapshot if uid in self.data))

    def items(self):
        """按顺序返回 `(uid, config)` 对。"""

        order_snapshot = tuple(self.order)
        return iter(
            tuple((uid, self.data[uid]) for uid in order_snapshot if uid in self.data)
        )

    def bind_add(self, slot: CollectionEventSlot) -> None:
        """绑定新增事件。"""

        identity = _callback_identity(slot)
        if any(item.identity == identity for item in self._on_add_slots):
            return
        self._on_add_slots.append(_WeakCallbackSlot.build(slot))

    def bind_before_del(self, slot: CollectionEventSlot) -> None:
        """绑定删除前事件。"""

        identity = _callback_identity(slot)
        if any(item.identity == identity for item in self._on_before_del_slots):
            return
        self._on_before_del_slots.append(_WeakCallbackSlot.build(slot))

    def bind_del(self, slot: CollectionEventSlot) -> None:
        """绑定删除后事件。"""

        identity = _callback_identity(slot)
        if any(item.identity == identity for item in self._on_del_slots):
            return
        self._on_del_slots.append(_WeakCallbackSlot.build(slot))

    def bind_reorder(self, slot: CollectionEventSlot) -> None:
        """绑定重排事件。"""

        identity = _callback_identity(slot)
        if any(item.identity == identity for item in self._on_reorder_slots):
            return
        self._on_reorder_slots.append(_WeakCallbackSlot.build(slot))

    def unbind_add(self, slot: CollectionEventSlot) -> None:
        """解绑新增事件。"""

        identity = _callback_identity(slot)
        self._on_add_slots = [
            item for item in self._on_add_slots if item.identity != identity
        ]

    def unbind_before_del(self, slot: CollectionEventSlot) -> None:
        """解绑删除前事件。"""

        identity = _callback_identity(slot)
        self._on_before_del_slots = [
            item for item in self._on_before_del_slots if item.identity != identity
        ]

    def unbind_del(self, slot: CollectionEventSlot) -> None:
        """解绑删除后事件。"""

        identity = _callback_identity(slot)
        self._on_del_slots = [
            item for item in self._on_del_slots if item.identity != identity
        ]

    def unbind_reorder(self, slot: CollectionEventSlot) -> None:
        """解绑重排事件。"""

        identity = _callback_identity(slot)
        self._on_reorder_slots = [
            item for item in self._on_reorder_slots if item.identity != identity
        ]
