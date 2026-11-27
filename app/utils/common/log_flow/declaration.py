"""插件声明的管线配置，不携带运行对象、监控器或模块搜索路径。"""

from pydantic import BaseModel, Field

from .contracts import (
    FunctionRef,
    LineRule,
    ProcessorFactorySpec,
    WindowRule,
    WorkerFactorySpec,
)
from .observation import ReportOrder


class SimpleFlowDeclaration(BaseModel, frozen=True, extra="forbid"):
    """匹配、提取和归并专项声明的节点。"""

    rules: tuple[LineRule, ...] = ()
    windows: tuple[WindowRule, ...] = Field(default=(), max_length=16)
    preprocess: FunctionRef | None = None
    postprocess: FunctionRef | WorkerFactorySpec | None = None
    report_order: ReportOrder = "first_seen"
    functions: tuple[FunctionRef, ...] = ()
    processor: ProcessorFactorySpec | None = None


class GeneralFlowDeclaration(BaseModel, frozen=True, extra="forbid"):
    """通用脚本 WebUI 的匹配规则和行预处理快照。"""

    patterns: str
    hooks: str = ""
