#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.models.config import MaaEndConfig, MaaEndUserConfig
from app.utils.constants import UTC4


class RuntimeBridgeError(ValueError):
    pass


def _load_source_config(source_path: Path) -> dict[str, Any]:
    if not source_path.exists():
        raise RuntimeBridgeError(f"未找到 MaaEnd 配置文件: {source_path}")

    try:
        return json.loads(source_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise RuntimeBridgeError(f"MaaEnd 配置 JSON 解析失败: {e}") from e


def _select_instance(config_data: dict[str, Any]) -> dict[str, Any]:
    instances = config_data.get("instances", [])
    if not instances:
        raise RuntimeBridgeError("托管配置中不存在 MaaEnd 实例")
    active_id = config_data.get("lastActiveInstanceId")
    selected_instance = next(
        (item for item in instances if item.get("id") == active_id), None
    )
    if selected_instance is None:
        selected_instance = instances[0]
    return selected_instance


def _resolve_resource_name(user_config: MaaEndUserConfig) -> str:
    server = str(user_config.get("Info", "Server") or "").strip()
    if server == "Official":
        return "官服"
    if server == "Bilibili":
        return "B服"
    raise RuntimeBridgeError(f"不支持的 MaaEnd 服务器类型: {server}")


def _apply_controller_and_resource(
    instance: dict[str, Any], script_config: MaaEndConfig, user_config: MaaEndUserConfig
):
    instance["resourceName"] = _resolve_resource_name(user_config)

    controller_type = str(script_config.get("Run", "ControllerType")).strip()
    if not controller_type:
        return

    instance["controllerName"] = controller_type


def _apply_pre_action(instance: dict[str, Any], script_config: MaaEndConfig):
    controller_type = str(script_config.get("Run", "ControllerType")).strip()
    if not controller_type.startswith("Win32"):
        return

    # Endfield 启动由 AUTO-MAS 统一管理，不再由 MaaEnd preAction 拉起
    pre_action = instance.get("preAction")
    if not isinstance(pre_action, dict):
        pre_action = {}
        instance["preAction"] = pre_action

    pre_action["enabled"] = False
    pre_action["program"] = ""
    pre_action["args"] = ""
    pre_action["waitForExit"] = False
    pre_action["skipIfRunning"] = False


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

    raise RuntimeBridgeError("Task.OptionOverride 必须是 JSON 对象或数组")


def _apply_option_override(instance: dict[str, Any], user_config: MaaEndUserConfig):
    override_raw = str(user_config.get("Task", "OptionOverride")).strip()
    if not override_raw:
        return

    try:
        override_data = json.loads(override_raw)
    except json.JSONDecodeError as e:
        raise RuntimeBridgeError(f"Task.OptionOverride JSON 解析失败: {e}") from e

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
            raise RuntimeBridgeError(f"任务覆盖配置格式错误: {task_key}")

        if "enabled" in payload:
            task["enabled"] = bool(payload.get("enabled"))

        option_values = payload.get("optionValues")
        if isinstance(option_values, dict):
            if not isinstance(task.get("optionValues"), dict):
                task["optionValues"] = {}
            task["optionValues"].update(option_values)


def _apply_visit_friends_steal_disable_today(
    instance: dict[str, Any], user_config: MaaEndUserConfig
) -> None:
    disabled_date = str(
        user_config.get("Data", "VisitFriendsStealDisabledDate") or ""
    ).strip()
    today = datetime.now(tz=UTC4).strftime("%Y-%m-%d")
    if disabled_date != today:
        return

    tasks = instance.get("tasks", [])
    if not isinstance(tasks, list):
        return

    for task in tasks:
        if not isinstance(task, dict):
            continue
        if str(task.get("taskName", "")).strip() != "VisitFriends":
            continue
        option_values = task.get("optionValues")
        if not isinstance(option_values, dict):
            option_values = {}
            task["optionValues"] = option_values
        option_values["PriorStealVegetables"] = {"type": "switch", "value": False}
        return


def build_runtime_config(
    script_id: str,
    user_id: str,
    script_config: MaaEndConfig,
    user_config: MaaEndUserConfig,
    source_path: Path,
    auto_run_on_launch: bool = True,
) -> Path:
    config_data = _load_source_config(source_path)
    selected_instance = _select_instance(config_data)
    _apply_controller_and_resource(selected_instance, script_config, user_config)
    _apply_pre_action(selected_instance, script_config)
    _apply_option_override(selected_instance, user_config)
    _apply_visit_friends_steal_disable_today(selected_instance, user_config)

    instance_id = selected_instance.get("id")
    if instance_id:
        config_data["lastActiveInstanceId"] = instance_id
        settings = config_data.get("settings")
        if not isinstance(settings, dict):
            settings = {}
            config_data["settings"] = settings
        settings["autoStartInstanceId"] = instance_id
        settings["autoRunOnLaunch"] = auto_run_on_launch

    runtime_path = Path.cwd() / f"data/{script_id}/{user_id}/Runtime/mxu-MaaEnd.runtime.json"
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_path.write_text(
        json.dumps(config_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return runtime_path


