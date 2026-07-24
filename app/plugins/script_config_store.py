from __future__ import annotations

import copy
import json
import uuid
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, Literal, Mapping

from pydantic import BaseModel

from app.core.script_config_codec import (
    build_config_model,
    form_to_storage,
    storage_to_form,
)

if TYPE_CHECKING:
    from app.core.script_types import ScriptTypeProvider


ConfigKind = Literal["script", "user"]


def _inherits_type(value: object, class_name: str, module_name: str) -> bool:
    return any(
        base.__name__ == class_name and base.__module__ == module_name
        for base in type(value).__mro__
    )


def _is_legacy_config(value: object) -> bool:
    return _inherits_type(value, "ConfigBase", "app.models.ConfigBase")


def _is_legacy_multiple_config(value: object) -> bool:
    return _inherits_type(
        value,
        "MultipleConfig",
        "app.models.ConfigBase",
    )


def _is_legacy_plugin_script(value: object) -> bool:
    return _inherits_type(
        value,
        "PluginScriptConfig",
        "app.models.plugin_script_config",
    )


def _is_legacy_plugin_user(value: object) -> bool:
    return _inherits_type(
        value,
        "PluginUserConfig",
        "app.models.plugin_script_config",
    )


def _is_native_entry(value: object) -> bool:
    return _inherits_type(value, "ConfigEntry", "app.configuration.v2.entry")


def _is_native_plugin_script(value: object) -> bool:
    return _inherits_type(
        value,
        "PluginScript",
        "app.configuration.roots.script",
    )


def _is_native_plugin_user(value: object) -> bool:
    return _inherits_type(
        value,
        "PluginUser",
        "app.configuration.roots.script",
    )


def _is_plugin_script_storage(value: object) -> bool:
    return _is_legacy_plugin_script(value) or _is_native_plugin_script(value)


def _is_plugin_user_storage(value: object) -> bool:
    return _is_legacy_plugin_user(value) or _is_native_plugin_user(value)


def _is_legacy_config_class(config_class: type[Any]) -> bool:
    return any(
        base.__name__ == "ConfigBase"
        and base.__module__ == "app.models.ConfigBase"
        for base in config_class.__mro__
    )


class RuntimeConfigModel:
    """Mutable task-local session backed by a Pydantic configuration model."""

    def __init__(
        self,
        config_class: type[BaseModel],
        payload: Mapping[str, Any],
        *,
        kind: ConfigKind,
    ) -> None:
        self.config_class = config_class
        self.kind = kind
        self._model: BaseModel
        self._payload: dict[str, Any]
        self._collections: dict[str, RuntimeConfigCollectionSnapshot] = {}
        self._load(dict(payload))

    def _load(self, payload: dict[str, Any]) -> None:
        normalized = copy.deepcopy(payload)
        normalized.pop("SubConfigsInfo", None)
        for collection_name in getattr(
            self.config_class,
            "_cfg_collection_fields",
            (),
        ):
            collection_payload = normalized.pop(collection_name, None)
            if isinstance(collection_payload, Mapping):
                field = self.config_class.model_fields.get(collection_name)
                collection_class = field.annotation if field is not None else None
                snapshot = RuntimeConfigCollectionSnapshot.from_payload(
                    collection_class,
                    collection_payload,
                    kind=self.kind,
                )
                if snapshot is not None:
                    self._collections[collection_name] = snapshot
        self._model = self.config_class.model_validate(normalized)
        self._payload = self._model.model_dump(mode="json")
        self._payload.pop("SubConfigsInfo", None)
        for collection_name in getattr(
            self.config_class,
            "_cfg_collection_fields",
            (),
        ):
            self._payload.pop(collection_name, None)
        for group, field in (
            set(getattr(self.config_class, "_cfg_virtual_specs", {}))
            | set(getattr(self.config_class, "_cfg_trigger_specs", {}))
        ):
            group_data = self._payload.get(group)
            if isinstance(group_data, dict):
                group_data.pop(field, None)

    def get(self, group: str, field: str) -> Any:
        group_data = self._payload.get(group)
        if not isinstance(group_data, Mapping) or field not in group_data:
            raise AttributeError(f"{self.config_class.__name__}.{group}.{field}")
        return copy.deepcopy(group_data[field])

    async def set(self, group: str, field: str, value: object) -> None:
        payload = copy.deepcopy(self._payload)
        group_data = payload.get(group)
        if not isinstance(group_data, dict):
            raise AttributeError(f"{self.config_class.__name__}.{group}")
        if field not in group_data:
            raise AttributeError(f"{self.config_class.__name__}.{group}.{field}")
        group_data[field] = copy.deepcopy(value)
        self._load(payload)

    async def load(self, payload: Mapping[str, Any]) -> None:
        self._load(dict(payload))

    async def toDict(  # noqa: N802 - task runtime compatibility surface
        self,
        if_decrypt: bool = True,
        regenerate_uuids: bool = False,
    ) -> dict[str, Any]:
        _ = if_decrypt
        if regenerate_uuids:
            raise ValueError("运行时配置会话不支持重新生成 UUID")
        return copy.deepcopy(self._payload)

    def model_dump(self, **_kwargs: Any) -> dict[str, Any]:
        return copy.deepcopy(self._payload)

    def __getattr__(self, name: str) -> Any:
        if name in self._collections:
            return self._collections[name]
        return getattr(self._model, name)


class RuntimeConfigCollectionSnapshot(Mapping[uuid.UUID, RuntimeConfigModel]):
    """Read-only task snapshot for a nested Config v2 collection."""

    def __init__(
        self,
        items: list[tuple[uuid.UUID, RuntimeConfigModel]],
    ) -> None:
        self.order = [item_uid for item_uid, _model in items]
        self.data = dict(items)

    @classmethod
    def from_payload(
        cls,
        collection_class: object,
        payload: Mapping[str, Any],
        *,
        kind: ConfigKind,
    ) -> RuntimeConfigCollectionSnapshot | None:
        entry_types = {
            entry_type.__name__: entry_type
            for entry_type in getattr(collection_class, "_default_entry_types", ())
            if isinstance(entry_type, type) and issubclass(entry_type, BaseModel)
        }
        if not entry_types:
            return None

        order_payload = payload.get("instances", payload.get("order", ()))
        ordered: list[tuple[uuid.UUID, RuntimeConfigModel]] = []
        seen: set[uuid.UUID] = set()
        if isinstance(order_payload, (list, tuple)):
            for item in order_payload:
                if isinstance(item, Mapping):
                    raw_uid = item.get("uid")
                    type_name = str(item.get("type") or "")
                else:
                    raw_uid = getattr(item, "uid", None)
                    type_name = str(getattr(item, "type", "") or "")
                if raw_uid in (None, ""):
                    continue
                try:
                    item_uid = uuid.UUID(str(raw_uid))
                except ValueError:
                    continue
                entry_class = entry_types.get(type_name) or next(iter(entry_types.values()))
                item_payload = payload.get(str(item_uid), {})
                if not isinstance(item_payload, Mapping):
                    continue
                ordered.append(
                    (
                        item_uid,
                        RuntimeConfigModel(entry_class, item_payload, kind=kind),
                    )
                )
                seen.add(item_uid)

        for raw_uid, item_payload in payload.items():
            if raw_uid in {"instances", "order"} or not isinstance(item_payload, Mapping):
                continue
            try:
                item_uid = uuid.UUID(str(raw_uid))
            except ValueError:
                continue
            if item_uid in seen:
                continue
            ordered.append(
                (
                    item_uid,
                    RuntimeConfigModel(
                        next(iter(entry_types.values())),
                        item_payload,
                        kind=kind,
                    ),
                )
            )
        return cls(ordered)

    def __getitem__(self, item_uid: uuid.UUID | str) -> RuntimeConfigModel:
        uid = item_uid if isinstance(item_uid, uuid.UUID) else uuid.UUID(item_uid)
        return self.data[uid]

    def __iter__(self) -> Iterator[uuid.UUID]:
        return iter(self.order)

    def __len__(self) -> int:
        return len(self.order)

    def items(self) -> Iterator[tuple[uuid.UUID, RuntimeConfigModel]]:
        for item_uid in self.order:
            yield item_uid, self.data[item_uid]


class RuntimeUserConfigCollection(Mapping[uuid.UUID, RuntimeConfigModel]):
    """Task-local user collection without the legacy MultipleConfig graph."""

    def __init__(
        self,
        items: list[tuple[str, RuntimeConfigModel]],
    ) -> None:
        self.order = [uuid.UUID(user_uid) for user_uid, _model in items]
        self.data = {
            uuid.UUID(user_uid): model
            for user_uid, model in items
        }

    def __getitem__(self, user_uid: uuid.UUID | str) -> RuntimeConfigModel:
        uid = user_uid if isinstance(user_uid, uuid.UUID) else uuid.UUID(user_uid)
        return self.data[uid]

    def __iter__(self) -> Iterator[uuid.UUID]:
        return iter(self.order)

    def __len__(self) -> int:
        return len(self.order)

    def items(self) -> Iterator[tuple[uuid.UUID, RuntimeConfigModel]]:
        for user_uid in self.order:
            yield user_uid, self.data[user_uid]

    async def toDict(  # noqa: N802 - task runtime compatibility surface
        self,
        if_decrypt: bool = True,
    ) -> dict[str, Any]:
        _ = if_decrypt
        payload: dict[str, Any] = {
            "instances": [
                {
                    "uid": str(user_uid),
                    "type": self.data[user_uid].config_class.__name__,
                }
                for user_uid in self.order
            ]
        }
        for user_uid, model in self.items():
            payload[str(user_uid)] = await model.toDict(if_decrypt=False)
        return payload


class ScriptConfigStore:
    """Separate script schema models from host persistence containers."""

    def __init__(
        self,
        *,
        provider: ScriptTypeProvider,
        storage_script_config: Any,
    ) -> None:
        self.provider = provider
        self.storage_script_config = storage_script_config

    async def lock(self) -> None:
        await self.storage_script_config.lock()

    async def unlock(self) -> None:
        await self.storage_script_config.unlock()

    async def read_script_data(self) -> dict[str, Any]:
        if (
            _is_native_entry(self.storage_script_config)
            and not _is_native_plugin_script(self.storage_script_config)
        ):
            payload = await self.storage_script_config.to_dict(if_decrypt=True)
            payload.pop("UserData", None)
            return payload
        raw_payload = await self._read_script_storage_payload(if_decrypt=True)
        return await storage_to_form(self.provider, raw_payload, "script")

    async def read_user_data(self, user_uid: uuid.UUID | str) -> dict[str, Any]:
        uid = self._normalize_uid(user_uid)
        storage_user = self._user_data[uid]
        if _is_native_entry(storage_user) and not _is_native_plugin_user(storage_user):
            return await storage_user.to_dict(if_decrypt=True)
        raw_payload = await self._read_user_storage_payload(uid, if_decrypt=True)
        return await storage_to_form(self.provider, raw_payload, "user")

    async def read_user_data_pairs(self) -> list[tuple[str, dict[str, Any]]]:
        result: list[tuple[str, dict[str, Any]]] = []
        for user_uid in self._iter_user_uids():
            result.append((str(user_uid), await self.read_user_data(user_uid)))
        return result

    async def load_script_model(self) -> Any:
        payload = await self.read_script_data()
        if not _is_legacy_config_class(self.provider.script_config_class):
            return RuntimeConfigModel(
                self.provider.script_config_class,
                payload,
                kind="script",
            )
        return await build_config_model(self.provider, payload, "script")

    async def load_user_model(
        self,
        user_uid: uuid.UUID | str,
    ) -> Any:
        uid = self._normalize_uid(user_uid)
        payload = await self.read_user_data(uid)
        if not _is_legacy_config_class(self.provider.user_config_class):
            return RuntimeConfigModel(
                self.provider.user_config_class,
                payload,
                kind="user",
            )
        return await build_config_model(self.provider, payload, "user")

    async def load_user_models(self) -> list[tuple[str, Any]]:
        result: list[tuple[str, Any]] = []
        for user_uid in self._iter_user_uids():
            result.append((str(user_uid), await self.load_user_model(user_uid)))
        return result

    async def load_user_collection(self) -> Any:
        models = await self.load_user_models()
        if not _is_legacy_config_class(self.provider.user_config_class):
            return RuntimeUserConfigCollection(models)

        from app.models.ConfigBase import MultipleConfig

        collection = MultipleConfig([self.provider.user_config_class])
        for user_uid, user_model in models:
            uid = uuid.UUID(user_uid)
            collection.order.append(uid)
            collection.data[uid] = user_model
        return collection

    async def save_script_model(self, model: Any) -> None:
        await self.write_script_data(await self._model_to_form_data(model))

    async def save_user_model(
        self,
        user_uid: uuid.UUID | str,
        model: Any,
    ) -> None:
        await self.write_user_data(user_uid, await self._model_to_form_data(model))

    async def save_user_models(
        self,
        models: Any | Mapping[uuid.UUID, Any],
    ) -> None:
        if not _is_plugin_script_storage(self.storage_script_config):
            if _is_legacy_multiple_config(models):
                await self._user_data.load(await models.toDict(if_decrypt=False))
                return
            for user_uid, model in models.items():
                await self.save_user_model(user_uid, model)
            return

        for user_uid, model in models.items():
            await self.save_user_model(user_uid, model)

    async def write_script_data(self, form_payload: Mapping[str, Any]) -> None:
        payload = copy.deepcopy(dict(form_payload))
        if _is_plugin_script_storage(self.storage_script_config):
            storage_payload = await form_to_storage(
                self.provider,
                payload,
                "script",
            )
            await self.storage_script_config.set(
                "PluginData",
                "Config",
                json.dumps(storage_payload, ensure_ascii=False),
            )
            normalized = await storage_to_form(
                self.provider,
                storage_payload,
                "script",
            )
            await self.storage_script_config.set(
                "Info",
                "Name",
                self._script_name(
                    normalized,
                    fallback=self.storage_script_config.get("Info", "Name"),
                ),
            )
            return

        if _is_native_entry(self.storage_script_config):
            payload.pop("SubConfigsInfo", None)
            payload.pop("UserData", None)
            groups = set(type(self.storage_script_config)._cfg_group_fields)
            await self.storage_script_config.set_many(
                {
                    group: dict(fields)
                    for group, fields in payload.items()
                    if group in groups and isinstance(fields, Mapping)
                }
            )
            return

        await self.storage_script_config.load(payload)

    async def write_user_data(
        self,
        user_uid: uuid.UUID | str,
        form_payload: Mapping[str, Any],
    ) -> None:
        uid = self._normalize_uid(user_uid)
        storage_user = self._user_data[uid]
        payload = copy.deepcopy(dict(form_payload))

        if _is_plugin_user_storage(storage_user):
            storage_payload = await form_to_storage(
                self.provider,
                payload,
                "user",
            )
            await storage_user.set(
                "PluginData",
                "Config",
                json.dumps(storage_payload, ensure_ascii=False),
            )
            normalized = await storage_to_form(
                self.provider,
                storage_payload,
                "user",
            )
            await storage_user.set(
                "Info",
                "Name",
                self._user_name(normalized, fallback=str(uid)),
            )
            return

        if _is_native_entry(storage_user):
            groups = set(type(storage_user)._cfg_group_fields)
            await storage_user.set_many(
                {
                    group: dict(fields)
                    for group, fields in payload.items()
                    if group in groups and isinstance(fields, Mapping)
                }
            )
            return

        await storage_user.load(payload)

    async def update_script_data(self, update: Mapping[str, Any]) -> None:
        if _is_native_entry(self.storage_script_config) and not _is_native_plugin_script(
            self.storage_script_config
        ):
            groups = set(type(self.storage_script_config)._cfg_group_fields)
            await self.storage_script_config.set_many(
                {
                    group: dict(fields)
                    for group, fields in update.items()
                    if group in groups and isinstance(fields, Mapping)
                }
            )
            return
        if not _is_plugin_script_storage(self.storage_script_config):
            for group, items in update.items():
                if not isinstance(items, Mapping):
                    continue
                for name, value in items.items():
                    await self.storage_script_config.set(group, name, value)
            return

        current = self._strip_virtual_fields(
            await self.read_script_data(),
            "script",
        )
        merged = self._deep_merge(current, dict(update))
        await self.write_script_data(self._strip_virtual_fields(merged, "script"))

    async def update_user_data(
        self,
        user_uid: uuid.UUID | str,
        update: Mapping[str, Any],
    ) -> None:
        uid = self._normalize_uid(user_uid)
        storage_user = self._user_data[uid]
        if _is_native_entry(storage_user) and not _is_native_plugin_user(storage_user):
            groups = set(type(storage_user)._cfg_group_fields)
            await storage_user.set_many(
                {
                    group: dict(fields)
                    for group, fields in update.items()
                    if group in groups and isinstance(fields, Mapping)
                }
            )
            return
        if not _is_plugin_user_storage(storage_user):
            for group, items in update.items():
                if not isinstance(items, Mapping):
                    continue
                for name, value in items.items():
                    await storage_user.set(group, name, value)
            return

        current = self._strip_virtual_fields(
            await self.read_user_data(uid),
            "user",
        )
        merged = self._deep_merge(current, dict(update))
        await self.write_user_data(
            uid,
            self._strip_virtual_fields(merged, "user"),
        )

    async def _read_script_storage_payload(self, *, if_decrypt: bool) -> Any:
        if _is_plugin_script_storage(self.storage_script_config):
            return self.storage_script_config.get("PluginData", "Config")
        return await self.storage_script_config.toDict(if_decrypt=if_decrypt)

    async def _read_user_storage_payload(
        self,
        user_uid: uuid.UUID,
        *,
        if_decrypt: bool,
    ) -> Any:
        storage_user = self._user_data[user_uid]
        if _is_plugin_user_storage(storage_user):
            return storage_user.get("PluginData", "Config")
        return await storage_user.toDict(if_decrypt=if_decrypt)

    @staticmethod
    async def _model_to_form_data(model: Any) -> dict[str, Any]:
        if isinstance(model, RuntimeConfigModel):
            return await model.toDict(if_decrypt=False)
        if _is_legacy_config(model):
            payload = await model.toDict(if_decrypt=False)
            payload.pop("SubConfigsInfo", None)
            return payload
        if isinstance(model, BaseModel):
            return model.model_dump(mode="json")
        raise TypeError(f"Unsupported script config model: {type(model).__name__}")

    def _strip_virtual_fields(
        self,
        payload: dict[str, Any],
        kind: ConfigKind,
    ) -> dict[str, Any]:
        cleaned = copy.deepcopy(payload)
        config_class = (
            self.provider.script_config_class
            if kind == "script"
            else self.provider.user_config_class
        )
        for group in getattr(config_class, "_field_groups", ()):
            group_data = cleaned.get(group.key)
            if not isinstance(group_data, dict):
                continue
            for field in group.fields:
                if field.virtual_handler is not None:
                    group_data.pop(field.name, None)
        return cleaned

    @classmethod
    def _deep_merge(
        cls,
        base: dict[str, Any],
        override: dict[str, Any],
    ) -> dict[str, Any]:
        merged = copy.deepcopy(base)
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = cls._deep_merge(merged[key], value)
            else:
                merged[key] = copy.deepcopy(value)
        return merged

    def _script_name(
        self,
        payload: dict[str, Any],
        *,
        fallback: str | None,
    ) -> str:
        script_name = payload.get("script_name")
        if isinstance(script_name, str) and script_name.strip():
            return script_name.strip()

        info = payload.get("Info")
        if isinstance(info, dict) and isinstance(info.get("Name"), str):
            info_name = info["Name"].strip()
            if info_name:
                return info_name

        if isinstance(fallback, str) and fallback.strip():
            return fallback.strip()
        return self.provider.display_name

    @staticmethod
    def _user_name(payload: dict[str, Any], *, fallback: str) -> str:
        user_name = payload.get("user_name")
        if isinstance(user_name, str) and user_name.strip():
            return user_name.strip()

        info = payload.get("Info")
        if isinstance(info, dict) and isinstance(info.get("Name"), str):
            info_name = info["Name"].strip()
            if info_name:
                return info_name

        return fallback

    @staticmethod
    def _normalize_uid(user_uid: Any) -> uuid.UUID:
        if isinstance(user_uid, uuid.UUID):
            return user_uid
        nested_uid = getattr(user_uid, "uid", None)
        if isinstance(nested_uid, uuid.UUID):
            return nested_uid
        return uuid.UUID(str(nested_uid if nested_uid is not None else user_uid))

    def _iter_user_uids(self) -> Iterator[uuid.UUID]:
        keys = getattr(self._user_data, "keys", None)
        if callable(keys):
            for user_uid in keys():
                yield self._normalize_uid(user_uid)
            return
        for user_uid in self._user_data.order:
            yield self._normalize_uid(user_uid)

    @property
    def _user_data(self) -> Any:
        user_data = getattr(self.storage_script_config, "UserData", None)
        if user_data is None:
            raise RuntimeError("Current script storage does not provide UserData")
        return user_data
