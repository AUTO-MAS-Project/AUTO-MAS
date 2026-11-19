"""LogFlow 主动上报能力；会话由 MAS 宿主绑定和签发。"""

from app.core.log_flow.contracts import (
    FileInput,
    FunctionRef,
    LineRule,
    WindowRule,
    WorkerFactorySpec,
)
from app.core.log_flow.declaration import PluginFlowDeclaration
from app.core.log_flow.push import PushReporter, SubmitResult
from app.core.log_flow.simple import SimpleFlowDeclaration

__all__ = [
    "FileInput",
    "FunctionRef",
    "LineRule",
    "PluginFlowDeclaration",
    "PushReporter",
    "SimpleFlowDeclaration",
    "SubmitResult",
    "WindowRule",
    "WorkerFactorySpec",
]
