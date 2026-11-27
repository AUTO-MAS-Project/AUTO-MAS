"""从本次调用提供的日志源采集节点，分析与归并在子进程完成。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from app.utils.common.log.flow_monitor import LogFlowMonitor

from .contracts import FileInput, PipelineSpec, WorkerFactorySpec, WorkerPluginPackage
from .declaration import GeneralFlowDeclaration, SimpleFlowDeclaration
from .observation import NodeObservation, SessionSummary
from .push import GuardedReporter, PushReporter
from .report import ReportMode, render_node_details
from .session import LogFlowSession, SessionOpenError


@dataclass(frozen=True)
class LogAnalysis:
    """调用方持有本次分析，退出上下文后可读取最终结果。"""

    _observation: NodeObservation
    reporter: PushReporter | None

    @property
    def observation(self) -> NodeObservation:
        """向本次运行的拥有者交接分析观察对象。"""
        return self._observation

    @property
    def result(self) -> SessionSummary | None:
        return self._observation.summary

    def report_lines(self, *, mode: ReportMode) -> list[str]:
        """用逐条或汇总模式渲染同一份分析结果。"""
        result = self.result
        return render_node_details(result, mode=mode) if result is not None else []


@asynccontextmanager
async def analyze_logs(
    declaration: SimpleFlowDeclaration | GeneralFlowDeclaration,
    *,
    monitor: LogFlowMonitor | None = None,
    file: FileInput | None = None,
    accept_push: bool = False,
    source: WorkerFactorySpec | None = None,
    sink: WorkerFactorySpec | None = None,
    plugin_package: WorkerPluginPackage | None = None,
    close_timeout: float = 2.0,
    prepare_report: bool = True,
) -> AsyncIterator[LogAnalysis]:
    """启动独立分析。调用方须在退出前停止生产端并交接尾部日志。"""
    if monitor is not None and (
        monitor.on_raw_line is not None or monitor.on_raw_incomplete is not None
    ):
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
        postprocess=specialized.postprocess
        if specialized is not None and prepare_report
        else None,
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
    observation = NodeObservation()
    try:
        session = await LogFlowSession.open(config, observation=observation)
    except SessionOpenError as exc:
        observation.finish("worker_error", str(exc))
        yield LogAnalysis(
            observation, GuardedReporter(None, lambda: False) if accept_push else None
        )
        return

    receiver = session.native_line_receiver() if monitor is not None else None
    mark_incomplete = session.mark_native_incomplete
    try:
        if monitor is not None:
            if monitor.on_raw_line is not None or monitor.on_raw_incomplete is not None:
                raise ValueError("日志监控器已有原始行消费者")
            monitor.on_raw_line = receiver
            monitor.on_raw_incomplete = mark_incomplete
        yield LogAnalysis(observation, session.push_reporter() if accept_push else None)
    finally:
        if monitor is not None:
            if monitor.on_raw_line is receiver:
                monitor.on_raw_line = None
            if monitor.on_raw_incomplete is mark_incomplete:
                monitor.on_raw_incomplete = None
        await session.close_on_exit(timeout=close_timeout)
