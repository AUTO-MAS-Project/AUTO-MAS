from __future__ import annotations

import copy
from typing import Any, cast

import json5
from app.task.MaaFW.tools.core.automas_maafw_interface.models import (
    SUPPORTED_OPTION_TYPES,
    MaaFWController,
    MaaFWInterface,
    MaaFWOption,
    MaaFWPipelineOverride,
    MaaFWResource,
    MaaFWTask,
    MaaFWTaskOptionValue,
)

from .hotkey import MaaFWHotkeyError, resolve_hotkey


def deep_merge_pipeline_override(
    base: MaaFWPipelineOverride | None,
    override: MaaFWPipelineOverride | None,
) -> MaaFWPipelineOverride:
    merged: MaaFWPipelineOverride = copy.deepcopy(base) if base else {}
    if not override:
        return merged

    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = deep_merge_pipeline_override(existing, value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


class MaaFWPipelineOverrideBuilder:
    def __init__(
        self,
        interface_model: MaaFWInterface,
        *,
        controller_names: set[str],
        resource_name: str | None,
    ) -> None:
        self.interface_model = interface_model
        self.controller_names = controller_names
        self.resource_name = resource_name

    def build_task_pipeline_override(
        self,
        task_name: str,
        options: dict[str, MaaFWTaskOptionValue],
    ) -> MaaFWPipelineOverride:
        task_definition = self._get_task_definition(task_name)
        if task_definition is None:
            return {}

        resource_definition = self._get_resource_definition()
        controller_option_names: list[str] = []
        for controller in self._get_active_controller_definitions():
            if controller.option:
                controller_option_names.extend(controller.option)

        merged = copy.deepcopy(task_definition.pipeline_override) or {}
        option_groups = [
            self.interface_model.global_option or [],
            resource_definition.option if resource_definition and resource_definition.option else [],
            controller_option_names,
            task_definition.option or [],
        ]
        for option_names in option_groups:
            merged = deep_merge_pipeline_override(
                merged,
                self._build_option_group_override(option_names, options),
            )
        return merged

    def _get_task_definition(self, task_name: str) -> MaaFWTask | None:
        return next((task for task in self.interface_model.task if task.name == task_name), None)

    def _get_resource_definition(self) -> MaaFWResource | None:
        if self.resource_name is None:
            return None
        return next(
            (resource for resource in self.interface_model.resource if resource.name == self.resource_name),
            None,
        )

    def _get_active_controller_definitions(self) -> list[MaaFWController]:
        return [
            controller
            for controller in self.interface_model.controller
            if controller.name in self.controller_names
        ]

    def _get_active_controller_type(self) -> str:
        controller_types = {
            controller.type for controller in self._get_active_controller_definitions()
        }
        if len(controller_types) != 1:
            raise MaaFWHotkeyError(
                "hotkey 键码映射需要且只能选择一个 controller"
            )
        return next(iter(controller_types))

    def _is_option_active_for_context(self, option: MaaFWOption) -> bool:
        if option.controller and not self.controller_names.intersection(option.controller):
            return False
        if option.resource and (self.resource_name is None or self.resource_name not in option.resource):
            return False
        return True

    def _normalize_choice_value(
        self,
        option_name: str,
        option: MaaFWOption,
        options: dict[str, MaaFWTaskOptionValue],
    ) -> str:
        case_names = [case.name for case in option.cases or []]
        default_value = option.default_case if isinstance(option.default_case, str) else ""
        if default_value not in case_names:
            default_value = case_names[0] if case_names else ""

        raw_value = options.get(option_name)
        if isinstance(raw_value, str) and raw_value in case_names:
            return raw_value
        return default_value

    def _normalize_checkbox_values(
        self,
        option_name: str,
        option: MaaFWOption,
        options: dict[str, MaaFWTaskOptionValue],
    ) -> list[str]:
        case_order = [case.name for case in option.cases or []]
        default_values = option.default_case if isinstance(option.default_case, list) else []
        raw_value = options.get(option_name)

        if raw_value is None:
            selected_values = [value for value in default_values if isinstance(value, str)]
        elif isinstance(raw_value, list):
            selected_values = [value for value in raw_value if isinstance(value, str)]
        elif isinstance(raw_value, str):
            try:
                parsed_value = json5.loads(raw_value)
            except Exception:
                parsed_value = [raw_value] if raw_value in case_order else []
            selected_values = (
                [value for value in parsed_value if isinstance(value, str)]
                if isinstance(parsed_value, list)
                else []
            )
        else:
            selected_values = []

        selected_set = set(selected_values)
        return [case_name for case_name in case_order if case_name in selected_set]

    def _coerce_input_value(self, raw_value: str, pipeline_type: str | None) -> tuple[object, str]:
        normalized_type = (pipeline_type or "string").lower()
        if normalized_type in {"bool", "boolean"}:
            typed_value = raw_value.lower() in {"true", "1", "yes", "y", "on"}
            return typed_value, "true" if typed_value else "false"
        if normalized_type in {"int", "integer"}:
            typed_value = int(raw_value)
            return typed_value, str(typed_value)
        if normalized_type in {"float", "double", "number"}:
            typed_value = float(raw_value)
            return typed_value, str(typed_value)
        return raw_value, raw_value

    def _substitute_placeholders(
        self,
        value: Any,
        typed_replacements: dict[str, object],
        text_replacements: dict[str, str],
    ) -> Any:
        if isinstance(value, dict):
            return {
                key: self._substitute_placeholders(nested_value, typed_replacements, text_replacements)
                for key, nested_value in value.items()
            }
        if isinstance(value, list):
            return [
                self._substitute_placeholders(item, typed_replacements, text_replacements)
                for item in value
            ]
        if isinstance(value, str):
            if value in typed_replacements:
                return copy.deepcopy(typed_replacements[value])
            substituted = value
            for placeholder, replacement in text_replacements.items():
                substituted = substituted.replace(placeholder, replacement)
            return substituted
        return copy.deepcopy(value)

    def _assign_scan_select_attach_value(
        self,
        value: Any,
        option_name: str,
        selected_value: str,
    ) -> Any:
        if isinstance(value, dict):
            copied = {
                key: self._assign_scan_select_attach_value(nested_value, option_name, selected_value)
                for key, nested_value in value.items()
            }
            attach_value = copied.get("attach")
            if isinstance(attach_value, dict) and option_name in attach_value:
                updated_attach = copy.deepcopy(attach_value)
                updated_attach[option_name] = selected_value
                copied["attach"] = updated_attach
            return copied
        if isinstance(value, list):
            return [
                self._assign_scan_select_attach_value(item, option_name, selected_value)
                for item in value
            ]
        return copy.deepcopy(value)

    def _build_input_override(
        self,
        option_name: str,
        option: MaaFWOption,
        options: dict[str, MaaFWTaskOptionValue],
    ) -> MaaFWPipelineOverride:
        if not option.pipeline_override or not option.inputs:
            return {}

        typed_replacements: dict[str, object] = {}
        text_replacements: dict[str, str] = {}
        for input_item in option.inputs:
            raw_option_value = options.get(option_name)
            raw_text = input_item.default or ""
            if isinstance(raw_option_value, dict):
                field_value = raw_option_value.get(input_item.name)
                if isinstance(field_value, str):
                    raw_text = field_value
            elif isinstance(raw_option_value, str):
                raw_text = raw_option_value
            elif isinstance(raw_option_value, list):
                raw_text = raw_option_value[0] if raw_option_value else ""

            typed_value, text_value = self._coerce_input_value(raw_text, input_item.pipeline_type)
            placeholder = f"{{{input_item.name}}}"
            typed_replacements[placeholder] = typed_value
            text_replacements[placeholder] = text_value

        return cast(
            MaaFWPipelineOverride,
            self._substitute_placeholders(
                option.pipeline_override,
                typed_replacements,
                text_replacements,
            ),
        )

    def _build_hotkey_override(
        self,
        option_name: str,
        option: MaaFWOption,
        options: dict[str, MaaFWTaskOptionValue],
    ) -> MaaFWPipelineOverride:
        if not option.pipeline_override or not option.hotkeys:
            return {}

        template_strings = _collect_template_strings(option.pipeline_override)
        raw_option_value = options.get(option_name)
        typed_replacements: dict[str, object] = {}
        controller_type = self._get_active_controller_type()

        for hotkey_item in option.hotkeys:
            placeholders = {
                f"{{{hotkey_item.name}}}",
                f"{{{hotkey_item.name}}}.primary",
                f"{{{hotkey_item.name}}}.modifier1",
                f"{{{hotkey_item.name}}}.modifier2",
                f"{{{hotkey_item.name}.primary}}",
                f"{{{hotkey_item.name}.modifier1}}",
                f"{{{hotkey_item.name}.modifier2}}",
            }
            referenced_values = {
                value
                for value in template_strings
                if any(placeholder in value for placeholder in placeholders)
            }
            if not referenced_values:
                continue
            invalid_templates = referenced_values - placeholders
            if invalid_templates:
                raise MaaFWHotkeyError(
                    "hotkey 占位符必须作为完整值使用: "
                    + ", ".join(sorted(invalid_templates))
                )

            raw_text = hotkey_item.default or ""
            if isinstance(raw_option_value, dict):
                field_value = raw_option_value.get(hotkey_item.name)
                if isinstance(field_value, str):
                    raw_text = field_value
            if not raw_text.strip():
                raise MaaFWHotkeyError(
                    f"hotkey 字段 {option_name}.{hotkey_item.name} 未配置"
                )

            resolved = resolve_hotkey(raw_text, controller_type)
            values = resolved.placeholder_values(hotkey_item.name)
            missing_placeholders = referenced_values - set(values)
            if missing_placeholders:
                raise MaaFWHotkeyError(
                    f"快捷键 {raw_text} 不包含所需修饰键: "
                    + ", ".join(sorted(missing_placeholders))
                )
            typed_replacements.update(values)

        return cast(
            MaaFWPipelineOverride,
            self._substitute_placeholders(
                option.pipeline_override,
                typed_replacements,
                {},
            ),
        )

    def _build_scan_select_override(
        self,
        option_name: str,
        option: MaaFWOption,
        options: dict[str, MaaFWTaskOptionValue],
    ) -> MaaFWPipelineOverride:
        if not option.pipeline_override:
            return {}
        if option.cases is None:
            return copy.deepcopy(option.pipeline_override)
        selected_value = self._normalize_choice_value(option_name, option, options)
        return cast(
            MaaFWPipelineOverride,
            self._assign_scan_select_attach_value(option.pipeline_override, option_name, selected_value),
        )

    def _build_option_override(
        self,
        option_name: str,
        options: dict[str, MaaFWTaskOptionValue],
        lineage: set[str] | None = None,
    ) -> MaaFWPipelineOverride:
        option = self.interface_model.option.get(option_name)
        if (
            option is None
            or option.type not in SUPPORTED_OPTION_TYPES
            or not self._is_option_active_for_context(option)
        ):
            return {}

        lineage = lineage or set()
        if option_name in lineage:
            return {}
        next_lineage = {*lineage, option_name}

        merged: MaaFWPipelineOverride = {}
        if option.type == "input":
            return deep_merge_pipeline_override(
                merged,
                self._build_input_override(option_name, option, options),
            )
        if option.type == "hotkey":
            return deep_merge_pipeline_override(
                merged,
                self._build_hotkey_override(option_name, option, options),
            )

        if option.type == "scan_select":
            merged = deep_merge_pipeline_override(
                merged,
                self._build_scan_select_override(option_name, option, options),
            )
        elif option.pipeline_override:
            merged = deep_merge_pipeline_override(merged, option.pipeline_override)

        if option.type in {"select", "switch"} and option.cases:
            active_case_name = self._normalize_choice_value(option_name, option, options)
            active_case = next((case for case in option.cases if case.name == active_case_name), None)
            if active_case and active_case.pipeline_override:
                merged = deep_merge_pipeline_override(merged, active_case.pipeline_override)
            if active_case and active_case.option:
                merged = deep_merge_pipeline_override(
                    merged,
                    self._build_option_group_override(active_case.option, options, next_lineage),
                )
            return merged

        if option.type == "checkbox" and option.cases:
            selected_case_names = set(self._normalize_checkbox_values(option_name, option, options))
            for case in option.cases:
                if case.name not in selected_case_names:
                    continue
                if case.pipeline_override:
                    merged = deep_merge_pipeline_override(merged, case.pipeline_override)
                if case.option:
                    merged = deep_merge_pipeline_override(
                        merged,
                        self._build_option_group_override(case.option, options, next_lineage),
                    )
        return merged

    def _build_option_group_override(
        self,
        option_names: list[str],
        options: dict[str, MaaFWTaskOptionValue],
        lineage: set[str] | None = None,
    ) -> MaaFWPipelineOverride:
        merged: MaaFWPipelineOverride = {}
        for option_name in option_names:
            merged = deep_merge_pipeline_override(
                merged,
                self._build_option_override(option_name, options, lineage),
            )
        return merged


def _collect_template_strings(value: Any) -> set[str]:
    if isinstance(value, dict):
        collected: set[str] = set()
        for nested_value in value.values():
            collected.update(_collect_template_strings(nested_value))
        return collected
    if isinstance(value, list):
        collected = set()
        for item in value:
            collected.update(_collect_template_strings(item))
        return collected
    if isinstance(value, str):
        return {value}
    return set()
