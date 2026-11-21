from __future__ import annotations

from pydantic import BaseModel, Field

from ..interface.agent_command import MaaFWAgentCommandPlan


class MaaFWAgentEnvPrepareResult(BaseModel):
    projectPath: str
    plans: list[MaaFWAgentCommandPlan] = Field(default_factory=list)
    preparedVenvs: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    messages: list[str] = Field(default_factory=list)
    # 宽松模式下健康检查没通过、照常放行的原因（每个 agent 一条，原文）。非空就是「报错照跑」：
    # 调用方不能把这次结果当成「运行环境已就绪」写缓存，worker 在 agent 退出时把它带进报错。
    healthWarnings: list[str] = Field(default_factory=list)
