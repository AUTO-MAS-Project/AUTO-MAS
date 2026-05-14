#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.models.ConfigBase import ConfigBase


MAAEND_PRESET_TEMPLATE_DIR = Path.cwd() / "res/templates/MaaEnd/config"
MAAEND_PRESET_TEMPLATE = MAAEND_PRESET_TEMPLATE_DIR / "mxu-MaaEnd.json"
MAAEND_PRESET_TEMPLATE_BOOK = {
    "Win32-Window": MAAEND_PRESET_TEMPLATE_DIR / "mxu-MaaEnd.win32-window.json",
    "Win32-Window-Background": (
        MAAEND_PRESET_TEMPLATE_DIR / "mxu-MaaEnd.win32-background.json"
    ),
    "Win32-Front": MAAEND_PRESET_TEMPLATE_DIR / "mxu-MaaEnd.win32-front.json",
    "ADB": MAAEND_PRESET_TEMPLATE_DIR / "mxu-MaaEnd.adb.json",
}
MAAEND_PRESET_TASK_CONFIG = {
    "ProtocolSpace": {
        "enabled": "IfProtocolSpace",
        "core_options": [
            "ProtocolSpaceTab",
            "OperatorProgression",
            "WeaponProgression",
            "CrisisDrills",
            "RewardsSetOption",
        ],
    },
}


def load_maaend_preset_template(controller_type: str) -> dict[str, Any]:
    """读取 MAS 自带的 MaaEnd 预设配置模板"""

    template_path = MAAEND_PRESET_TEMPLATE_BOOK.get(
        controller_type, MAAEND_PRESET_TEMPLATE
    )
    if not template_path.exists():
        template_path = MAAEND_PRESET_TEMPLATE

    return json.loads(template_path.read_text(encoding="utf-8"))


def get_maaend_active_instance(config_data: dict[str, Any]) -> dict[str, Any]:
    """获取 MaaEnd 配置中当前应运行的实例"""

    instances = config_data["instances"]
    for instance in instances:
        if instance.get("id") == "automas":
            return instance

    active_id = config_data.get("lastActiveInstanceId")
    for instance in instances:
        if instance.get("id") == active_id:
            return instance

    return instances[0]


def build_maaend_preset_config(
    config: ConfigBase,
    controller_type: str,
) -> dict[str, Any]:
    """使用当前 MAS 模板和 MAS 保存的预设选项生成 MaaEnd 配置"""

    config_data = load_maaend_preset_template(controller_type)
    instance = get_maaend_active_instance(config_data)
    template_tasks = {
        task.get("taskName"): task
        for task in instance["tasks"]
    }
    stored_options = json.loads(config.get("Task", "Options"))

    tasks: list[dict[str, Any]] = []
    for template_task in instance["tasks"]:
        task_name = template_task["taskName"]
        task_config = MAAEND_PRESET_TASK_CONFIG.get(task_name, {})
        task = deepcopy(template_tasks[task_name])
        if "enabled" in task_config:
            task["enabled"] = bool(config.get("Task", task_config["enabled"]))
        if task_name in stored_options:
            for field, option in stored_options[task_name].items():
                if field in task.get("optionValues", {}):
                    task["optionValues"][field] = deepcopy(option)
        for field in task_config.get("core_options", []):
            task["optionValues"].setdefault(field, {"type": "select"})["caseName"] = (
                config.get("Task", field)
            )
        tasks.append(task)

    instance["id"] = "automas"
    instance["name"] = "AUTO-MAS"
    instance["tasks"] = tasks
    config_data["instances"] = [instance]
    config_data["lastActiveInstanceId"] = "automas"
    config_data["recentlyClosed"] = []
    return config_data


async def save_maaend_preset_options(
    config: ConfigBase,
    config_data: dict[str, Any],
    mark_configured: bool = False,
    controller_type: str = "Win32-Window",
) -> None:
    """从 MaaEnd 配置中抽取静态预设任务选项并保存到 MAS 配置"""

    instance = get_maaend_active_instance(config_data)
    options: dict[str, dict[str, Any]] = {}
    defaults = load_maaend_preset_template(controller_type)
    default_instance = get_maaend_active_instance(defaults)
    default_options_map = {
        task.get("taskName"): task.get("optionValues", {})
        for task in default_instance["tasks"]
    }
    for task in instance["tasks"]:
        task_name = task.get("taskName")
        if task_name not in default_options_map:
            continue
        task_config = MAAEND_PRESET_TASK_CONFIG.get(task_name, {})
        option_values = task.get("optionValues", {})
        options[task_name] = deepcopy(option_values)
        default_options = default_options_map.get(task_name, {})
        for field in task_config.get("core_options", []):
            await config.set(
                "Task",
                field,
                option_values.get(field, default_options[field])["caseName"],
            )

    await config.set("Task", "Options", json.dumps(options, ensure_ascii=False))
    if mark_configured:
        await config.set("Data", "IfPresetConfigured", True)
