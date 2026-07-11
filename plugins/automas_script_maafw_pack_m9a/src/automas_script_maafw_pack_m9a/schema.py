"""M9A project-pack schema overrides for the shared MaaFW editor."""

from __future__ import annotations

import json
from dataclasses import replace

from app.plugins.fields import PluginFieldGroup
from automas_script_maafw.schema import SCRIPT_GROUPS, USER_GROUPS, build_source_config


schema = {
    "__no_plugin_config__": {
        "type": "boolean",
        "default": True,
        "hidden": True,
        "configurable": False,
        "title": "No plugin-level configuration",
    },
}


M9A_PERIOD_TASK_DEFAULTS = {
    "DailyOnceTasks": ["Psychube"],
    "WeeklyOnceTasks": [],
    "MonthlyOnceTasks": ["SleepDream"],
}


def _build_m9a_info_group(group: PluginFieldGroup) -> PluginFieldGroup:
    name_field = replace(group.fields[0], default="新M9A脚本")
    path_field = replace(
        group.fields[2],
        label="M9A 项目路径",
        placeholder="选择包含 interface.json 的 M9A 项目目录",
    )
    return replace(
        group,
        fields=(
            name_field,
            group.fields[1],
            path_field,
            *group.fields[3:],
        ),
    )


def _build_m9a_run_group(group: PluginFieldGroup) -> PluginFieldGroup:
    return replace(
        group,
        fields=tuple(
            replace(field, default=json.dumps(M9A_PERIOD_TASK_DEFAULTS[field.name]))
            if field.name in M9A_PERIOD_TASK_DEFAULTS
            else field
            for field in group.fields
        ),
    )


def _build_m9a_group(group: PluginFieldGroup) -> PluginFieldGroup:
    if group.key == "Info":
        return _build_m9a_info_group(group)
    if group.key == "Run":
        return _build_m9a_run_group(group)
    return group


M9A_SCRIPT_GROUPS: tuple[PluginFieldGroup, ...] = tuple(
    _build_m9a_group(group) for group in SCRIPT_GROUPS
)

# User config intentionally reuses the MaaFW surface and storage shape.
M9A_USER_GROUPS = USER_GROUPS

__all__ = ["M9A_SCRIPT_GROUPS", "M9A_USER_GROUPS", "build_source_config"]
