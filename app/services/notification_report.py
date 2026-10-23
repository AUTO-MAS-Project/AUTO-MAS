"""报告与签到摘要的内容组合，不读取配置或修改任务状态。"""

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from app.models.notification import DeferredContent, NotifyPayload, resolve_content
from app.models.notification_community import CommunityNotificationResult
from app.models.notification_report import TaskReportSummary
from app.services.community_notification import (
    append_community_summary_html,
    build_community_notification_payload,
    format_community_task_summary,
)


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

    def prepare_payloads(
        self,
        payload: NotifyPayload,
        *,
        summary: TaskReportSummary,
        embedded_summary: str = "",
    ) -> tuple[NotifyPayload, NotifyPayload]:
        return prepare_report_payloads(
            payload, summary=summary, embedded_summary=embedded_summary
        )


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


def prepare_report_payloads(
    payload: NotifyPayload,
    *,
    summary: TaskReportSummary,
    embedded_summary: str = "",
) -> tuple[NotifyPayload, NotifyPayload]:
    """返回不含摘要与含摘要两个版本，兼容已在正文内嵌摘要的报告。"""

    if not embedded_summary:
        return (
            payload,
            append_report_summary(payload, summary) if summary.text else payload,
        )

    def merged_markdown() -> str:
        markdown = resolve_content(payload.markdown or payload.text)
        summary_markdown = resolve_content(summary.markdown)
        if summary_markdown and summary_markdown not in markdown:
            return (
                markdown.replace(embedded_summary, summary_markdown)
                if embedded_summary in markdown
                else f"{markdown}\n\n{summary_markdown}"
            )
        return markdown

    clean = replace(
        payload,
        text=payload.text.replace(embedded_summary, "").rstrip(),
        html=(
            _map_body(
                payload.html, lambda html: html.replace(embedded_summary, "").rstrip()
            )
            if payload.html is not None
            else None
        ),
        summary=(
            replace(
                payload.summary,
                text=payload.summary.text.replace(embedded_summary, "").rstrip(),
                overflow_text=(
                    payload.summary.overflow_text.replace(embedded_summary, "").rstrip()
                    if payload.summary.overflow_text is not None
                    else None
                ),
            )
            if payload.summary is not None
            else None
        ),
        markdown=(
            _map_body(
                payload.markdown,
                lambda markdown: markdown.replace(
                    resolve_content(summary.markdown), ""
                ).rstrip(),
                dependencies=_dependencies(summary.markdown),
            )
            if payload.markdown is not None
            else payload.text.replace(embedded_summary, "").rstrip()
        ),
    )
    return clean, replace(
        payload,
        markdown=DeferredContent(
            merged_markdown,
            dependencies=_dependencies(payload.markdown, summary.markdown),
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
