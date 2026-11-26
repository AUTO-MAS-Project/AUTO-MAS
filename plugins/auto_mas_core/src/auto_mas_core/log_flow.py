"""LogFlow 声明、独立分析、主动上报和任务报告。"""

from app.task.log_flow.report import LogFlowTaskReport
from app.utils.common.expression import ExpressionFunction
from app.utils.common.log.flow_monitor import LogFlowMonitor as LogMonitor
from app.utils.common.log_flow.analysis import LogAnalysis, analyze_logs
from app.utils.common.log_flow.contracts import (
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
    WorkerPluginPackage,
)
from app.utils.common.log_flow.declaration import (
    GeneralFlowDeclaration,
    SimpleFlowDeclaration,
)
from app.utils.common.log_flow.extensions import Sink, Source
from app.utils.common.log_flow.observation import (
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
from app.utils.common.log_flow.processor import ProcessorOutput, TextProcessor
from app.utils.common.log_flow.push import PushReporter, SubmitResult
from app.utils.common.log_flow.report import ReportMode

__all__ = [
    "ExpressionFunction",
    "FileInput",
    "LogAnalysis",
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
    "WorkerPluginPackage",
    "analyze_logs",
]
