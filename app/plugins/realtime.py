from __future__ import annotations

import asyncio
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict

from app.utils import get_logger
from app.plugins.frontend_extensions import build_page_snapshot

PLUGIN_SYSTEM_WS_ID = "PluginSystem"

logger = get_logger("PluginRealtime")

SENSITIVE_VALUE_REDACTED = "***"


def _redact_sensitive_schema(
    schema: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """移除 schema 内敏感字段携带的默认值和示例值。"""
    redacted = deepcopy(schema)
    for field_schema in redacted.values():
        if not isinstance(field_schema, dict):
            continue
        if field_schema.get("sensitive") is True:
            field_schema.pop("default", None)
            field_schema.pop("examples", None)
            field_schema.pop("options", None)
        properties = field_schema.get("properties")
        if isinstance(properties, dict):
            field_schema["properties"] = _redact_sensitive_schema(properties)
    return redacted


def _redact_sensitive_config(
    config: Any,
    schema: Dict[str, Dict[str, Any]] | None,
) -> Any:
    """根据 schema 标记脱敏配置中的敏感字段值。

    schema 标记的敏感字段会被替换为占位符；嵌套 ``properties`` 递归处理。
    schema 缺失或配置出现未声明字段时采用 fail-closed 策略，不向广播快照
    透传未经分类的数据。

    Args:
        config: 原始配置值。
        schema: 插件 schema 字段映射，可能为 None 或空字典。

    Returns:
        脱敏后的配置副本。
    """
    if not isinstance(config, dict):
        return deepcopy(config)
    if not schema:
        return {}

    redacted: Dict[str, Any] = {}
    for field_name, value in config.items():
        field_schema = schema.get(field_name)
        if not isinstance(field_schema, dict):
            redacted[field_name] = SENSITIVE_VALUE_REDACTED
            continue
        if field_schema.get("sensitive") is True:
            redacted[field_name] = SENSITIVE_VALUE_REDACTED
            continue
        properties = field_schema.get("properties")
        if isinstance(value, dict) and isinstance(properties, dict):
            redacted[field_name] = _redact_sensitive_config(value, properties)
            continue
        redacted[field_name] = deepcopy(value)
    return redacted


def _redact_instances_sensitive(
    instances: list[Any],
    schemas: Dict[str, Dict[str, Any]],
) -> list[Any]:
    """对实例列表中的 config 字段执行敏感字段脱敏。

    Args:
        instances: 原始实例列表。
        schemas: 插件名到 schema 的映射。

    Returns:
        脱敏后的实例列表深拷贝。
    """
    redacted: list[Any] = []
    for item in instances:
        if not isinstance(item, dict):
            redacted.append(deepcopy(item))
            continue
        copied = deepcopy(item)
        plugin_name = str(copied.get("plugin") or "")
        config = copied.get("config")
        schema = schemas.get(plugin_name)
        if config is not None:
            copied["config"] = _redact_sensitive_config(config, schema)
        redacted.append(copied)
    return redacted


def _serialize_record(record: Any) -> Dict[str, Any]:
    return {
        "instance_id": str(getattr(record, "instance_id", "") or ""),
        "plugin": str(getattr(record, "plugin_name", "") or ""),
        "status": str(getattr(record, "status", "configured") or "configured"),
        "generation": int(getattr(record, "generation", 0) or 0),
        "lifecycle_phase": str(
            getattr(record, "lifecycle_phase", getattr(record, "status", "configured"))
            or "configured"
        ),
        "lifecycle_updated_at": getattr(record, "lifecycle_updated_at", None),
        "reload_count": int(getattr(record, "reload_count", 0) or 0),
        "last_reload_reason": getattr(record, "last_reload_reason", None),
        "last_reload_at": getattr(record, "last_reload_at", None),
        "created_at": getattr(record, "created_at", None),
        "discovered_at": getattr(record, "discovered_at", None),
        "loaded_at": getattr(record, "loaded_at", None),
        "activated_at": getattr(record, "activated_at", None),
        "disposed_at": getattr(record, "disposed_at", None),
        "unloaded_at": getattr(record, "unloaded_at", None),
        "last_error": getattr(record, "last_error", None),
        "last_error_at": getattr(record, "last_error_at", None),
    }


async def send_plugin_system_message(message_type: str, data: Dict[str, Any]) -> None:
    """向前端推送插件系统实时消息 (id=PluginSystem)。"""
    try:
        from app.core.ws import Publisher

        await Publisher.send(
            id=PLUGIN_SYSTEM_WS_ID,
            type=message_type,
            data=data,
        )
    except Exception as exc:
        logger.warning(
            f"send plugin realtime message failed: {type(exc).__name__}: {exc}"
        )


def schedule_plugin_system_message(message_type: str, data: Dict[str, Any]) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    loop.create_task(send_plugin_system_message(message_type, data))


def publish_runtime_record(record: Any, *, event: str) -> None:
    payload = {
        "event": event,
        "record": _serialize_record(record),
    }
    schedule_plugin_system_message("plugin.runtime.updated", payload)


async def build_plugin_snapshot(*, discovered: Dict[str, Any] | None = None) -> Dict[str, Any]:
    from .config_store import PluginConfigStore
    from .manager import PluginManager

    config_store = PluginConfigStore()
    plugins_dir = Path.cwd() / "plugins"
    if discovered is None:
        discovered = await PluginManager.discover_plugins()
    root = await config_store.get_root(
        plugins_dir,
        discovered,
        auto_create_missing=False,
    )

    schemas: Dict[str, Dict[str, Any]] = {}
    schema_errors: Dict[str, str] = {}
    plugin_services: Dict[str, Dict[str, Any]] = {}
    plugin_packages: Dict[str, Dict[str, Any]] = {}
    for plugin_name, plugin_source in discovered.items():
        try:
            schemas[plugin_name] = _redact_sensitive_schema(
                config_store.load_schema(plugin_name)
            )
        except Exception as exc:
            schemas[plugin_name] = {}
            schema_errors[plugin_name] = f"{type(exc).__name__}: {exc}"

        package_name = str(getattr(plugin_source, "distribution", "") or "").strip()
        if package_name:
            plugin_packages[plugin_name] = {
                "package": package_name,
                "version": getattr(plugin_source, "version", None),
                "source": str(getattr(plugin_source, "source", "pypi") or "pypi"),
                "path": str(getattr(plugin_source, "path", "") or "") or None,
            }

        try:
            _, plugin_class = PluginManager.loader._resolve_plugin_module_and_class(
                plugin_name,
                plugin_source,
                clear_cache=False,
            )
            provides, needs, wants = PluginManager.loader._meta(plugin_class)
            plugin_services[plugin_name] = {
                "provides": sorted(provides),
                "needs": sorted(needs),
                "wants": sorted(wants),
            }
        except Exception:
            plugin_services[plugin_name] = {
                "provides": [],
                "needs": [],
                "wants": [],
            }

    runtime_states: Dict[str, Dict[str, Any]] = {}
    for instance_id, record in getattr(PluginManager.loader, "records", {}).items():
        runtime_states[str(instance_id)] = _serialize_record(record)

    for item in root.get("instances", []):
        if not isinstance(item, dict):
            continue
        instance_id = str(item.get("id") or "")
        if not instance_id or instance_id in runtime_states:
            continue
        runtime_states[instance_id] = {
            "instance_id": instance_id,
            "plugin": str(item.get("plugin") or ""),
            "status": "configured",
            "generation": 0,
            "lifecycle_phase": "configured",
            "lifecycle_updated_at": None,
            "reload_count": 0,
            "last_reload_reason": None,
            "last_reload_at": None,
            "created_at": None,
            "discovered_at": None,
            "loaded_at": None,
            "activated_at": None,
            "disposed_at": None,
            "unloaded_at": None,
            "last_error": None,
            "last_error_at": None,
        }

    from .server import plugin_server

    server_snapshot = plugin_server.snapshot()
    page_items, page_errors = build_page_snapshot(
        discovered=discovered,
        records=getattr(PluginManager.loader, "records", {}),
    )
    return {
        "code": 200,
        "status": "success",
        "message": "ok",
        "version": int(root.get("version", 1)),
        "discovered_plugins": list(discovered.keys()),
        "schemas": schemas,
        "schema_errors": schema_errors,
        "plugin_services": plugin_services,
        "plugin_routes": server_snapshot["plugin_routes"],
        "plugin_actions": server_snapshot["plugin_actions"],
        "plugin_packages": plugin_packages,
        "instances": _redact_instances_sensitive(
            root.get("instances", []),
            schemas,
        ),
        "runtime_states": runtime_states,
        "pages": page_items,
        "page_errors": page_errors,
    }


async def publish_plugin_snapshot(
    *,
    reason: str,
    message: str | None = None,
    discovered: Dict[str, Any] | None = None,
) -> None:
    snapshot = await build_plugin_snapshot(discovered=discovered)
    snapshot["reason"] = reason
    if message:
        snapshot["message"] = message
    await send_plugin_system_message("plugin.snapshot.updated", snapshot)


def schedule_plugin_snapshot(
    *,
    reason: str,
    message: str | None = None,
    discovered: Dict[str, Any] | None = None,
) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    loop.create_task(
        publish_plugin_snapshot(reason=reason, message=message, discovered=discovered)
    )
