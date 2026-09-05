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


from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import (
    SUPPORTED_OPTION_TYPES,
    MaaFWInterface,
    MaaFWOption,
    MaaFWPreset,
    MaaFWPresetOptionValue,
    MaaFWTaskOptionsByTask,
    MaaFWTaskOptionValue,
    build_pretask_task_name,
    is_pretask_task_name,
    iter_pretasks,
)

CUSTOM_PRESET_NAME = "__auto_mas_custom_preset__"


class MaaFWTaskPresetSnapshot(BaseModel):
    taskOrder: list[str] = Field(default_factory=list)
    taskChecked: dict[str, bool] = Field(default_factory=dict)
    taskOptions: MaaFWTaskOptionsByTask = Field(default_factory=dict)


class MaaFWTaskConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    selectedPreset: str = CUSTOM_PRESET_NAME
    presets: dict[str, MaaFWTaskPresetSnapshot] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_raw_config(cls, value: Any):
        if not isinstance(value, dict):
            return value

        selected_preset = _normalize_preset_name(value.get("selectedPreset"))
        raw_presets = value.get("presets")
        normalized_presets: dict[str, dict[str, Any]] = {}
        if isinstance(raw_presets, dict):
            for preset_name, snapshot in raw_presets.items():
                if isinstance(preset_name, str):
                    normalized_presets[preset_name] = _normalize_raw_snapshot(snapshot)

        return {
            "selectedPreset": selected_preset,
            "presets": normalized_presets,
        }


def normalize_task_config(
    config: MaaFWTaskConfig,
    interface_model: MaaFWInterface,
) -> MaaFWTaskConfig:
    preset_snapshots: dict[str, MaaFWTaskPresetSnapshot] = {}
    custom_snapshot = config.presets.get(CUSTOM_PRESET_NAME)
    preset_snapshots[CUSTOM_PRESET_NAME] = normalize_snapshot(
        custom_snapshot,
        interface_model,
    )

    for preset in interface_model.preset:
        persisted_snapshot = config.presets.get(preset.name)
        snapshot = persisted_snapshot or build_interface_preset_snapshot(
            interface_model,
            preset,
        )
        preset_snapshots[preset.name] = normalize_snapshot(snapshot, interface_model)

    selected_preset = _normalize_preset_name(config.selectedPreset)
    if selected_preset not in preset_snapshots:
        selected_preset = CUSTOM_PRESET_NAME

    return MaaFWTaskConfig(
        selectedPreset=selected_preset,
        presets=preset_snapshots,
    )


def normalize_snapshot(
    snapshot: MaaFWTaskPresetSnapshot | dict[str, Any] | None,
    interface_model: MaaFWInterface,
) -> MaaFWTaskPresetSnapshot:
    default_task_order = _build_default_task_order(interface_model)
    pretask_task_order = [
        build_pretask_task_name(pretask) for pretask in iter_pretasks(interface_model)
    ]
    all_task_ids = [*pretask_task_order, *default_task_order]
    valid_task_ids = set(all_task_ids)
    normalized_order: list[str] = []
    seen_task_ids: set[str] = set()
    raw_snapshot = _normalize_raw_snapshot(snapshot)

    raw_task_order = [
        task_id for task_id in raw_snapshot["taskOrder"] if task_id in valid_task_ids
    ]
    partitioned_task_order = [
        task_id for task_id in raw_task_order if is_pretask_task_name(task_id)
    ] + [task_id for task_id in raw_task_order if not is_pretask_task_name(task_id)]
    for task_id in partitioned_task_order:
        if task_id in valid_task_ids and task_id not in seen_task_ids:
            normalized_order.append(task_id)
            seen_task_ids.add(task_id)

    for task_id in default_task_order:
        if task_id not in seen_task_ids:
            normalized_order.append(task_id)

    normalized_checked = {task_id: False for task_id in all_task_ids}
    for task_id, checked in raw_snapshot["taskChecked"].items():
        if task_id in valid_task_ids:
            normalized_checked[task_id] = bool(checked)

    normalized_options = normalize_task_options_by_task(
        raw_snapshot["taskOptions"],
        normalized_order,
        interface_model,
    )
    return MaaFWTaskPresetSnapshot(
        taskOrder=normalized_order,
        taskChecked=normalized_checked,
        taskOptions=normalized_options,
    )


def normalize_task_options_by_task(
    raw_task_options: dict[str, Any] | None,
    task_names: list[str],
    interface_model: MaaFWInterface,
    *,
    controller_name: str | None = None,
    resource_name: str | None = None,
) -> MaaFWTaskOptionsByTask:
    task_option_maps = _build_task_option_maps(
        interface_model,
        controller_name=controller_name,
        resource_name=resource_name,
    )
    normalized: MaaFWTaskOptionsByTask = {}

    for task_name in [item for item in task_names if isinstance(item, str)]:
        option_map = task_option_maps.get(task_name, {})
        defaults, value_types = _build_option_defaults(option_map)
        case_name_sets = _build_option_case_name_sets(option_map)
        raw_options_for_task = (
            raw_task_options.get(task_name)
            if isinstance(raw_task_options, dict)
            else None
        )
        normalized[task_name] = _normalize_options_for_task(
            raw_options_for_task,
            option_map,
            defaults,
            value_types,
            case_name_sets,
        )

    return normalized


def normalize_task_execution_payload(
    raw_task_list: Any,
    raw_task_options: Any,
    interface_model: MaaFWInterface,
    *,
    controller_name: str | None = None,
    resource_name: str | None = None,
) -> tuple[list[str], MaaFWTaskOptionsByTask]:
    pretask_task_names = [
        build_pretask_task_name(pretask) for pretask in iter_pretasks(interface_model)
    ]
    valid_task_names = {
        *pretask_task_names,
        *(task.name for task in interface_model.task),
    }
    normalized_task_list: list[str] = []
    seen_task_names: set[str] = set()

    if isinstance(raw_task_list, list):
        for task_name in raw_task_list:
            if not isinstance(task_name, str):
                continue
            if task_name not in valid_task_names or task_name in seen_task_names:
                continue
            normalized_task_list.append(task_name)
            seen_task_names.add(task_name)

    normalized_task_list = [
        task_name
        for task_name in normalized_task_list
        if is_pretask_task_name(task_name)
    ] + [
        task_name
        for task_name in normalized_task_list
        if not is_pretask_task_name(task_name)
    ]

    normalized_task_options = normalize_task_options_by_task(
        raw_task_options if isinstance(raw_task_options, dict) else None,
        normalized_task_list,
        interface_model,
        controller_name=controller_name,
        resource_name=resource_name,
    )
    return normalized_task_list, normalized_task_options


def build_interface_preset_snapshot(
    interface_model: MaaFWInterface,
    preset: MaaFWPreset,
    *,
    task_order: list[str] | None = None,
    task_option_maps: dict[str, dict[str, MaaFWOption]] | None = None,
    include_default_options: bool = True,
) -> MaaFWTaskPresetSnapshot:
    task_order = task_order or _build_default_task_order(interface_model)
    task_checked = {task_name: False for task_name in task_order}
    task_option_maps = task_option_maps or _build_task_option_maps(interface_model)
    task_options_by_task: MaaFWTaskOptionsByTask = {}

    if include_default_options:
        for task_name in task_order:
            defaults, _ = _build_option_defaults(task_option_maps.get(task_name, {}))
            task_options_by_task[task_name] = defaults

    ordered_preset_tasks: list[str] = []
    seen_task_names: set[str] = set()
    for preset_task in preset.task or []:
        if preset_task.name not in task_checked or preset_task.name in seen_task_names:
            continue

        ordered_preset_tasks.append(preset_task.name)
        seen_task_names.add(preset_task.name)
        task_checked[preset_task.name] = bool(
            True if preset_task.enabled is None else preset_task.enabled
        )

        option_map = task_option_maps.get(preset_task.name, {})
        target_options = task_options_by_task.setdefault(preset_task.name, {})
        for option_name, option_value in (preset_task.option or {}).items():
            if option_name not in option_map:
                continue
            _apply_preset_option_value(
                option_name,
                option_value,
                option_map,
                target_options,
            )

    normalized_order = ordered_preset_tasks + [
        task_name for task_name in task_order if task_name not in seen_task_names
    ]
    return MaaFWTaskPresetSnapshot(
        taskOrder=normalized_order,
        taskChecked=task_checked,
        taskOptions=task_options_by_task,
    )


def _normalize_raw_snapshot(snapshot: Any) -> dict[str, Any]:
    if isinstance(snapshot, MaaFWTaskPresetSnapshot):
        return {
            "taskOrder": [item for item in snapshot.taskOrder if isinstance(item, str)],
            "taskChecked": {
                task_id: bool(checked)
                for task_id, checked in snapshot.taskChecked.items()
                if isinstance(task_id, str)
            },
            "taskOptions": _normalize_raw_task_options(snapshot.taskOptions),
        }

    if not isinstance(snapshot, dict):
        return {
            "taskOrder": [],
            "taskChecked": {},
            "taskOptions": {},
        }

    task_order = snapshot.get("taskOrder")
    task_checked = snapshot.get("taskChecked")
    return {
        "taskOrder": (
            [item for item in task_order if isinstance(item, str)]
            if isinstance(task_order, list)
            else []
        ),
        "taskChecked": (
            {
                task_id: bool(checked)
                for task_id, checked in task_checked.items()
                if isinstance(task_id, str)
            }
            if isinstance(task_checked, dict)
            else {}
        ),
        "taskOptions": _normalize_raw_task_options(snapshot.get("taskOptions")),
    }


def _normalize_raw_task_options(
    value: Any,
) -> dict[str, dict[str, MaaFWTaskOptionValue]]:
    normalized: dict[str, dict[str, MaaFWTaskOptionValue]] = {}
    if not isinstance(value, dict):
        return normalized

    for task_id, option_map in value.items():
        if not isinstance(task_id, str) or not isinstance(option_map, dict):
            continue

        normalized_options: dict[str, MaaFWTaskOptionValue] = {}
        for option_name, option_value in option_map.items():
            if not isinstance(option_name, str):
                continue
            normalized_value = _normalize_option_value_for_storage(option_value)
            if normalized_value is not None:
                normalized_options[option_name] = normalized_value
        normalized[task_id] = normalized_options

    return normalized


def _normalize_option_value_for_storage(value: Any) -> MaaFWTaskOptionValue | None:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    if isinstance(value, dict):
        return {
            key: item
            for key, item in value.items()
            if isinstance(key, str) and isinstance(item, str)
        }
    return None


def _normalize_preset_name(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return CUSTOM_PRESET_NAME


def _build_default_task_order(interface_model: MaaFWInterface) -> list[str]:
    return [task.name for task in interface_model.task]


def _build_task_option_maps(
    interface_model: MaaFWInterface,
    *,
    controller_name: str | None = None,
    resource_name: str | None = None,
) -> dict[str, dict[str, MaaFWOption]]:
    option_map = interface_model.option
    task_option_maps: dict[str, dict[str, MaaFWOption]] = {}
    common_option_names = _build_common_option_names(
        interface_model,
        controller_name=controller_name,
        resource_name=resource_name,
    )

    for task in interface_model.task:
        collected: dict[str, MaaFWOption] = {}
        _collect_task_options(common_option_names, option_map, collected)
        _collect_task_options(task.option or [], option_map, collected)
        task_option_maps[task.name] = collected

    for pretask in iter_pretasks(interface_model):
        if (
            controller_name is not None
            and pretask.controller
            and controller_name not in pretask.controller
        ):
            continue
        if (
            resource_name is not None
            and pretask.resource
            and resource_name not in pretask.resource
        ):
            continue
        collected: dict[str, MaaFWOption] = {}
        _collect_task_options(pretask.option or [], interface_model.option, collected)
        task_option_maps[build_pretask_task_name(pretask)] = collected

    return task_option_maps


def _build_common_option_names(
    interface_model: MaaFWInterface,
    *,
    controller_name: str | None = None,
    resource_name: str | None = None,
) -> list[str]:
    option_names: list[str] = []
    option_names.extend(interface_model.global_option or [])

    for resource in interface_model.resource:
        if resource_name is not None and resource.name != resource_name:
            continue
        option_names.extend(resource.option or [])

    for controller in interface_model.controller:
        if controller_name is not None and controller.name != controller_name:
            continue
        option_names.extend(controller.option or [])

    return option_names


def _collect_task_options(
    option_names: list[str],
    option_map: dict[str, MaaFWOption],
    target: dict[str, MaaFWOption],
) -> None:
    for option_name in option_names:
        if option_name in target:
            continue
        option = option_map.get(option_name)
        if option is None or option.type not in SUPPORTED_OPTION_TYPES:
            continue

        target[option_name] = option
        for case in option.cases or []:
            if case.option:
                _collect_task_options(case.option, option_map, target)


def _build_option_defaults(
    option_map: dict[str, MaaFWOption],
) -> tuple[dict[str, MaaFWTaskOptionValue], dict[str, str]]:
    defaults: dict[str, MaaFWTaskOptionValue] = {}
    value_types: dict[str, str] = {}

    for option_name, option in option_map.items():
        if option.type in {"select", "scan_select", "switch"}:
            default_value = option.default_case
            if not isinstance(default_value, str):
                default_value = option.cases[0].name if option.cases else ""
            defaults[option_name] = default_value
            value_types[option_name] = "string"
            continue

        if option.type == "checkbox":
            selected_values = (
                set(option.default_case)
                if isinstance(option.default_case, list)
                else set()
            )
            defaults[option_name] = [
                case.name for case in option.cases or [] if case.name in selected_values
            ]
            value_types[option_name] = "string_list"
            continue

        if option.type == "input":
            # input 的 default 是**给用户看的预填提示**，不是「没配时该执行的值」。
            # M9A 的 自定义兑换码 default 就是字面量「占位」，该选项又直接挂在
            # 任务上永远生效；把它当值注入会真提交一个无效兑换码，任务卡死。
            # MFAAvalonia 自己的实例配置里，未填写的输入存的也是空串。
            # default 改由前端作为 placeholder 展示，不进入执行值。
            input_defaults: dict[str, str] = {}
            for input_case in option.inputs or []:
                input_defaults[input_case.name] = ""
            defaults[option_name] = input_defaults
            value_types[option_name] = "object"
            continue

        if option.type == "hotkey":
            hotkey_defaults: dict[str, str] = {}
            for hotkey_case in option.hotkeys or []:
                hotkey_defaults[hotkey_case.name] = hotkey_case.default or ""
            defaults[option_name] = hotkey_defaults
            value_types[option_name] = "object"

    return defaults, value_types


def _build_option_case_name_sets(
    option_map: dict[str, MaaFWOption],
) -> dict[str, set[str]]:
    case_name_sets: dict[str, set[str]] = {}

    for option_name, option in option_map.items():
        if option.type in {"select", "scan_select", "switch", "checkbox"}:
            case_name_sets[option_name] = {case.name for case in option.cases or []}

    return case_name_sets


def _normalize_options_for_task(
    raw_options_for_task: Any,
    option_map: dict[str, MaaFWOption],
    defaults: dict[str, MaaFWTaskOptionValue],
    value_types: dict[str, str],
    case_name_sets: dict[str, set[str]],
) -> dict[str, MaaFWTaskOptionValue]:
    normalized_options = {
        key: _clone_option_value(value) for key, value in defaults.items()
    }
    if not isinstance(raw_options_for_task, dict):
        return normalized_options

    for option_key, option_value in raw_options_for_task.items():
        if not isinstance(option_key, str) or option_key not in option_map:
            continue

        expected_type = value_types.get(option_key)
        if expected_type is None:
            normalized_value = _normalize_option_value_for_storage(option_value)
            if normalized_value is not None:
                normalized_options[option_key] = normalized_value
            continue

        if expected_type == "string" and isinstance(option_value, str):
            allowed_cases = case_name_sets.get(option_key)
            if allowed_cases is not None and option_value not in allowed_cases:
                continue
            normalized_options[option_key] = option_value
            continue

        if expected_type == "string_list" and isinstance(option_value, list):
            normalized_items = [item for item in option_value if isinstance(item, str)]
            allowed_cases = case_name_sets.get(option_key)
            if allowed_cases is not None:
                normalized_items = [
                    item for item in normalized_items if item in allowed_cases
                ]
            normalized_options[option_key] = normalized_items
            continue

        if expected_type == "object" and isinstance(option_value, dict):
            option = option_map.get(option_key)
            if option is None or option.type not in {"input", "hotkey"}:
                continue
            existing_value = normalized_options.get(option_key)
            normalized_fields = (
                {
                    key: item
                    for key, item in existing_value.items()
                    if isinstance(key, str) and isinstance(item, str)
                }
                if isinstance(existing_value, dict)
                else {}
            )
            field_names = (
                [input_case.name for input_case in option.inputs or []]
                if option.type == "input"
                else [hotkey_case.name for hotkey_case in option.hotkeys or []]
            )
            for field_name in field_names:
                field_value = option_value.get(field_name)
                if isinstance(field_value, str):
                    normalized_fields[field_name] = field_value
            normalized_options[option_key] = normalized_fields

    return normalized_options


def _clone_option_value(value: MaaFWTaskOptionValue) -> MaaFWTaskOptionValue:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    if isinstance(value, dict):
        return {
            key: item
            for key, item in value.items()
            if isinstance(key, str) and isinstance(item, str)
        }
    return value


def _apply_preset_option_value(
    option_name: str,
    value: MaaFWPresetOptionValue,
    option_map: dict[str, MaaFWOption],
    target_options: dict[str, MaaFWTaskOptionValue],
) -> None:
    option = option_map.get(option_name)
    if option is None:
        return

    if option.type in {"input", "hotkey"}:
        if not isinstance(value, dict):
            return
        existing_value = target_options.get(option_name)
        normalized_fields: dict[str, str] = (
            {
                key: item
                for key, item in existing_value.items()
                if isinstance(key, str) and isinstance(item, str)
            }
            if isinstance(existing_value, dict)
            else {}
        )
        field_names = (
            [input_case.name for input_case in option.inputs or []]
            if option.type == "input"
            else [hotkey_case.name for hotkey_case in option.hotkeys or []]
        )
        for field_name in field_names:
            field_value = value.get(field_name)
            if isinstance(field_value, str):
                normalized_fields[field_name] = field_value
        target_options[option_name] = normalized_fields
        return

    if option.type == "checkbox":
        if isinstance(value, list):
            target_options[option_name] = [
                item for item in value if isinstance(item, str)
            ]
        return

    if isinstance(value, str):
        target_options[option_name] = value
        return

    normalized_value = _normalize_option_value_for_storage(value)
    if normalized_value is not None:
        target_options[option_name] = normalized_value
