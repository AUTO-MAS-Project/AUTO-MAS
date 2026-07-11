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


from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


MaaFWDocumentContent = str | list[str]
MaaFWPipelineOverride = dict[str, Any]
MaaFWPresetOptionValue = str | list[str] | dict[str, str]
MaaFWTaskOptionValue = str | list[str] | dict[str, str]
MaaFWTaskOptionsByTask = dict[str, dict[str, MaaFWTaskOptionValue]]

PRETASK_TASK_PREFIX = "__MXU_PRETASK__"
PRETASK_TASK_ENTRY = "MXU_PRETASK"
SUPPORTED_OPTION_TYPES = frozenset(
    {"select", "checkbox", "input", "switch", "scan_select"}
)


class MaaFWAdbController(BaseModel):
    model_config = ConfigDict(extra="allow")


class MaaFWWin32Controller(BaseModel):
    model_config = ConfigDict(extra="allow")

    class_regex: str | None = None
    window_regex: str | None = None
    mouse: str | None = None
    keyboard: str | None = None
    screencap: str | None = None


class MaaFWMacOSController(BaseModel):
    model_config = ConfigDict(extra="allow")

    title_regex: str | None = None
    input: str | None = None
    screencap: str | None = None


class MaaFWPlayCoverController(BaseModel):
    model_config = ConfigDict(extra="allow")

    uuid: str | None = None


class MaaFWGamepadController(BaseModel):
    model_config = ConfigDict(extra="allow")

    class_regex: str | None = None
    window_regex: str | None = None
    gamepad_type: str | None = None
    screencap: str | None = None


class MaaFWWlRootsController(BaseModel):
    model_config = ConfigDict(extra="allow")


class MaaFWController(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    label: str | None = None
    description: str | None = None
    icon: str | None = None
    type: str
    display_short_side: int | None = 720
    display_long_side: int | None = None
    display_raw: bool | None = False
    permission_required: bool | None = False
    attach_resource_path: list[str] | None = None
    option: list[str] | None = None
    adb: MaaFWAdbController | None = None
    win32: MaaFWWin32Controller | None = None
    macos: MaaFWMacOSController | None = None
    playcover: MaaFWPlayCoverController | None = None
    gamepad: MaaFWGamepadController | None = None
    wlroots: MaaFWWlRootsController | None = None


class MaaFWResource(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    label: str | None = None
    description: str | None = None
    icon: str | None = None
    path: list[str] = Field(default_factory=list)
    controller: list[str] | None = None
    option: list[str] | None = None
    hash: str | None = None


class MaaFWAgent(BaseModel):
    model_config = ConfigDict(extra="allow")

    child_exec: str
    child_args: list[str] | None = None
    identifier: str | None = None
    embedded: bool | None = None


class MaaFWPretask(BaseModel):
    model_config = ConfigDict(extra="allow")

    exec: str
    args: list[str] | None = None
    name: str | None = None
    label: str | None = None
    description: str | None = None
    icon: str | None = None
    option: list[str] | None = None
    resource: list[str] | None = None
    controller: list[str] | None = None


class MaaFWTask(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    label: str | None = None
    entry: str
    default_check: bool | None = False
    description: str | None = None
    doc: MaaFWDocumentContent | None = None
    desc: MaaFWDocumentContent | None = None
    icon: str | None = None
    group: list[str] | None = None
    resource: list[str] | None = None
    controller: list[str] | None = None
    pipeline_override: MaaFWPipelineOverride | None = None
    option: list[str] | None = None


class MaaFWGroup(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    label: str | None = None
    description: str | None = None
    icon: str | None = None
    default_expand: bool | None = True


class MaaFWOptionCase(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    label: str | None = None
    description: str | None = None
    icon: str | None = None
    option: list[str] | None = None
    pipeline_override: MaaFWPipelineOverride | None = None


class MaaFWInputCase(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    label: str | None = None
    description: str | None = None
    icon: str | None = None
    default: str | None = None
    pipeline_type: str | None = None
    verify: str | None = None
    verify_error: str | None = None
    pattern_msg: str | None = None

    @model_validator(mode="after")
    def fill_verify_error_alias(self):
        if self.pattern_msg is None and self.verify_error:
            self.pattern_msg = self.verify_error
        if self.verify_error is None and self.pattern_msg:
            self.verify_error = self.pattern_msg
        return self


class MaaFWOption(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str = "select"
    label: str | None = None
    description: str | None = None
    icon: str | None = None
    controller: list[str] | None = None
    resource: list[str] | None = None
    cases: list[MaaFWOptionCase] | None = None
    inputs: list[MaaFWInputCase] | None = None
    scan_dir: str | None = None
    scan_filter: str | None = None
    pipeline_override: MaaFWPipelineOverride | None = None
    default_case: str | list[str] | None = None


class MaaFWPresetTask(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    enabled: bool | None = True
    option: dict[str, MaaFWPresetOptionValue] | None = None


class MaaFWPreset(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    label: str | None = None
    description: str | None = None
    icon: str | None = None
    task: list[MaaFWPresetTask] | None = None


class MaaFWInterface(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
        serialize_by_alias=True,
    )

    interface_version: Literal[2]
    languages: dict[str, str] | None = None
    name: str
    label: str | None = None
    title: str | None = None
    icon: str | None = None
    mirrorchyan_rid: str | None = None
    mirrorchyan_multiplatform: bool | None = None
    github: str | None = None
    version: str | None = None
    contact: str | None = None
    license: str | None = None
    welcome: str | None = None
    description: str | None = None
    controller: list[MaaFWController] = Field(default_factory=list)
    resource: list[MaaFWResource] = Field(default_factory=list)
    group: list[MaaFWGroup] | None = None
    pretask: MaaFWPretask | list[MaaFWPretask] | None = None
    agent: MaaFWAgent | list[MaaFWAgent] | None = None
    task: list[MaaFWTask] = Field(default_factory=list)
    option: dict[str, MaaFWOption] = Field(default_factory=dict)
    global_option: list[str] | None = None
    import_: list[str] | None = Field(default=None, alias="import")
    preset: list[MaaFWPreset] = Field(default_factory=list)

    @model_validator(mode="after")
    def fill_display_defaults(self):
        if self.label is None:
            self.label = self.name
        if self.title is None and self.label and self.version:
            self.title = f"{self.label} {self.version}"
        return self


def iter_pretasks(interface: MaaFWInterface) -> list[MaaFWPretask]:
    """Return ProjectInterface pretasks as a stable list."""

    raw_pretasks = interface.pretask
    if isinstance(raw_pretasks, list):
        return raw_pretasks
    return [raw_pretasks] if raw_pretasks is not None else []


def build_pretask_task_name(pretask: MaaFWPretask) -> str:
    """Build the pseudo-task name used by MXU-compatible clients."""

    return f"{PRETASK_TASK_PREFIX}{pretask.name or pretask.exec}"


def is_pretask_task_name(task_name: str) -> bool:
    """Return whether a persisted task name identifies a pretask pseudo-task."""

    return task_name.startswith(PRETASK_TASK_PREFIX)


def find_pretask_by_task_name(
    interface: MaaFWInterface,
    task_name: str,
) -> MaaFWPretask | None:
    """Resolve a persisted pseudo-task name to its ProjectInterface pretask."""

    return next(
        (
            pretask
            for pretask in iter_pretasks(interface)
            if build_pretask_task_name(pretask) == task_name
        ),
        None,
    )
