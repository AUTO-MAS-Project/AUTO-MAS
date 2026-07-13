from __future__ import annotations

import importlib
import json
import uuid
from pathlib import Path
from typing import Any

from app.core import Config
from app.core.script_config_codec import storage_to_form
from app.models.plugin_script_config import PluginScriptConfig
from app.plugins import PluginHttpRequest, ScriptAdapterDefinition, ScriptAdapterPlugin

from .adapter import OkScriptAdapterHooks
from .common.provider import ok_script_mas_config_dir
from .providers import detect_ok_script_provider
from .shell.manifest import OkProjectInspectError, inspect_ok_project
from .shell.runtime import OkConfigStore
from .schema import OkScriptConfig, OkScriptUserConfig


DEFAULT_INSTANCE = {
    "name": "ok-script 通用适配",
    "enabled": True,
    "config": {},
}

SCRIPT_TYPE_BINDINGS = [
    {
        "type_key": "OkScript",
        "display_name": "ok-script 项目",
        "script_config_class_name": "OkefConfig",
    }
]


def _read_form_config(script_id: str) -> Any:
    return Config.ScriptConfig[uuid.UUID(script_id)]


async def _script_form_config(script_id: str) -> dict[str, Any]:
    storage_config = _read_form_config(script_id)
    if isinstance(storage_config, PluginScriptConfig):
        if str(storage_config.get("Meta", "PluginTypeKey") or "") != "OkScript":
            raise ValueError("脚本不是 ok-script 插件配置")
        from app.core.script_types import script_type_registry

        return await storage_to_form(
            script_type_registry.get("OkScript"),
            storage_config.get("PluginData", "Config"),
            "script",
        )

    data = await storage_config.toDict(if_decrypt=False)
    data.pop("SubConfigsInfo", None)
    return data


def _build_generic_fields(data: dict[str, Any]) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    for name, value in data.items():
        field_type = (
            "bool"
            if isinstance(value, bool)
            else "int"
            if isinstance(value, int)
            else "float"
            if isinstance(value, float)
            else "list"
            if isinstance(value, list)
            else "json"
            if isinstance(value, dict)
            else "string"
        )
        fields.append(
            {
                "name": str(name),
                "label": str(name),
                "type": field_type,
                "description": "",
                "value": value,
                "options": None,
                "section": "通用",
            }
        )
    return fields


def _load_provider_schema(provider: Any):
    module = importlib.import_module(provider.config_schema_module)
    return (
        getattr(module, "build_fields_for_config"),
        getattr(module, provider.config_info_loader),
        getattr(module, f"load_{provider.resource_name.replace('-', '')}_option_labels"),
    )


async def migrate_legacy_okef_config(legacy_script: Any, provider: Any) -> Any:
    """将旧 OkefConfig 转换为插件配置，同时保留用户 UUID 与顺序。"""

    script_data = await legacy_script.toDict(if_decrypt=False)
    script_data.pop("SubConfigsInfo", None)

    migrated_script = provider.script_config_class()
    await migrated_script.load(script_data)

    for user_uid, legacy_user in legacy_script.UserData.items():
        user_data = await legacy_user.toDict(if_decrypt=False)
        user_data.pop("SubConfigsInfo", None)

        migrated_user = provider.user_config_class()
        await migrated_user.load(user_data)
        migrated_script.UserData.order.append(user_uid)
        migrated_script.UserData.data[user_uid] = migrated_user

    return migrated_script


class Plugin(ScriptAdapterPlugin):
    """ok-script 框架项目的通用插件适配器。"""

    def build_script_adapters(self) -> list[ScriptAdapterDefinition]:
        return [
            ScriptAdapterDefinition(
                type_key="OkScript",
                display_name="ok-script 项目",
                script_model=OkScriptConfig,
                user_model=OkScriptUserConfig,
                hooks_factory=OkScriptAdapterHooks,
                supported_modes=("AutoProxy",),
                icon="General",
                editor_kind="builtin:ok-script",
                script_class_name="OkScriptPluginConfig",
                user_class_name="OkScriptPluginUserConfig",
                legacy_config_class_name="OkefConfig",
                legacy_user_config_class_name="OkefUserConfig",
                metadata={
                    "framework": "ok-script",
                    "source": "ok_script_adapter",
                    "legacy_config_migrator": migrate_legacy_okef_config,
                },
            )
        ]

    async def on_start(self) -> None:
        await super().on_start()
        self.ctx.server.http("/ok-script/inspect", self._inspect_project, methods=("POST",))
        self.ctx.server.http("/ok-script/configs/list", self._list_configs, methods=("GET", "POST"))
        self.ctx.server.http("/ok-script/configs/batch-update", self._batch_update_configs, methods=("POST",))

    async def _inspect_project(self, request: PluginHttpRequest) -> dict[str, Any]:
        payload = request.json if isinstance(request.json, dict) else request.query
        root_path = Path(str(payload.get("root_path") or payload.get("rootPath") or ""))
        try:
            manifest = inspect_ok_project(root_path)
            provider = detect_ok_script_provider(
                manifest.root_path,
                manifest.resource_name,
            )
            return {
                "code": 200,
                "status": "success",
                "message": "项目解析成功",
                "data": manifest.to_dict(),
                "provider": provider.build_client_metadata() if provider else None,
            }
        except OkProjectInspectError as exc:
            return {"code": 400, "status": "error", "message": str(exc), "data": None}
        except Exception as exc:
            return {
                "code": 500,
                "status": "error",
                "message": f"{type(exc).__name__}: {exc}",
                "data": None,
            }

    async def _list_configs(self, request: PluginHttpRequest) -> dict[str, Any]:
        payload = request.json if isinstance(request.json, dict) else request.query
        script_id = str(payload.get("script_id") or payload.get("scriptId") or "")
        user_id = str(payload.get("user_id") or payload.get("userId") or "")
        if not script_id or not user_id:
            return {"code": 400, "status": "error", "message": "缺少 script_id 或 user_id"}
        try:
            form_config = await _script_form_config(script_id)
            root_path = Path(str(form_config.get("Info", {}).get("RootPath") or ""))
            manifest = inspect_ok_project(root_path)
            provider = detect_ok_script_provider(root_path, manifest.resource_name)
            config_dir = ok_script_mas_config_dir(script_id, user_id)
            store = OkConfigStore(config_dir)
            if not config_dir.exists() or not any(config_dir.iterdir()):
                store.copy_missing_from(manifest.config_dir)
            else:
                store.copy_missing_from(manifest.config_dir)

            result: list[dict[str, Any]] = []
            option_labels: dict[str, str] = {}
            if provider is not None:
                build_fields, get_config_info, load_labels = _load_provider_schema(provider)
                option_labels = load_labels(root_path)
                infos = get_config_info(config_dir) if provider.config_info_uses_directory else get_config_info()
                for info in infos:
                    filename = str(info["filename"])
                    current_data = store.read(filename) if filename in store.list() else {}
                    fields = build_fields(filename, current_data, option_labels)
                    result.append({**info, "fieldCount": len(fields), "fields": fields, "currentData": current_data})
            else:
                for filename in store.list():
                    if Path(filename).name != filename:
                        continue
                    current_data = store.read(filename)
                    fields = _build_generic_fields(current_data)
                    result.append({"filename": filename, "displayName": filename, "group": "通用配置", "taskIndex": None, "fieldCount": len(fields), "fields": fields, "currentData": current_data})

            provider_data = provider.build_client_metadata() if provider is not None else {
                "resourceName": manifest.resource_name,
                "displayName": manifest.display_name,
                "taskOptions": [{"value": task.index, "label": task.label or task.selector} for task in manifest.tasks],
                "accountFields": None,
                "runtimeVerified": True,
                "runtimeBlockReason": "",
            }
            return {"code": 200, "status": "success", "data": result, "optionLabels": option_labels, "provider": provider_data, "manifest": manifest.to_dict()}
        except (OkProjectInspectError, ValueError, KeyError) as exc:
            return {"code": 400, "status": "error", "message": str(exc), "data": []}
        except Exception as exc:
            return {"code": 500, "status": "error", "message": f"{type(exc).__name__}: {exc}", "data": []}

    async def _batch_update_configs(self, request: PluginHttpRequest) -> dict[str, Any]:
        payload = request.json if isinstance(request.json, dict) else {}
        script_id = str(payload.get("script_id") or payload.get("scriptId") or "")
        user_id = str(payload.get("user_id") or payload.get("userId") or "")
        configs = payload.get("configs")
        if not script_id or not user_id or not isinstance(configs, dict):
            return {"code": 400, "status": "error", "message": "请求参数不完整"}
        try:
            store = OkConfigStore(ok_script_mas_config_dir(script_id, user_id))
            updated = []
            for filename, data in configs.items():
                if not isinstance(filename, str) or not isinstance(data, dict):
                    raise ValueError("配置文件名和配置内容必须有效")
                store.write(filename, data)
                updated.append(filename)
            return {"code": 200, "status": "success", "data": updated}
        except (ValueError, RuntimeError) as exc:
            return {"code": 400, "status": "error", "message": str(exc)}
        except Exception as exc:
            return {"code": 500, "status": "error", "message": f"{type(exc).__name__}: {exc}"}
