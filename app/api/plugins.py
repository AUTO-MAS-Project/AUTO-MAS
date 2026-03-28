#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body
from pydantic import BaseModel, Field

from app.core.plugins import PluginConfigStore, PluginManager
from app.core.plugins.dev_stub_generator import (
    generate_plugin_context_stubs,
    is_dev_stub_generation_enabled,
)
from app.models.schema import OutBase


router = APIRouter(prefix="/api/plugins", tags=["插件实例"])
config_store = PluginConfigStore()


class PluginInstanceModel(BaseModel):
    id: str = Field(..., description="实例ID")
    plugin: str = Field(..., description="插件名")
    enabled: bool = Field(default=True, description="是否启用")
    name: str = Field(..., description="实例名称")
    config: Dict[str, Any] = Field(default_factory=dict, description="插件配置")


class PluginRuntimeStateModel(BaseModel):
    instance_id: str = Field(..., description="实例ID")
    plugin: str = Field(..., description="插件名")
    status: str = Field(default="configured", description="运行状态")
    generation: int = Field(default=0, description="实例代际（每次重载成功后递增）")
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
    version: int = Field(default=1, description="配置版本")
    discovered_plugins: List[str] = Field(default_factory=list, description="已发现插件")
    schemas: Dict[str, Dict[str, Any]] = Field(default_factory=dict, description="插件Schema映射")
    schema_errors: Dict[str, str] = Field(default_factory=dict, description="插件Schema加载错误")
    instances: List[PluginInstanceModel] = Field(default_factory=list, description="插件实例列表")
    runtime_states: Dict[str, PluginRuntimeStateModel] = Field(
        default_factory=dict,
        description="插件实例运行态",
    )


class PluginAddIn(BaseModel):
    plugin: str = Field(..., description="插件名")
    name: Optional[str] = Field(default=None, description="实例名称")
    enabled: bool = Field(default=True, description="是否启用")
    config: Dict[str, Any] = Field(default_factory=dict, description="插件配置")


class PluginAddOut(OutBase):
    instance: Optional[PluginInstanceModel] = Field(default=None, description="新增实例")


class PluginUpdateIn(BaseModel):
    instanceId: str = Field(..., description="实例ID")
    plugin: Optional[str] = Field(default=None, description="插件名")
    name: Optional[str] = Field(default=None, description="实例名称")
    enabled: Optional[bool] = Field(default=None, description="是否启用")
    config: Optional[Dict[str, Any]] = Field(default=None, description="插件配置")


class PluginDeleteIn(BaseModel):
    instanceId: str = Field(..., description="实例ID")


class PluginReloadInstanceIn(BaseModel):
    instanceId: str = Field(..., description="实例ID")


class PluginReloadPluginIn(BaseModel):
    plugin: str = Field(..., description="插件名")


class PluginDevRebuildCtxStubIn(BaseModel):
    force: bool = Field(default=False, description="是否在非开发模式下强制生成")


class PluginDevRebuildCtxStubOut(OutBase):
    output_dir: Optional[str] = Field(default=None, description="生成目录")
    changed_files: List[str] = Field(default_factory=list, description="已更新文件")
    unchanged_files: List[str] = Field(default_factory=list, description="未变更文件")


def _discover_plugins(plugins_dir: Path) -> Dict[str, Any]:
    """发现插件（兼容本地目录与 PyPI Entry Point）。"""
    loader = PluginManager.loader
    loader.plugins_dir = plugins_dir
    return loader.discover()


def _build_instances(root: Dict[str, Any]) -> List[PluginInstanceModel]:
    instances: List[PluginInstanceModel] = []
    for item in root.get("instances", []):
        if not isinstance(item, dict):
            continue
        instances.append(PluginInstanceModel(**item))
    return instances


def _build_schemas(discovered: Dict[str, Any]) -> tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
    schemas: Dict[str, Dict[str, Any]] = {}
    errors: Dict[str, str] = {}
    for plugin_name, plugin_source in discovered.items():
        plugin_path = getattr(plugin_source, "path", None)
        try:
            schemas[plugin_name] = config_store.load_schema(plugin_name, plugin_path)
        except Exception as e:
            schemas[plugin_name] = {}
            errors[plugin_name] = f"{type(e).__name__}: {e}"
    return schemas, errors


def _build_runtime_states(root: Dict[str, Any]) -> Dict[str, PluginRuntimeStateModel]:
    """构建插件实例运行态快照。

    优先返回运行中记录（来自 PluginLoader），若实例尚未加载则返回 configured 状态。
    """
    result: Dict[str, PluginRuntimeStateModel] = {}

    records = getattr(PluginManager.loader, "records", {})
    for instance_id, record in records.items():
        result[str(instance_id)] = PluginRuntimeStateModel(
            instance_id=str(record.instance_id),
            plugin=str(record.plugin_name),
            status=str(record.status),
            generation=int(getattr(record, "generation", 0) or 0),
            lifecycle_phase=str(getattr(record, "lifecycle_phase", record.status) or record.status),
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

    for item in root.get("instances", []):
        if not isinstance(item, dict):
            continue
        instance_id = str(item.get("id") or "")
        if not instance_id or instance_id in result:
            continue
        plugin_name = str(item.get("plugin") or "")
        result[instance_id] = PluginRuntimeStateModel(
            instance_id=instance_id,
            plugin=plugin_name,
            status="configured",
            generation=0,
            lifecycle_phase="configured",
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
        plugins_dir = Path.cwd() / "plugins"
        discovered = _discover_plugins(plugins_dir)
        root = await config_store.get_root(
            plugins_dir,
            discovered,
            auto_create_missing=False,
        )
        schemas, schema_errors = _build_schemas(discovered)
        return PluginsGetOut(
            version=int(root.get("version", 1)),
            discovered_plugins=list(discovered.keys()),
            schemas=schemas,
            schema_errors=schema_errors,
            instances=_build_instances(root),
            runtime_states=_build_runtime_states(root),
        )
    except Exception as e:
        return PluginsGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            version=1,
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
    "/dev/rebuild_ctx_stub",
    tags=["Action"],
    summary="重建插件 ctx 类型提示文件",
    response_model=PluginDevRebuildCtxStubOut,
    status_code=200,
)
async def rebuild_plugin_ctx_stub(
    data: PluginDevRebuildCtxStubIn = Body(...),
) -> PluginDevRebuildCtxStubOut:
    """手动触发插件上下文 .pyi 重建。

    该接口用于插件开发阶段快速刷新类型提示，便于 IDE 立即获得最新签名。

    Args:
        data (PluginDevRebuildCtxStubIn): 重建参数。

    Returns:
        PluginDevRebuildCtxStubOut: 重建结果摘要。

    Raises:
        无。接口内部会捕获异常并转换为统一错误响应。
    """
    try:
        if not data.force and not is_dev_stub_generation_enabled():
            return PluginDevRebuildCtxStubOut(
                code=403,
                status="error",
                message="当前非开发模式，请设置 AUTO_MAS_DEV=1 或传 force=true",
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
    response_model=PluginAddOut,
    status_code=200,
)
async def add_plugin_instance(data: PluginAddIn = Body(...)) -> PluginAddOut:
    try:
        plugins_dir = Path.cwd() / "plugins"
        discovered = _discover_plugins(plugins_dir)

        if data.plugin not in discovered:
            raise ValueError(f"未发现插件: {data.plugin}")

        # 先校验配置是否合法（包含默认值注入）
        plugin_path = getattr(discovered[data.plugin], "path", None)
        effective_config = config_store.load_effective_config(
            data.plugin,
            plugin_path,
            data.config,
        )

        root = await config_store.get_root(
            plugins_dir,
            discovered,
            auto_create_missing=False,
        )
        instance = {
            "id": config_store.generate_instance_id(data.plugin),
            "plugin": data.plugin,
            "enabled": data.enabled,
            "name": data.name or f"{data.plugin} 实例",
            "config": effective_config,
        }
        root.setdefault("instances", []).append(instance)
        await config_store.save_root(plugins_dir, root)

        if PluginManager.started and data.enabled:
            await PluginManager.reload_instance(instance["id"])

        return PluginAddOut(instance=PluginInstanceModel(**instance))
    except Exception as e:
        return PluginAddOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            instance=None,
        )


@router.post(
    "/update",
    tags=["Update"],
    summary="更新插件实例",
    response_model=OutBase,
    status_code=200,
)
async def update_plugin_instance(data: PluginUpdateIn = Body(...)) -> OutBase:
    try:
        plugins_dir = Path.cwd() / "plugins"
        discovered = _discover_plugins(plugins_dir)
        root = await config_store.get_root(
            plugins_dir,
            discovered,
            auto_create_missing=False,
        )

        instances = root.get("instances", [])
        target = None
        for item in instances:
            if isinstance(item, dict) and item.get("id") == data.instanceId:
                target = item
                break

        if target is None:
            raise ValueError(f"未找到插件实例: {data.instanceId}")

        next_plugin = data.plugin if data.plugin is not None else target.get("plugin")
        if not isinstance(next_plugin, str) or next_plugin not in discovered:
            raise ValueError(f"未发现插件: {next_plugin}")

        next_config = data.config if data.config is not None else target.get("config", {})
        plugin_path = getattr(discovered[next_plugin], "path", None)
        effective_config = config_store.load_effective_config(
            next_plugin,
            plugin_path,
            next_config,
        )

        target["plugin"] = next_plugin
        target["config"] = effective_config
        if data.name is not None:
            target["name"] = data.name
        if data.enabled is not None:
            target["enabled"] = data.enabled

        await config_store.save_root(plugins_dir, root)

        if PluginManager.started:
            await PluginManager.reload_instance(data.instanceId)

        return OutBase()
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {str(e)}")


@router.post(
    "/delete",
    tags=["Delete"],
    summary="删除插件实例",
    response_model=OutBase,
    status_code=200,
)
async def delete_plugin_instance(data: PluginDeleteIn = Body(...)) -> OutBase:
    try:
        plugins_dir = Path.cwd() / "plugins"
        discovered = _discover_plugins(plugins_dir)
        root = await config_store.get_root(
            plugins_dir,
            discovered,
            auto_create_missing=False,
        )

        old_instances = root.get("instances", [])
        new_instances = [
            item
            for item in old_instances
            if not (isinstance(item, dict) and item.get("id") == data.instanceId)
        ]

        if len(new_instances) == len(old_instances):
            raise ValueError(f"未找到插件实例: {data.instanceId}")

        if PluginManager.started:
            await PluginManager.loader.unload_instance(data.instanceId)

        root["instances"] = new_instances
        await config_store.save_root(plugins_dir, root)
        return OutBase()
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {str(e)}")
