from __future__ import annotations

from typing import Any, Literal

from app.task.MaaFW.tools.core.automas_maafw_agent_env.models import MaaFWAgentCommandPlan
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
    nativePluginPaths: list[MaaFWResolvedPath] = Field(default_factory=list)
    agents: list[MaaFWAgentCommandPlan] = Field(default_factory=list)
    pretasks: list[MaaFWPretaskRunPlan] = Field(default_factory=list)
    piEnv: dict[str, str] = Field(default_factory=dict)
    tasks: list[MaaFWTaskRunPlan] = Field(default_factory=list)
    skippedTasks: list[MaaFWSkippedTaskPlan] = Field(default_factory=list)
    # ``None`` keeps the ordinary/legacy project-manifest behaviour. Managed
    # execution supplies an authoritative boolean from Project Store so a
    # writable checkout cannot opt itself into the shared worker runtime.
    managedSharedAgentDependenciesComplete: bool | None = None
    # Store indexes whose bundled interpreter was intentionally stripped and
    # projected to the managed ``python`` route. Only these external plans may
    # be rebound to the exact shared runtime interpreter.
    managedPythonAgentIndexes: list[int] | None = None


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
    # 等待 adb 认出设备的秒数。冷启动的模拟器在 open() 返回后往往还要一段时间
    # adbd 才起来；宿主按该模拟器的 Info.MaxWaitTime 下发，缺省时用 runner 常量。
    adbReadyTimeout: int | None = None


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
    # 并入自 mfwa：宿主进程身份，worker 据此看门狗自杀，避免宿主崩溃后留下孤儿
    # 进程继续占用设备。createTime 与 pid 配对使用，防 pid 复用误判。
    ownerPid: int | None = None
    ownerCreateTime: float | None = None
