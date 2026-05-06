from __future__ import annotations

import asyncio
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Literal

from app.utils import get_logger

PLUGIN_SYSTEM_WS_ID = "PluginSystem"

logger = get_logger("PluginRealtime")


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


async def send_plugin_system_message(message_type: Literal["Update", "Message", "Info", "Signal"], data: Dict[str, Any]) -> None:
    try:
        from app.core import Config

        await Config.send_websocket_message(
            id=PLUGIN_SYSTEM_WS_ID,
            type=message_type,
            data=data,
        )
    except Exception as exc:
        logger.warning(
            f"send plugin realtime message failed: {type(exc).__name__}: {exc}"
        )


def schedule_plugin_system_message(message_type: Literal["Update", "Message", "Info", "Signal"], data: Dict[str, Any]) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    loop.create_task(send_plugin_system_message(message_type, data))


def publish_runtime_record(record: Any, *, event: str) -> None:
    payload = {
        "kind": "runtime_state",
        "event": event,
        "record": _serialize_record(record),
    }
    schedule_plugin_system_message("Update", payload)


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
        plugin_path = getattr(plugin_source, "path", None)
        try:
            schemas[plugin_name] = config_store.load_schema(plugin_name, plugin_path)
        except Exception as exc:
            schemas[plugin_name] = {}
            schema_errors[plugin_name] = f"{type(exc).__name__}: {exc}"

        package_name = str(getattr(plugin_source, "distribution", "") or "").strip()
        if package_name:
            plugin_packages[plugin_name] = {
                "package": package_name,
                "version": getattr(plugin_source, "version", None),
                "source": str(getattr(plugin_source, "source", "pypi") or "pypi"),
                "path": str(plugin_path) if plugin_path else None,
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
        "instances": deepcopy(root.get("instances", [])),
        "runtime_states": runtime_states,
    }


async def publish_plugin_snapshot(
    *,
    reason: str,
    message: str | None = None,
    discovered: Dict[str, Any] | None = None,
) -> None:
    snapshot = await build_plugin_snapshot(discovered=discovered)
    snapshot["kind"] = "snapshot"
    snapshot["reason"] = reason
    if message:
        snapshot["message"] = message
    await send_plugin_system_message("Update", snapshot)


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
