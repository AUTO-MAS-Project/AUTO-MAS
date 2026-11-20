"""按实际运行归集 LogFlow 明细并交由 Notify 投递。"""

from collections.abc import Set
from dataclasses import replace
from uuid import UUID

from app.models.notification.channel import DispatchResult
from app.models.notification.report import TaskResultReport
from app.models.task import TaskItem, TaskScriptItem, TaskUserItem
from app.utils.common.log_flow.observation import NodeDisplayStatus, SessionSummary
from app.utils.common.log_flow.report import ReportMode, render_node_details


class LogFlowTaskReport:
    """托管执行侧持有，按运行节点取详情，交由现有任务报告投递。"""

    def __init__(self, script: TaskScriptItem) -> None:
        task = script.root
        if not isinstance(task, TaskItem):
            raise ValueError("日志报告需要已绑定任务的托管运行节点")
        self._script = script
        self._task = task
        self._reports: dict[UUID, tuple[ReportMode, SessionSummary]] = {}

    def validate_run(self, run: TaskScriptItem | TaskUserItem) -> None:
        if run is not self._script and self._script.users.get(run.uid) is not run:
            raise ValueError("日志会话不属于该托管报告")

    def record(
        self,
        run: TaskScriptItem | TaskUserItem,
        mode: ReportMode,
        summary: SessionSummary,
    ) -> None:
        self._reports[run.uid] = mode, summary

    def details_for(
        self,
        run: TaskScriptItem | TaskUserItem,
        *,
        statuses: Set[NodeDisplayStatus] | None = None,
    ) -> list[str]:
        self.validate_run(run)
        if (report := self._reports.get(run.uid)) is None:
            return []
        mode, summary = report
        return render_node_details(summary, mode=mode, statuses=statuses)

    async def send(
        self, *, title: str, report: TaskResultReport, append_details: bool = True
    ) -> DispatchResult:
        """托管结果定稿后提交一次，复用 Notify 的收件、筛选及异步投递。"""
        from app.core import Notify

        requested = self._task.notification_state.log_flow_reports
        if self._script.uid in requested:
            return DispatchResult()
        if append_details:
            blocks = [report.result]
            runs: tuple[TaskScriptItem | TaskUserItem, ...] = (
                self._script,
                *self._script.users.values(),
            )
            for run in runs:
                lines = self.details_for(run)
                if lines:
                    blocks.append("\n".join((f"【{run.info.name}】", *lines)))
            if len(blocks) > 1:
                report = replace(report, result="\n\n".join(blocks))
        requested.add(self._script.uid)
        accepted = False

        def accept() -> None:
            nonlocal accepted
            accepted = True

        try:
            return await Notify.push_proxy_result(
                title=title, report=report, task_info=self._task, on_accepted=accept
            )
        except BaseException:
            if not accepted:
                requested.discard(self._script.uid)
            raise
