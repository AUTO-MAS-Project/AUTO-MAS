import json
from pathlib import Path
from typing import Any

from app.models.config import MaaEndConfig, MaaEndUserConfig


class RuntimeBridgeError(ValueError):
    pass


def _load_source_config(script_config: MaaEndConfig) -> dict[str, Any]:
    source_path = Path(script_config.get("Info", "Path")) / "config" / "mxu-MaaEnd.json"
    if not source_path.exists():
        raise RuntimeBridgeError(f"MaaEnd config file not found: {source_path}")

    try:
        return json.loads(source_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise RuntimeBridgeError(f"Invalid MaaEnd config json: {e}") from e


def _select_instance(
    config_data: dict[str, Any], user_config: MaaEndUserConfig, script_config: MaaEndConfig
) -> dict[str, Any]:
    instances = config_data.get("instances", [])
    if not instances:
        raise RuntimeBridgeError("No MaaEnd instances in mxu-MaaEnd.json")

    preset_ref = str(user_config.get("Task", "PresetOverride")).strip()
    if not preset_ref:
        preset_ref = str(script_config.get("MaaEnd", "PresetTask")).strip()

    selected_instance = None
    if preset_ref:
        selected_instance = next(
            (item for item in instances if str(item.get("id", "")).strip() == preset_ref),
            None,
        )

    # Backward compatibility for historical name-based preset values.
    if selected_instance is None and preset_ref:
        selected_instance = next(
            (item for item in instances if str(item.get("name", "")).strip() == preset_ref),
            None,
        )

    if selected_instance is None:
        active_id = config_data.get("lastActiveInstanceId")
        selected_instance = next(
            (item for item in instances if item.get("id") == active_id), None
        )

    if selected_instance is None:
        selected_instance = instances[0]

    return selected_instance


def _apply_controller_and_resource(instance: dict[str, Any], script_config: MaaEndConfig):
    resource_profile = str(script_config.get("MaaEnd", "ResourceProfile")).strip()
    if resource_profile:
        instance["resourceName"] = resource_profile

    controller_type = str(script_config.get("Run", "ControllerType")).strip()
    if not controller_type:
        return

    instance["controllerName"] = controller_type


def _collect_override_items(
    override_data: dict[str, Any] | list[Any],
) -> list[tuple[str, Any]]:
    if isinstance(override_data, dict):
        return [(str(task_key), payload) for task_key, payload in override_data.items()]

    if isinstance(override_data, list):
        override_items: list[tuple[str, Any]] = []
        for item in override_data:
            if not isinstance(item, dict):
                continue
            task_key = item.get("taskName") or item.get("id")
            if task_key is None:
                continue
            override_items.append((str(task_key), item))
        return override_items

    raise RuntimeBridgeError("Task.OptionOverride must be json object or array")


def _apply_option_override(instance: dict[str, Any], user_config: MaaEndUserConfig):
    override_raw = str(user_config.get("Task", "OptionOverride")).strip()
    if not override_raw:
        return

    try:
        override_data = json.loads(override_raw)
    except json.JSONDecodeError as e:
        raise RuntimeBridgeError(f"Invalid Task.OptionOverride json: {e}") from e

    tasks = instance.get("tasks", [])
    if not tasks:
        return

    task_by_name = {
        str(task.get("taskName", "")): task
        for task in tasks
        if isinstance(task, dict) and task.get("taskName") is not None
    }
    task_by_id = {
        str(task.get("id", "")): task
        for task in tasks
        if isinstance(task, dict) and task.get("id") is not None
    }

    for task_key, payload in _collect_override_items(override_data):
        task = task_by_name.get(task_key) or task_by_id.get(task_key)
        if task is None:
            continue

        if isinstance(payload, bool):
            task["enabled"] = payload
            continue

        if not isinstance(payload, dict):
            raise RuntimeBridgeError(f"Invalid task override payload: {task_key}")

        if "enabled" in payload:
            task["enabled"] = bool(payload.get("enabled"))

        option_values = payload.get("optionValues")
        if isinstance(option_values, dict):
            if not isinstance(task.get("optionValues"), dict):
                task["optionValues"] = {}
            task["optionValues"].update(option_values)


def build_runtime_config(
    script_id: str,
    user_id: str,
    script_config: MaaEndConfig,
    user_config: MaaEndUserConfig,
) -> Path:
    config_data = _load_source_config(script_config)
    selected_instance = _select_instance(config_data, user_config, script_config)
    _apply_controller_and_resource(selected_instance, script_config)
    _apply_option_override(selected_instance, user_config)

    instance_id = selected_instance.get("id")
    if instance_id:
        config_data["lastActiveInstanceId"] = instance_id
        settings = config_data.get("settings")
        if not isinstance(settings, dict):
            settings = {}
            config_data["settings"] = settings
        settings["autoStartInstanceId"] = instance_id
        settings["autoRunOnLaunch"] = True

    runtime_path = Path.cwd() / f"data/{script_id}/{user_id}/Runtime/mxu-MaaEnd.runtime.json"
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_path.write_text(
        json.dumps(config_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return runtime_path
