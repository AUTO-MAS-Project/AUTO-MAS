from __future__ import annotations

import asyncio
import ast
import difflib
import inspect
import re
import textwrap
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from collections.abc import Callable, Coroutine
from collections.abc import AsyncIterator
from typing import Any, ClassVar, TypeVar, cast

from pydantic import AliasChoices, AliasPath, BaseModel, ConfigDict, PrivateAttr

from .base import (
    MultipleConfig,
    MultipleConfigDeleteEvent,
    atomic_write_text,
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


def _default_virtual_dependencies_cache() -> (
    dict[tuple[str, str], tuple[tuple[str, str], ...]]
):
    return {}


def _default_ref_validation_cache() -> dict[tuple[str, str, tuple[str, ...], str], Any]:
    return {}


def _normalize_mapping(value: Any) -> dict[str, Any]:
    """将任意映射值规范化为 `dict[str, Any]`。"""

    if not isinstance(value, dict):
        return {}
    mapping = cast(dict[object, Any], value)
    return {str(key): item for key, item in mapping.items()}


_SNAKE_1 = re.compile(r"(.)([A-Z][a-z]+)")
_SNAKE_2 = re.compile(r"([a-z0-9])([A-Z])")


def _to_snake_case(name: str) -> str:
    """将 ``PascalCase``/``camelCase`` 名称转换为 ``snake_case``。

    该函数用于统一配置协议键名输出，并在输入解析时做名称归一化匹配。

    Args:
        name: 原始名称。

    Returns:
        snake_case 格式名称。
    """

    first_pass = _SNAKE_1.sub(r"\1_\2", name)
    return _SNAKE_2.sub(r"\1_\2", first_pass).lower()


def _resolve_alias_paths(validation_alias: Any) -> list[tuple[str, ...]]:
    if validation_alias is None:
        return []

    if isinstance(validation_alias, str):
        return [(validation_alias,)]

    if isinstance(validation_alias, AliasPath):
        path = tuple(
            item
            for item in validation_alias.path
            if isinstance(item, str) and item != ""
        )
        return [path] if path else []

    if isinstance(validation_alias, AliasChoices):
        alias_paths: list[tuple[str, ...]] = []
        for choice in validation_alias.choices:
            alias_paths.extend(_resolve_alias_paths(choice))
        return alias_paths

    return []


def _try_resolve_alias_value(
    raw: dict[str, Any],
    group_name: str,
    group_data: dict[str, Any],
    validation_alias: Any,
) -> tuple[Any, bool]:
    for alias_path in _resolve_alias_paths(validation_alias):
        if not alias_path:
            continue

        if len(alias_path) == 1:
            alias_key = alias_path[0]
            if alias_key in group_data:
                return group_data[alias_key], True
            continue

        current: Any
        root_key = alias_path[0]
        if root_key == group_name:
            current = group_data
            walk_keys = alias_path[1:]
        else:
            current = _normalize_mapping(raw.get(root_key, {}))
            walk_keys = alias_path[1:]

        matched = True
        for key in walk_keys:
            if not isinstance(current, dict):
                matched = False
                break

            current_dict = cast(dict[str, Any], current)
            if key not in current_dict:
                matched = False
                break

            current = current_dict[key]

        if matched:
            return cast(Any, current), True

    return None, False


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
    skip_virtual: bool,
) -> dict[str, Any]:
    """将分组模型导出为字典，并按需解密加密字段。"""

    data: dict[str, Any] = {}

    for field_name in type(group_model).model_fields:
        virtual_field = _get_field_marker(group_model, field_name, VirtualField)
        if virtual_field is not None:
            if skip_virtual:
                continue
            data[_to_snake_case(field_name)] = owner.get_virtual_value(
                group_name, field_name, virtual_field
            )
            continue

        value = getattr(group_model, field_name)

        if isinstance(value, BaseModel):
            data[_to_snake_case(field_name)] = _export_group_model(
                owner, field_name, value, if_decrypt, skip_virtual
            )
            continue

        if if_decrypt and _is_encrypted_field(group_model, field_name):
            data[_to_snake_case(field_name)] = decrypt_encrypted_string(str(value))
            continue

        data[_to_snake_case(field_name)] = value

    return data


class PydanticConfigBase(BaseModel):
    """基于 pydantic v2 的配置基类，兼容旧版 ConfigBase 常用接口。"""

    model_config = ConfigDict(extra="allow", validate_assignment=True)

    LEGACY_FIELD_MAP: ClassVar[dict[tuple[str, str], tuple[str, str]]] = {}
    related_config: ClassVar[dict[str, MultipleConfig[Any]]] = {}
    _class_virtual_dependencies: ClassVar[
        dict[
            type["PydanticConfigBase"],
            dict[tuple[str, str], tuple[tuple[str, str], ...]],
        ]
    ] = {}
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
    _mutex: asyncio.Lock = PrivateAttr(default_factory=asyncio.Lock)
    _virtual_dependencies_cache: dict[tuple[str, str], tuple[tuple[str, str], ...]] = (
        PrivateAttr(default_factory=_default_virtual_dependencies_cache)
    )
    _ref_validation_cache: dict[tuple[str, str, tuple[str, ...], str], Any] = (
        PrivateAttr(default_factory=_default_ref_validation_cache)
    )
    _ref_validation_cache_enabled: bool = PrivateAttr(default=False)

    @property
    def file(self) -> Path | None:
        return self._file

    @property
    def is_locked(self) -> bool:
        return self._is_locked

    def model_post_init(self, __context: Any) -> None:
        self._build_virtual_dependency_cache()
        self._register_ref_bindings()

    def _suggest_candidates(self, value: str, candidates: list[str]) -> list[str]:
        if not candidates:
            return []

        snake = _to_snake_case(value)
        exact_snake_matches = [
            candidate for candidate in candidates if _to_snake_case(candidate) == snake
        ]
        if exact_snake_matches:
            return exact_snake_matches[:3]

        close_matches = difflib.get_close_matches(value, candidates, n=3, cutoff=0.5)
        if close_matches:
            return close_matches

        snake_matches = difflib.get_close_matches(
            snake,
            [_to_snake_case(candidate) for candidate in candidates],
            n=3,
            cutoff=0.5,
        )
        mapped: list[str] = []
        for snake_match in snake_matches:
            for candidate in candidates:
                if _to_snake_case(candidate) == snake_match and candidate not in mapped:
                    mapped.append(candidate)
        return mapped[:3]

    def _resolve_group_name(self, group: str) -> str:
        """将调用侧传入的分组名解析为模型中的真实分组名。

        支持两类匹配：
        - 精确匹配（如 ``Info``）
        - snake_case 等价匹配（如 ``info``）

        Args:
            group: 外部输入的分组名。

        Returns:
            配置模型中的真实分组名。

        Raises:
            AttributeError: 分组不存在时抛出。
        """

        groups = self._group_index()
        if group in groups:
            return group

        snake = _to_snake_case(group)
        for candidate in groups:
            if _to_snake_case(candidate) == snake:
                return candidate

        suggestions = self._suggest_candidates(group, list(groups.keys()))
        if suggestions:
            raise AttributeError(
                f"配置分组 '{group}' 不存在。你可能想用: {', '.join(suggestions)}"
            )
        raise AttributeError(
            f"配置分组 '{group}' 不存在。可用分组: {', '.join(groups.keys())}"
        )

    def _resolve_field_name(self, group: str, name: str) -> str:
        """将字段名解析为指定分组中的真实字段名。

        先解析分组，再在该分组下执行字段名精确匹配与 snake_case 等价匹配。

        Args:
            group: 分组名（可为原名或 snake_case）。
            name: 字段名（可为原名或 snake_case）。

        Returns:
            配置模型中的真实字段名。

        Raises:
            AttributeError: 分组或字段不存在时抛出。
        """

        resolved_group = self._resolve_group_name(group)
        group_model = self._group_index().get(resolved_group)
        if group_model is None:
            raise AttributeError(f"配置分组 '{group}' 不存在")

        fields = type(group_model).model_fields
        if name in fields:
            return name

        snake = _to_snake_case(name)
        for candidate in fields:
            if _to_snake_case(candidate) == snake:
                return candidate

        field_candidates = list(fields.keys())
        suggestions = self._suggest_candidates(name, field_candidates)
        if suggestions:
            raise AttributeError(
                f"配置项 '{group}.{name}' 不存在。你可能想用: "
                f"{resolved_group}.{suggestions[0]}"
            )
        raise AttributeError(
            f"配置项 '{group}.{name}' 不存在。"
            f"可用字段: {', '.join(field_candidates)}"
        )

    def _normalize_dependency(self, dependency: tuple[str, str]) -> tuple[str, str]:
        """将虚拟字段依赖项规范化为真实 ``(group, field)`` 对。

        主要用于把手工声明依赖或自动推导依赖统一为内部可比较的标准形式。

        Args:
            dependency: 原始依赖项。

        Returns:
            规范化后的依赖项。
        """

        group, name = dependency
        resolved_group = self._resolve_group_name(group)
        resolved_name = self._resolve_field_name(resolved_group, name)
        return resolved_group, resolved_name

    def _infer_virtual_dependencies(self, getter: str) -> tuple[tuple[str, str], ...]:
        """从虚拟字段 getter 源码中自动推导依赖字段。

        推导策略：
        - 解析方法 AST；
        - 扫描 ``self.get("Group", "Field")`` 形式调用；
        - 对提取结果执行名称归一化与去重。

        注意：若源码不可获取、语法不可解析或调用参数非常量字符串，
        对应依赖将被安全忽略。

        Args:
            getter: getter 方法名。

        Returns:
            推导出的依赖项元组。
        """

        method = getattr(type(self), getter, None)
        if method is None:
            return ()

        try:
            source = inspect.getsource(method)
        except (OSError, TypeError):
            return ()

        try:
            tree = ast.parse(textwrap.dedent(source))
        except SyntaxError:
            return ()

        dependencies: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "get":
                continue
            if (
                not isinstance(node.func.value, ast.Name)
                or node.func.value.id != "self"
            ):
                continue
            if len(node.args) < 2:
                continue

            arg_group = node.args[0]
            arg_name = node.args[1]
            if not (
                isinstance(arg_group, ast.Constant)
                and isinstance(arg_group.value, str)
                and isinstance(arg_name, ast.Constant)
                and isinstance(arg_name.value, str)
            ):
                continue

            try:
                dep = self._normalize_dependency((arg_group.value, arg_name.value))
            except AttributeError:
                continue

            if dep in seen:
                continue
            seen.add(dep)
            dependencies.append(dep)

        return tuple(dependencies)

    def _build_virtual_dependency_cache(self) -> None:
        """构建虚拟字段依赖缓存。

        缓存键为 ``(group, field)``，值为该虚拟字段依赖列表。
        规则：
        - 优先使用显式 ``depends_on``；
        - 否则对字符串 getter 执行自动推导；
        - 其他情况依赖为空。

        缓存在 ``model_post_init`` 阶段构建，用于 ``set`` 触发时高效判断
        哪些虚拟字段需要重新计算并派发绑定事件。
        """

        cls = type(self)
        class_cache = cls._class_virtual_dependencies.get(cls)
        if class_cache is not None:
            self._virtual_dependencies_cache = class_cache
            return

        class_cache = {}

        for group_name, group_model in self._group_index().items():
            for field_name in type(group_model).model_fields:
                virtual_field = _get_field_marker(group_model, field_name, VirtualField)
                if virtual_field is None:
                    continue

                if virtual_field.depends_on:
                    deps = tuple(
                        self._normalize_dependency(dep)
                        for dep in virtual_field.depends_on
                    )
                elif isinstance(virtual_field.getter, str):
                    deps = self._infer_virtual_dependencies(virtual_field.getter)
                else:
                    deps = ()

                class_cache[(group_name, field_name)] = deps

        cls._class_virtual_dependencies[cls] = class_cache
        self._virtual_dependencies_cache = class_cache

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
            if self._ref_validation_cache_enabled:
                return self._normalize_ref_value_cached(ref_field, value)
            return self._normalize_ref_value(ref_field, value)
        return value

    def _normalize_ref_value_cached(self, spec: RefField, value: Any) -> Any:
        cache_key = (
            spec.target,
            str(spec.default),
            tuple(str(item) for item in spec.allow_values),
            str(value),
        )
        if cache_key in self._ref_validation_cache:
            return self._ref_validation_cache[cache_key]

        normalized = self._normalize_ref_value(spec, value)
        self._ref_validation_cache[cache_key] = normalized
        return normalized

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
                deps = self._virtual_dependencies_cache.get(
                    (group_name, field_name), ()
                )
                if dependency in deps:
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

        is_outermost = self._transaction_depth == 0
        if is_outermost:
            self._ref_validation_cache_enabled = True
            self._ref_validation_cache.clear()

        self._transaction_depth += 1
        try:
            yield self
        finally:
            self._transaction_depth -= 1
            if self._transaction_depth == 0:
                await self._flush_pending_changes()
            if is_outermost:
                self._ref_validation_cache_enabled = False
                self._ref_validation_cache.clear()

    async def _flush_pending_changes(self) -> None:
        await self._flush_pending_bindings()

        if self._pending_save and self._file:
            self._pending_save = False
            await self._save_unlocked()

        if self._pending_sync:
            self._pending_sync = False
            if self._save_methods:
                await asyncio.gather(*(_() for _ in self._save_methods))

    async def _save_unlocked(self) -> None:
        if not self._file:
            raise ValueError("文件路径未设置, 请先调用 `connect` 方法连接配置文件")

        content = dump_toml(await self.toDict(if_decrypt=False, skip_virtual=True))
        atomic_write_text(self._file, content)

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
        """从外部字典加载配置，支持新旧命名协议混读。

        支持内容：
        - 分组与字段的 PascalCase / snake_case 双格式读取；
        - ``sub_configs_info`` 与 ``SubConfigsInfo`` 兼容；
        - 字段 ``validation_alias`` 回退解析；
        - ``LEGACY_FIELD_MAP`` 旧字段映射回填。

        加载完成后会触发持久化与级联保存方法，保证内存态与磁盘态一致。

        Args:
            data: 待加载的原始配置字典。
        """

        async with self._mutex:
            if self._is_locked:
                raise ValueError("配置已锁定, 无法修改")

            raw: dict[str, Any] = dict(data)

            sub_configs = _normalize_mapping(
                raw.pop("sub_configs_info", raw.pop("SubConfigsInfo", {}))
            )

            for name, sub_config in self._multiple_config_index().items():
                data_for_sub = sub_configs.get(
                    _to_snake_case(name), sub_configs.get(name)
                )
                if isinstance(data_for_sub, dict):
                    await sub_config.load(_normalize_mapping(data_for_sub))

            for group_name, group_model in self._group_index().items():
                group_data = _normalize_mapping(
                    raw.get(_to_snake_case(group_name), raw.get(group_name, {}))
                )

                for field_name in list(type(group_model).model_fields.keys()):
                    if self._get_virtual_field(group_name, field_name) is not None:
                        continue

                    candidate: Any = None
                    has_value = False

                    if field_name in group_data:
                        candidate = group_data[field_name]
                        has_value = True
                    elif _to_snake_case(field_name) in group_data:
                        candidate = group_data[_to_snake_case(field_name)]
                        has_value = True
                    else:
                        field_info = type(group_model).model_fields.get(field_name)
                        if field_info is not None:
                            candidate, has_value = _try_resolve_alias_value(
                                raw,
                                group_name,
                                group_data,
                                field_info.validation_alias,
                            )

                    if not has_value:
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
                    except (TypeError, ValueError) as e:
                        raise ValueError(
                            f"加载配置项失败: {group_name}.{field_name}={candidate!r}"
                        ) from e

            if self._file:
                await self._save_unlocked()

            if self._save_methods:
                await asyncio.gather(*(_() for _ in self._save_methods))

    async def toDict(
        self,
        if_decrypt: bool = True,
        regenerate_uuids: bool = False,
        skip_virtual: bool = False,
    ) -> dict[str, Any]:
        """将当前配置导出为 snake_case 协议字典。

        导出规则：
        - 所有分组键与字段键均转换为 snake_case；
        - 虚拟字段导出为实时计算值；
        - 子配置统一放入 ``sub_configs_info``；
        - 是否解密由 ``if_decrypt`` 控制。

        Args:
            if_decrypt: 是否在导出时自动解密加密字段。
            regenerate_uuids: 透传给子配置容器的 UUID 重生参数。

        Returns:
            可序列化的配置字典。
        """

        data: dict[str, Any] = {}

        for group_name, group_model in self._group_index().items():
            data[_to_snake_case(group_name)] = _export_group_model(
                self, group_name, group_model, if_decrypt, skip_virtual
            )

        for name, item in self._multiple_config_index().items():
            if "sub_configs_info" not in data:
                data["sub_configs_info"] = {}
            data["sub_configs_info"][_to_snake_case(name)] = await item.toDict(
                if_decrypt, regenerate_uuids, skip_virtual
            )

        return data

    def get(self, group: str, name: str) -> Any:
        """读取单个配置项，支持 snake_case 与原字段名。

        读取流程：
        1. 解析分组和字段真实名称；
        2. 若为虚拟字段，返回 getter 计算结果；
        3. 若为加密字段，返回自动解密值；
        4. 否则返回原值。

        Args:
            group: 分组名。
            name: 字段名。

        Returns:
            配置值。
        """

        resolved_group = self._resolve_group_name(group)
        resolved_name = self._resolve_field_name(resolved_group, name)

        group_model = self._group_index().get(resolved_group)
        if group_model is None or not hasattr(group_model, resolved_name):
            raise AttributeError(f"配置项 '{group}.{name}' 不存在")

        virtual_field = self._get_virtual_field(resolved_group, resolved_name)
        if virtual_field is not None:
            return self._get_virtual_value(resolved_group, resolved_name, virtual_field)

        value = getattr(group_model, resolved_name)
        if _is_encrypted_field(group_model, resolved_name):
            return decrypt_encrypted_string(str(value))
        return value

    async def set(self, group: str, name: str, value: Any) -> None:
        """设置单个配置项，并联动依赖虚拟字段与绑定回调。

        关键行为：
        - 支持 snake_case 名称解析；
        - 对引用字段执行归一化（UUID/默认值校验）；
        - 计算受影响虚拟字段的前后值差异，按需触发绑定事件；
        - 根据事务状态决定立即保存或延迟提交。

        Args:
            group: 分组名。
            name: 字段名。
            value: 新值。
        """

        async with self._mutex:
            resolved_group = self._resolve_group_name(group)
            resolved_name = self._resolve_field_name(resolved_group, name)

            group_model = self._group_index().get(resolved_group)
            if group_model is None or not hasattr(group_model, resolved_name):
                raise AttributeError(f"配置项 '{group}.{name}' 不存在")

            if self._is_locked:
                raise ValueError("配置已锁定, 无法修改")

            virtual_field = self._get_virtual_field(resolved_group, resolved_name)
            if virtual_field is not None:
                await self._set_virtual_value(resolved_group, resolved_name, value)
                return

            old_value = getattr(group_model, resolved_name)
            virtual_old_values = {
                (virtual_group, virtual_name): self._get_virtual_value(
                    virtual_group, virtual_name, virtual_field
                )
                for virtual_group, virtual_name, virtual_field in self._iter_virtual_dependents(
                    (resolved_group, resolved_name)
                )
            }
            value = self._normalize_value(resolved_group, resolved_name, value)

            try:
                setattr(group_model, resolved_name, value)
            except (TypeError, ValueError) as e:
                raise ValueError(
                    f"设置配置项失败: {resolved_group}.{resolved_name}={value!r}"
                ) from e

            new_value = getattr(group_model, resolved_name)
            if old_value != new_value:
                await self._queue_binding(resolved_group, resolved_name, new_value)

            for (
                virtual_group,
                virtual_name,
            ), old_virtual_value in virtual_old_values.items():
                new_virtual_value = self.get(virtual_group, virtual_name)
                if old_virtual_value != new_virtual_value:
                    await self._queue_binding(
                        virtual_group, virtual_name, new_virtual_value
                    )

            if self._file:
                await self._save_unlocked()

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
        resolved_group = self._resolve_group_name(group)
        resolved_name = self._resolve_field_name(resolved_group, name)

        group_model = self._group_index().get(resolved_group)
        if group_model is None or not hasattr(group_model, resolved_name):
            raise AttributeError(f"配置项 '{group}.{name}' 不存在")

        if self._is_locked:
            raise ValueError("配置已锁定, 无法修改")

        key = (resolved_group, resolved_name)
        if key not in self._bindings:
            self._bindings[key] = []
        if slot not in self._bindings[key]:
            self._bindings[key].append(slot)

    def unbind(self, group: str, name: str, slot: Slot) -> None:
        resolved_group = self._resolve_group_name(group)
        resolved_name = self._resolve_field_name(resolved_group, name)

        group_model = self._group_index().get(resolved_group)
        if group_model is None or not hasattr(group_model, resolved_name):
            raise AttributeError(f"配置项 '{group}.{name}' 不存在")

        if self._is_locked:
            raise ValueError("配置已锁定, 无法修改")

        key = (resolved_group, resolved_name)
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

        async with self._mutex:
            await self._save_unlocked()

    async def lock(self) -> None:
        self._is_locked = True
        for config in self._multiple_config_index().values():
            await config.lock()

    async def unlock(self) -> None:
        self._is_locked = False
        for config in self._multiple_config_index().values():
            await config.unlock()
