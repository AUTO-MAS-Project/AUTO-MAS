#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

import asyncio
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body
from pydantic import BaseModel, Field

from app.core.plugins import PluginConfigStore, PluginManager
from app.core.plugins.realtime import publish_plugin_snapshot
from app.api.ws_command import ws_command
from app.models.schema import OutBase
from app.utils import get_logger


logger = get_logger("插件API")


if os.getenv("AUTO_MAS_DEV") == "1":
    from scripts.dev_stub_generator import (
        generate_plugin_context_stubs,
        is_dev_stub_generation_enabled,
    )
else:
    def is_dev_stub_generation_enabled() -> bool:
        """判断是否允许生成开发期类型提示。

        Returns:
            bool: 在非开发模式下恒为 False。
        """
        return False


    def generate_plugin_context_stubs() -> Dict[str, Any]:
        """非开发模式下的兜底实现。

        Returns:
            Dict[str, Any]: 不返回有效结果，调用时将抛出异常。

        Raises:
            RuntimeError: 当 AUTO_MAS_DEV 不为 "1" 时禁止生成类型提示。
        """
        raise RuntimeError("当前非开发模式，未加载 dev_stub_generator")


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


class PluginServiceModel(BaseModel):
    provides: List[str] = Field(default_factory=list, description="提供的服务")
    needs: List[str] = Field(default_factory=list, description="必须服务")
    wants: List[str] = Field(default_factory=list, description="可选服务")


class PluginsGetOut(OutBase):
    version: int = Field(default=1, description="配置版本")
    discovered_plugins: List[str] = Field(default_factory=list, description="已发现插件")
    schemas: Dict[str, Dict[str, Any]] = Field(default_factory=dict, description="插件Schema映射")
    schema_errors: Dict[str, str] = Field(default_factory=dict, description="插件Schema加载错误")
    plugin_services: Dict[str, PluginServiceModel] = Field(
        default_factory=dict,
        description="插件服务声明",
    )
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


class PluginPackageIn(BaseModel):
    package: str = Field(..., description="PyPI 包名")


async def _discover_plugins(plugins_dir: Path) -> Dict[str, Any]:
    """发现插件（先自动安装本地 editable，再统一按 Entry Point 发现）。"""
    PluginManager.plugins_dir = plugins_dir
    PluginManager.loader.plugins_dir = plugins_dir
    return await PluginManager.discover_plugins()


def _schedule_update_reload(instance_id: str) -> None:
    async def _runner() -> None:
        try:
            await PluginManager.reload_instance(instance_id)
        except Exception as exc:
            logger.error(
                f"插件实例后台重载失败: instance_id={instance_id}, error={type(exc).__name__}: {exc}",
                exc_info=True,
            )
            try:
                await publish_plugin_snapshot(
                    reason="api.plugins.update.reload_failed",
                    message=f"插件实例后台重载失败: {instance_id}",
                )
            except Exception as snapshot_exc:
                logger.warning(
                    f"插件快照后台发布失败: instance_id={instance_id}, "
                    f"error={type(snapshot_exc).__name__}: {snapshot_exc}"
                )

    asyncio.create_task(_runner())


def _schedule_enabled_runtime_update(instance_id: str, enabled: bool) -> None:
    async def _runner() -> None:
        try:
            await PluginManager.apply_instance_enabled(instance_id, enabled)
        except Exception as exc:
            logger.error(
                f"插件实例后台启用状态切换失败: instance_id={instance_id}, error={type(exc).__name__}: {exc}",
                exc_info=True,
            )
            try:
                await publish_plugin_snapshot(
                    reason="api.plugins.update.enabled_failed",
                    message=f"插件实例启用状态切换失败: {instance_id}",
                )
            except Exception as snapshot_exc:
                logger.warning(
                    f"插件快照后台发布失败: instance_id={instance_id}, "
                    f"error={type(snapshot_exc).__name__}: {snapshot_exc}"
                )

    asyncio.create_task(_runner())


def _schedule_update_snapshot(instance_id: str, reason: str = "api.plugins.update") -> None:
    async def _runner() -> None:
        try:
            await publish_plugin_snapshot(
                reason=reason,
                message=f"已更新插件实例: {instance_id}",
            )
        except Exception as snapshot_exc:
            logger.warning(
                f"插件快照后台发布失败: instance_id={instance_id}, "
                f"error={type(snapshot_exc).__name__}: {snapshot_exc}"
            )

    asyncio.create_task(_runner())


def _need_discover_for_update(data: PluginUpdateIn) -> bool:
    return data.plugin is not None or data.config is not None


def _is_name_only_update(data: PluginUpdateIn) -> bool:
    return (
        data.name is not None
        and data.plugin is None
        and data.config is None
        and data.enabled is None
    )


def _is_enabled_only_update(data: PluginUpdateIn) -> bool:
    return (
        data.enabled is not None
        and data.plugin is None
        and data.config is None
        and data.name is None
    )


def _resolve_effective_config(
    *,
    data: PluginUpdateIn,
    target: Dict[str, Any],
    discovered: Dict[str, Any],
    need_discover: bool,
) -> tuple[str, Dict[str, Any]]:
    next_plugin = data.plugin if data.plugin is not None else target.get("plugin")
    if not isinstance(next_plugin, str) or not next_plugin:
        raise ValueError(f"插件实例缺少有效 plugin 字段: {data.instanceId}")

    # 仅更新启用状态/名称时，沿用现有配置，避免无关 schema 校验影响开关流程。
    if data.plugin is None and data.config is None:
        current_config = target.get("config", {})
        if not isinstance(current_config, dict):
            raise ValueError(f"插件实例配置无效: {data.instanceId}")
        return next_plugin, current_config

    next_config = data.config if data.config is not None else target.get("config", {})

    plugin_path = None
    if need_discover:
        if next_plugin not in discovered:
            raise ValueError(f"未发现插件: {next_plugin}")
        plugin_path = getattr(discovered[next_plugin], "path", None)

    effective_config = config_store.load_effective_config(
        next_plugin,
        plugin_path,
        next_config,
    )
    return next_plugin, effective_config



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


def _build_plugin_services(discovered: Dict[str, Any]) -> Dict[str, PluginServiceModel]:
    services: Dict[str, PluginServiceModel] = {}
    loader = PluginManager.loader

    for plugin_name, plugin_source in discovered.items():
        try:
            _, plugin_class = loader._resolve_plugin_module_and_class(plugin_name, plugin_source)
            provides, needs, wants = loader._meta(plugin_class)
            services[plugin_name] = PluginServiceModel(
                provides=sorted(provides),
                needs=sorted(needs),
                wants=sorted(wants),
            )
        except Exception:
            services[plugin_name] = PluginServiceModel()

    return services


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


@ws_command("plugins.get")
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
        discovered = await _discover_plugins(plugins_dir)
        root = await config_store.get_root(
            plugins_dir,
            discovered,
            auto_create_missing=False,
        )
        schemas, schema_errors = _build_schemas(discovered)
        plugin_services = _build_plugin_services(discovered)
        return PluginsGetOut(
            version=int(root.get("version", 1)),
            discovered_plugins=list(discovered.keys()),
            schemas=schemas,
            schema_errors=schema_errors,
            plugin_services=plugin_services,
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
            plugin_services={},
            instances=[],
            runtime_states={},
        )


@ws_command("plugins.reload")
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
        await publish_plugin_snapshot(
            reason="api.plugins.reload",
            message="插件系统已重载",
        )
        return OutBase(message="插件系统重载成功")
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {str(e)}")


@ws_command("plugins.reload_instance")
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
        await publish_plugin_snapshot(
            reason="api.plugins.reload_instance",
            message=f"插件实例已重载: {data.instanceId}",
        )
        return OutBase(message=f"插件实例重载成功: {data.instanceId}")
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {str(e)}")


@ws_command("plugins.reload_plugin")
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
        await publish_plugin_snapshot(
            reason="api.plugins.reload_plugin",
            message=f"插件已重载: {data.plugin}",
        )
        return OutBase(message=f"插件重载成功: {data.plugin}")
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {str(e)}")


@ws_command("plugins.install_package")
@router.post(
    "/install_package",
    tags=["Action"],
    summary="下载安装插件包",
    response_model=OutBase,
    status_code=200,
)
async def install_plugin_package(data: PluginPackageIn = Body(...)) -> OutBase:
    """下载安装指定插件包。

    Args:
        data (PluginPackageIn): 包名参数。

    Returns:
        OutBase: 统一响应对象。

    Raises:
        无。接口内部会捕获异常并转换为统一错误响应。
    """
    try:
        await PluginManager.install_plugin_package(data.package)
        await publish_plugin_snapshot(
            reason="api.plugins.install_package",
            message=f"插件包已安装: {data.package}",
        )
        return OutBase(message=f"插件包下载安装成功: {data.package}")
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {str(e)}")


@ws_command("plugins.uninstall_package")
@router.post(
    "/uninstall_package",
    tags=["Action"],
    summary="卸载插件包",
    response_model=OutBase,
    status_code=200,
)
async def uninstall_plugin_package(data: PluginPackageIn = Body(...)) -> OutBase:
    """卸载指定插件包。

    Args:
        data (PluginPackageIn): 包名参数。

    Returns:
        OutBase: 统一响应对象。

    Raises:
        无。接口内部会捕获异常并转换为统一错误响应。
    """
    try:
        await PluginManager.uninstall_plugin_package(data.package)
        await publish_plugin_snapshot(
            reason="api.plugins.uninstall_package",
            message=f"插件包已卸载: {data.package}",
        )
        return OutBase(message=f"插件包卸载成功: {data.package}")
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {str(e)}")


@ws_command("plugins.dev.rebuild_ctx_stub")
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


@ws_command("plugins.add")
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
        discovered = await _discover_plugins(plugins_dir)

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

        await publish_plugin_snapshot(
            reason="api.plugins.add",
            message=f"已新增插件实例: {instance['id']}",
        )

        return PluginAddOut(instance=PluginInstanceModel(**instance))
    except Exception as e:
        return PluginAddOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            instance=None,
        )


@ws_command("plugins.update")
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
        need_discover = _need_discover_for_update(data)
        discovered: Dict[str, Any] = {}
        if need_discover:
            discovered = await _discover_plugins(plugins_dir)
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

        was_enabled = bool(target.get("enabled", False))
        next_plugin, effective_config = _resolve_effective_config(
            data=data,
            target=target,
            discovered=discovered,
            need_discover=need_discover,
        )

        target["plugin"] = next_plugin
        target["config"] = effective_config
        if data.name is not None:
            target["name"] = data.name
        if data.enabled is not None:
            target["enabled"] = data.enabled

        await config_store.save_root(plugins_dir, root)

        if PluginManager.started:
            if _is_name_only_update(data):
                _schedule_update_snapshot(data.instanceId, reason="api.plugins.update.name")
            elif _is_enabled_only_update(data) and was_enabled != bool(data.enabled):
                _schedule_enabled_runtime_update(data.instanceId, bool(data.enabled))
            else:
                _schedule_update_reload(data.instanceId)
        else:
            asyncio.create_task(
                publish_plugin_snapshot(
                    reason="api.plugins.update",
                    message=f"已更新插件实例: {data.instanceId}",
                )
            )

        return OutBase()
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {str(e)}")


@ws_command("plugins.delete")
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
        discovered = await _discover_plugins(plugins_dir)
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
        await publish_plugin_snapshot(
            reason="api.plugins.delete",
            message=f"已删除插件实例: {data.instanceId}",
        )
        return OutBase()
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {str(e)}")
