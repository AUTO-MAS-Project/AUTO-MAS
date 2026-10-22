"""报告与签到摘要的内容组合，不读取配置或修改任务状态。"""

from dataclasses import replace

from app.models.notification import NotifyPayload
from app.models.notification_report import TaskReportSummary
from app.services.community_notification import append_community_summary_html


def append_report_summary(
    payload: NotifyPayload, summary: TaskReportSummary
) -> NotifyPayload:
    """把同一摘要分别写入正文、HTML、Markdown 和紧凑内容。"""

    return replace(
        payload,
        text=f"{payload.text}\n\n{summary.text}",
        html=(
            append_community_summary_html(payload.html, summary.text)
            if payload.html is not None
            else None
        ),
        markdown=(
            f"{payload.markdown or payload.text}\n\n{summary.markdown}"
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

    markdown = payload.markdown or payload.text
    if summary.markdown and summary.markdown not in markdown:
        markdown = (
            markdown.replace(embedded_summary, summary.markdown)
            if embedded_summary in markdown
            else f"{markdown}\n\n{summary.markdown}"
        )
    clean = replace(
        payload,
        text=payload.text.replace(embedded_summary, "").rstrip(),
        html=(
            payload.html.replace(embedded_summary, "").rstrip()
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
            payload.markdown.replace(summary.markdown, "").rstrip()
            if payload.markdown is not None
            else payload.text.replace(embedded_summary, "").rstrip()
        ),
    )
    return clean, replace(payload, markdown=markdown)
