"""把采集收尾结果桥接到现有逐条或汇总排版。"""

from typing import Literal

from app.core.notify.report import render_aggregate_push_log, render_scatter_push_log
from app.models.log_flow import SessionSummary
from app.utils.common.log.patterns import LOG_TYPE_ERROR
from app.utils.common.log_box.results import LogEntry

type ReportMode = Literal["关闭", "逐条", "汇总"]


def render_node_details(
    summary: SessionSummary, *, mode: ReportMode, include_error_nodes: bool = True
) -> list[str]:
    """供拥有通知交付责任的调用方使用，保留原有排版和失败过滤语义。"""
    if mode == "关闭":
        return []
    report_entries = summary.report_entries
    if report_entries is None and not summary.requires_final_report:
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
