"""插件声明的管线配置，不携带运行对象、监控器或模块搜索路径。"""

from pydantic import BaseModel, Field

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
    source: WorkerFactorySpec | None = None
    sink: WorkerFactorySpec | None = None
