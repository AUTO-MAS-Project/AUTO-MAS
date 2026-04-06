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
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from collections.abc import AsyncIterator, Callable, Coroutine, Iterator
from typing import Any, Generic, Protocol, TypeVar, cast, overload
from importlib import import_module

from loguru import logger
from filelock import FileLock, Timeout


tomli_w = import_module("tomli_w")


PRIMARY_CONFIG_SUFFIX = ".toml"
LEGACY_CONFIG_SUFFIX = ".json"


def dump_toml(data: dict[str, Any]) -> str:
    """
    使用 tomli-w 库序列化 TOML 数据。

    Args:
        data: 要序列化的字典数据

    Returns:
        TOML 格式的字符串

    Raises:
        TypeError: 如果数据包含不可序列化的类型
    """
    try:
        return cast(Any, tomli_w).dumps(data)
    except (TypeError, ValueError) as e:
        logger.error(f"TOML 序列化失败: {e}, 数据类型: {type(data)}")
        raise


def atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    """原子写入文本文件，使用跨进程文件锁 + 写后校验。"""

    temp_file = path.with_suffix(f"{path.suffix}.tmp")
    lock_file = path.with_suffix(f"{path.suffix}.lock")
    file_lock = FileLock(str(lock_file), timeout=10)
    try:
        with file_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp_file.write_text(content, encoding=encoding)

            verify_content = temp_file.read_text(encoding=encoding)
            if verify_content != content:
                raise OSError(f"配置写入校验失败: {path}")

            if os.name == "nt" and path.exists():
                backup_file = path.with_suffix(f"{path.suffix}.bak")
                try:
                    path.replace(backup_file)
                except OSError as backup_error:
                    logger.warning(
                        f"旧配置备份失败，尝试直接覆盖: {path}, 错误: {backup_error}"
                    )

            temp_file.replace(path)
    except Timeout as e:
        logger.error(f"获取配置文件锁超时: {path}, 错误: {e}")
        raise
    finally:
        if temp_file.exists():
            try:
                temp_file.unlink()
            except OSError as cleanup_error:
                logger.warning(
                    f"清理临时配置文件失败: {temp_file}, 错误: {cleanup_error}"
                )


def _load_json_config(path: Path) -> dict[str, Any]:
    """
    加载 JSON 配置文件。

    Args:
        path: 配置文件路径

    Returns:
        配置字典，如果文件为空或格式错误则返回空字典
    """
    try:
        raw_text = path.read_text(encoding="utf-8")
        if not raw_text.strip():
            logger.debug(f"配置文件为空: {path}")
            return {}

        loaded = json.loads(raw_text)
        if not isinstance(loaded, dict):
            logger.warning(f"配置文件不是字典类型: {path}, 类型: {type(loaded)}")
            return {}

        mapping = cast(dict[object, Any], loaded)
        return {str(key): item for key, item in mapping.items()}
    except json.JSONDecodeError as e:
        logger.error(f"JSON 解析失败: {path}, 错误: {e}")
        return {}
    except OSError as e:
        logger.error(f"读取 JSON 配置失败: {path}, 错误: {e}")
        return {}


def _load_toml_config(path: Path) -> dict[str, Any]:
    """
    加载 TOML 配置文件。

    Args:
        path: 配置文件路径

    Returns:
        配置字典，如果文件为空或格式错误则返回空字典
    """
    try:
        raw_text = path.read_text(encoding="utf-8")
        if not raw_text.strip():
            logger.debug(f"配置文件为空: {path}")
            return {}

        loaded = tomllib.loads(raw_text)
        mapping = cast(dict[object, Any], loaded)
        return {str(key): item for key, item in mapping.items()}
    except tomllib.TOMLDecodeError as e:
        logger.error(f"TOML 解析失败: {path}, 错误: {e}")
        return {}
    except OSError as e:
        logger.error(f"读取 TOML 配置失败: {path}, 错误: {e}")
        return {}


def _load_config_with_legacy_migration(
    path: Path,
) -> tuple[dict[str, Any], Path | None]:
    """
    加载配置文件，支持从 JSON 迁移到 TOML。

    优先级：
    1. 如果存在 .json 文件且 .toml 文件不存在或为空，则加载 .json
    2. 否则加载 .toml 文件
    3. 如果 .toml 加载失败，回退到 .json

    Args:
        path: TOML 配置文件路径

    Returns:
        (配置字典, 旧版 JSON 文件路径或 None)
    """
    legacy_json_file = path.with_suffix(LEGACY_CONFIG_SUFFIX)

    # 情况 1: JSON 存在且 TOML 不存在或为空
    if legacy_json_file.exists() and (not path.exists() or path.stat().st_size == 0):
        logger.info(f"从旧版 JSON 配置迁移: {legacy_json_file} -> {path}")
        data = _load_json_config(legacy_json_file)
        return data, legacy_json_file

    # 情况 2: TOML 不存在
    if not path.exists():
        logger.debug(f"配置文件不存在: {path}")
        return {}, legacy_json_file if legacy_json_file.exists() else None

    # 情况 3: 尝试加载 TOML
    data = _load_toml_config(path)
    if data or not legacy_json_file.exists():
        return data, legacy_json_file if legacy_json_file.exists() else None

    # 情况 4: TOML 加载失败，回退到 JSON
    logger.warning(f"TOML 加载失败，回退到 JSON: {legacy_json_file}")
    return _load_json_config(legacy_json_file), legacy_json_file


def _backup_legacy_config_if_needed(
    current_file: Path, legacy_file: Path | None
) -> None:
    """
    备份旧版 JSON 配置文件。

    仅在以下条件同时满足时备份：
    1. 旧版文件存在
    2. 新版文件存在且非空
    3. 备份文件不存在

    Args:
        current_file: 当前 TOML 配置文件路径
        legacy_file: 旧版 JSON 配置文件路径
    """
    if legacy_file is None or not legacy_file.exists():
        return
    if not current_file.exists() or current_file.stat().st_size == 0:
        return

    legacy_backup = legacy_file.with_suffix(f"{legacy_file.suffix}.bak")
    if not legacy_backup.exists():
        try:
            legacy_file.replace(legacy_backup)
            logger.info(f"已备份旧版配置: {legacy_file} -> {legacy_backup}")
        except OSError as e:
            logger.error(f"备份旧版配置失败: {legacy_file}, 错误: {e}")


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
        self,
        if_decrypt: bool = True,
        regenerate_uuids: bool = False,
        skip_virtual: bool = False,
    ) -> dict[str, Any]: ...

    async def lock(self) -> None: ...

    async def unlock(self) -> None: ...

    def bind_owner_collection(
        self, collection: "MultipleConfig[Any]", uid: uuid.UUID
    ) -> None: ...


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
        return id(callback.__self__), callback.__func__
    return callback


@dataclass(slots=True)
class _WeakCallbackSlot:
    """容器事件弱引用回调槽。"""

    identity: object
    callback: CollectionEventSlot | None = None
    weak_method: weakref.WeakMethod[Any] | None = None

    @classmethod
    def build(cls, callback: CollectionEventSlot) -> "_WeakCallbackSlot":
        if (
            inspect.ismethod(callback)
            and getattr(callback, "__self__", None) is not None
        ):
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


async def _emit_collection_slots(slots: list[_WeakCallbackSlot], event: Any) -> None:
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
        self._mutex = asyncio.Lock()

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
        """
        将运行期配置连接到指定 TOML 文件。

        Args:
            path: 配置文件路径，必须以 .toml 结尾

        Raises:
            ValueError: 如果文件扩展名不是 .toml 或配置已锁定
        """
        if path.suffix != PRIMARY_CONFIG_SUFFIX:
            raise ValueError(f"配置文件必须是 .toml 格式，当前: {path.suffix}")

        if self.is_locked:
            raise ValueError("配置已锁定，无法修改")

        async with self._mutex:
            logger.info(f"连接配置文件: {path}")
            self.file = path

            if not self.file.exists():
                self.file.parent.mkdir(parents=True, exist_ok=True)
                self.file.touch()
                logger.debug(f"创建新配置文件: {self.file}")

            try:
                data, legacy_file = _load_config_with_legacy_migration(self.file)
                await self.load(data)
                await self.add_save_method(self.save)
                _backup_legacy_config_if_needed(self.file, legacy_file)
                logger.info(f"配置加载成功: {path}, 项目数: {len(self.data)}")
            except (OSError, ValueError, TypeError) as e:
                logger.error(f"配置加载失败: {path}, 错误: {e}")
                raise

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
            await self._save_unlocked()

        if self._pending_sync:
            self._pending_sync = False
            if self._save_methods:
                await asyncio.gather(*(_() for _ in self._save_methods))

    async def _save_unlocked(self) -> None:
        """在已持有互斥锁时保存配置。"""

        if not self.file:
            raise ValueError("文件路径未设置，请先调用 connect() 方法")

        content = dump_toml(await self.toDict(if_decrypt=False))
        atomic_write_text(self.file, content)
        logger.debug(f"配置保存成功: {self.file}, 大小: {len(content)} 字节")

    async def load(self, data: dict[str, Any]) -> None:
        """从字典加载多实例配置数据。"""

        async with self._mutex:
            if self.is_locked:
                raise ValueError("配置已锁定, 无法修改")

            self.order = []
            self.data = {}

            instances = data.get("instances")
            if not isinstance(instances, list):
                return
            instances_list = cast(list[object], instances)

            for instance in instances_list:
                if not isinstance(instance, dict):
                    continue
                instance_dict = cast(dict[object, Any], instance)

                uid_str = instance_dict.get("uid")
                type_name = instance_dict.get("type")
                if not isinstance(uid_str, str) or not isinstance(type_name, str):
                    continue
                if type_name not in self.sub_config_type:
                    continue

                instance_data = data.get(uid_str)
                if not isinstance(instance_data, dict):
                    continue
                instance_data_dict = cast(dict[str, Any], instance_data)

                try:
                    uid = uuid.UUID(uid_str)
                except (TypeError, ValueError):
                    continue

                config = self.sub_config_type[type_name]()
                config.bind_owner_collection(self, uid)
                self.order.append(uid)
                self.data[uid] = config
                await config.load(instance_data_dict)

            if self.file:
                await self._save_unlocked()

            if self._save_methods:
                await asyncio.gather(*(_() for _ in self._save_methods))

    async def toDict(
        self,
        if_decrypt: bool = True,
        regenerate_uuids: bool = False,
        skip_virtual: bool = False,
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
                if_decrypt, regenerate_uuids, skip_virtual
            )

        return data

    @overload
    async def get(self, uid: uuid.UUID) -> dict[str, Any]: ...

    @overload
    async def get(self, uid: None = None) -> dict[str, Any]: ...

    async def get(self, uid: uuid.UUID | None = None) -> dict[str, Any]:
        """获取指定 UID 的单个配置。"""

        if uid is None:
            return await self.toDict()

        if uid not in self.data:
            raise ValueError(f"配置项 '{uid}' 不存在。")

        data: dict[str, Any] = {
            "instances": [
                {"uid": str(current_uid), "type": type(self.data[current_uid]).__name__}
                for current_uid in self.order
                if current_uid == uid
            ],
            str(uid): await self.data[uid].toDict(),
        }
        return data

    async def save(self) -> None:
        """
        保存当前多实例配置到文件。

        如果在事务中，则延迟保存；否则立即写入文件。

        Raises:
            ValueError: 如果文件路径未设置
            OSError: 如果文件写入失败
        """
        if not self.file:
            raise ValueError("文件路径未设置，请先调用 connect() 方法")

        if self._transaction_depth > 0:
            self._pending_save = True
            logger.debug(f"事务中，延迟保存: {self.file}")
            return

        async with self._mutex:
            try:
                await self._save_unlocked()
            except (OSError, ValueError, TypeError) as e:
                logger.error(f"配置保存失败: {self.file}, 错误: {e}")
                raise

    async def add(self, config_type: type[T]) -> tuple[uuid.UUID, T]:
        """
        新增一个指定类型的子配置实例。

        Args:
            config_type: 配置类型，必须在允许的类型列表中

        Returns:
            (新配置的 UUID, 配置实例)

        Raises:
            ValueError: 如果配置类型不被允许或配置已锁定
        """
        async with self._mutex:
            if config_type not in self.sub_config_type.values():
                raise ValueError(f"配置类型 {config_type.__name__} 不被允许")
            if self.is_locked:
                raise ValueError("配置已锁定，无法修改")

            uid = uuid.uuid4()
            config = config_type()
            config.bind_owner_collection(self, uid)
            self.order.append(uid)
            self.data[uid] = config

            logger.info(f"新增配置: {config_type.__name__}, UID: {uid}")

            for save_method in self._save_methods:
                await config.add_save_method(save_method)

            if self.file:
                await config.add_save_method(self.save)
                await self._save_unlocked()

            if self._transaction_depth > 0:
                self._pending_sync = self._pending_sync or bool(self._save_methods)
            elif self._save_methods:
                await asyncio.gather(*(_() for _ in self._save_methods))

            await _emit_collection_slots(
                self._on_add_slots, MultipleConfigAddEvent(self, uid, config)
            )

            return uid, config

    async def remove(self, uid: uuid.UUID) -> None:
        """
        移除一个子配置实例。

        Args:
            uid: 要移除的配置 UUID

        Raises:
            ValueError: 如果配置不存在、已锁定或父容器已锁定
        """
        async with self._mutex:
            if self.is_locked:
                raise ValueError("配置已锁定，无法修改")
            if uid not in self.data:
                raise ValueError(f"配置项 '{uid}' 不存在")
            if self.data[uid].is_locked:
                raise ValueError(f"配置项 '{uid}' 已锁定，无法移除")

            config = self.data[uid]
            logger.info(f"移除配置: {type(config).__name__}, UID: {uid}")

            await _emit_collection_slots(
                self._on_before_del_slots, MultipleConfigDeleteEvent(self, uid, config)
            )

            self.data.pop(uid)
            self.order.remove(uid)

            if self.file:
                await self._save_unlocked()

            if self._transaction_depth > 0:
                self._pending_sync = self._pending_sync or bool(self._save_methods)
            elif self._save_methods:
                await asyncio.gather(*(_() for _ in self._save_methods))

            await _emit_collection_slots(
                self._on_del_slots, MultipleConfigDeleteEvent(self, uid, config)
            )

    async def setOrder(self, order: list[uuid.UUID]) -> None:  # noqa: N802
        """设置子配置实例顺序。"""

        async with self._mutex:
            if set(order) != set(self.data.keys()):
                raise ValueError("顺序与当前配置项不匹配")
            if self.is_locked:
                raise ValueError("配置已锁定, 无法修改")

            self.order = order

            if self.file:
                await self._save_unlocked()

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

    def keys(self) -> Iterator[uuid.UUID]:
        """返回全部 UID。"""

        return iter(tuple(self.order))

    def values(self) -> Iterator[T]:
        """按顺序返回全部子配置实例。"""

        if not self.data:
            return iter(())
        order_snapshot = tuple(self.order)
        return iter(tuple(self.data[uid] for uid in order_snapshot if uid in self.data))

    def items(self) -> Iterator[tuple[uuid.UUID, T]]:
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
