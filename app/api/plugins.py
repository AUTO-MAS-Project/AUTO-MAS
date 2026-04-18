#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

import os
from typing import Any, Optional

from fastapi import APIRouter, Body
from pydantic import BaseModel, Field

from app.contracts.common_contract import OutBase
from app.core.plugins import PluginConfigStore, PluginManager


DEV_STUB_ENABLED = os.getenv("AUTO_MAS_DEV") == "1"


def _dev_stub_generation_disabled() -> bool:
    return False


def _raise_dev_stub_generation_disabled() -> dict[str, Any]:
    raise RuntimeError("当前未启用插件上下文类型提示生成")


is_dev_stub_generation_enabled = _dev_stub_generation_disabled
generate_plugin_context_stubs = _raise_dev_stub_generation_disabled

if DEV_STUB_ENABLED:
    from scripts.dev_stub_generator import (
        generate_plugin_context_stubs,
        is_dev_stub_generation_enabled,
    )


router = APIRouter(prefix="/api/plugins", tags=["插件实例"])
config_store = PluginConfigStore()


class PluginInstanceModel(BaseModel):
    id: str = Field(..., description="实例ID")
    plugin: str = Field(..., description="插件名")
    enabled: bool = Field(default=True, description="是否启用")
    name: str = Field(..., description="实例名称")
    config: dict[str, Any] = Field(default_factory=dict, description="插件配置")


class PluginRuntimeStateModel(BaseModel):
    instance_id: str = Field(..., description="实例ID")
    plugin: str = Field(..., description="插件名")
    status: str = Field(default="configured", description="运行状态")
    generation: int = Field(default=0, description="实例代际")
    lifecycle_phase: str = Field(default="configured", description="生命周期阶段")
    lifecycle_updated_at: Optional[str] = Field(default=None, description="生命周期阶段更新时间")
    reload_count: int = Field(default=0, description="成功重载次数")
    last_reload_reason: Optional[str] = Field(default=None, description="最近重载原因")
    last_reload_at: Optional[str] = Field(default=None, description="最近重载时间")
    created_at: Optional[str] = Field(default=None, description="记录创建时间")
    discovered_at: Optional[str] = Field(default=None, description="发现时间")
    loaded_at: Optional[str] = Field(default=None, description="代码加载时间")
    activated_at: Optional[str] = Field(default=None, description="激活时间")
    disposed_at: Optional[str] = Field(default=None, description="销毁时间")
    unloaded_at: Optional[str] = Field(default=None, description="卸载时间")
    last_error: Optional[str] = Field(default=None, description="最近错误")
    last_error_at: Optional[str] = Field(default=None, description="最近错误时间")


class PluginsGetOut(OutBase):
    discovered_plugins: list[str] = Field(default_factory=list, description="已发现插件")
    schemas: dict[str, dict[str, Any]] = Field(default_factory=dict, description="插件Schema映射")
    schema_errors: dict[str, str] = Field(default_factory=dict, description="插件Schema加载错误")
    instances: list[PluginInstanceModel] = Field(default_factory=list, description="插件实例列表")
    runtime_states: dict[str, PluginRuntimeStateModel] = Field(
        default_factory=dict,
        description="插件实例运行态",
    )


class PluginAddIn(BaseModel):
    plugin: str = Field(..., description="插件名")
    name: Optional[str] = Field(default=None, description="实例名称")
    enabled: bool = Field(default=True, description="是否启用")
    config: dict[str, Any] = Field(default_factory=dict, description="插件配置")


class PluginMutationOut(OutBase):
    instance: Optional[PluginInstanceModel] = Field(default=None, description="当前实例")


class PluginUpdateIn(BaseModel):
    instanceId: str = Field(..., description="实例ID")
    plugin: Optional[str] = Field(default=None, description="插件名")
    name: Optional[str] = Field(default=None, description="实例名称")
    enabled: Optional[bool] = Field(default=None, description="是否启用")
    config: Optional[dict[str, Any]] = Field(default=None, description="插件配置")


class PluginDeleteIn(BaseModel):
    instanceId: str = Field(..., description="实例ID")


class PluginReloadInstanceIn(BaseModel):
    instanceId: str = Field(..., description="实例ID")


class PluginReloadPluginIn(BaseModel):
    plugin: str = Field(..., description="插件名")


class PluginDevRebuildCtxStubIn(BaseModel):
    force: bool = Field(default=False, description="是否强制重建")


class PluginDevRebuildCtxStubOut(OutBase):
    output_dir: Optional[str] = Field(default=None, description="生成目录")
    changed_files: list[str] = Field(default_factory=list, description="已更新文件")
    unchanged_files: list[str] = Field(default_factory=list, description="未变更文件")


class PluginPackageIn(BaseModel):
    package: str = Field(..., description="PyPI 包名")


async def _discover_plugins() -> dict[str, Any]:
    return await PluginManager.discover_plugins()


def _to_instance_model(instance: PluginConfigStore.PluginInstance) -> PluginInstanceModel:
    return PluginInstanceModel(
        id=instance.id,
        plugin=instance.plugin,
        enabled=instance.enabled,
        name=instance.name,
        config=instance.config,
    )


def _build_schemas(
    discovered: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    schemas: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    for plugin_name, plugin_source in discovered.items():
        plugin_path = getattr(plugin_source, "path", None)
        try:
            schemas[plugin_name] = config_store.load_schema(plugin_name, plugin_path)
        except Exception as e:
            schemas[plugin_name] = {}
            errors[plugin_name] = f"{type(e).__name__}: {e}"
    return schemas, errors


def _build_runtime_states(
    instances: list[PluginConfigStore.PluginInstance],
) -> dict[str, PluginRuntimeStateModel]:
    result: dict[str, PluginRuntimeStateModel] = {}
    records = getattr(PluginManager.loader, "records", {})

    for instance in instances:
        record = records.get(instance.id)
        if record is None:
            result[instance.id] = PluginRuntimeStateModel(
                instance_id=instance.id,
                plugin=instance.plugin,
                status="configured",
                generation=0,
                lifecycle_phase="configured",
            )
            continue

        result[instance.id] = PluginRuntimeStateModel(
            instance_id=str(record.instance_id),
            plugin=str(record.plugin_name),
            status=str(record.status),
            generation=int(getattr(record, "generation", 0) or 0),
            lifecycle_phase=str(
                getattr(record, "lifecycle_phase", record.status) or record.status
            ),
            lifecycle_updated_at=getattr(record, "lifecycle_updated_at", None),
            reload_count=int(getattr(record, "reload_count", 0) or 0),
            last_reload_reason=getattr(record, "last_reload_reason", None),
            last_reload_at=getattr(record, "last_reload_at", None),
            created_at=record.created_at,
            discovered_at=record.discovered_at,
            loaded_at=record.loaded_at,
            activated_at=record.activated_at,
            disposed_at=record.disposed_at,
            unloaded_at=record.unloaded_at,
            last_error=record.last_error,
            last_error_at=record.last_error_at,
        )

    return result


@router.post(
    "/get",
    tags=["Get"],
    summary="获取插件实例配置",
    response_model=PluginsGetOut,
    status_code=200,
)
async def get_plugins() -> PluginsGetOut:
    try:
        discovered = await _discover_plugins()
        instances = await config_store.load_instances()
        schemas, schema_errors = _build_schemas(discovered)
        return PluginsGetOut(
            discovered_plugins=list(discovered.keys()),
            schemas=schemas,
            schema_errors=schema_errors,
            instances=[_to_instance_model(instance) for instance in instances],
            runtime_states=_build_runtime_states(instances),
        )
    except Exception as e:
        return PluginsGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            discovered_plugins=[],
            schemas={},
            schema_errors={},
            instances=[],
            runtime_states={},
        )


@router.post(
    "/reload",
    tags=["Action"],
    summary="重载插件实例",
    response_model=OutBase,
    status_code=200,
)
async def reload_plugins() -> OutBase:
    try:
        await PluginManager.reload()
        return OutBase(message="插件系统重载成功")
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {str(e)}")


@router.post(
    "/reload_instance",
    tags=["Action"],
    summary="重载单个插件实例",
    response_model=OutBase,
    status_code=200,
)
async def reload_plugin_instance(data: PluginReloadInstanceIn = Body(...)) -> OutBase:
    try:
        await PluginManager.reload_instance(data.instanceId)
        return OutBase(message=f"插件实例重载成功: {data.instanceId}")
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {str(e)}")


@router.post(
    "/reload_plugin",
    tags=["Action"],
    summary="按插件名重载所有实例",
    response_model=OutBase,
    status_code=200,
)
async def reload_plugin_by_name(data: PluginReloadPluginIn = Body(...)) -> OutBase:
    try:
        await PluginManager.reload_plugin(data.plugin)
        return OutBase(message=f"插件重载成功: {data.plugin}")
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {str(e)}")


@router.post(
    "/install_package",
    tags=["Action"],
    summary="下载安装插件包",
    response_model=OutBase,
    status_code=200,
)
async def install_plugin_package(data: PluginPackageIn = Body(...)) -> OutBase:
    try:
        await PluginManager.install_plugin_package(data.package)
        return OutBase(message=f"插件包下载安装成功: {data.package}")
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {str(e)}")


@router.post(
    "/uninstall_package",
    tags=["Action"],
    summary="卸载插件包",
    response_model=OutBase,
    status_code=200,
)
async def uninstall_plugin_package(data: PluginPackageIn = Body(...)) -> OutBase:
    try:
        await PluginManager.uninstall_plugin_package(data.package)
        return OutBase(message=f"插件包卸载成功: {data.package}")
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {str(e)}")


@router.post(
    "/dev/rebuild_ctx_stub",
    tags=["Action"],
    summary="重建插件 ctx 类型提示文件",
    response_model=PluginDevRebuildCtxStubOut,
    status_code=200,
)
async def rebuild_plugin_ctx_stub(
    data: PluginDevRebuildCtxStubIn = Body(...),
) -> PluginDevRebuildCtxStubOut:
    try:
        if not DEV_STUB_ENABLED:
            return PluginDevRebuildCtxStubOut(
                code=403,
                status="error",
                message="当前非开发模式，禁止生成插件上下文类型提示",
                output_dir=None,
                changed_files=[],
                unchanged_files=[],
            )

        if not data.force and not is_dev_stub_generation_enabled():
            return PluginDevRebuildCtxStubOut(
                code=403,
                status="error",
                message="当前未启用插件上下文类型提示生成",
                output_dir=None,
                changed_files=[],
                unchanged_files=[],
            )

        result = generate_plugin_context_stubs()
        changed_files = result.get("changed_files", [])
        unchanged_files = result.get("unchanged_files", [])
        return PluginDevRebuildCtxStubOut(
            message=(
                "插件上下文类型提示重建完成: "
                f"changed={len(changed_files)}, unchanged={len(unchanged_files)}"
            ),
            output_dir=result.get("output_dir"),
            changed_files=changed_files,
            unchanged_files=unchanged_files,
        )
    except Exception as e:
        return PluginDevRebuildCtxStubOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            output_dir=None,
            changed_files=[],
            unchanged_files=[],
        )


@router.post(
    "/add",
    tags=["Add"],
    summary="新增插件实例",
    response_model=PluginMutationOut,
    status_code=200,
)
async def add_plugin_instance(data: PluginAddIn = Body(...)) -> PluginMutationOut:
    try:
        discovered = await _discover_plugins()
        instance = await config_store.create_instance(
            plugin_name=data.plugin,
            name=data.name,
            enabled=data.enabled,
            raw_config=data.config,
            discovered_plugins=discovered,
        )
        if PluginManager.started and instance.enabled:
            await PluginManager.reload_instance(instance.id)

        return PluginMutationOut(
            message=f"插件实例创建成功: {instance.id}",
            instance=_to_instance_model(instance),
        )
    except Exception as e:
        return PluginMutationOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            instance=None,
        )


@router.post(
    "/update",
    tags=["Update"],
    summary="更新插件实例",
    response_model=PluginMutationOut,
    status_code=200,
)
async def update_plugin_instance(data: PluginUpdateIn = Body(...)) -> PluginMutationOut:
    try:
        discovered = await _discover_plugins()
        previous, current = await config_store.update_instance(
            data.instanceId,
            plugin_name=data.plugin,
            name=data.name,
            enabled=data.enabled,
            raw_config=data.config,
            discovered_plugins=discovered,
        )

        if PluginManager.started:
            if previous.id != current.id:
                await PluginManager.loader.unload_instance(previous.id)

            if current.enabled:
                await PluginManager.reload_instance(current.id)
            else:
                await PluginManager.loader.unload_instance(current.id)

        return PluginMutationOut(
            message=f"插件实例更新成功: {current.id}",
            instance=_to_instance_model(current),
        )
    except Exception as e:
        return PluginMutationOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            instance=None,
        )


@router.post(
    "/delete",
    tags=["Delete"],
    summary="删除插件实例",
    response_model=OutBase,
    status_code=200,
)
async def delete_plugin_instance(data: PluginDeleteIn = Body(...)) -> OutBase:
    try:
        instance = await config_store.delete_instance(data.instanceId)
        if PluginManager.started:
            await PluginManager.loader.unload_instance(instance.id)

        return OutBase(message=f"插件实例删除成功: {instance.id}")
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {str(e)}")
