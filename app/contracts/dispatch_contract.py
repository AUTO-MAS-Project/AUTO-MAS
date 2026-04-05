from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common_contract import ApiModel, OutBase


class DispatchIn(ApiModel):
    taskId: str = Field(
        ...,
        description="目标任务ID, 设置类任务可选对应脚本ID或用户ID, 代理类任务可选对应队列ID或脚本ID",
    )


class TaskCreateIn(DispatchIn):
    mode: Literal["AutoProxy", "ManualReview", "ScriptConfig"] = Field(
        ..., description="任务模式"
    )


class TaskCreateOut(OutBase):
    taskId: str = Field(..., description="新创建的任务ID")


class PowerIn(ApiModel):
    signal: Literal[
        "NoAction",
        "Shutdown",
        "ShutdownForce",
        "Reboot",
        "Hibernate",
        "Sleep",
        "KillSelf",
    ] = Field(..., description="电源操作信号")


class PowerOut(OutBase):
    signal: Literal[
        "NoAction",
        "Shutdown",
        "ShutdownForce",
        "Reboot",
        "Hibernate",
        "Sleep",
        "KillSelf",
    ] = Field(..., description="电源操作信号")


__all__ = ["DispatchIn", "TaskCreateIn", "TaskCreateOut", "PowerIn", "PowerOut"]
