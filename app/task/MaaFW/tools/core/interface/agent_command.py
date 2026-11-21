"""agent 命令计划的数据模型（下发给 worker 的计划里 ``agents`` 一项的形状）。

模型只是普通数据，随运行计划的类型归解析这一侧；怎么算出来（解释器、隔离 venv 的目录）
要读 agent 环境的依赖清单、引用记录与 venv 目录，在 agent 环境
（``agent_env.planner.build_maafw_agent_command_plans``），借运行环境时算好填进计划。
"""

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
    # interface 的 agent.timeout（秒，MFAA 私有扩展）；只决定等 agent 连上的预算
    timeout: float | None = None
    embedded: bool = False
