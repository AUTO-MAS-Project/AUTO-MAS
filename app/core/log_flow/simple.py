"""默认 LogFlow 的宿主装配；声明不携带执行对象或进程参数。"""

from collections.abc import AsyncIterator, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.models.log_flow import (
    NodeObservation,
    ObservationCursor,
    ObservationPage,
    ObservationSnapshot,
)
from app.models.task import TaskScriptItem, TaskUserItem
from app.utils.common.log.monitor import LogMonitor

from .contracts import (
    FileInput,
    PipelineSpec,
    WorkerFactorySpec,
    WorkerPluginPackage,
)
from .declaration import GeneralFlowDeclaration, SimpleFlowDeclaration
from .manager import open_for_run
from .ownership import FlowOwner
from .push import GuardedReporter, PushReporter
from .report import ReportMode, render_node_details
from .session import LogFlowSession, SessionOpenError


class ReadNodes(Protocol):
    def __call__(
        self, *, after: ObservationCursor | None = None, limit: int = 50
    ) -> ObservationPage: ...


@dataclass(frozen=True)
class FlowAccess:
    read_nodes: ReadNodes
    reporter: PushReporter | None
    snapshot_nodes: Callable[[], ObservationSnapshot]


@asynccontextmanager
async def _open_unowned(
    run: TaskScriptItem | TaskUserItem, config: PipelineSpec
) -> AsyncIterator[LogFlowSession]:
    session = await open_for_run(run, config)
    try:
        yield session
    finally:
        await session.close_on_exit()


@asynccontextmanager
async def open_custom_flow(
    declaration: SimpleFlowDeclaration | GeneralFlowDeclaration,
    *,
    run: TaskScriptItem | TaskUserItem,
    mode: ReportMode,
    receive_report: Callable[[list[str]], None] | None = None,
    monitor: LogMonitor | None = None,
    file: FileInput | None = None,
    accept_push: bool = False,
    source: WorkerFactorySpec | None = None,
    sink: WorkerFactorySpec | None = None,
    owner: FlowOwner | None = None,
    plugin_package: WorkerPluginPackage | None = None,
) -> AsyncIterator[FlowAccess]:
    """宿主按运行分支绑定来源；上报方不能指定归属或冒充原生来源。"""
    if monitor is not None and monitor.on_raw_line is not None:
        raise ValueError("日志监控器已有原始行消费者")
    specialized = (
        declaration if isinstance(declaration, SimpleFlowDeclaration) else None
    )
    webui = declaration if isinstance(declaration, GeneralFlowDeclaration) else None
    if file is not None:
        file = file.model_copy(update={"path": str(Path(file.path).absolute())})
    config = PipelineSpec(
        file=file,
        accept_mas=monitor is not None,
        accept_push=accept_push,
        source=source,
        sink=sink,
        rules=specialized.rules if specialized is not None else (),
        windows=specialized.windows if specialized is not None else (),
        preprocess=specialized.preprocess if specialized is not None else None,
        postprocess=(
            specialized.postprocess
            if specialized is not None and mode != "关闭"
            else None
        ),
        report_order=specialized.report_order
        if specialized is not None
        else "first_seen",
        functions=specialized.functions if specialized is not None else (),
        processor=specialized.processor if specialized is not None else None,
        general_patterns=webui.patterns if webui is not None else None,
        general_hooks=webui.hooks if webui is not None else "",
        general_log_time=(monitor.time_start, monitor.time_end, monitor.time_format)
        if webui is not None and monitor is not None and monitor.time_format
        else None,
        plugin_package=plugin_package,
    )
    opening = (
        owner.open(run, config) if owner is not None else _open_unowned(run, config)
    )
    observation: NodeObservation | None = None

    def publish_report(deliver: Callable[[list[str]], None]) -> None:
        if observation is not None and (summary := observation.summary) is not None:
            deliver(render_node_details(summary, mode=mode))

    async with AsyncExitStack() as stack:
        if mode != "关闭" and receive_report is not None:
            # 先登记，退出时先完成采集收尾，再交付报告。
            stack.callback(publish_report, receive_report)
        try:
            session = await stack.enter_async_context(opening)
        except SessionOpenError:
            observation = run.node_observation
            assert observation is not None
            reporter = GuardedReporter(None, lambda: False) if accept_push else None
            yield FlowAccess(observation.read, reporter, observation.capture)
            return
        receiver = session.native_line_receiver() if monitor is not None else None
        report_native_gap = session.mark_native_incomplete
        reporter = session.push_reporter() if accept_push else None
        if reporter is not None and owner is not None:
            reporter = GuardedReporter(reporter, lambda: owner.accepting)

        def detach() -> None:
            if monitor is not None and monitor.on_raw_line is receiver:
                monitor.on_raw_line = None
            if monitor is not None and monitor.on_raw_incomplete is report_native_gap:
                monitor.on_raw_incomplete = None

        try:
            if monitor is not None:
                if monitor.on_raw_line is not None:
                    raise ValueError("日志监控器已有原始行消费者")
                monitor.on_raw_line = receiver
                monitor.on_raw_incomplete = report_native_gap
                if owner is not None:
                    owner.attach_cleanup(session, detach)
            observation = session.observation
            yield FlowAccess(observation.read, reporter, observation.capture)
        finally:
            detach()


@asynccontextmanager
async def open_simple_flow(
    declaration: SimpleFlowDeclaration | GeneralFlowDeclaration,
    *,
    run: TaskScriptItem | TaskUserItem,
    monitor: LogMonitor,
    mode: ReportMode,
    receive_report: Callable[[list[str]], None],
    owner: FlowOwner | None = None,
) -> AsyncIterator[ReadNodes]:
    """默认只使用 MAS 原生日志，复用自定义装配的生命周期。"""
    async with open_custom_flow(
        declaration,
        run=run,
        mode=mode,
        receive_report=receive_report,
        monitor=monitor,
        owner=owner,
    ) as access:
        yield access.read_nodes
