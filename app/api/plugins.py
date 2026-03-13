#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body
from pydantic import BaseModel, Field

from app.core.plugins import PluginConfigStore, PluginManager
from app.models.schema import OutBase


router = APIRouter(prefix="/api/plugins", tags=["插件实例"])
config_store = PluginConfigStore()


class PluginInstanceModel(BaseModel):
    id: str = Field(..., description="实例ID")
    plugin: str = Field(..., description="插件名")
    enabled: bool = Field(default=True, description="是否启用")
    name: str = Field(..., description="实例名称")
    config: Dict[str, Any] = Field(default_factory=dict, description="插件配置")


class PluginsGetOut(OutBase):
    version: int = Field(default=1, description="配置版本")
    discovered_plugins: List[str] = Field(default_factory=list, description="已发现插件")
    schemas: Dict[str, Dict[str, Any]] = Field(default_factory=dict, description="插件Schema映射")
    schema_errors: Dict[str, str] = Field(default_factory=dict, description="插件Schema加载错误")
    instances: List[PluginInstanceModel] = Field(default_factory=list, description="插件实例列表")


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


def _discover_plugins(plugins_dir: Path) -> Dict[str, Path]:
    discovered: Dict[str, Path] = {}
    if not plugins_dir.exists():
        return discovered

    for item in sorted(plugins_dir.iterdir()):
        if not item.is_dir():
            continue
        if (item / "plugin.py").exists():
            discovered[item.name] = item
    return discovered


def _build_instances(root: Dict[str, Any]) -> List[PluginInstanceModel]:
    instances: List[PluginInstanceModel] = []
    for item in root.get("instances", []):
        if not isinstance(item, dict):
            continue
        instances.append(PluginInstanceModel(**item))
    return instances


def _build_schemas(discovered: Dict[str, Path]) -> tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
    schemas: Dict[str, Dict[str, Any]] = {}
    errors: Dict[str, str] = {}
    for plugin_name, plugin_path in discovered.items():
        try:
            schemas[plugin_name] = config_store.load_schema(plugin_name, plugin_path)
        except Exception as e:
            schemas[plugin_name] = {}
            errors[plugin_name] = f"{type(e).__name__}: {e}"
    return schemas, errors


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
        root = config_store.get_root(
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
        effective_config = config_store.load_effective_config(
            data.plugin,
            discovered[data.plugin],
            data.config,
        )

        root = config_store.get_root(
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
        config_store.save_root(plugins_dir, root)

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
        root = config_store.get_root(
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
        effective_config = config_store.load_effective_config(
            next_plugin,
            discovered[next_plugin],
            next_config,
        )

        target["plugin"] = next_plugin
        target["config"] = effective_config
        if data.name is not None:
            target["name"] = data.name
        if data.enabled is not None:
            target["enabled"] = data.enabled

        config_store.save_root(plugins_dir, root)
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
        root = config_store.get_root(
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

        root["instances"] = new_instances
        config_store.save_root(plugins_dir, root)
        return OutBase()
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {str(e)}")
