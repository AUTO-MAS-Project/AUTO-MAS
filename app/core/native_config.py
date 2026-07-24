"""Host-facing facade backed exclusively by native Config v2 roots.

This module is intentionally import-independent from ``app.models.ConfigBase``
and ``app.core.config``.  It preserves the HTTP/service-level configuration
contract while the callers are migrated off the legacy object graph.
"""

from __future__ import annotations

import asyncio
import copy
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

from app.configuration.authoritative import (
    AuthoritativeConfigurationRuntime,
    AuthoritativeRuntimeState,
    ensure_authoritative_path_budget,
)
from app.configuration.production import ProductionRoots
from app.configuration.roots.config import Webhook
from app.configuration.roots.emulator import Emulator
from app.configuration.roots.game_sign import GameSignAccount
from app.configuration.roots.plan import MaaPlan
from app.configuration.roots.queue import Queue, QueueItem, TimeSet
from app.configuration.roots.script import (
    GeneralScript,
    GeneralUser,
    M9AScript,
    M9AUser,
    MaaEndScript,
    MaaEndUser,
    MaaFWScript,
    MaaFWUser,
    MaaScript,
    MaaUser,
    PluginScript,
    PluginUser,
    SrcScript,
    SrcUser,
)
from app.configuration.v2.collection import ConfigCollection
from app.configuration.v2.entry import ConfigEntry
from app.configuration.v2.fields import is_virtual_model_field
from app.configuration.v2.manager import config_manager


PowerAction = Literal[
    "NoAction",
    "Shutdown",
    "ShutdownForce",
    "Reboot",
    "Hibernate",
    "Sleep",
    "KillSelf",
    "Logoff",
]


@dataclass(frozen=True)
class _NativeScriptCrudDescriptor:
    """Static v2 types that can safely serve the legacy scripts transport."""

    api_type_key: str
    legacy_script_type: str
    script_entry_type: type[ConfigEntry]
    legacy_user_type: str
    user_entry_type: type[ConfigEntry]
    writable: bool = True


_NATIVE_SCRIPT_CRUD_DESCRIPTORS = (
    _NativeScriptCrudDescriptor(
        "MAA", "MaaConfig", MaaScript, "MaaUserConfig", MaaUser
    ),
    _NativeScriptCrudDescriptor(
        "SRC", "SrcConfig", SrcScript, "SrcUserConfig", SrcUser
    ),
    _NativeScriptCrudDescriptor(
        "MaaEnd", "MaaEndConfig", MaaEndScript, "MaaEndUserConfig", MaaEndUser
    ),
    _NativeScriptCrudDescriptor(
        "M9A", "M9AConfig", M9AScript, "M9AUserConfig", M9AUser
    ),
    _NativeScriptCrudDescriptor(
        "MaaFW", "MaaFWConfig", MaaFWScript, "MaaFWUserConfig", MaaFWUser
    ),
    _NativeScriptCrudDescriptor(
        "General", "GeneralConfig", GeneralScript, "GeneralUserConfig", GeneralUser
    ),
    # Plugin records are readable so existing users can inspect opaque
    # metadata.  Their public type is resolved from Meta.PluginTypeKey and
    # writes are handled by the provider-aware native codec, never by this
    # static descriptor.
    _NativeScriptCrudDescriptor(
        "PluginScript",
        "PluginScriptConfig",
        PluginScript,
        "PluginUserConfig",
        PluginUser,
        writable=False,
    ),
)
_SCRIPT_DESCRIPTOR_BY_API_TYPE = {
    item.api_type_key: item for item in _NATIVE_SCRIPT_CRUD_DESCRIPTORS
}
_SCRIPT_DESCRIPTOR_BY_ENTRY_TYPE = {
    item.script_entry_type: item for item in _NATIVE_SCRIPT_CRUD_DESCRIPTORS
}


def _read_version(workspace_root: Path) -> str:
    try:
        payload = json.loads(
            (workspace_root / "res" / "version.json").read_text(encoding="utf-8")
        )
        version = payload["version"]
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError):
        return "v6.0.0-alpha.UNKNOWN"
    return version if isinstance(version, str) else "v6.0.0-alpha.UNKNOWN"


class NativeConfigFacade:
    """Business facade for the eight authoritative Config v2 roots."""

    def __init__(
        self,
        *,
        workspace_root: Path | None = None,
        config_directory: Path | None = None,
    ) -> None:
        self.workspace_root = Path(
            Path.cwd() if workspace_root is None else workspace_root
        ).resolve(strict=False)
        self.config_path = Path(
            self.workspace_root / "config"
            if config_directory is None
            else config_directory
        ).resolve(strict=False)
        self.log_path = self.workspace_root / "debug" / "app.log"
        self.database_path = self.workspace_root / "data" / "data.db"
        self.history_path = self.workspace_root / "history"
        self.VERSION = _read_version(self.workspace_root)

        self.server: Any | None = None
        self.websocket: Any | None = None
        self._websocket_missing_logged = False
        self.power_sign: PowerAction = "NoAction"
        self.temp_task: list[asyncio.Task[Any]] = []
        self.loop: asyncio.AbstractEventLoop | None = None

        self._runtime = AuthoritativeConfigurationRuntime(self.config_path)

    @property
    def initialized(self) -> bool:
        try:
            self._runtime.state
        except RuntimeError:
            return False
        return True

    @property
    def state(self) -> AuthoritativeRuntimeState:
        return self._runtime.state

    @property
    def roots(self) -> ProductionRoots:
        return self._runtime.roots

    @property
    def EmulatorConfig(self):  # noqa: N802 - stable host-facing name
        return self.roots.emulators

    @property
    def PlanConfig(self):  # noqa: N802 - stable host-facing name
        return self.roots.plans

    @property
    def ScriptConfig(self):  # noqa: N802 - stable host-facing name
        return self.roots.scripts

    @property
    def QueueConfig(self):  # noqa: N802 - stable host-facing name
        return self.roots.queues

    @property
    def ToolsConfig(self):  # noqa: N802 - stable host-facing name
        return self.roots.tools

    @property
    def PluginConfig(self):  # noqa: N802 - stable host-facing name
        return self.roots.plugins

    @property
    def GameSign_Accounts(self):  # noqa: N802 - stable host-facing name
        return self.roots.game_sign_accounts

    @property
    def Notify_CustomWebhooks(self):  # noqa: N802 - stable host-facing name
        return self.roots.config.Notify_CustomWebhooks

    def __getattr__(self, name: str) -> object:
        # Global groups (Function/Voice/Start/UI/Notify/Update/Data) remain
        # discoverable on the facade without making the facade a ConfigEntry.
        if name.startswith("_"):
            raise AttributeError(name)
        root = self.roots.config
        if name in root.model_fields:
            return getattr(root, name)
        raise AttributeError(name)

    async def init_config(self) -> None:
        """Activate the authoritative generation without legacy initialization."""

        ensure_authoritative_path_budget(self.config_path)
        self.config_path.mkdir(parents=True, exist_ok=True)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.history_path.mkdir(parents=True, exist_ok=True)
        self.loop = asyncio.get_running_loop()
        await self._runtime.initialize()

    def close(self) -> None:
        self._runtime.close()

    def export_r6_rollback_bundle(self, export_parent: Path | None = None) -> Path:
        return self._runtime.export_r6_rollback_bundle(export_parent)

    def get(self, group: str, field: str) -> object:
        return self.roots.config.get(group, field)

    async def set(self, group: str, field: str, value: object) -> None:
        await self.roots.config.set(group, field, value)

    async def toDict(  # noqa: N802 - stable host transport surface
        self,
        if_decrypt: bool = True,
        regenerate_uuids: bool = False,
    ) -> dict[str, object]:
        if regenerate_uuids:
            raise ValueError("global configuration has no regenerable identity")
        return await self.roots.config.to_dict(
            if_decrypt=if_decrypt,
            include_reactive=if_decrypt,
        )

    async def send_json(self, data: dict[str, object]) -> None:
        """Send a legacy raw envelope through the single WS core."""

        from app.core.ws.bootstrap import send_json

        await send_json(data)

    async def send_websocket_message(
        self,
        id: str,
        type: str,
        data: dict[str, object],
    ) -> None:
        """Preserve the external plugin WS sender contract."""

        from app.core.ws.bootstrap import send_websocket_message

        await send_websocket_message(id=id, type=type, data=data)

    @staticmethod
    async def _entry_payload(entry: ConfigEntry) -> dict[str, object]:
        return await entry.to_dict(
            if_decrypt=True,
            include_reactive=True,
        )

    @classmethod
    async def _collection_payload(
        cls,
        collection: ConfigCollection[ConfigEntry],
        *,
        legacy_type: str,
        uid: UUID | None = None,
    ) -> tuple[list[dict[str, str]], dict[str, dict[str, object]]]:
        if uid is None:
            selected = list(collection.keys())
        else:
            if uid not in collection:
                raise ValueError(f"配置项 '{uid}' 不存在")
            selected = [uid]
        index = [
            {"uid": str(item_uid), "type": legacy_type}
            for item_uid in selected
        ]
        data = {
            str(item_uid): await cls._entry_payload(collection[item_uid])
            for item_uid in selected
        }
        return index, data

    @staticmethod
    async def _update_entry(
        entry: ConfigEntry,
        data: Mapping[str, Mapping[str, object]],
    ) -> None:
        """Apply a legacy transport update without persisting read-only views.

        ``toDict()`` deliberately includes virtual fields so legacy callers
        can render them.  The historical read-then-save flow sends that
        complete payload back to the host, however virtual values are
        calculated views in Config v2 and cannot be assigned.  Drop only the
        registered virtual paths; unknown fields still reach ``set_many`` and
        fail normally, while trigger fields retain their existing semantics.
        """

        # Some legacy script groups declare ``Virtual[...]`` fields on a
        # shared group class while registering their getter on a subclass.
        # Derive the compatibility filter from the effective group's field
        # metadata rather than relying only on the entry decorator registry.
        virtual_paths = {
            (group_name, field_name)
            for group_name in type(entry)._cfg_group_fields
            for field_name, field_info in type(
                getattr(entry.effective, group_name)
            ).model_fields.items()
            if is_virtual_model_field(field_info)
        }
        writable_data = {
            group: {
                field: value
                for field, value in fields.items()
                if (group, field) not in virtual_paths
            }
            for group, fields in data.items()
        }
        writable_data = {
            group: fields for group, fields in writable_data.items() if fields
        }
        if writable_data:
            await entry.set_many(writable_data)

    @staticmethod
    async def _add(
        collection: ConfigCollection[ConfigEntry],
        entry_type: type[ConfigEntry],
    ) -> tuple[UUID, ConfigEntry]:
        uid = collection.add(entry_type)
        await collection.commit()
        return uid, collection[uid]

    @staticmethod
    async def _remove(
        collection: ConfigCollection[ConfigEntry],
        uid: UUID,
    ) -> None:
        collection.remove(uid)
        await collection.commit()

    @staticmethod
    async def _reorder(
        collection: ConfigCollection[ConfigEntry],
        order: list[str],
    ) -> None:
        collection.set_order([UUID(item) for item in order])
        await collection.commit()

    @staticmethod
    def _script_descriptor_for_entry(
        entry: ConfigEntry,
    ) -> _NativeScriptCrudDescriptor:
        descriptor = _SCRIPT_DESCRIPTOR_BY_ENTRY_TYPE.get(type(entry))
        if descriptor is None:
            raise RuntimeError(
                "Config v2 尚不能为该脚本类型生成兼容 transport: "
                f"{type(entry).__name__}"
            )
        return descriptor

    @classmethod
    def _script_type_key_for_entry(cls, entry: ConfigEntry) -> str:
        """Resolve the provider type key without loading the legacy graph."""

        descriptor = cls._script_descriptor_for_entry(entry)
        if descriptor.script_entry_type is not PluginScript:
            return descriptor.api_type_key

        type_key = str(entry.get("Meta", "PluginTypeKey") or "").strip()
        if not type_key:
            raise KeyError("插件脚本记录缺少 Meta.PluginTypeKey")
        return type_key

    def get_script_type_key(self, script_id: str | UUID) -> str:
        """Return the authoritative provider key for one script record."""

        uid = script_id if isinstance(script_id, UUID) else UUID(script_id)
        return self._script_type_key_for_entry(self.roots.scripts[uid])

    @staticmethod
    def _decode_plugin_config(raw: object) -> dict[str, Any]:
        if raw in (None, ""):
            return {}
        if isinstance(raw, dict):
            return json.loads(json.dumps(raw, ensure_ascii=False))
        if not isinstance(raw, str):
            raise TypeError(
                "插件脚本配置必须是 JSON 对象或 JSON 字符串: "
                f"{type(raw).__name__}"
            )
        decoded = json.loads(raw)
        if not isinstance(decoded, dict):
            raise TypeError("插件脚本配置 JSON 必须是对象")
        return decoded

    def _resolve_script_record_provider(self, entry: ConfigEntry) -> Any:
        """Resolve a loaded provider or an explicit unavailable fallback."""

        from app.core.script_types import (
            build_unavailable_plugin_fallback_provider,
            script_type_registry,
        )

        script_type_registry.bootstrap()
        type_key = self._script_type_key_for_entry(entry)
        try:
            return script_type_registry.get(type_key)
        except KeyError:
            return build_unavailable_plugin_fallback_provider(type_key)

    @staticmethod
    def _require_native_provider(provider: Any, *, action: str) -> None:
        """Reject legacy provider classes on the authoritative runtime."""

        if provider.metadata.get("available", True) is False:
            reason = str(
                provider.metadata.get("unavailable_reason")
                or "provider 当前不可用"
            )
            raise RuntimeError(
                f"脚本类型 {provider.type_key} 当前不可用，无法{action}: {reason}"
            )
        for config_class in (
            provider.script_config_class,
            provider.user_config_class,
        ):
            if not isinstance(config_class, type) or not issubclass(
                config_class,
                BaseModel,
            ):
                raise RuntimeError(
                    f"脚本类型 {provider.type_key} 仍依赖旧配置基类，无法{action}"
                )

    @staticmethod
    def _schema_default_payload(schema: dict[str, Any]) -> dict[str, Any]:
        """Build a new record payload from the provider's declared defaults."""

        payload: dict[str, Any] = {}
        groups = schema.get("groups")
        if not isinstance(groups, list):
            return payload
        for group in groups:
            if not isinstance(group, dict):
                continue
            group_key = str(group.get("key") or "").strip()
            fields = group.get("fields")
            if not group_key or not isinstance(fields, list):
                continue
            group_payload: dict[str, Any] = {}
            for field in fields:
                if not isinstance(field, dict) or "default" not in field:
                    continue
                field_name = str(field.get("name") or "").strip()
                if not field_name:
                    continue
                group_payload[field_name] = copy.deepcopy(field["default"])
            if group_payload:
                payload[group_key] = group_payload
        return payload

    @classmethod
    async def _provider_default_payload(
        cls,
        provider: Any,
        kind: Literal["script", "user"],
    ) -> dict[str, Any]:
        from app.core.script_config_codec import form_to_storage

        schema = (
            provider.build_script_schema()
            if kind == "script"
            else provider.build_user_schema()
        )
        return await form_to_storage(
            provider,
            cls._schema_default_payload(schema),
            kind,
        )

    @staticmethod
    def _record_name(
        provider: Any,
        payload: dict[str, Any],
        fallback: str,
    ) -> str:
        for candidate in (
            payload.get("script_name"),
            payload.get("user_name"),
        ):
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        info = payload.get("Info")
        if isinstance(info, dict):
            name = info.get("Name")
            if isinstance(name, str) and name.strip():
                return name.strip()
        return fallback

    @classmethod
    async def _provider_form_payload(
        cls,
        provider: Any,
        raw_payload: object,
        kind: Literal["script", "user"],
    ) -> dict[str, Any]:
        from app.core.script_config_codec import storage_to_form

        return await storage_to_form(
            provider,
            cls._decode_plugin_config(raw_payload),
            kind,
        )

    async def _script_record_config_data(
        self,
        entry: ConfigEntry,
    ) -> dict[str, Any]:
        if type(entry) is PluginScript:
            provider = self._resolve_script_record_provider(entry)
            return await self._provider_form_payload(
                provider,
                entry.get("PluginData", "Config"),
                "script",
            )
        payload = await entry.toDict(if_decrypt=True)
        payload.pop("UserData", None)
        payload.pop("SubConfigsInfo", None)
        return payload

    async def get_script_record_capability(
        self,
        script_id: str | UUID,
    ) -> Any:
        """Resolve executable modes directly from the authoritative record."""

        uid = script_id if isinstance(script_id, UUID) else UUID(script_id)
        entry = self.roots.scripts[uid]
        provider = self._resolve_script_record_provider(entry)
        config_data = (
            await self._script_record_config_data(entry)
            if provider.record_capability_resolver is not None
            else {}
        )
        return provider.resolve_record_capability(config_data)

    async def get_script_type_descriptors(self) -> list[Any]:
        """Return provider descriptors without constructing ConfigBase models."""

        from app.core.script_types import (
            build_descriptor,
            script_type_registry,
        )
        from app.models.script_api import ScriptTypeDescriptor

        script_type_registry.bootstrap()
        return [
            ScriptTypeDescriptor(**build_descriptor(provider))
            for provider in script_type_registry.list()
        ]

    @staticmethod
    def _require_writable_script_descriptor(
        descriptor: _NativeScriptCrudDescriptor,
        *,
        action: str,
    ) -> None:
        if descriptor.writable:
            return
        raise RuntimeError(
            f"脚本类型 {descriptor.legacy_script_type} 尚未完成原生 provider/codec "
            f"迁移，无法{action}"
        )

    @classmethod
    async def _legacy_webhook_collection_transport(
        cls,
        collection: ConfigCollection[ConfigEntry],
    ) -> dict[str, object]:
        result: dict[str, object] = {"instances": []}
        index = result["instances"]
        assert isinstance(index, list)
        for uid, entry in collection.items():
            index.append({"uid": str(uid), "type": "Webhook"})
            result[str(uid)] = await cls._entry_payload(entry)
        return result

    @classmethod
    async def _legacy_user_entry_transport(
        cls,
        entry: ConfigEntry,
        descriptor: _NativeScriptCrudDescriptor,
    ) -> dict[str, object]:
        if type(entry) is not descriptor.user_entry_type:
            raise RuntimeError(
                "脚本 UserData 与脚本类型不一致，拒绝生成不可信 transport"
            )
        payload = await cls._entry_payload(entry)
        webhooks = getattr(entry, "Notify_CustomWebhooks", None)
        if webhooks is not None:
            payload.pop("Notify_CustomWebhooks", None)
            payload["SubConfigsInfo"] = {
                "Notify_CustomWebhooks": await cls._legacy_webhook_collection_transport(
                    webhooks
                )
            }
        return payload

    @classmethod
    async def _legacy_user_collection_transport(
        cls,
        script: ConfigEntry,
        descriptor: _NativeScriptCrudDescriptor,
    ) -> dict[str, object]:
        users = getattr(script, "UserData", None)
        if not isinstance(users, ConfigCollection):
            raise RuntimeError("脚本缺少原生 UserData 集合")
        result: dict[str, object] = {"instances": []}
        index = result["instances"]
        assert isinstance(index, list)
        for uid, user in users.items():
            index.append({"uid": str(uid), "type": descriptor.legacy_user_type})
            result[str(uid)] = await cls._legacy_user_entry_transport(
                user,
                descriptor,
            )
        return result

    @classmethod
    async def _legacy_script_entry_transport(
        cls,
        entry: ConfigEntry,
        descriptor: _NativeScriptCrudDescriptor,
    ) -> dict[str, object]:
        payload = await cls._entry_payload(entry)
        # ``to_dict`` exposes v2 ``UserData: {order, data}``.  The old HTTP
        # contract expects exactly ``SubConfigsInfo.UserData`` instead.  This
        # projection is response-only and must never be reused for persistence
        # or r6 rollback conversion (which requires encrypted wire values).
        payload.pop("UserData", None)
        payload["SubConfigsInfo"] = {
            "UserData": await cls._legacy_user_collection_transport(
                entry,
                descriptor,
            )
        }
        return payload

    async def add_script(
        self,
        script: str,
        script_id: str | None = None,
    ) -> tuple[UUID, ConfigEntry]:
        """Create a native static script record without legacy ConfigBase.

        Copy/clone is intentionally rejected: Config v2 must regenerate child
        UUIDs and coordinate external ``data/`` files transactionally before
        that behavior can be made safe.  Dynamic plugin providers likewise
        remain fail-closed until the native provider catalog is available.
        """

        if script_id is not None:
            raise RuntimeError(
                "Config v2 原生脚本暂不支持复制创建；请新建脚本或使用兼容迁移流程"
            )
        descriptor = _SCRIPT_DESCRIPTOR_BY_API_TYPE.get(script)
        if descriptor is not None and descriptor.writable:
            async with config_manager.transaction():
                uid = self.roots.scripts.add(descriptor.script_entry_type)
                await self.roots.scripts.commit()
            return uid, self.roots.scripts[uid]

        from app.core.script_types import script_type_registry

        script_type_registry.bootstrap()
        try:
            provider = script_type_registry.get(script)
        except KeyError:
            raise RuntimeError(
                f"脚本类型 {script} 尚未完成原生 Config v2 迁移，无法新增"
            ) from None
        self._require_native_provider(provider, action="新增")
        payload = await self._provider_default_payload(provider, "script")
        name = self._record_name(provider, payload, provider.display_name)

        async with config_manager.transaction():
            uid = self.roots.scripts.add(PluginScript)
            await self.roots.scripts.commit()
            await self.roots.scripts[uid].set_many(
                {
                    "Meta": {"PluginTypeKey": provider.type_key},
                    "Info": {"Name": name},
                    "PluginData": {
                        "Config": json.dumps(payload, ensure_ascii=False)
                    },
                }
            )
        return uid, self.roots.scripts[uid]

    async def get_script(
        self,
        script_id: str | None,
    ) -> tuple[list[dict[str, str]], dict[str, dict[str, object]]]:
        """Return legacy-compatible script records from native typed roots."""

        if script_id is None:
            selected = list(self.roots.scripts.items())
        else:
            uid = UUID(script_id)
            if uid not in self.roots.scripts:
                raise ValueError(f"配置项 '{uid}' 不存在")
            selected = [(uid, self.roots.scripts[uid])]

        index: list[dict[str, str]] = []
        data: dict[str, dict[str, object]] = {}
        for uid, entry in selected:
            descriptor = self._script_descriptor_for_entry(entry)
            index.append({"uid": str(uid), "type": descriptor.legacy_script_type})
            data[str(uid)] = await self._legacy_script_entry_transport(
                entry,
                descriptor,
            )
        return index, data

    async def update_script(
        self,
        script_id: str,
        data: Mapping[str, Mapping[str, object]],
    ) -> None:
        uid = UUID(script_id)
        entry = self.roots.scripts[uid]
        if entry.is_locked:
            raise RuntimeError(f"脚本 {script_id} 正在运行, 无法更新配置项")
        descriptor = self._script_descriptor_for_entry(entry)
        if type(entry) is PluginScript:
            provider = self._resolve_script_record_provider(entry)
            self._require_native_provider(provider, action="更新")
            from app.core.script_config_codec import form_to_storage

            payload = await form_to_storage(provider, dict(data), "script")
            name = self._record_name(
                provider,
                payload,
                str(entry.get("Info", "Name") or provider.display_name),
            )
            await entry.set_many(
                {
                    "Info": {"Name": name},
                    "PluginData": {
                        "Config": json.dumps(payload, ensure_ascii=False)
                    },
                }
            )
            return
        self._require_writable_script_descriptor(descriptor, action="更新")
        await self._update_entry(entry, data)

    async def del_script(self, script_id: str) -> None:
        """Delete a static script and its queue references atomically.

        The native reference field uses ``SET_DEFAULT`` by design; the legacy
        public API instead removed matching QueueItem records.  Keep that
        observable behavior in this facade without broadening the underlying
        reference policy.  External ``data/<script>`` cleanup is deliberately
        deferred because filesystem deletion is not rollback-safe yet.
        """

        script_uid = UUID(script_id)
        script = self.roots.scripts[script_uid]
        if script.is_locked:
            raise RuntimeError(f"脚本 {script_id} 正在运行, 无法删除")
        descriptor = self._script_descriptor_for_entry(script)
        if type(script) is not PluginScript:
            self._require_writable_script_descriptor(descriptor, action="删除")

        async with config_manager.transaction():
            for queue_uid, queue in self.roots.queues.items():
                matching_items = [
                    item_uid
                    for item_uid, item in queue.QueueItem.items()
                    if item.Info.ScriptId == str(script_uid)
                ]
                if not matching_items:
                    continue
                if queue.is_locked:
                    raise RuntimeError(
                        f"队列 {queue_uid} 正在运行, 无法删除关联脚本"
                    )
                for item_uid in matching_items:
                    item = queue.QueueItem[item_uid]
                    if item.is_locked:
                        raise RuntimeError(
                            f"队列项 {item_uid} 正在运行, 无法删除关联脚本"
                        )
                    queue.QueueItem.remove(item_uid)
                    await queue.QueueItem.commit()
            self.roots.scripts.remove(script_uid)
            await self.roots.scripts.commit()

    async def reorder_script(self, index_list: list[str]) -> None:
        await self._reorder(self.roots.scripts, index_list)

    async def get_user(
        self,
        script_id: str,
        user_id: str | None,
    ) -> tuple[list[dict[str, str]], dict[str, dict[str, object]]]:
        script = self.roots.scripts[UUID(script_id)]
        descriptor = self._script_descriptor_for_entry(script)
        users = getattr(script, "UserData", None)
        if not isinstance(users, ConfigCollection):
            raise RuntimeError("脚本缺少原生 UserData 集合")
        if user_id is None:
            selected = list(users.items())
        else:
            uid = UUID(user_id)
            if uid not in users:
                raise ValueError(f"配置项 '{uid}' 不存在")
            selected = [(uid, users[uid])]

        index: list[dict[str, str]] = []
        data: dict[str, dict[str, object]] = {}
        for uid, entry in selected:
            index.append({"uid": str(uid), "type": descriptor.legacy_user_type})
            data[str(uid)] = await self._legacy_user_entry_transport(
                entry,
                descriptor,
            )
        return index, data

    async def add_user(self, script_id: str) -> tuple[UUID, ConfigEntry]:
        script = self.roots.scripts[UUID(script_id)]
        descriptor = self._script_descriptor_for_entry(script)
        if type(script) is PluginScript:
            provider = self._resolve_script_record_provider(script)
            self._require_native_provider(provider, action="新增用户")
            payload = await self._provider_default_payload(provider, "user")
            name = self._record_name(provider, payload, "新用户")
            users = script.UserData
            async with config_manager.transaction():
                uid = users.add(PluginUser)
                await users.commit()
                await users[uid].set_many(
                    {
                        "Meta": {"PluginTypeKey": provider.type_key},
                        "Info": {"Name": name},
                        "PluginData": {
                            "Config": json.dumps(payload, ensure_ascii=False)
                        },
                    }
                )
            return uid, users[uid]
        self._require_writable_script_descriptor(descriptor, action="新增用户")
        users = getattr(script, "UserData", None)
        if not isinstance(users, ConfigCollection):
            raise RuntimeError("脚本缺少原生 UserData 集合")
        async with config_manager.transaction():
            uid = users.add(descriptor.user_entry_type)
            await users.commit()
        return uid, users[uid]

    async def update_user(
        self,
        script_id: str,
        user_id: str,
        data: Mapping[str, Mapping[str, object]],
    ) -> None:
        script = self.roots.scripts[UUID(script_id)]
        descriptor = self._script_descriptor_for_entry(script)
        if type(script) is PluginScript:
            provider = self._resolve_script_record_provider(script)
            self._require_native_provider(provider, action="更新用户")
            from app.core.script_config_codec import form_to_storage

            payload = await form_to_storage(provider, dict(data), "user")
            user = script.UserData[UUID(user_id)]
            name = self._record_name(
                provider,
                payload,
                str(user.get("Info", "Name") or "新用户"),
            )
            await user.set_many(
                {
                    "Info": {"Name": name},
                    "PluginData": {
                        "Config": json.dumps(payload, ensure_ascii=False)
                    },
                }
            )
            return
        self._require_writable_script_descriptor(descriptor, action="更新用户")
        users = getattr(script, "UserData", None)
        if not isinstance(users, ConfigCollection):
            raise RuntimeError("脚本缺少原生 UserData 集合")
        await self._update_entry(users[UUID(user_id)], data)

    async def del_user(self, script_id: str, user_id: str) -> None:
        script = self.roots.scripts[UUID(script_id)]
        descriptor = self._script_descriptor_for_entry(script)
        if type(script) is not PluginScript:
            self._require_writable_script_descriptor(descriptor, action="删除用户")
        users = getattr(script, "UserData", None)
        if not isinstance(users, ConfigCollection):
            raise RuntimeError("脚本缺少原生 UserData 集合")
        user_uid = UUID(user_id)
        user = users[user_uid]
        if user.is_locked:
            raise RuntimeError(f"用户 {user_id} 正在运行, 无法删除")
        async with config_manager.transaction():
            users.remove(user_uid)
            await users.commit()

    async def reorder_user(self, script_id: str, index_list: list[str]) -> None:
        script = self.roots.scripts[UUID(script_id)]
        descriptor = self._script_descriptor_for_entry(script)
        if type(script) is not PluginScript:
            self._require_writable_script_descriptor(
                descriptor,
                action="调整用户顺序",
            )
        users = getattr(script, "UserData", None)
        if not isinstance(users, ConfigCollection):
            raise RuntimeError("脚本缺少原生 UserData 集合")
        await self._reorder(users, index_list)

    async def get_script_records(
        self,
        script_id: str | None = None,
    ) -> list[Any]:
        """Return the unified scripts2 records from authoritative roots."""

        from app.models.script_api import ScriptRecord

        if script_id is None:
            selected = list(self.roots.scripts.items())
        else:
            uid = UUID(script_id)
            selected = [(uid, self.roots.scripts[uid])]

        records: list[ScriptRecord] = []
        for uid, entry in selected:
            provider = self._resolve_script_record_provider(entry)
            config_data = await self._script_record_config_data(entry)
            name = self._record_name(
                provider,
                config_data,
                str(entry.get("Info", "Name") or provider.display_name),
            )
            if type(entry) is PluginScript:
                config_data.setdefault("Info", {})["Name"] = name
            capability = provider.resolve_record_capability(config_data)
            records.append(
                ScriptRecord(
                    id=str(uid),
                    type=provider.type_key,
                    name=name,
                    config=config_data,
                    schema=copy.deepcopy(provider.build_script_schema()),
                    editor_kind=provider.editor_kind,
                    supported_modes=list(capability.supported_modes or ()),
                    available=capability.available,
                    unavailable_reason=capability.unavailable_reason,
                    icon=provider.icon,
                    icon_url=(
                        f"/api/script-types/{provider.type_key}/icon"
                        if provider.icon_path
                        else None
                    ),
                    theme_color=provider.metadata.get("theme_color"),
                    docs_url=provider.docs_url,
                    edit_hint=provider.metadata.get("script_edit_hint"),
                    user_count=len(entry.UserData),
                )
            )
        return records

    async def get_user_records(
        self,
        script_id: str,
        user_id: str | None = None,
    ) -> list[Any]:
        """Return unified user records without constructing MultipleConfig."""

        from app.models.script_api import ScriptUserRecord

        script_uid = UUID(script_id)
        script = self.roots.scripts[script_uid]
        provider = self._resolve_script_record_provider(script)
        users = getattr(script, "UserData", None)
        if not isinstance(users, ConfigCollection):
            raise RuntimeError("脚本缺少原生 UserData 集合")
        if user_id is None:
            selected = list(users.items())
        else:
            uid = UUID(user_id)
            selected = [(uid, users[uid])]

        records: list[ScriptUserRecord] = []
        for uid, entry in selected:
            if type(entry) is PluginUser:
                config_data = await self._provider_form_payload(
                    provider,
                    entry.get("PluginData", "Config"),
                    "user",
                )
                name = self._record_name(
                    provider,
                    config_data,
                    str(entry.get("Info", "Name") or uid),
                )
                config_data.setdefault("Info", {})["Name"] = name
            else:
                config_data = await entry.toDict(if_decrypt=True)
                config_data.pop("Notify_CustomWebhooks", None)
                config_data.pop("SubConfigsInfo", None)
                name = self._record_name(provider, config_data, str(uid))
            records.append(
                ScriptUserRecord(
                    id=str(uid),
                    script_id=str(script_uid),
                    type=provider.type_key,
                    name=name,
                    config=config_data,
                    schema=copy.deepcopy(provider.build_user_schema()),
                )
            )
        return records

    async def get_setting(self) -> dict[str, object]:
        return await self._entry_payload(self.roots.config)

    async def update_setting(
        self,
        data: Mapping[str, Mapping[str, object]],
    ) -> None:
        await self._update_entry(self.roots.config, data)

    async def get_tools(self) -> dict[str, object]:
        return await self._entry_payload(self.roots.tools)

    async def update_tools(
        self,
        data: Mapping[str, Mapping[str, object]],
    ) -> None:
        await self._update_entry(self.roots.tools, data)

    async def add_plan(self, script: str) -> tuple[UUID, ConfigEntry]:
        if script != "MaaPlan":
            raise ValueError(f"不支持的计划类型: {script}")
        return await self._add(self.roots.plans, MaaPlan)

    async def get_plan(
        self,
        plan_id: str | None,
    ) -> tuple[list[dict[str, str]], dict[str, dict[str, object]]]:
        return await self._collection_payload(
            self.roots.plans,
            legacy_type="MaaPlanConfig",
            uid=None if plan_id is None else UUID(plan_id),
        )

    async def update_plan(
        self,
        plan_id: str,
        data: Mapping[str, Mapping[str, object]],
    ) -> None:
        await self._update_entry(self.roots.plans[plan_id], data)

    async def del_plan(self, plan_id: str) -> None:
        await self._remove(self.roots.plans, UUID(plan_id))

    async def reorder_plan(self, index_list: list[str]) -> None:
        await self._reorder(self.roots.plans, index_list)

    async def add_emulator(self) -> tuple[UUID, ConfigEntry]:
        return await self._add(self.roots.emulators, Emulator)

    async def get_emulator(
        self,
        emulator_id: str | None,
    ) -> tuple[list[dict[str, str]], dict[str, dict[str, object]]]:
        return await self._collection_payload(
            self.roots.emulators,
            legacy_type="EmulatorConfig",
            uid=None if emulator_id is None else UUID(emulator_id),
        )

    async def update_emulator(
        self,
        emulator_id: str,
        data: Mapping[str, Mapping[str, object]],
    ) -> None:
        await self._update_entry(self.roots.emulators[emulator_id], data)

    async def del_emulator(self, emulator_id: str) -> None:
        await self._remove(self.roots.emulators, UUID(emulator_id))

    async def reorder_emulator(self, index_list: list[str]) -> None:
        await self._reorder(self.roots.emulators, index_list)

    async def add_queue(self) -> tuple[UUID, ConfigEntry]:
        return await self._add(self.roots.queues, Queue)

    async def get_queue(
        self,
        queue_id: str | None,
    ) -> tuple[list[dict[str, str]], dict[str, dict[str, object]]]:
        return await self._collection_payload(
            self.roots.queues,
            legacy_type="QueueConfig",
            uid=None if queue_id is None else UUID(queue_id),
        )

    async def update_queue(
        self,
        queue_id: str,
        data: Mapping[str, Mapping[str, object]],
    ) -> None:
        await self._update_entry(self.roots.queues[queue_id], data)

    async def del_queue(self, queue_id: str) -> None:
        await self._remove(self.roots.queues, UUID(queue_id))

    async def reorder_queue(self, index_list: list[str]) -> None:
        await self._reorder(self.roots.queues, index_list)

    def _queue_child(
        self,
        queue_id: str,
        name: Literal["TimeSet", "QueueItem"],
    ) -> ConfigCollection[ConfigEntry]:
        queue = self.roots.queues[queue_id]
        return getattr(queue, name)

    async def get_time_set(
        self,
        queue_id: str,
        time_set_id: str | None,
    ) -> tuple[list[dict[str, str]], dict[str, dict[str, object]]]:
        return await self._collection_payload(
            self._queue_child(queue_id, "TimeSet"),
            legacy_type="TimeSet",
            uid=None if time_set_id is None else UUID(time_set_id),
        )

    async def add_time_set(self, queue_id: str) -> tuple[UUID, ConfigEntry]:
        return await self._add(self._queue_child(queue_id, "TimeSet"), TimeSet)

    async def update_time_set(
        self,
        queue_id: str,
        time_set_id: str,
        data: Mapping[str, Mapping[str, object]],
    ) -> None:
        await self._update_entry(
            self._queue_child(queue_id, "TimeSet")[time_set_id],
            data,
        )

    async def del_time_set(self, queue_id: str, time_set_id: str) -> None:
        await self._remove(
            self._queue_child(queue_id, "TimeSet"),
            UUID(time_set_id),
        )

    async def reorder_time_set(
        self,
        queue_id: str,
        index_list: list[str],
    ) -> None:
        await self._reorder(
            self._queue_child(queue_id, "TimeSet"),
            index_list,
        )

    async def get_queue_item(
        self,
        queue_id: str,
        queue_item_id: str | None,
    ) -> tuple[list[dict[str, str]], dict[str, dict[str, object]]]:
        return await self._collection_payload(
            self._queue_child(queue_id, "QueueItem"),
            legacy_type="QueueItem",
            uid=None if queue_item_id is None else UUID(queue_item_id),
        )

    async def add_queue_item(self, queue_id: str) -> tuple[UUID, ConfigEntry]:
        return await self._add(
            self._queue_child(queue_id, "QueueItem"),
            QueueItem,
        )

    async def update_queue_item(
        self,
        queue_id: str,
        queue_item_id: str,
        data: Mapping[str, Mapping[str, object]],
    ) -> None:
        await self._update_entry(
            self._queue_child(queue_id, "QueueItem")[queue_item_id],
            data,
        )

    async def del_queue_item(self, queue_id: str, queue_item_id: str) -> None:
        await self._remove(
            self._queue_child(queue_id, "QueueItem"),
            UUID(queue_item_id),
        )

    async def reorder_queue_item(
        self,
        queue_id: str,
        index_list: list[str],
    ) -> None:
        await self._reorder(
            self._queue_child(queue_id, "QueueItem"),
            index_list,
        )

    async def get_game_sign_accounts(self) -> dict[str, object]:
        index, data = await self._collection_payload(
            self.roots.game_sign_accounts,
            legacy_type="GameSignAccountGroup",
        )
        return {"instances": index, **data}

    async def add_game_sign_account(self) -> tuple[UUID, ConfigEntry]:
        return await self._add(
            self.roots.game_sign_accounts,
            GameSignAccount,
        )

    async def get_game_sign_account(
        self,
        account_id: str,
    ) -> dict[str, object]:
        return await self._entry_payload(
            self.roots.game_sign_accounts[account_id]
        )

    async def update_game_sign_account(
        self,
        account_id: str,
        data: Mapping[str, Mapping[str, object]],
    ) -> None:
        await self._update_entry(
            self.roots.game_sign_accounts[account_id],
            data,
        )

    async def delete_game_sign_account(self, account_id: str) -> None:
        await self._remove(
            self.roots.game_sign_accounts,
            UUID(account_id),
        )

    async def reorder_game_sign_accounts(self, order: list[str]) -> None:
        await self._reorder(self.roots.game_sign_accounts, order)

    def _webhooks(
        self,
        script_id: str | None,
        user_id: str | None,
    ) -> ConfigCollection[ConfigEntry]:
        if script_id is None and user_id is None:
            return self.roots.config.Notify_CustomWebhooks
        if script_id is None or user_id is None:
            raise ValueError("script_id 与 user_id 必须同时提供")
        script = self.roots.scripts[script_id]
        user_data = getattr(script, "UserData", None)
        if not isinstance(user_data, ConfigCollection):
            raise TypeError("脚本类型不支持用户 Webhook")
        user = user_data[user_id]
        webhooks = getattr(user, "Notify_CustomWebhooks", None)
        if not isinstance(webhooks, ConfigCollection):
            raise TypeError("用户类型不支持 Webhook")
        return webhooks

    async def get_webhook(
        self,
        script_id: str | None,
        user_id: str | None,
        webhook_id: str | None,
    ) -> tuple[list[dict[str, str]], dict[str, dict[str, object]]]:
        return await self._collection_payload(
            self._webhooks(script_id, user_id),
            legacy_type="Webhook",
            uid=None if webhook_id is None else UUID(webhook_id),
        )

    async def add_webhook(
        self,
        script_id: str | None,
        user_id: str | None,
    ) -> tuple[UUID, ConfigEntry]:
        return await self._add(self._webhooks(script_id, user_id), Webhook)

    async def update_webhook(
        self,
        script_id: str | None,
        user_id: str | None,
        webhook_id: str,
        data: Mapping[str, Mapping[str, object]],
    ) -> None:
        await self._update_entry(
            self._webhooks(script_id, user_id)[webhook_id],
            data,
        )

    async def del_webhook(
        self,
        script_id: str | None,
        user_id: str | None,
        webhook_id: str,
    ) -> None:
        await self._remove(
            self._webhooks(script_id, user_id),
            UUID(webhook_id),
        )

    async def reorder_webhook(
        self,
        script_id: str | None,
        user_id: str | None,
        index_list: list[str],
    ) -> None:
        await self._reorder(
            self._webhooks(script_id, user_id),
            index_list,
        )


# Construction is side-effect free: directories and generations are touched
# only by ``init_config``.  This singleton mirrors the stable host import
# surface while remaining independent from the legacy object graph.
Config = NativeConfigFacade()


__all__ = ["Config", "NativeConfigFacade", "PowerAction"]
