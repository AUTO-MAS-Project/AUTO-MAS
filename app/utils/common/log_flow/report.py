"""按日志节点状态渲染收尾报告。"""

from collections.abc import Set
from datetime import datetime
from typing import Literal

from .observation import NodeDisplayStatus, ReportEntry, SessionSummary

type ReportMode = Literal["关闭", "逐条", "汇总"]

_STATUS_LABELS: dict[NodeDisplayStatus, str] = {
    "success": "✅ 成功",
    "skipped": "⏭ 跳过",
    "failed": "❌ 失败",
    "exception": "⚠ 异常",
    "running": "⏳ 进行中",
    "warning": "⚠ 警告",
}


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
