"""默认 LogFlow 的宿主装配；声明不携带执行对象或进程参数。"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Protocol

from pydantic import BaseModel, Field

from app.models.log_flow import ObservationCursor, ObservationPage
from app.models.task import TaskScriptItem, TaskUserItem
from app.utils.common.log.monitor import LogMonitor

from .contracts import (
    FunctionRef,
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


@asynccontextmanager
async def open_simple_flow(
    declaration: SimpleFlowDeclaration,
    *,
    run: TaskScriptItem | TaskUserItem,
    monitor: LogMonitor,
    mode: ReportMode,
    receive_report: Callable[[list[str]], None],
) -> AsyncIterator[ReadNodes]:
    """宿主绑定当前运行和监控器；调用侧只拿到会话的分页读取函数。"""
    if monitor.on_raw_line is not None:
        raise ValueError("日志监控器已有原始行消费者")
    session = await open_for_run(
        run,
        PipelineSpec(
            accept_mas=True,
            rules=declaration.rules,
            windows=declaration.windows,
            postprocess=declaration.postprocess,
            processor=declaration.processor,
        ),
    )
    receiver = session.native_line_receiver()

    def read_nodes(
        *, after: ObservationCursor | None = None, limit: int = 50
    ) -> ObservationPage:
        return session.observation.read(after=after, limit=limit)

    try:
        if monitor.on_raw_line is not None:
            raise ValueError("日志监控器已有原始行消费者")
        monitor.on_raw_line = receiver
        yield read_nodes
    finally:
        if monitor.on_raw_line is receiver:
            monitor.on_raw_line = None
        summary = await session.close()
    if mode != "关闭":
        receive_report(render_node_details(summary, mode=mode))
