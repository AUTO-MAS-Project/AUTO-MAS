from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


MaaFWAgentRuntimeKind = Literal[
    "embedded",
    "project_python",
    "project_binary",
    "isolated_venv",
    "external",
]


class MaaFWAgentCommandPlan(BaseModel):
    childExec: str
    executable: str
    executableExists: bool | None = None
    fallbackReason: str | None = None
    runtimeKind: MaaFWAgentRuntimeKind | str | None = None
    isolatedVenvPath: str | None = None
    childArgs: list[str] = Field(default_factory=list)
    command: list[str] = Field(default_factory=list)
    cwd: str
    identifier: str | None = None
    embedded: bool = False


class MaaFWAgentEnvPrepareResult(BaseModel):
    projectPath: str
    plans: list[MaaFWAgentCommandPlan] = Field(default_factory=list)
    preparedVenvs: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    messages: list[str] = Field(default_factory=list)
