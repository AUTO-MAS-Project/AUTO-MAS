"""默认 LogFlow 的宿主装配；声明不携带执行对象或进程参数。"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, Field

from app.models.log_flow import ObservationCursor, ObservationPage
from app.models.task import TaskScriptItem, TaskUserItem
from app.utils.common.log.monitor import LogMonitor

from .contracts import (
    FileInput,
    FunctionRef,
    InputRecord,
    LineRule,
    PipelineSpec,
    ProcessorFactorySpec,
    WindowRule,
)
from .manager import open_for_run
from .report import ReportMode, render_node_details


class SimpleFlowDeclaration(BaseModel, frozen=True):
    """MAS 原生日志的节点规则；规则在初始化时编译，关闭时冲刷及归并。"""

    rules: tuple[LineRule, ...] = ()
    windows: tuple[WindowRule, ...] = Field(default=(), max_length=16)
    postprocess: FunctionRef | None = None
    processor: ProcessorFactorySpec | None = None


class ReadNodes(Protocol):
    def __call__(
        self, *, after: ObservationCursor | None = None, limit: int = 50
    ) -> ObservationPage: ...


@dataclass(frozen=True)
class FlowAccess:
    read_nodes: ReadNodes
    submit: Callable[[InputRecord], bool] | None


@asynccontextmanager
async def open_custom_flow(
    declaration: SimpleFlowDeclaration,
    *,
    run: TaskScriptItem | TaskUserItem,
    mode: ReportMode,
    receive_report: Callable[[list[str]], None],
    monitor: LogMonitor | None = None,
    file: FileInput | None = None,
    accept_push: bool = False,
) -> AsyncIterator[FlowAccess]:
    """宿主按运行分支绑定来源；上报方不能指定归属或冒充原生来源。"""
    if monitor is not None and monitor.on_raw_line is not None:
        raise ValueError("日志监控器已有原始行消费者")
    session = await open_for_run(
        run,
        PipelineSpec(
            file=file,
            accept_mas=monitor is not None,
            accept_push=accept_push,
            rules=declaration.rules,
            windows=declaration.windows,
            postprocess=declaration.postprocess,
            processor=declaration.processor,
        ),
    )
    receiver = session.native_line_receiver() if monitor is not None else None

    def read_nodes(
        *, after: ObservationCursor | None = None, limit: int = 50
    ) -> ObservationPage:
        return session.observation.read(after=after, limit=limit)

    try:
        if monitor is not None:
            if monitor.on_raw_line is not None:
                raise ValueError("日志监控器已有原始行消费者")
            monitor.on_raw_line = receiver
        yield FlowAccess(read_nodes, session.submit if accept_push else None)
    finally:
        if monitor is not None and monitor.on_raw_line is receiver:
            monitor.on_raw_line = None
        summary = await session.close()
    if mode != "关闭":
        receive_report(render_node_details(summary, mode=mode))


@asynccontextmanager
async def open_simple_flow(
    declaration: SimpleFlowDeclaration,
    *,
    run: TaskScriptItem | TaskUserItem,
    monitor: LogMonitor,
    mode: ReportMode,
    receive_report: Callable[[list[str]], None],
) -> AsyncIterator[ReadNodes]:
    """默认只使用 MAS 原生日志，复用自定义装配的生命周期。"""
    async with open_custom_flow(
        declaration, run=run, mode=mode, receive_report=receive_report, monitor=monitor
    ) as access:
        yield access.read_nodes
