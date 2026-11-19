"""LogFlow 会话的内部声明和进程消息。"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    Field,
    JsonValue,
    TypeAdapter,
    model_validator,
)

from app.models.log_flow import Node, NodeAttributes, NodeDisplayStatus, ReportedNodeKey
from app.utils.common.log.sources import FileCursor, capture_file_cursor

# 进程管道的单条消息预算；不是日志文件或 SDK 限额。
MAX_FRAME_BYTES = 64 * 1024
MAX_PENDING_RECORDS = 64
MAX_NATIVE_PENDING_RECORDS = 2048
MAX_HOST_PENDING_BYTES = MAX_PENDING_RECORDS * MAX_FRAME_BYTES
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
    start_cursor: FileCursor | None = None

    async def capture_start(self) -> Self:
        """在启动脚本之前固定本轮文件及字节起点。"""
        path = str(Path(self.path).absolute())
        cursor = await asyncio.to_thread(
            capture_file_cursor, path, start_from_end=self.start_from_end
        )
        return self.model_copy(update={"path": path, "start_cursor": cursor})


class WorkerFactorySpec(BaseModel, frozen=True):
    """宿主选出的工厂及可序列化参数，不是公开插件注册声明。"""

    factory: FunctionRef
    options: dict[str, JsonValue] = Field(default_factory=dict)


class WorkerPluginPackage(BaseModel, frozen=True):
    name: str
    import_root: str
    dependency_root: str
    sdk_root: str


ProcessorFactorySpec = WorkerFactorySpec


class PipelineSpec(BaseModel, frozen=True):
    file: FileInput | None = None
    rules: tuple[LineRule, ...] = ()
    windows: tuple[WindowRule, ...] = Field(default=(), max_length=16)
    accept_push: bool = False
    accept_mas: bool = False
    functions: tuple[FunctionRef, ...] = ()
    preprocess: FunctionRef | None = None
    postprocess: FunctionRef | WorkerFactorySpec | None = None
    general_patterns: str | None = None
    general_hooks: str = ""
    general_log_time: tuple[int, int, str] | None = None
    processor: ProcessorFactorySpec | None = None
    source: WorkerFactorySpec | None = None
    sink: WorkerFactorySpec | None = None
    plugin_package: WorkerPluginPackage | None = None

    @model_validator(mode="after")
    def check_sources(self) -> Self:
        if (
            self.file is None
            and self.source is None
            and not (self.accept_push or self.accept_mas)
        ):
            raise ValueError("至少声明一个日志来源")
        if self.file is not None and not (
            self.rules
            or self.windows
            or self.general_patterns is not None
            or self.processor is not None
        ):
            raise ValueError("文件采集必须声明规则")
        if self.general_patterns is not None and (
            self.rules or self.windows or self.functions or self.preprocess is not None
        ):
            raise ValueError("通用脚本和专项规则必须选用一种处理方式")
        if self.processor is not None and (
            self.rules
            or self.windows
            or self.functions
            or self.preprocess is not None
            or self.general_patterns is not None
            or self.general_hooks
        ):
            raise ValueError("自定义处理器与内置处理规则不能同时使用")
        return self


def _validate_timestamp(timestamp: float) -> float:
    try:
        datetime.fromtimestamp(timestamp)
    except (OSError, OverflowError, ValueError) as exc:
        raise ValueError("日志时间戳应为可转换为本地时间的 Unix 秒数") from exc
    return timestamp


type _LogTimestamp = Annotated[
    float, Field(allow_inf_nan=False), AfterValidator(_validate_timestamp)
]


class TextRecord(BaseModel, frozen=True):
    kind: Literal["text"] = "text"
    text: str
    source: Literal["push", "mas"] = "push"
    timestamp: _LogTimestamp | None = None


class ReportedRecord(BaseModel, frozen=True):
    kind: Literal["reported"] = "reported"
    node_type: str = Field(min_length=1)
    text: str = Field(min_length=1)
    timestamp: _LogTimestamp | None = None
    node_id: ReportedNodeKey | None = None
    status: NodeDisplayStatus | None = None
    attributes: NodeAttributes = ()


class WithdrawnRecord(BaseModel, frozen=True):
    kind: Literal["withdrawn"] = "withdrawn"
    node_id: ReportedNodeKey


type InputRecord = Annotated[
    TextRecord | ReportedRecord | WithdrawnRecord, Field(discriminator="kind")
]
INPUT_RECORD: TypeAdapter[InputRecord] = TypeAdapter(InputRecord)


class Ready(BaseModel):
    kind: Literal["ready"] = "ready"
    pid: int = Field(gt=0)


class Observed(BaseModel):
    kind: Literal["node"] = "node"
    node: Node


class Closed(BaseModel):
    kind: Literal["closed"] = "closed"
    sink_error: str = ""


class ReportEntry(BaseModel, frozen=True):
    node_type: str
    text: str
    timestamp: _LogTimestamp | None = None


class FinalEntry(BaseModel):
    kind: Literal["final_entry"] = "final_entry"
    entry: ReportEntry


class FinalReportReady(BaseModel):
    kind: Literal["final_report_ready"] = "final_report_ready"


class Failed(BaseModel):
    kind: Literal["failed"] = "failed"
    reason: Literal["worker_error", "capacity"] = "worker_error"
    detail: str


type WorkerMessage = Annotated[
    Ready | Observed | FinalEntry | FinalReportReady | Closed | Failed,
    Field(discriminator="kind"),
]
WORKER_MESSAGE: TypeAdapter[WorkerMessage] = TypeAdapter(WorkerMessage)
