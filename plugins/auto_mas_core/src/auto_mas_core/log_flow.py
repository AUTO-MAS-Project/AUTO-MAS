"""LogFlow 声明、主动上报和任务报告；会话由 MAS 宿主绑定和签发。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.log_flow.contracts import (
    FileInput,
    FunctionRef,
    InputRecord,
    LineRule,
    ReportedRecord,
    TextRecord,
    WindowRule,
    WithdrawnRecord,
    WorkerFactorySpec,
)
from app.core.log_flow.declaration import (
    GeneralFlowDeclaration,
    PluginFlowDeclaration,
    SimpleFlowDeclaration,
)
from app.core.log_flow.extensions import Sink, Source
from app.core.log_flow.processor import TextProcessor
from app.core.log_flow.push import PushReporter, SubmitResult
from app.core.log_flow.report import LogFlowTaskReport, ReportMode
from app.core.log_flow.simple import FlowAccess
from app.models.log_flow import (
    Node,
    NodeDisplayStatus,
    ObservationCursor,
    ObservationPage,
)
from app.utils.common.expression import ExpressionFunction

if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager

    from app.models.task import TaskScriptItem, TaskUserItem
    from app.plugin.base import BasePlugin
    from app.utils.common.log.monitor import LogMonitor


def open_log_flow(
    plugin: BasePlugin,
    name: str,
    *,
    run: TaskScriptItem | TaskUserItem,
    monitor: LogMonitor | None = None,
    mode: ReportMode | None = None,
    task_report: LogFlowTaskReport | None = None,
    general_rules: GeneralFlowDeclaration | None = None,
) -> AbstractAsyncContextManager[FlowAccess]:
    """为当前运行打开具名声明，返回实时节点与已启用的上报能力。"""
    from app.core import Plugin

    return Plugin.open_log_flow(
        plugin,
        name,
        run=run,
        monitor=monitor,
        mode=mode,
        task_report=task_report,
        general_rules=general_rules,
    )


__all__ = [
    "ExpressionFunction",
    "FileInput",
    "FlowAccess",
    "FunctionRef",
    "GeneralFlowDeclaration",
    "InputRecord",
    "LineRule",
    "LogFlowTaskReport",
    "Node",
    "NodeDisplayStatus",
    "ObservationCursor",
    "ObservationPage",
    "PluginFlowDeclaration",
    "PushReporter",
    "ReportMode",
    "ReportedRecord",
    "SimpleFlowDeclaration",
    "Sink",
    "Source",
    "SubmitResult",
    "TextProcessor",
    "TextRecord",
    "WindowRule",
    "WithdrawnRecord",
    "WorkerFactorySpec",
    "open_log_flow",
]
