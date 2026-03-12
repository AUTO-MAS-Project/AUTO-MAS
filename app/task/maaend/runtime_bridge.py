import json
from pathlib import Path
from typing import Any

from app.models.config import MaaEndConfig, MaaEndUserConfig
from app.utils import get_logger


logger = get_logger("MaaEnd RuntimeBridge")


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
    if not isinstance(instances, list) or len(instances) == 0:
        raise RuntimeBridgeError("No MaaEnd instances in mxu-MaaEnd.json")

    preset_name = str(user_config.get("Task", "PresetOverride")).strip()
    if not preset_name:
        preset_name = str(script_config.get("MaaEnd", "PresetTask")).strip()

    selected_instance = None
    if preset_name:
        selected_instance = next(
            (item for item in instances if str(item.get("name", "")).strip() == preset_name),
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

    controller_name = str(instance.get("controllerName", "")).strip()
    if not controller_name:
        instance["controllerName"] = controller_type
        return

    if "-" in controller_name:
        _, suffix = controller_name.split("-", 1)
        instance["controllerName"] = f"{controller_type}-{suffix}"
    else:
        instance["controllerName"] = controller_type


def _apply_option_override(instance: dict[str, Any], user_config: MaaEndUserConfig):
    override_raw = str(user_config.get("Task", "OptionOverride")).strip()
    if not override_raw:
        return
    try:
        override_data = json.loads(override_raw)
    except json.JSONDecodeError as e:
        raise RuntimeBridgeError(f"Invalid Task.OptionOverride json: {e}") from e

    tasks = instance.get("tasks", [])
    if not isinstance(tasks, list) or len(tasks) == 0:
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

    if isinstance(override_data, list):
        override_items = []
        for item in override_data:
            if not isinstance(item, dict):
                continue
            task_key = item.get("taskName") or item.get("id")
            if task_key:
                override_items.append((str(task_key), item))
    elif isinstance(override_data, dict):
        override_items = list(override_data.items())
    else:
        raise RuntimeBridgeError("Task.OptionOverride must be json object or array")

    for task_key, payload in override_items:
        task = task_by_name.get(task_key) or task_by_id.get(task_key)
        if task is None:
            logger.warning(f"Task override target not found: {task_key}")
            continue

        if isinstance(payload, bool):
            task["enabled"] = payload
            continue

        if not isinstance(payload, dict):
            logger.warning(f"Ignore invalid task override payload: {task_key}")
            continue

        if "enabled" in payload:
            task["enabled"] = bool(payload.get("enabled"))
        elif "Enabled" in payload:
            task["enabled"] = bool(payload.get("Enabled"))

        option_values = None
        if isinstance(payload.get("optionValues"), dict):
            option_values = payload["optionValues"]
        elif isinstance(payload.get("OptionValues"), dict):
            option_values = payload["OptionValues"]
        else:
            candidate = {
                k: v
                for k, v in payload.items()
                if isinstance(v, dict)
                and any(x in v for x in ("type", "value", "caseName", "values"))
            }
            if candidate:
                option_values = candidate

        if option_values:
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

    runtime_path = (
        Path.cwd() / f"data/{script_id}/{user_id}/Runtime/mxu-MaaEnd.runtime.json"
    )
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_path.write_text(
        json.dumps(config_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return runtime_path
