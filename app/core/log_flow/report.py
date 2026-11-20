"""按 LogFlow 节点状态渲染收尾报告，并交由 Notify 投递。"""

from collections.abc import Set
from dataclasses import replace
from datetime import datetime
from typing import Literal
from uuid import UUID

from app.models.log_flow import NodeDisplayStatus, ReportEntry, SessionSummary
from app.models.notification.channel import DispatchResult
from app.models.notification.report import TaskResultReport
from app.models.task import TaskItem, TaskScriptItem, TaskUserItem

type ReportMode = Literal["关闭", "逐条", "汇总"]

_STATUS_LABELS: dict[NodeDisplayStatus, str] = {
    "success": "✅ 成功",
    "skipped": "⏭ 跳过",
    "failed": "❌ 失败",
    "exception": "⚠ 异常",
    "running": "⏳ 进行中",
    "warning": "⚠ 警告",
}


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


def render_node_details(
    summary: SessionSummary,
    *,
    mode: ReportMode,
    statuses: Set[NodeDisplayStatus] | None = None,
) -> list[str]:
    """按 LogFlow 状态呈现本次会话的有效节点。"""
    if mode == "关闭":
        return []
    report_entries = summary.report_entries
    if report_entries is None and (
        not summary.complete or not summary.requires_final_report
    ):
        nodes = (
            sorted(summary.nodes, key=lambda node: node.sequence)
            if summary.report_order == "last_updated"
            else summary.nodes
        )
        report_entries = tuple(ReportEntry.from_node(node) for node in nodes)
    entries = [
        entry
        for entry in report_entries or ()
        if (
            entry.status in statuses
            if statuses is not None
            else entry.status != "running"
        )
    ]
    if mode == "逐条":
        lines = [_render_entry(entry) for entry in entries]
    else:
        lines = _render_groups(entries)
    if not summary.complete:
        lines.append("⚠️ 节点采集不完整")
    return lines


def _render_entry(entry: ReportEntry) -> str:
    text = entry.text
    if (label := _STATUS_LABELS.get(entry.status)) is not None:
        text = f"{label}: {text}"
    if entry.timestamp is not None:
        return f"{datetime.fromtimestamp(entry.timestamp):%H:%M} - {text}"
    return text


def _render_groups(entries: list[ReportEntry]) -> list[str]:
    groups: dict[NodeDisplayStatus, list[str]] = {}
    rows: list[str | list[str]] = []
    for entry in entries:
        if (label := _STATUS_LABELS.get(entry.status)) is None:
            rows.append(entry.text)
            continue
        if entry.status not in groups:
            group = [f"{label}: {entry.text}"]
            groups[entry.status] = group
            rows.append(group)
        else:
            groups[entry.status].append(entry.text)
    return [", ".join(row) if isinstance(row, list) else row for row in rows]
