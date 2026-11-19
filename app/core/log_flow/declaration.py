"""插件声明的管线配置，不携带运行对象、监控器或模块搜索路径。"""

from typing import Self

from pydantic import BaseModel, Field, model_validator

from app.models.log_flow import ReportOrder

from .contracts import (
    FileInput,
    FunctionRef,
    LineRule,
    ProcessorFactorySpec,
    WindowRule,
    WorkerFactorySpec,
)


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


class PluginFlowDeclaration(BaseModel, frozen=True):
    rules: SimpleFlowDeclaration | GeneralFlowDeclaration = SimpleFlowDeclaration()
    use_mas_log: bool = True
    accept_push: bool = False
    file: FileInput | None = None
    use_run_file: bool = False
    source: WorkerFactorySpec | None = None
    sink: WorkerFactorySpec | None = None

    @model_validator(mode="after")
    def check_file_binding(self) -> Self:
        if self.use_run_file and self.file is not None:
            raise ValueError("日志文件只能选择固定绑定或按运行绑定")
        return self
