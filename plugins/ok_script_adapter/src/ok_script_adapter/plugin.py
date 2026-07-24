from __future__ import annotations

import asyncio
import importlib
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core import Config as app_config
from app.core.script_config_codec import storage_to_form
from app.models.plugin_script_config import PluginScriptConfig
from app.plugins import (
    PluginHttpRequest,
    PluginHttpResponse,
    ScriptAdapterDefinition,
    ScriptAdapterPlugin,
)
from app.utils import get_logger

from .adapter import OkScriptAdapterHooks
from .common.config_schema import (
    FIELD_SCHEMA_VERSION,
    ConfigSnapshot,
    FieldSchema,
    build_config_draft,
    materialize_field_schemas,
    render_legacy_fields,
    schema_catalog_fingerprint,
)
from .common.provider import ok_script_mas_config_dir, resolve_game_executable_path
from .common.runtime_lock import get_ok_script_config_lock
from .providers import detect_ok_script_provider, get_ok_script_provider
from .shell.config_parser import ProjectConfigDescription, ProjectConfigParser
from .shell.descriptor import OkProjectDescriptor, OkProjectInspectError
from .shell.manifest import inspect_ok_project
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


@dataclass(frozen=True, slots=True)
class _ConfigSchemaContext:
    """一个项目配置端点共用的 schema 解析上下文。"""

    description: ProjectConfigDescription
    provider_builder: Any | None
    config_info_loader: Any | None
    option_labels: dict[str, str]


@dataclass(frozen=True, slots=True)
class _ConfigProject:
    """已校验脚本存储对应的项目 descriptor 与配置 schema。"""

    root_path: Path
    descriptor: OkProjectDescriptor
    provider: Any
    schema_context: _ConfigSchemaContext


def normalize_ok_script_form(data: dict[str, Any]) -> dict[str, Any]:
    """根据项目 Manifest 回填可展示的 ok-script 元数据。"""

    info = data.get("Info")
    if not isinstance(info, dict):
        return data

    root_path = str(info.get("RootPath") or "").strip()
    descriptor = None
    if root_path:
        try:
            descriptor = inspect_ok_project(Path(root_path))
        except (OSError, OkProjectInspectError):
            pass

    if descriptor is not None:
        provider = get_ok_script_provider(descriptor.resource_name)
        resource_name = descriptor.resource_name
        project_label = (
            provider.display_name
            if provider is not None
            else descriptor.display_name or descriptor.resource_name
        )
        info["RootPath"] = descriptor.root_path.as_posix()
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


def _load_provider_schema(provider: Any):
    module = importlib.import_module(provider.config_schema_module)
    return (
        getattr(module, "build_field_schemas_for_config"),
        getattr(module, provider.config_info_loader),
        getattr(module, f"load_{provider.resource_name.replace('-', '')}_option_labels"),
    )


def _descriptor_with_provider(
    descriptor: OkProjectDescriptor,
    provider: Any,
) -> OkProjectDescriptor:
    if provider is None:
        return descriptor
    return descriptor.with_runtime_verification(
        verified=provider.runtime_verified,
        reason=provider.runtime_block_reason,
    )


def _build_config_schema_context(
    descriptor: OkProjectDescriptor,
    provider: Any,
    root_path: Path,
) -> _ConfigSchemaContext:
    description = ProjectConfigParser(descriptor).parse()
    if provider is None:
        return _ConfigSchemaContext(
            description=description,
            provider_builder=None,
            config_info_loader=None,
            option_labels={},
        )

    provider_builder, config_info_loader, load_labels = _load_provider_schema(provider)
    return _ConfigSchemaContext(
        description=description,
        provider_builder=provider_builder,
        config_info_loader=config_info_loader,
        option_labels=load_labels(root_path),
    )


async def _load_config_project(storage_config: PluginScriptConfig) -> _ConfigProject:
    form_config = await _script_form_config(storage_config)
    info = form_config.get("Info")
    root_value = str(info.get("RootPath") or "").strip() if isinstance(info, dict) else ""
    if not root_value:
        raise ValueError("请先设置 ok-script 项目路径")

    root_path = Path(root_value)
    descriptor = inspect_ok_project(root_path)
    provider = get_ok_script_provider(descriptor.resource_name)
    descriptor = _descriptor_with_provider(descriptor, provider)
    return _ConfigProject(
        root_path=root_path,
        descriptor=descriptor,
        provider=provider,
        schema_context=_build_config_schema_context(
            descriptor,
            provider,
            root_path,
        ),
    )


def _build_file_schemas(
    context: _ConfigSchemaContext,
    filename: str,
    current_data: dict[str, Any],
) -> tuple[FieldSchema, ...]:
    resource = context.description.get(filename)
    upstream = resource.fields if resource is not None else ()
    if context.provider_builder is not None:
        return context.provider_builder(
            filename,
            current_data,
            context.option_labels,
            upstream=upstream,
        )
    return materialize_field_schemas(current_data, upstream=upstream)


def _merge_config_infos(
    provider_infos: list[dict[str, Any]],
    description: ProjectConfigDescription,
    fallback_files: tuple[str, ...],
) -> list[dict[str, Any]]:
    infos: list[dict[str, Any]] = []
    by_filename: dict[str, dict[str, Any]] = {}

    for raw_info in provider_infos:
        filename = str(raw_info.get("filename") or "").strip()
        if not filename or filename in by_filename:
            continue
        info = dict(raw_info)
        info["filename"] = filename
        infos.append(info)
        by_filename[filename] = info

    for resource in description.resources:
        existing = by_filename.get(resource.filename)
        if existing is not None:
            if resource.task_index is not None:
                existing["taskIndex"] = resource.task_index
            continue
        info = {
            "filename": resource.filename,
            "displayName": resource.display_name,
            "group": resource.group,
            "taskIndex": resource.task_index,
        }
        infos.append(info)
        by_filename[resource.filename] = info

    for filename in fallback_files:
        if filename in by_filename:
            continue
        relative = Path(filename)
        directory = relative.parent.as_posix()
        info = {
            "filename": filename,
            "displayName": relative.name,
            "directory": "" if directory == "." else directory,
            "group": "通用配置",
            "taskIndex": None,
        }
        infos.append(info)
        by_filename[filename] = info
    return infos


def _provider_client_metadata(
    descriptor: OkProjectDescriptor,
    provider: Any,
) -> dict[str, Any]:
    if provider is not None:
        metadata = provider.build_client_metadata()
        provider_options = {
            option.index: option.label for option in provider.task_options
        }
    else:
        metadata = {
            "resourceName": descriptor.resource_name,
            "displayName": descriptor.display_name or descriptor.resource_name,
            "accountFields": None,
            "runtimeVerified": descriptor.capabilities.runtime.verified,
            "runtimeBlockReason": descriptor.capabilities.runtime.reason,
            "gameProcessName": "",
        }
        provider_options = {}

    runtime = descriptor.capabilities.runtime
    metadata["runtimeVerified"] = runtime.verified
    metadata["runtimeBlockReason"] = runtime.reason

    task_options: list[dict[str, Any]] = []
    for task in descriptor.tasks:
        provider_label = provider_options.get(task.index, "")
        provider_selector = (
            provider_label.partition("（")[0].partition("(")[0].strip()
        )
        label = (
            provider_label
            if provider_selector == task.selector
            else task.label or task.selector
        )
        task_options.append({"value": task.index, "label": label})
    metadata["taskOptions"] = task_options
    return metadata


def _merge_diagnostics(
    descriptor: OkProjectDescriptor,
    diagnostics: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in (
        *(diagnostic.to_dict() for diagnostic in descriptor.diagnostics),
        *diagnostics,
    ):
        key = (str(item.get("code") or ""), str(item.get("path") or ""))
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


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
        self.ctx.server.http(
            "/ok-script/inspect",
            self._inspect_project,
            methods=("POST",),
        )
        self.ctx.server.http(
            "/ok-script/game-path/resolve",
            self._resolve_game_path,
            methods=("POST",),
        )
        self.ctx.server.http(
            "/ok-script/configs/list",
            self._list_configs,
            methods=("GET", "POST"),
        )
        self.ctx.server.http(
            "/ok-script/configs/batch-update",
            self._batch_update_configs,
            methods=("POST",),
        )

    async def _inspect_project(self, request: PluginHttpRequest) -> dict[str, Any]:
        payload = request.json if isinstance(request.json, dict) else request.query
        root_path = Path(str(payload.get("root_path") or payload.get("rootPath") or ""))
        try:
            descriptor = inspect_ok_project(root_path)
            provider = get_ok_script_provider(descriptor.resource_name)
            project_label = (
                provider.display_name
                if provider is not None
                else descriptor.display_name or descriptor.resource_name
            )
            descriptor = _descriptor_with_provider(descriptor, provider)
            descriptor_data = descriptor.to_dict()
            descriptor_data["displayName"] = project_label
            descriptor_data["identity"]["displayName"] = project_label
            descriptor_data["formPatch"] = {
                "Info": {
                    "Name": project_label,
                    "ResourceName": descriptor.resource_name,
                    "ProjectLabel": project_label,
                    "RootPath": descriptor.root_path.as_posix(),
                },
                "script_name": project_label,
            }
            return {
                "code": 200,
                "status": "success",
                "message": "项目解析成功",
                "data": descriptor_data,
                "provider": _provider_client_metadata(descriptor, provider),
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
            project = await _load_config_project(access.storage_config)
            descriptor = project.descriptor
            provider = project.provider
            schema_context = project.schema_context
            config_dir = access.config_dir
            config_lock = get_ok_script_config_lock(config_dir)
            if config_lock.locked():
                return _config_busy_response()
            async with config_lock:
                store = OkConfigStore(config_dir)
                source_store = OkConfigStore(descriptor.config_dir)
                source_files = source_store.list()
                copied_files = store.copy_missing_from(descriptor.config_dir)
                user_files = store.list()

                result: list[dict[str, Any]] = []
                schemas_by_file: dict[str, tuple[FieldSchema, ...]] = {}
                provider_infos: list[dict[str, Any]] = []
                if provider is not None:
                    get_config_info = schema_context.config_info_loader
                    provider_infos = (
                        get_config_info(config_dir)
                        if provider.config_info_uses_directory
                        else get_config_info()
                    )

                available_files = set(user_files)
                infos = _merge_config_infos(
                    provider_infos,
                    schema_context.description,
                    user_files if provider is None else (),
                )
                for info in infos:
                    filename = store.validate_name(str(info["filename"]))
                    current_data = (
                        store.read(filename) if filename in available_files else {}
                    )
                    schemas = _build_file_schemas(
                        schema_context,
                        filename,
                        current_data,
                    )
                    if not schemas and filename not in available_files:
                        continue
                    schemas_by_file[filename] = schemas
                    source_fingerprint = schema_catalog_fingerprint(
                        {filename: schemas},
                        source_fingerprint=schema_context.description.fingerprint,
                    )
                    snapshot = ConfigSnapshot(
                        values=current_data,
                        source_fingerprint=source_fingerprint,
                    )
                    result.append(
                        {
                            **info,
                            "filename": filename,
                            "fieldCount": len(schemas),
                            "fields": render_legacy_fields(schemas, current_data),
                            "currentData": current_data,
                            "fieldSchema": [schema.to_dict() for schema in schemas],
                            "snapshot": snapshot.to_dict(),
                        }
                    )

                config_state, diagnostics = _config_source_status(
                    manifest=descriptor,
                    provider=provider,
                    source_files=source_files,
                    user_files=user_files,
                    copied_files=copied_files,
                )

            provider_data = _provider_client_metadata(descriptor, provider)
            descriptor_data = descriptor.to_dict()
            schema_fingerprint = schema_catalog_fingerprint(
                schemas_by_file,
                source_fingerprint=schema_context.description.fingerprint,
            )
            diagnostics = [
                *(item.to_dict() for item in schema_context.description.diagnostics),
                *diagnostics,
            ]
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
                "schemaVersion": FIELD_SCHEMA_VERSION,
                "schemaFingerprint": schema_fingerprint,
                "configState": config_state,
                "diagnostics": _merge_diagnostics(descriptor, diagnostics),
                "optionLabels": schema_context.option_labels,
                "provider": provider_data,
                "descriptor": descriptor_data,
                "manifest": descriptor_data,
            }
        except (OkProjectInspectError, OkShellRuntimeError, ValueError, KeyError) as exc:
            logger.warning(f"拒绝读取 ok-script 用户配置: {exc}")
            return {"code": 400, "status": "error", "message": str(exc), "data": []}
        except Exception as exc:
            return {
                "code": 500,
                "status": "error",
                "message": f"{type(exc).__name__}: {exc}",
                "data": [],
            }

    async def _batch_update_configs(
        self,
        request: PluginHttpRequest,
    ) -> dict[str, Any] | PluginHttpResponse:
        payload = request.json if isinstance(request.json, dict) else {}
        script_id = str(payload.get("script_id") or payload.get("scriptId") or "")
        user_id = str(payload.get("user_id") or payload.get("userId") or "")
        configs = payload.get("configs")
        mode = str(payload.get("mode") or "commit").strip().casefold()
        if not script_id or not user_id or not isinstance(configs, dict):
            return {"code": 400, "status": "error", "message": "请求参数不完整"}
        if mode not in {"validate", "commit"}:
            return {"code": 400, "status": "error", "message": "mode 必须是 validate 或 commit"}
        try:
            access = _resolve_config_access(script_id, user_id)
            config_lock = get_ok_script_config_lock(access.config_dir)
            if config_lock.locked():
                return _config_busy_response()
            async with config_lock:
                store = OkConfigStore(access.config_dir)
                updates: list[tuple[str, dict[str, Any]]] = []
                filename_keys: set[str] = set()
                for filename, data in configs.items():
                    if not isinstance(filename, str) or not isinstance(data, dict):
                        raise ValueError("配置文件名和配置内容必须有效")
                    normalized = store.validate_name(filename)
                    filename_key = os.path.normcase(normalized)
                    if filename_key in filename_keys:
                        raise ValueError(f"配置文件重复: {normalized}")
                    filename_keys.add(filename_key)
                    updates.append((normalized, data))

                project = await _load_config_project(access.storage_config)
                available_files = set(store.list())
                drafts = []
                for filename, data in updates:
                    original = store.read(filename) if filename in available_files else {}
                    schemas = _build_file_schemas(
                        project.schema_context,
                        filename,
                        original,
                    )
                    if not schemas and not original:
                        schemas = _build_file_schemas(
                            project.schema_context,
                            filename,
                            data,
                        )
                    drafts.append(
                        build_config_draft(
                            filename,
                            original,
                            data,
                            schemas,
                        )
                    )

                errors = [
                    {"filename": draft.filename, **error.to_dict()}
                    for draft in drafts
                    for error in draft.errors
                ]
                if errors:
                    return PluginHttpResponse(
                        body={
                            "code": 422,
                            "status": "validation_error",
                            "message": "配置校验失败，未写入任何文件",
                            "mode": mode,
                            "data": [],
                            "drafts": [draft.to_dict() for draft in drafts],
                            "errors": errors,
                        },
                        status_code=422,
                    )

                if mode == "validate":
                    return {
                        "code": 200,
                        "status": "validated",
                        "message": "配置校验通过，尚未写入",
                        "mode": mode,
                        "data": [],
                        "drafts": [draft.to_dict() for draft in drafts],
                    }

                updated: list[str] = []
                for draft in drafts:
                    store.write(draft.filename, draft.merged, merge=False)
                    updated.append(draft.filename)
            return {
                "code": 200,
                "status": "success",
                "message": "配置保存成功",
                "mode": mode,
                "data": updated,
                "drafts": [draft.to_dict() for draft in drafts],
            }
        except (OkProjectInspectError, OkShellRuntimeError, ValueError, KeyError) as exc:
            logger.warning(f"拒绝更新 ok-script 用户配置: {exc}")
            return {"code": 400, "status": "error", "message": str(exc)}
        except Exception as exc:
            return {"code": 500, "status": "error", "message": f"{type(exc).__name__}: {exc}"}
