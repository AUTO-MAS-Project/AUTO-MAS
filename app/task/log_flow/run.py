"""L4 日志监控与运行树写入的生命周期。"""

import asyncio
from contextlib import AsyncExitStack

from app.models.task import TaskUserItem
from app.task.lifecycle import TaskBase
from app.utils.common.log.flow_monitor import LogFlowMonitor
from app.utils.common.log_flow.analysis import LogAnalysis, analyze_logs
from app.utils.common.log_flow.contracts import (
    FileInput,
    WorkerFactorySpec,
    WorkerPluginPackage,
)
from app.utils.common.log_flow.declaration import (
    GeneralFlowDeclaration,
    SimpleFlowDeclaration,
)
from app.utils.common.log_flow.observation import SessionSummary
from app.utils.common.log_flow.push import PushReporter

_PUBLISH_SECONDS = 0.05


class LogFlow(TaskBase):
    """接管附着了本轮日志来源的监视器，并按批更新对应账号的运行节点。"""

    def __init__(
        self,
        monitor: LogFlowMonitor,
        user_info: TaskUserItem,
        declaration: SimpleFlowDeclaration | GeneralFlowDeclaration,
        *,
        file: FileInput | None = None,
        accept_push: bool = False,
        source: WorkerFactorySpec | None = None,
        sink: WorkerFactorySpec | None = None,
        plugin_package: WorkerPluginPackage | None = None,
        close_timeout: float = 2.0,
        prepare_report: bool = True,
    ) -> None:
        super().__init__()
        self._monitor = monitor
        self._user_info = user_info
        self._analysis_context = analyze_logs(
            declaration,
            monitor=monitor,
            file=file,
            accept_push=accept_push,
            source=source,
            sink=sink,
            plugin_package=plugin_package,
            close_timeout=close_timeout,
            prepare_report=prepare_report,
        )
        self._cleanup = AsyncExitStack()
        self._analysis: LogAnalysis | None = None
        self._publishing: asyncio.Task[None] | None = None
        self._finished = asyncio.Event()
        self._started = False

    @property
    def result(self) -> SessionSummary | None:
        return self._analysis.result if self._analysis is not None else None

    @property
    def reporter(self) -> PushReporter | None:
        return self._analysis.reporter if self._analysis is not None else None

    async def run(self) -> None:
        """在 L4 的调用上下文中运行一次，并将执行错误交还调用方。"""
        if self._started:
            raise RuntimeError("同一日志运行只能执行一次")
        self._started = True
        await super().run()
        if self.error is not None:
            raise self.error

    async def main_task(self) -> None:
        self._cleanup.push_async_callback(self._publish_final)
        self._analysis = await self._cleanup.enter_async_context(self._analysis_context)
        self._cleanup.push_async_callback(self._monitor.stop_owned_source)
        self._cleanup.callback(self._finished.set)
        self._cleanup.push_async_callback(self._monitor.stop)
        # 只在此子协程暂存并提交分析字段。业务配置与日志生产仍由 L4 调用协程管理。
        self._publishing = asyncio.create_task(self._publish_nodes(self._analysis))
        await self._monitor.run_source()

    async def _publish_nodes(self, analysis: LogAnalysis) -> None:
        last_sequence = 0
        observation = analysis.observation
        while not self._finished.is_set():
            try:
                await asyncio.wait_for(self._finished.wait(), timeout=_PUBLISH_SECONDS)
                break
            except TimeoutError:
                sequence = len(observation)
                if sequence != last_sequence:
                    await self._user_info.publish_log_analysis(
                        nodes=observation.snapshot()
                    )
                    last_sequence = sequence

    async def _publish_final(self) -> None:
        try:
            if self._publishing is not None:
                await self._publishing
        finally:
            if (result := self.result) is not None:
                await self._user_info.record_log_analysis(result)
            else:
                await self._user_info.publish_log_analysis(
                    nodes=(), close_reason="worker_error"
                )

    async def final_task(self) -> None:
        await self._cleanup.aclose()
