"""把采集收尾结果桥接到现有逐条或汇总排版。"""

from dataclasses import replace
from typing import Literal
from uuid import UUID

from app.core.notify.report import render_aggregate_push_log, render_scatter_push_log
from app.models.log_flow import SessionSummary
from app.models.notification.channel import DispatchResult
from app.models.notification.report import TaskResultReport
from app.models.task import TaskItem, TaskScriptItem, TaskUserItem
from app.utils.common.log.patterns import LOG_TYPE_ERROR
from app.utils.common.log_box.results import LogEntry

type ReportMode = Literal["关闭", "逐条", "汇总"]


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
        self, run: TaskScriptItem | TaskUserItem, *, include_error_nodes: bool = True
    ) -> list[str]:
        self.validate_run(run)
        if (report := self._reports.get(run.uid)) is None:
            return []
        mode, summary = report
        return render_node_details(
            summary, mode=mode, include_error_nodes=include_error_nodes
        )

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
            for run in (self._script, *self._script.users.values()):
                lines = self.details_for(
                    run, include_error_nodes=report.uncompleted_count > 0
                )
                if lines:
                    blocks.append("\n".join((f"【{run.info.name}】", *lines)))
            if len(blocks) > 1:
                report = replace(report, result="\n\n".join(blocks))
        requested.add(self._script.uid)
        return await Notify.push_proxy_result(
            title=title, report=report, task_info=self._task
        )


def render_node_details(
    summary: SessionSummary, *, mode: ReportMode, include_error_nodes: bool = True
) -> list[str]:
    """供拥有通知交付责任的调用方使用，保留原有排版和失败过滤语义。"""
    if mode == "关闭":
        return []
    report_entries = summary.report_entries
    if report_entries is None and (
        not summary.complete or not summary.requires_final_report
    ):
        report_entries = tuple(
            (node.node_type, node.text, node.timestamp) for node in summary.nodes
        )
    entries = [
        LogEntry(*entry)
        for entry in report_entries or ()
        if include_error_nodes or entry[0] != LOG_TYPE_ERROR
    ]
    if mode == "逐条":
        lines = render_scatter_push_log(entries)
    else:
        lines = render_aggregate_push_log(entries)
    if not summary.complete:
        lines.append("⚠️ 节点采集不完整")
    return lines
