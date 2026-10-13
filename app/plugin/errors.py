"""插件系统统一异常。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class PluginError(Exception):
    """插件系统基类错误。"""

    def __init__(self, message: str, *, payload: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.payload = payload or {}


class PluginBusyError(PluginError):
    """忙锁占用：禁止并发生命周期动作。"""


class PluginPrecheckError(PluginError):
    """预检失败：不进入过渡态、不执行预设。"""


class PluginNotFoundError(PluginError):
    """列表中不存在该插件。"""


class PluginStateError(PluginError):
    """当前状态或操作限制不允许该操作。"""


class PluginOperationError(PluginError):
    """预检已通过，执行阶段失败。"""


@dataclass
class VersionConflict:
    plugin_name: str
    distribution: str
    required: str
    proposed: str
    message: str


@dataclass
class DisableCheckFailure:
    plugin_name: str
    message: str


@dataclass
class PlanDiff:
    target_plugin: str
    target_distribution: str
    changes: list[tuple[str, str | None, str]]
    plugin_packages_touched: list[str]
    effect: str  # reload_one | reload_all_touched


@dataclass
class PrecheckOk:
    plan: PlanDiff


@dataclass
class PluginOpResult:
    """单个插件在一次生命周期/级联动作中的结果。"""

    plugin_name: str
    status: str  # succeeded | failed | skipped
    operation: str
    error: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class CascadeResult:
    operation: str
    results: list[PluginOpResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(r.status == "succeeded" for r in self.results)

    @property
    def partial(self) -> bool:
        statuses = {r.status for r in self.results}
        return "succeeded" in statuses and ("failed" in statuses or "skipped" in statuses)
