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
from .constants import (
    MAAEND_CORE_OPTION_FIELD_BOOK,
    MAAEND_DEFAULT_CONTROLLER,
    MAAEND_PRESET_TASK_CONFIG,
)


MAAEND_PRESET_TEMPLATE_DIR = Path.cwd() / "res/templates/MaaEnd/config"
MAAEND_PRESET_TEMPLATE = MAAEND_PRESET_TEMPLATE_DIR / "mxu-MaaEnd.json"
MAAEND_CONFIG_FILENAME = "mxu-MaaEnd.json"


def load_maaend_preset_template() -> dict[str, Any]:
    """读取 MAS 自带的 MaaEnd 预设配置模板"""

    return json.loads(MAAEND_PRESET_TEMPLATE.read_text(encoding="utf-8"))


def load_maaend_config(config_dir: Path) -> dict[str, Any]:
    """读取 MaaEnd 配置文件"""

    return json.loads(
        (config_dir / MAAEND_CONFIG_FILENAME).read_text(encoding="utf-8")
    )


def save_maaend_config(config_dir: Path, config_data: dict[str, Any]) -> None:
    """写入 MaaEnd 配置文件"""

    (config_dir / MAAEND_CONFIG_FILENAME).write_text(
        json.dumps(config_data, ensure_ascii=False, indent=4),
        encoding="utf-8",
    )


def get_maaend_preset_instance(
    config_data: dict[str, Any], controller_type: str
) -> dict[str, Any]:
    """按控制器类型获取 MAS 预设实例"""

    for instance in config_data["instances"]:
        if instance.get("controllerName") == controller_type:
            return instance

    raise ValueError(f"控制器 {controller_type} 暂不支持 MaaEnd 预设模式")


def is_maaend_preset_supported(controller_type: str) -> bool:
    """判断控制器是否存在 MAS 预设实例"""

    try:
        get_maaend_preset_instance(load_maaend_preset_template(), controller_type)
    except (FileNotFoundError, KeyError, ValueError):
        return False
    return True


def get_maaend_active_instance(config_data: dict[str, Any]) -> dict[str, Any]:
    """获取 MaaEnd 配置中当前应运行的实例"""

    instances = config_data["instances"]
    if not instances:
        return {"tasks": []}

    return instances[0]


def apply_maaend_sanity_task_config(
    tasks: list[dict[str, Any]],
    sanity_enabled: bool,
    sanity_task_config: dict[str, Any],
) -> tuple[bool, bool]:
    """将 MAS 理智配置写入 MaaEnd 任务配置"""

    if not sanity_enabled:
        for task in tasks:
            if task["taskName"] in ("ProtocolSpace", "AutoEssence"):
                task["enabled"] = False
        return True, True

    protocol_space_configured = False
    auto_essence_configured = False
    sanity_task_type = sanity_task_config["SanityTaskType"]
    auto_essence_location = ""
    if sanity_task_type == "Essence":
        auto_essence_location = sanity_task_config.get(
            "AutoEssenceSpecifiedLocation", ""
        )

    for task in tasks:
        if task["taskName"] == "ProtocolSpace":
            task["enabled"] = (
                sanity_task_type != "Essence" and not protocol_space_configured
            )
            if not task["enabled"]:
                continue

            protocol_space_configured = True
            task.setdefault("optionValues", {})
            task["optionValues"]["ProtocolSpaceTab"] = {
                "type": "select",
                "caseName": sanity_task_type,
            }
            task["optionValues"]["OperatorProgression"] = {
                "type": "select",
                "caseName": sanity_task_config["OperatorProgression"],
            }
            task["optionValues"]["WeaponProgression"] = {
                "type": "select",
                "caseName": sanity_task_config["WeaponProgression"],
            }
            task["optionValues"]["CrisisDrills"] = {
                "type": "select",
                "caseName": sanity_task_config["CrisisDrills"],
            }
            task["optionValues"]["RewardsSetOption"] = {
                "type": "select",
                "caseName": sanity_task_config["RewardsSetOption"],
            }
        elif task["taskName"] == "AutoEssence":
            task["enabled"] = (
                sanity_task_type == "Essence" and not auto_essence_configured
            )
            if not task["enabled"]:
                continue

            auto_essence_configured = True
            task.setdefault("optionValues", {})
            task["optionValues"]["AutoEssenceSpecifiedLocation"] = {
                "type": "select",
                "caseName": auto_essence_location,
            }

    return protocol_space_configured, auto_essence_configured


def build_maaend_preset_config(
    config: ConfigBase,
    controller_type: str,
) -> dict[str, Any]:
    """使用当前 MAS 模板和 MAS 保存的预设选项生成 MaaEnd 配置"""

    config_data = load_maaend_preset_template()
    instance = get_maaend_preset_instance(config_data, controller_type)
    stored_options = json.loads(config.get("Task", "Options"))

    tasks: list[dict[str, Any]] = []
    for template_task in instance["tasks"]:
        task_name = template_task["taskName"]
        task_config = MAAEND_PRESET_TASK_CONFIG.get(task_name, {})
        task = deepcopy(template_task)
        if "enabled" in task_config:
            task["enabled"] = bool(config.get("Task", task_config["enabled"]))
            if task_name == "ProtocolSpace":
                task["enabled"] = (
                    task["enabled"]
                    and config.get("Task", "SanityTaskType") != "Essence"
                )
            elif task_name == "AutoEssence":
                task["enabled"] = (
                    task["enabled"]
                    and config.get("Task", "SanityTaskType") == "Essence"
                )
        if task_name in stored_options:
            task["optionValues"] = deepcopy(stored_options[task_name])
        for field in task_config.get("core_options", []):
            option_field = MAAEND_CORE_OPTION_FIELD_BOOK.get(field, field)
            task.setdefault("optionValues", {})
            task["optionValues"].setdefault(option_field, {"type": "select"})[
                "caseName"
            ] = (
                config.get("Task", field)
            )
        tasks.append(task)

    instance["tasks"] = tasks
    config_data["instances"] = [instance]
    return config_data


async def save_maaend_preset_options(
    config: ConfigBase,
    config_data: dict[str, Any],
    mark_configured: bool = False,
    controller_type: str = MAAEND_DEFAULT_CONTROLLER,
) -> None:
    """从 MaaEnd 配置中抽取静态预设任务选项并保存到 MAS 配置"""

    instance = get_maaend_active_instance(config_data)
    options: dict[str, dict[str, Any]] = {}
    preset_task_names = {
        task.get("taskName")
        for task in get_maaend_preset_instance(
            load_maaend_preset_template(), controller_type
        )["tasks"]
    }
    for task in instance["tasks"]:
        task_name = task.get("taskName")
        if task_name not in preset_task_names:
            continue
        task_config = MAAEND_PRESET_TASK_CONFIG.get(task_name, {})
        option_values = task.get("optionValues", {})
        options[task_name] = deepcopy(option_values)
        for field in task_config.get("core_options", []):
            option_field = MAAEND_CORE_OPTION_FIELD_BOOK.get(field, field)
            option = option_values.get(option_field)
            if not option or "caseName" not in option:
                continue
            await config.set(
                "Task",
                field,
                option["caseName"],
            )

    await config.set("Task", "Options", json.dumps(options, ensure_ascii=False))
    if mark_configured:
        await config.set("Data", "IfPresetConfigured", True)
