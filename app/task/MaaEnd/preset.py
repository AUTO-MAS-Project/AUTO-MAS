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

from .constants import MAAEND_DEFAULT_CONTROLLER


MAAEND_CONFIG_FILENAME = "mxu-MaaEnd.json"
MAAEND_LOCAL_METADATA_FIELDS = ("version", "interfaceTaskSnapshot")


def load_maaend_preset_template() -> dict[str, Any]:
    """读取 MAS 自带的 MaaEnd 预设配置模板"""

    return json.loads(
        (
            Path.cwd() / f"res/templates/MaaEnd/config/{MAAEND_CONFIG_FILENAME}"
        ).read_text(encoding="utf-8")
    )


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


def apply_maaend_local_metadata(
    config_data: dict[str, Any], local_config_data: dict[str, Any] | None
) -> None:
    """使用 MaaEnd 本地配置中的 MXU 元数据覆盖运行配置"""

    for field in MAAEND_LOCAL_METADATA_FIELDS:
        config_data.pop(field, None)
        if local_config_data is not None and field in local_config_data:
            config_data[field] = deepcopy(local_config_data[field])


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
    tasks: list[dict[str, Any]], sanity_task_config: dict[str, Any]
) -> tuple[bool, bool]:
    """将 MAS 理智配置写入 MaaEnd 任务配置"""

    protocol_space_configured = False
    auto_essence_configured = False
    sanity_enabled = any(
        task.get("enabled", True)
        for task in tasks
        if task.get("taskName") in ("ProtocolSpace", "AutoEssence")
    )
    if not sanity_enabled:
        return True, True

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


def build_maaend_preset_config(controller_type: str) -> dict[str, Any]:
    """使用当前 MAS 模板生成 MaaEnd 预设配置"""

    config_data = load_maaend_preset_template()
    instance = get_maaend_preset_instance(config_data, controller_type)
    for task in instance["tasks"]:
        task.setdefault("enabled", True)
    config_data["instances"] = [instance]
    return config_data


def load_or_create_maaend_preset_config(
    config_dir: Path, controller_type: str
) -> dict[str, Any]:
    """读取保存的 MaaEnd 预设配置，不存在时用模板创建"""

    config_path = config_dir / MAAEND_CONFIG_FILENAME
    if config_path.exists():
        return load_maaend_config(config_dir)

    config_dir.mkdir(parents=True, exist_ok=True)
    config_data = build_maaend_preset_config(controller_type)
    save_maaend_config(config_dir, config_data)
    return config_data


def merge_maaend_preset_options(
    preset_config_data: dict[str, Any],
    edited_config_data: dict[str, Any],
    controller_type: str = MAAEND_DEFAULT_CONTROLLER,
) -> None:
    """将 MaaEnd 预设任务 optionValues 拼回保存配置"""

    preset_instance = get_maaend_active_instance(preset_config_data)
    edited_instance = get_maaend_active_instance(edited_config_data)
    preset_task_names = {
        task.get("taskName")
        for task in get_maaend_preset_instance(
            load_maaend_preset_template(), controller_type
        )["tasks"]
    }
    preset_tasks = {
        task.get("taskName"): task
        for task in preset_instance.get("tasks", [])
        if task.get("taskName") in preset_task_names
    }
    for task in edited_instance.get("tasks", []):
        task_name = task.get("taskName")
        preset_task = preset_tasks.get(task_name)
        if preset_task is None:
            continue
        preset_task["optionValues"] = deepcopy(task.get("optionValues", {}))
