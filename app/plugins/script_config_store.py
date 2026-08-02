from __future__ import annotations

import copy
import json
import uuid
from typing import TYPE_CHECKING, Any, Literal, Mapping

from pydantic import BaseModel

from app.core.script_config_codec import (
    build_config_model,
    form_to_storage,
    storage_to_form,
)
from app.models.ConfigBase import ConfigBase, MultipleConfig
from app.models.plugin_script_config import PluginScriptConfig, PluginUserConfig

if TYPE_CHECKING:
    from app.core.script_types import ScriptTypeProvider


ConfigKind = Literal["script", "user"]


class ScriptConfigStore:
    """Separate script schema models from host persistence containers."""

    def __init__(
        self,
        *,
        provider: ScriptTypeProvider,
        storage_script_config: ConfigBase,
    ) -> None:
        self.provider = provider
        self.storage_script_config = storage_script_config

    async def lock(self) -> None:
        await self.storage_script_config.lock()

    async def unlock(self) -> None:
        await self.storage_script_config.unlock()

    async def read_script_data(self) -> dict[str, Any]:
        raw_payload = await self._read_script_storage_payload(if_decrypt=True)
        return await storage_to_form(self.provider, raw_payload, "script")

    async def read_user_data(self, user_uid: uuid.UUID | str) -> dict[str, Any]:
        uid = self._normalize_uid(user_uid)
        raw_payload = await self._read_user_storage_payload(uid, if_decrypt=True)
        return await storage_to_form(self.provider, raw_payload, "user")

    async def read_user_data_pairs(self) -> list[tuple[str, dict[str, Any]]]:
        result: list[tuple[str, dict[str, Any]]] = []
        for user_uid in self._user_data.order:
            result.append((str(user_uid), await self.read_user_data(user_uid)))
        return result

    async def load_script_model(self) -> Any:
        raw_payload = await self._read_script_storage_payload(if_decrypt=False)
        return await build_config_model(
            self.provider,
            raw_payload,
            "script",
            from_storage=True,
        )

    async def load_user_model(
        self,
        user_uid: uuid.UUID | str,
    ) -> Any:
        uid = self._normalize_uid(user_uid)
        raw_payload = await self._read_user_storage_payload(uid, if_decrypt=False)
        return await build_config_model(
            self.provider,
            raw_payload,
            "user",
            from_storage=True,
        )

    async def load_user_models(self) -> list[tuple[str, Any]]:
        result: list[tuple[str, Any]] = []
        for user_uid in self._user_data.order:
            result.append((str(user_uid), await self.load_user_model(user_uid)))
        return result

    async def load_user_collection(self) -> MultipleConfig[Any]:
        collection = MultipleConfig([self.provider.user_config_class])
        for user_uid, user_model in await self.load_user_models():
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
        models: MultipleConfig[Any] | Mapping[uuid.UUID, Any],
    ) -> None:
        if not isinstance(self.storage_script_config, PluginScriptConfig):
            if isinstance(models, MultipleConfig):
                await self._user_data.load(await models.toDict(if_decrypt=False))
                return
            for user_uid, model in models.items():
                await self.save_user_model(user_uid, model)
            return

        for user_uid, model in models.items():
            await self.save_user_model(user_uid, model)

    async def write_script_data(self, form_payload: Mapping[str, Any]) -> None:
        payload = copy.deepcopy(dict(form_payload))
        if isinstance(self.storage_script_config, PluginScriptConfig):
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

        await self.storage_script_config.load(payload)

    async def write_user_data(
        self,
        user_uid: uuid.UUID | str,
        form_payload: Mapping[str, Any],
    ) -> None:
        uid = self._normalize_uid(user_uid)
        storage_user = self._user_data[uid]
        payload = copy.deepcopy(dict(form_payload))

        if isinstance(storage_user, PluginUserConfig):
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

        await storage_user.load(payload)

    async def update_script_data(self, update: Mapping[str, Any]) -> None:
        if not isinstance(self.storage_script_config, PluginScriptConfig):
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
        if not isinstance(storage_user, PluginUserConfig):
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
        if isinstance(self.storage_script_config, PluginScriptConfig):
            return self.storage_script_config.get("PluginData", "Config")
        return await self.storage_script_config.toDict(if_decrypt=if_decrypt)

    async def _read_user_storage_payload(
        self,
        user_uid: uuid.UUID,
        *,
        if_decrypt: bool,
    ) -> Any:
        storage_user = self._user_data[user_uid]
        if isinstance(storage_user, PluginUserConfig):
            return storage_user.get("PluginData", "Config")
        return await storage_user.toDict(if_decrypt=if_decrypt)

    @staticmethod
    async def _model_to_form_data(model: Any) -> dict[str, Any]:
        if isinstance(model, ConfigBase):
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
    def _normalize_uid(user_uid: uuid.UUID | str) -> uuid.UUID:
        return user_uid if isinstance(user_uid, uuid.UUID) else uuid.UUID(user_uid)

    @property
    def _user_data(self) -> Any:
        user_data = getattr(self.storage_script_config, "UserData", None)
        if user_data is None:
            raise RuntimeError("Current script storage does not provide UserData")
        return user_data
