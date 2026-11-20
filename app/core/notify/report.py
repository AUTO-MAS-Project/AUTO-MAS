"""报告与签到摘要的内容组合，不读取配置或修改任务状态。"""

from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import datetime
from typing import Any

from app.core.notify.community_content import (
    append_community_summary_html,
    build_community_notification_payload,
    format_community_task_summary,
)
from app.models.notification import DeferredContent, NotifyPayload, resolve_content
from app.models.notification.community import CommunityNotificationResult
from app.models.notification.report import (
    STATUS_MARKS,
    Node,
    NodeStatus,
    TaskReportSummary,
    UserReportText,
)
from app.utils.common.log_box.results import Entry, LogEntry


class DefaultReportRenderer:
    """生产内容实现；协调器可用替身运行，无须加载模板或 Pillow。"""

    def community_summary(
        self, results: tuple[CommunityNotificationResult, ...]
    ) -> TaskReportSummary:
        return TaskReportSummary(
            text=format_community_task_summary(results).strip(),
            markdown=DeferredContent(
                lambda: format_community_task_summary(
                    results, output_format="markdown"
                ).strip()
            ),
        )

    def community_payload(
        self, results: tuple[CommunityNotificationResult, ...]
    ) -> NotifyPayload:
        return build_community_notification_payload(results)

    def append_summary(
        self, payload: NotifyPayload, summary: TaskReportSummary
    ) -> NotifyPayload:
        return append_report_summary(payload, summary)


def append_report_summary(
    payload: NotifyPayload, summary: TaskReportSummary
) -> NotifyPayload:
    """把同一摘要分别写入正文、HTML、Markdown 和紧凑内容。"""

    return replace(
        payload,
        text=f"{payload.text}\n\n{summary.text}",
        html=(
            _map_body(
                payload.html,
                lambda html: append_community_summary_html(html, summary.text),
            )
            if payload.html is not None
            else None
        ),
        markdown=(
            _map_body(
                payload.markdown or payload.text,
                lambda markdown: f"{markdown}\n\n{resolve_content(summary.markdown)}",
                dependencies=_dependencies(summary.markdown),
            )
            if summary.markdown
            else payload.markdown or payload.text
        ),
        summary=(
            replace(
                payload.summary,
                text=f"{payload.summary.text}\n\n{summary.text}",
                overflow_text=(
                    f"{payload.summary.overflow_text or payload.text}\n\n{summary.text}"
                ),
            )
            if payload.summary is not None
            else None
        ),
    )


def _dependencies(*values: object) -> tuple[DeferredContent[Any], ...]:
    return tuple(value for value in values if isinstance(value, DeferredContent))


def _map_body(
    body: str | DeferredContent[str],
    transform: Callable[[str], str],
    *,
    dependencies: tuple[DeferredContent[Any], ...] = (),
) -> DeferredContent[str]:
    """组合正文仍保持惰性，某种表达失败不会中断其他表达。"""

    return DeferredContent(
        lambda: transform(resolve_content(body)),
        dependencies=(*_dependencies(body), *dependencies),
    )


_STATUS_RENDER_ORDER = {"success": 0, "skipped": 1, "failed": 2}


def render_scatter_push_log(entries: list[LogEntry]) -> list[str]:
    """逐条式渲染：每条结果独占一行，加采集时间（HH:MM）前缀

    无时间戳（通用脚本等旧式二元组条目）时仅输出文本原样，保持兼容；
    带「【账号】」前缀的条目前缀置于时间之前。
    """
    lines: list[str] = []
    for entry in entries:
        text = entry.text
        ts = entry.timestamp
        prefix = ""
        node = Node.from_text(entry.text)
        if node is not None and node.account:
            prefix = f"【{node.account}】"
            text = f"{STATUS_MARKS[node.status]}: {node.name}"
        if ts is not None:
            text = f"{datetime.fromtimestamp(ts).strftime('%H:%M')} - {text}"
        lines.append(prefix + text)
    return lines


def render_aggregate_push_log(entries: Iterable[Entry]) -> list[str]:
    """汇总式渲染：按（账号, 状态前缀）分组合并节点名，同组合并为一行

    账号按组首次出现排列，同账号内成功/跳过/失败固定在前；不具状态前缀的
    条目（如「🔋 剩余体力: 30」）原样独占一行；「⚠ 异常」及未知状态组内容长
    且重要性低，固定垫底。
    """
    groups: dict[tuple[str | None, NodeStatus], list[str]] = {}
    order: list[tuple[str | None, NodeStatus]] = []
    plain: list[str] = []
    for item in entries:
        entry = item if isinstance(item, LogEntry) else LogEntry.from_legacy(item)
        node = Node.from_text(entry.text)
        if node is not None:
            key = (node.account, node.status)
            if key not in groups:
                order.append(key)
                groups[key] = []
            groups[key].append(node.name)
        else:
            plain.append(entry.text)
    # 账号首次出现顺序（多账号前缀保留时按账号分块，不跨账号交错）
    first_acc: dict[str | None, int] = {}
    for idx, (acc, _status) in enumerate(order):
        first_acc.setdefault(acc, idx)

    def _render_group(key: tuple[str | None, NodeStatus]) -> str:
        acc, status = key
        prefix = f"【{acc}】" if acc else ""
        return f"{prefix}{STATUS_MARKS[status]}: {', '.join(groups[key])}"

    normal_keys = sorted(
        (key for key in order if key[1] in _STATUS_RENDER_ORDER),
        key=lambda key: (first_acc[key[0]], _STATUS_RENDER_ORDER[key[1]]),
    )
    tail_keys = [key for key in order if key[1] not in _STATUS_RENDER_ORDER]
    lines = [_render_group(key) for key in normal_keys]
    lines += plain
    lines += [_render_group(key) for key in tail_keys]
    return lines


def render_user_result_text(users: Iterable[UserReportText]) -> str:
    """只排版调用方提供的结果；不选择模式、筛选条目或统计完成数。"""
    return "\n\n".join(
        "\n".join((f"{user.name}: {user.result}", *user.detail_lines)) for user in users
    )
