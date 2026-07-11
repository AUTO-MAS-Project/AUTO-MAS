from __future__ import annotations

from typing import Any, Literal

from automas_maafw_agent_env.models import MaaFWAgentCommandPlan
from pydantic import BaseModel, ConfigDict, Field


MaaFWControllerType = Literal["Adb", "Win32"]


class MaaFWResolvedPath(BaseModel):
    raw: str
    resolved: str
    exists: bool
    isFile: bool = False
    isDir: bool = False


class MaaFWResourceBundlePlan(BaseModel):
    name: str
    label: str | None = None
    paths: list[MaaFWResolvedPath] = Field(default_factory=list)
    attachedPaths: list[MaaFWResolvedPath] = Field(default_factory=list)


class MaaFWTaskRunPlan(BaseModel):
    name: str
    label: str | None = None
    entry: str
    options: dict[str, Any] = Field(default_factory=dict)
    pipelineOverride: dict[str, Any] = Field(default_factory=dict)
    logOptions: dict[str, Any] = Field(default_factory=dict)
    overrideNodes: list[str] = Field(default_factory=list)


class MaaFWSkippedTaskPlan(BaseModel):
    name: str
    label: str | None = None
    entry: str | None = None
    reason: str


class MaaFWPretaskRunPlan(BaseModel):
    name: str
    label: str | None = None
    executable: str
    args: list[str] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)


class MaaFWRunPlan(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    path: str
    projectName: str
    projectLabel: str | None = None
    controllerName: str
    controllerType: str
    resourceName: str
    resource: MaaFWResourceBundlePlan
    agents: list[MaaFWAgentCommandPlan] = Field(default_factory=list)
    pretasks: list[MaaFWPretaskRunPlan] = Field(default_factory=list)
    piEnv: dict[str, str] = Field(default_factory=dict)
    tasks: list[MaaFWTaskRunPlan] = Field(default_factory=list)
    skippedTasks: list[MaaFWSkippedTaskPlan] = Field(default_factory=list)


class MaaFWDeviceConfig(BaseModel):
    type: MaaFWControllerType
    adbPath: str | None = None
    address: str | None = None
    hWnd: int | None = None
    screencapMethods: int = 0
    inputMethods: int = 0
    screencapMethod: int = 0
    mouseMethod: int = 0
    keyboardMethod: int = 0
    config: dict[str, Any] = Field(default_factory=dict)


class MaaFWRunResult(BaseModel):
    success: bool
    projectName: str
    controllerName: str
    resourceName: str
    completedTasks: list[str] = Field(default_factory=list)
    failedTask: str | None = None
    errorMessage: str | None = None


class MaaFWRunnerJobPayload(BaseModel):
    plan: MaaFWRunPlan
    deviceConfig: MaaFWDeviceConfig
