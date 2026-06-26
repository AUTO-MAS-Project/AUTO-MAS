#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.


from pathlib import Path
from typing import Any

from app.models.schema import (
    MaaFWAdbEmulatorExtraCapabilityInfo,
    MaaFWControlCapabilitiesInfo,
    MaaFWControllerInfo,
    MaaFWGroupInfo,
    MaaFWInterfacePreviewData,
    MaaFWOptionCaseInfo,
    MaaFWOptionInfo,
    MaaFWOptionInputInfo,
    MaaFWPresetInfo,
    MaaFWProjectInfo,
    MaaFWResourceInfo,
    MaaFWTaskInfo,
    MaaFWTaskSnapshot,
)

from .interface_models import MaaFWInterface
from .control_capabilities import build_adb_emulator_extra_capabilities
from .run_plan import _load_i18n_mapping, _resolve_i18n_value
from .task_config import _build_task_option_maps, build_interface_preset_snapshot


def build_maafw_interface_preview_data(
    root_path: Path,
    interface: MaaFWInterface,
) -> MaaFWInterfacePreviewData:
    """Build MaaFW ProjectInterface preview data for API and tests."""
    i18n_mapping = _load_i18n_mapping(root_path, interface)
    task_order = [task.name for task in interface.task]
    task_option_maps = _build_task_option_maps(interface)

    def tr(value: Any) -> Any:
        return _resolve_i18n_value(value, i18n_mapping)

    def tr_text(value: str | None) -> str | None:
        translated = tr(value)
        return translated if isinstance(translated, str) else value

    def tr_description(value: str | None) -> str | None:
        return resolve_maafw_description(root_path, tr_text(value))

    agent_count = 0
    if isinstance(interface.agent, list):
        agent_count = len(interface.agent)
    elif interface.agent is not None:
        agent_count = 1

    presets: list[MaaFWPresetInfo] = []
    for preset in interface.preset:
        snapshot = build_interface_preset_snapshot(
            interface,
            preset,
            task_order=task_order,
            task_option_maps=task_option_maps,
            include_default_options=False,
        )
        checked_count = sum(
            1 for checked in snapshot.taskChecked.values() if checked
        )
        presets.append(
            MaaFWPresetInfo(
                name=preset.name,
                label=tr_text(preset.label),
                description=tr_description(preset.description),
                taskCount=len(preset.task or []),
                checkedCount=checked_count,
                snapshot=MaaFWTaskSnapshot(**snapshot.model_dump()),
            )
        )

    return MaaFWInterfacePreviewData(
        path=str(root_path),
        project=MaaFWProjectInfo(
            name=interface.name,
            label=tr_text(interface.label),
            title=tr_text(interface.title),
            version=interface.version,
            github=interface.github,
            mirrorchyanRid=interface.mirrorchyan_rid,
            mirrorchyanMultiplatform=interface.mirrorchyan_multiplatform,
            description=tr_description(interface.description),
            icon=interface.icon,
        ),
        globalOption=interface.global_option or [],
        controlCapabilities=MaaFWControlCapabilitiesInfo(
            emulatorExtras={
                emulator_type: MaaFWAdbEmulatorExtraCapabilityInfo(
                    screencap=capability.screencap,
                    input=capability.input,
                )
                for emulator_type, capability in build_adb_emulator_extra_capabilities(
                    root_path
                ).items()
            },
        ),
        controllers=[
            MaaFWControllerInfo(
                name=controller.name,
                label=tr_text(controller.label),
                type=controller.type,
                description=tr_description(controller.description),
                icon=controller.icon,
                option=controller.option or [],
                permissionRequired=bool(controller.permission_required),
            )
            for controller in interface.controller
        ],
        resources=[
            MaaFWResourceInfo(
                name=resource.name,
                label=tr_text(resource.label),
                description=tr_description(resource.description),
                icon=resource.icon,
                path=resource.path,
                controller=resource.controller or [],
                option=resource.option or [],
            )
            for resource in interface.resource
        ],
        groups=[
            MaaFWGroupInfo(
                name=group.name,
                label=tr_text(group.label),
                description=tr_description(group.description),
                icon=group.icon,
                defaultExpand=bool(group.default_expand),
            )
            for group in interface.group or []
        ],
        tasks=[
            MaaFWTaskInfo(
                name=task.name,
                label=tr_text(task.label),
                entry=task.entry,
                description=tr_description(task.description),
                icon=task.icon,
                group=task.group or [],
                controller=task.controller or [],
                resource=task.resource or [],
                option=task.option or [],
                defaultCheck=bool(task.default_check),
            )
            for task in interface.task
        ],
        options=[
            MaaFWOptionInfo(
                name=option_name,
                type=option.type,
                label=tr_text(option.label),
                description=tr_description(option.description),
                icon=option.icon,
                controller=option.controller or [],
                resource=option.resource or [],
                cases=[
                    MaaFWOptionCaseInfo(
                        name=case.name,
                        label=tr_text(case.label),
                        description=tr_description(case.description),
                        icon=case.icon,
                        option=case.option or [],
                    )
                    for case in option.cases or []
                ],
                inputs=[
                    MaaFWOptionInputInfo(
                        name=input_item.name,
                        label=tr_text(input_item.label),
                        description=tr_description(input_item.description),
                        icon=input_item.icon,
                        default=input_item.default,
                        pipelineType=input_item.pipeline_type,
                        verify=input_item.verify,
                        verifyError=input_item.verify_error,
                        patternMsg=input_item.pattern_msg,
                    )
                    for input_item in option.inputs or []
                ],
                defaultCase=option.default_case,
            )
            for option_name, option in interface.option.items()
        ],
        presets=presets,
        importCount=len(interface.import_ or []),
        agentCount=agent_count,
    )


def resolve_maafw_description(root_path: Path, description: str | None) -> str | None:
    if not isinstance(description, str):
        return description

    raw_description = description.strip()
    if not raw_description or "\n" in raw_description or raw_description.startswith("<"):
        return description
    if raw_description.startswith(("http://", "https://")):
        return description

    description_path = Path(raw_description)
    if description_path.is_absolute() or ".." in description_path.parts:
        return description

    try:
        root = root_path.resolve()
        resolved_path = (root / description_path).resolve()
        resolved_path.relative_to(root)
    except Exception:
        return description

    if not resolved_path.is_file():
        return description
    if resolved_path.suffix.lower() not in {".md", ".markdown", ".txt", ".html", ".htm"}:
        return description

    try:
        if resolved_path.stat().st_size > 512 * 1024:
            return description
        return resolved_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return resolved_path.read_text(encoding="utf-8-sig")
        except Exception:
            return description
    except Exception:
        return description
