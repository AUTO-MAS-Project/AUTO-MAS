from __future__ import annotations

import asyncio
import importlib
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core import Config as app_config
from app.core.script_config_codec import storage_to_form
from app.models.plugin_script_config import PluginScriptConfig
from app.plugins import PluginHttpRequest, ScriptAdapterDefinition, ScriptAdapterPlugin
from app.utils import get_logger

from .adapter import OkScriptAdapterHooks
from .common.provider import ok_script_mas_config_dir, resolve_game_executable_path
from .common.runtime_lock import get_ok_script_config_lock
from .providers import detect_ok_script_provider, get_ok_script_provider
from .shell.manifest import OkProjectInspectError, inspect_ok_project
from .shell.runtime import OkConfigStore, OkShellRuntimeError
from .schema import Config, OkScriptConfig, OkScriptUserConfig


DEFAULT_INSTANCE = {
    "name": "ok-script 通用适配",
    "enabled": True,
    "config": {},
}
logger = get_logger("ok-script 插件适配")


@dataclass(frozen=True, slots=True)
class _ConfigAccess:
    """Validated ownership and filesystem scope for one user config request."""

    script_uid: uuid.UUID
    user_uid: uuid.UUID
    storage_config: PluginScriptConfig
    config_dir: Path


def normalize_ok_script_form(data: dict[str, Any]) -> dict[str, Any]:
    """根据项目 Manifest 回填可展示的 ok-script 元数据。"""

    info = data.get("Info")
    if not isinstance(info, dict):
        return data

    root_path = str(info.get("RootPath") or "").strip()
    manifest = None
    if root_path:
        try:
            manifest = inspect_ok_project(Path(root_path))
        except (OSError, OkProjectInspectError):
            pass

    if manifest is not None:
        provider = detect_ok_script_provider(
            manifest.root_path,
            manifest.resource_name,
        )
        resource_name = manifest.resource_name
        project_label = (
            provider.display_name
            if provider is not None
            else manifest.display_name or manifest.resource_name
        )
        info["RootPath"] = manifest.root_path.as_posix()
    else:
        provider = get_ok_script_provider(info.get("ResourceName"))
        if provider is None:
            return data
        resource_name = provider.resource_name
        project_label = provider.display_name

    info["ResourceName"] = resource_name
    info["ProjectLabel"] = project_label
    info["Name"] = project_label
    data["script_name"] = project_label
    return data


def _parse_uuid(value: object, field_name: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value).strip())
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError(f"{field_name} 不是有效 UUID") from exc


def _resolve_config_access(script_id: object, user_id: object) -> _ConfigAccess:
    script_uid = _parse_uuid(script_id, "script_id")
    user_uid = _parse_uuid(user_id, "user_id")
    try:
        storage_config = app_config.ScriptConfig[script_uid]
    except (KeyError, TypeError) as exc:
        raise ValueError("指定脚本不存在") from exc

    if not isinstance(storage_config, PluginScriptConfig):
        raise ValueError("脚本不是 ok-script 插件配置")
    if str(storage_config.get("Meta", "PluginTypeKey") or "").strip() != "OkScript":
        raise ValueError("脚本不是 ok-script 插件配置")
    if user_uid not in storage_config.UserData:
        raise ValueError("用户不属于指定 ok-script 脚本")

    return _ConfigAccess(
        script_uid=script_uid,
        user_uid=user_uid,
        storage_config=storage_config,
        config_dir=ok_script_mas_config_dir(script_uid, user_uid),
    )


async def _script_form_config(storage_config: PluginScriptConfig) -> dict[str, Any]:
    from app.core.script_types import script_type_registry

    return await storage_to_form(
        script_type_registry.get("OkScript"),
        storage_config.get("PluginData", "Config"),
        "script",
    )


def _config_source_status(
    *,
    manifest: Any,
    provider: Any,
    source_files: tuple[str, ...],
    user_files: tuple[str, ...],
    copied_files: tuple[str, ...],
) -> tuple[str, list[dict[str, Any]]]:
    diagnostics: list[dict[str, Any]] = []
    source_exists = manifest.config_dir.is_dir()

    if not source_exists:
        diagnostics.append(
            {
                "code": "CONFIG_SOURCE_MISSING",
                "level": "warning",
                "message": "未找到项目默认 JSON 配置目录",
                "path": str(manifest.config_dir),
            }
        )
    elif not source_files:
        diagnostics.append(
            {
                "code": "CONFIG_SOURCE_EMPTY",
                "level": "warning",
                "message": "项目默认配置目录中没有 JSON 文件",
                "path": str(manifest.config_dir),
            }
        )

    if copied_files:
        diagnostics.append(
            {
                "code": "CONFIG_DEFAULTS_COPIED",
                "level": "info",
                "message": f"已补齐 {len(copied_files)} 个用户配置文件",
            }
        )

    if provider is None:
        diagnostics.append(
            {
                "code": "PROVIDER_UNREGISTERED",
                "level": "warning",
                "message": "当前项目没有已验证的 provider，仅开放通用配置诊断",
            }
        )

    if user_files:
        return "ready", diagnostics

    if provider is not None or manifest.tasks:
        diagnostics.append(
            {
                "code": "CONFIG_SCHEMA_ONLY",
                "level": "warning",
                "message": "已识别项目配置结构，但尚无可编辑的用户 JSON 配置",
            }
        )
        return "schema_only", diagnostics

    if not source_exists:
        return "source_missing", diagnostics

    diagnostics.append(
        {
            "code": "CONFIG_UNSUPPORTED",
            "level": "error",
            "message": "当前项目没有可读取的 JSON 配置或已登记 schema",
        }
    )
    return "unsupported", diagnostics


def _config_busy_response() -> dict[str, Any]:
    return {
        "code": 409,
        "status": "busy",
        "message": "当前用户配置正在被编辑或用于任务运行，请稍后重试",
        "data": [],
        "diagnostics": [
            {
                "code": "CONFIG_BUSY",
                "level": "warning",
                "message": "同一用户配置不能同时编辑和运行",
            }
        ],
    }


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
                editor_kind="plugin:ok_script_adapter",
                script_class_name="OkScriptPluginConfig",
                user_class_name="OkScriptPluginUserConfig",
                metadata={
                    "framework": "ok-script",
                    "source": "ok_script_adapter",
                    "normalize_script_form": normalize_ok_script_form,
                    "client": {
                        "config_editor": {
                            "kind": "json-files",
                            "endpoint_prefix": "/plugin/ok-script/configs",
                        }
                    },
                },
            )
        ]

    async def on_start(self) -> None:
        await super().on_start()
        self.ctx.server.http("/ok-script/inspect", self._inspect_project, methods=("POST",))
        self.ctx.server.http(
            "/ok-script/game-path/resolve",
            self._resolve_game_path,
            methods=("POST",),
        )
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
            project_label = (
                provider.display_name
                if provider is not None
                else manifest.display_name or manifest.resource_name
            )
            manifest_data = manifest.to_dict()
            manifest_data["displayName"] = project_label
            manifest_data["formPatch"] = {
                "Info": {
                    "Name": project_label,
                    "ResourceName": manifest.resource_name,
                    "ProjectLabel": project_label,
                    "RootPath": manifest.root_path.as_posix(),
                },
                "script_name": project_label,
            }
            return {
                "code": 200,
                "status": "success",
                "message": "项目解析成功",
                "data": manifest_data,
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

    async def _resolve_game_path(self, request: PluginHttpRequest) -> dict[str, Any]:
        payload = request.json if isinstance(request.json, dict) else request.query
        root_path = Path(str(payload.get("root_path") or payload.get("rootPath") or ""))
        selected_path = str(
            payload.get("selected_path") or payload.get("selectedPath") or ""
        ).strip()
        resource_name = payload.get("resource_name") or payload.get("resourceName") or ""
        if not selected_path:
            return {
                "code": 400,
                "status": "error",
                "message": "请选择游戏目录后再检测",
            }

        provider = detect_ok_script_provider(root_path, resource_name)
        if provider is None:
            return {
                "code": 400,
                "status": "error",
                "message": "请先选择并识别 ok-script 项目目录",
            }

        resolved_path = await asyncio.to_thread(
            resolve_game_executable_path,
            provider,
            selected_path,
        )
        if resolved_path is None:
            return {
                "code": 400,
                "status": "error",
                "message": (
                    f"所选位置未找到 {provider.display_name} 游戏主程序 "
                    f"{provider.game_process_name}"
                ),
            }

        normalized_path = resolved_path.as_posix()
        return {
            "code": 200,
            "status": "success",
            "message": f"已定位 {provider.game_process_name}",
            "data": {
                "path": normalized_path,
                "formPatch": {"Game": {"Path": normalized_path}},
            },
        }

    async def _list_configs(self, request: PluginHttpRequest) -> dict[str, Any]:
        payload = request.json if isinstance(request.json, dict) else request.query
        script_id = str(payload.get("script_id") or payload.get("scriptId") or "")
        user_id = str(payload.get("user_id") or payload.get("userId") or "")
        if not script_id or not user_id:
            return {"code": 400, "status": "error", "message": "缺少 script_id 或 user_id"}
        try:
            access = _resolve_config_access(script_id, user_id)
            form_config = await _script_form_config(access.storage_config)
            root_path = Path(str(form_config.get("Info", {}).get("RootPath") or ""))
            manifest = inspect_ok_project(root_path)
            provider = detect_ok_script_provider(root_path, manifest.resource_name)
            config_dir = access.config_dir
            config_lock = get_ok_script_config_lock(config_dir)
            if config_lock.locked():
                return _config_busy_response()
            async with config_lock:
                store = OkConfigStore(config_dir)
                source_store = OkConfigStore(manifest.config_dir)
                source_files = source_store.list()
                copied_files = store.copy_missing_from(manifest.config_dir)
                user_files = store.list()

                result: list[dict[str, Any]] = []
                option_labels: dict[str, str] = {}
                if provider is not None:
                    build_fields, get_config_info, load_labels = _load_provider_schema(provider)
                    option_labels = load_labels(root_path)
                    infos = (
                        get_config_info(config_dir)
                        if provider.config_info_uses_directory
                        else get_config_info()
                    )
                    available_files = set(user_files)
                    for info in infos:
                        filename = str(info["filename"])
                        current_data = (
                            store.read(filename) if filename in available_files else {}
                        )
                        fields = build_fields(filename, current_data, option_labels)
                        result.append(
                            {
                                **info,
                                "fieldCount": len(fields),
                                "fields": fields,
                                "currentData": current_data,
                            }
                        )
                else:
                    for filename in user_files:
                        current_data = store.read(filename)
                        fields = _build_generic_fields(current_data)
                        relative = Path(filename)
                        directory = relative.parent.as_posix()
                        result.append(
                            {
                                "filename": filename,
                                "displayName": relative.name,
                                "directory": "" if directory == "." else directory,
                                "group": "通用配置",
                                "taskIndex": None,
                                "fieldCount": len(fields),
                                "fields": fields,
                                "currentData": current_data,
                            }
                        )

                config_state, diagnostics = _config_source_status(
                    manifest=manifest,
                    provider=provider,
                    source_files=source_files,
                    user_files=user_files,
                    copied_files=copied_files,
                )

            provider_data = provider.build_client_metadata() if provider is not None else {
                "resourceName": manifest.resource_name,
                "displayName": manifest.display_name or manifest.resource_name,
                "taskOptions": [{"value": task.index, "label": task.label or task.selector} for task in manifest.tasks],
                "accountFields": None,
                "runtimeVerified": False,
                "runtimeBlockReason": "当前项目仅完成通用配置识别，尚未验证自动运行能力",
            }
            return {
                "code": 200,
                "status": "success",
                "message": {
                    "ready": "配置读取成功",
                    "schema_only": "已识别配置结构，但项目尚未生成 JSON 配置",
                    "source_missing": "未找到项目配置源",
                    "unsupported": "当前项目配置格式暂不受支持",
                }[config_state],
                "data": result,
                "configState": config_state,
                "diagnostics": diagnostics,
                "optionLabels": option_labels,
                "provider": provider_data,
                "manifest": manifest.to_dict(),
            }
        except (OkProjectInspectError, OkShellRuntimeError, ValueError, KeyError) as exc:
            logger.warning(f"拒绝读取 ok-script 用户配置: {exc}")
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
            access = _resolve_config_access(script_id, user_id)
            config_lock = get_ok_script_config_lock(access.config_dir)
            if config_lock.locked():
                return _config_busy_response()
            async with config_lock:
                store = OkConfigStore(access.config_dir)
                updates: list[tuple[str, dict[str, Any]]] = []
                for filename, data in configs.items():
                    if not isinstance(filename, str) or not isinstance(data, dict):
                        raise ValueError("配置文件名和配置内容必须有效")
                    updates.append((store.validate_name(filename), data))

                updated = []
                for filename, data in updates:
                    store.write(filename, data)
                    updated.append(filename)
            return {"code": 200, "status": "success", "data": updated}
        except (ValueError, RuntimeError) as exc:
            logger.warning(f"拒绝更新 ok-script 用户配置: {exc}")
            return {"code": 400, "status": "error", "message": str(exc)}
        except Exception as exc:
            return {"code": 500, "status": "error", "message": f"{type(exc).__name__}: {exc}"}
