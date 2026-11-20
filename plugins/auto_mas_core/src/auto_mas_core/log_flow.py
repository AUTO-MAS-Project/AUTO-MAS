"""LogFlow 声明、主动上报和任务报告；会话由 MAS 宿主绑定和签发。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.log_flow.contracts import (
    FileInput,
    FunctionRef,
    InputRecord,
    LinePreprocessor,
    LineRule,
    PostProcessor,
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
from app.core.log_flow.processor import ProcessorOutput, TextProcessor
from app.core.log_flow.push import PushReporter, SubmitResult
from app.core.log_flow.report import LogFlowTaskReport, ReportMode
from app.core.log_flow.simple import FlowAccess
from app.models.log_flow import (
    Node,
    NodeAttribute,
    NodeAttributes,
    NodeDisplayStatus,
    ObservationCursor,
    ObservationPage,
    ObservationSnapshot,
    ReportEntry,
    ReportOrder,
)
from app.utils.common.expression import ExpressionFunction
from app.utils.common.log.flow_monitor import LogFlowMonitor as LogMonitor

if TYPE_CHECKING:
    from collections.abc import Mapping
    from contextlib import AbstractAsyncContextManager

    from pydantic import JsonValue

    from app.models.task import TaskScriptItem, TaskUserItem
    from app.plugin.base import BasePlugin


def open_log_flow(
    plugin: BasePlugin,
    name: str,
    *,
    run: TaskScriptItem | TaskUserItem,
    monitor: LogMonitor | None = None,
    file_input: FileInput | None = None,
    mode: ReportMode | None = None,
    task_report: LogFlowTaskReport | None = None,
    general_rules: GeneralFlowDeclaration | None = None,
    postprocess_options: Mapping[str, JsonValue] | None = None,
) -> AbstractAsyncContextManager[FlowAccess]:
    """为当前运行打开具名声明，返回实时节点与已启用的上报能力。"""
    from app.core import Plugin

    return Plugin.open_log_flow(
        plugin,
        name,
        run=run,
        monitor=monitor,
        file_input=file_input,
        mode=mode,
        task_report=task_report,
        general_rules=general_rules,
        postprocess_options=postprocess_options,
    )


__all__ = [
    "ExpressionFunction",
    "FileInput",
    "FlowAccess",
    "FunctionRef",
    "GeneralFlowDeclaration",
    "InputRecord",
    "LinePreprocessor",
    "LineRule",
    "LogFlowTaskReport",
    "LogMonitor",
    "Node",
    "NodeAttribute",
    "NodeAttributes",
    "NodeDisplayStatus",
    "ObservationCursor",
    "ObservationPage",
    "ObservationSnapshot",
    "PluginFlowDeclaration",
    "PostProcessor",
    "ProcessorOutput",
    "PushReporter",
    "ReportMode",
    "ReportOrder",
    "ReportedRecord",
    "ReportEntry",
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
