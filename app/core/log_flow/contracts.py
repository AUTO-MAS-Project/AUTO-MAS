"""LogFlow 会话的内部声明和进程消息。"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, TypeAdapter, model_validator

from app.models.log_flow import Node

# 进程管道的单条消息预算；不是日志文件或 SDK 限额。
MAX_FRAME_BYTES = 64 * 1024
MAX_PENDING_RECORDS = 64
MAX_NODE_FRAMES = 4096
MAX_NODE_BYTES = 4 * 1024 * 1024


class LineRule(BaseModel, frozen=True):
    match: str = Field(min_length=1)
    extract: str = ""
    node_type: str = Field(min_length=1)


class WindowRule(BaseModel, frozen=True):
    start: str = Field(min_length=1)
    end: str | None = None
    extract: str = ""
    max_lines: int = Field(default=50, ge=2, le=100)
    node_type: str = Field(min_length=1)


class FunctionRef(BaseModel, frozen=True):
    name: str = Field(min_length=1)
    module: str = Field(min_length=1)
    attribute: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")


class FileInput(BaseModel, frozen=True):
    path: str = Field(min_length=1)
    start_from_end: bool = True
    rotated_name: str | None = None


class PipelineSpec(BaseModel, frozen=True):
    file: FileInput | None = None
    rules: tuple[LineRule, ...] = ()
    windows: tuple[WindowRule, ...] = Field(default=(), max_length=16)
    accept_push: bool = False
    accept_mas: bool = False
    functions: tuple[FunctionRef, ...] = ()
    postprocess: FunctionRef | None = None
    general_patterns: str | None = None
    general_hooks: str = ""

    @model_validator(mode="after")
    def check_sources(self) -> Self:
        if self.file is None and not (self.accept_push or self.accept_mas):
            raise ValueError("至少声明一个日志来源")
        if self.file is not None and not (
            self.rules or self.windows or self.general_patterns is not None
        ):
            raise ValueError("文件采集必须声明规则")
        if self.general_patterns is not None and (
            self.rules or self.windows or self.functions
        ):
            raise ValueError("通用脚本和专项规则必须选用一种处理方式")
        return self


class TextRecord(BaseModel, frozen=True):
    kind: Literal["text"] = "text"
    text: str
    source: Literal["push", "mas"] = "push"
    timestamp: float | None = Field(default=None, allow_inf_nan=False)


class ReportedRecord(BaseModel, frozen=True):
    kind: Literal["reported"] = "reported"
    node_type: str = Field(min_length=1)
    text: str = Field(min_length=1)
    timestamp: float | None = Field(default=None, allow_inf_nan=False)


type InputRecord = Annotated[TextRecord | ReportedRecord, Field(discriminator="kind")]
INPUT_RECORD: TypeAdapter[InputRecord] = TypeAdapter(InputRecord)


class Ready(BaseModel):
    kind: Literal["ready"] = "ready"
    pid: int = Field(gt=0)


class Observed(BaseModel):
    kind: Literal["node"] = "node"
    node: Node


class Closed(BaseModel):
    kind: Literal["closed"] = "closed"
    has_final_report: bool = False


class ReportEntry(BaseModel, frozen=True):
    node_type: str
    text: str
    timestamp: float | None = Field(default=None, allow_inf_nan=False)


class FinalEntry(BaseModel):
    kind: Literal["final_entry"] = "final_entry"
    entry: ReportEntry


class Failed(BaseModel):
    kind: Literal["failed"] = "failed"
    reason: Literal["worker_error", "capacity"] = "worker_error"
    detail: str


type WorkerMessage = Annotated[
    Ready | Observed | FinalEntry | Closed | Failed, Field(discriminator="kind")
]
WORKER_MESSAGE: TypeAdapter[WorkerMessage] = TypeAdapter(WorkerMessage)
