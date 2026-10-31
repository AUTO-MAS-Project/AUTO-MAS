#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


from __future__ import annotations

import re
from collections.abc import Callable
from html import escape
from html.parser import HTMLParser
from typing import Literal

from app.core.notify import templates as _notification_template
from app.models.notification import DeferredContent, NotificationImage, NotifyPayload
from app.models.notification.community import CommunityNotificationResult

_PLATFORM_ORDER = ("森空岛", "米游社", "库街区", "塔吉多", "云异环")
NotificationBodyFormat = Literal["text", "markdown"]


def _result_status_text(item: CommunityNotificationResult) -> str:
    """将单条签到结果转换为模板中的短状态。"""

    status = item.status
    if status == "already_signed":
        return "已签"
    if status == "success":
        return "签到成功"
    if status == "risk_control":
        return "签到失败-风控"

    reason = item.reason.strip()
    if not reason or reason in {"失败", "签到失败"}:
        return "签到失败"
    if reason.startswith("签到失败-"):
        return reason
    return f"签到失败-{reason}"


def _result_account(item: CommunityNotificationResult) -> str:
    """返回优先使用角色名/UID 的账号标识。"""

    account = item.account.strip()
    if account:
        return account
    account_uid = item.account_uid.strip()
    return account_uid or "未知用户"


def _result_nickname(item: CommunityNotificationResult) -> str:
    """从已确认的账号展示格式中提取角色名，保留其它原始昵称。"""

    account = " ".join(_result_account(item).splitlines())
    # 上游常用 昵称/昵称(UID)，昵称本身也可能带斜线。
    repeated = re.fullmatch(r"(?P<name>.+)/(?P=name)\(\d+\)", account)
    if repeated:
        return repeated.group("name")
    role = re.fullmatch(r"[^/]+/(.+)\(\d+\)", account)
    if role:
        return role.group(1).strip()
    alias, separator, suffix = account.rpartition("/")
    if (
        separator
        and alias
        and suffix
        in (
            item.platform,
            item.game,
            "官服",
            "B服",
        )
    ):
        return alias
    return account


def _ordered_platforms(
    grouped: dict[str, list[CommunityNotificationResult]],
) -> list[str]:
    """按通知模板固定社区顺序，并保留未知平台结果。"""

    return [
        *[platform for platform in _PLATFORM_ORDER if platform in grouped],
        *[platform for platform in grouped if platform not in _PLATFORM_ORDER],
    ]


def _result_detail(item: CommunityNotificationResult) -> str:
    """保留已签和失败原因，有奖励的成功结果省去重复状态文案。"""

    status = _result_status_text(item)
    game = item.game.strip()
    reward = item.reward.strip().replace("×", "x")
    if not reward:
        return status
    # 云异环的剩余时长属于状态，不能标成新领取的奖励。
    duration_only = game == "云异环" and not reward.startswith("每日首登")
    reward_text = reward if duration_only else f"📥{reward}"
    if item.status == "success" and not duration_only:
        return reward_text
    return f"{status} {reward_text}"


def _format_notification_item(item: CommunityNotificationResult) -> str:
    """生成各通知渠道共用的紧凑单行结果。"""

    marker = "✅" if item.succeeded else "❌"
    game = str(item.game or item.platform or "未知")
    identity = _result_nickname(item)
    detail = _result_detail(item)
    return " ".join(f"{marker} [{game}] {identity} {detail}".splitlines())


def _community_notification_rows(
    results: tuple[CommunityNotificationResult, ...],
    *,
    include_signature: bool = True,
    include_title: bool = True,
) -> list[tuple[str, str]]:
    """统一文本、Markdown、HTML 与图片中的平台分组和结果行。"""

    if not results:
        return []

    grouped: dict[str, list[CommunityNotificationResult]] = {}
    for item in results:
        platform = item.platform
        grouped.setdefault(platform, []).append(item)

    rows: list[tuple[str, str]] = []
    if include_title:
        rows.append(("title", "【社区签到通知】"))
    for platform in _ordered_platforms(grouped):
        items = grouped[platform]
        total = len(items)
        success_count = sum(1 for item in items if item.succeeded)
        platform = " ".join(platform.splitlines())
        rows.append(("heading", f"• {platform}({success_count}/{total})："))
        for item in items:
            rows.append(("item", _format_notification_item(item)))
    if include_signature:
        rows.append(("footer", "AUTO-MAS 敬上"))
    return rows


def _prepare_community_images(
    results: tuple[CommunityNotificationResult, ...],
) -> Callable[[], tuple[NotificationImage, ...]]:
    from app.core.notify.image import render_community_image

    rows = _community_notification_rows(results)
    return lambda: (
        NotificationImage(
            id="community-sign-summary",
            data=render_community_image(rows),
            alt="社区签到结果",
            mime_type="image/png",
        ),
    )


def _escape_markdown_text(value: str) -> str:
    """账号和奖励作为文字展示，不解释为 Markdown 或 HTML。"""

    return re.sub(r"([\\`*_{}\[\]<>!#|])", r"\\\1", " ".join(value.splitlines()))


def format_community_notification(
    results: tuple[CommunityNotificationResult, ...],
    *,
    output_format: NotificationBodyFormat = "markdown",
    include_signature: bool = True,
    include_title: bool = True,
) -> str:
    """按社区分组生成通知正文，并显式支持文本与 Markdown。"""

    lines: list[str] = []
    for kind, text in _community_notification_rows(
        results, include_signature=include_signature, include_title=include_title
    ):
        if kind in {"heading", "footer"} and lines:
            lines.append("")
        if output_format == "markdown":
            text = _escape_markdown_text(text)
            if kind in {"title", "heading"}:
                text = f"**{text}**"
        elif kind == "heading":
            text = f" {text}"
        lines.append(text)

    separator = "  \n" if output_format == "markdown" else "\n"
    return separator.join(lines)


def format_community_task_summary(
    results: tuple[CommunityNotificationResult, ...],
    *,
    output_format: NotificationBodyFormat = "text",
) -> str:
    """复用紧凑通知格式追加社区结果，签名由原任务报告保留。"""

    return format_community_notification(
        results, output_format=output_format, include_signature=False
    )


class _TaskReportSummaryPosition(HTMLParser):
    """定位模板签名或正文末尾，保持专项 HTML 和样式原样。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.position: tuple[int, int] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if (
            self.position is None
            and "signature" in (dict(attrs).get("class") or "").split()
        ):
            self.position = self.getpos()

    def handle_endtag(self, tag: str) -> None:
        if self.position is None and tag == "body":
            self.position = self.getpos()


def append_community_summary_html(content: str, summary: str) -> str:
    """在任务报告签名前追加经过转义的社区摘要。"""

    parser = _TaskReportSummaryPosition()
    parser.feed(content)
    parser.close()
    offset = len(content)
    if parser.position is not None:
        line, column = parser.position
        offset = (
            sum(len(part) for part in content.splitlines(keepends=True)[: line - 1])
            + column
        )
    fragment = (
        '<div class="content"><div class="result-box" style="white-space: pre-wrap">'
        f"{escape(summary)}</div></div>"
    )
    return f"{content[:offset]}{fragment}{content[offset:]}"


def _community_html_fragment(
    results: tuple[CommunityNotificationResult, ...],
    *,
    include_signature: bool = True,
    include_title: bool = True,
) -> str:
    """生成社区通知的 HTML 主体，动态文本先统一转义。"""

    tags = {"title": "h2", "heading": "h3", "item": "p", "footer": "p"}
    html_lines = []
    for kind, text in _community_notification_rows(
        results, include_signature=include_signature, include_title=include_title
    ):
        tag = tags[kind]
        html_lines.append(f"<{tag}>{escape(text)}</{tag}>")
    return "".join(html_lines)


def _prepare_community_html(
    results: tuple[CommunityNotificationResult, ...], title: str
) -> Callable[[], str]:
    """按 MAS 通知模板渲染社区签到邮件正文。"""

    template = _notification_template.get_notification_template("community_result.html")
    return lambda: template.render(
        title=title,
        content=_community_html_fragment(
            results, include_signature=False, include_title=False
        ),
    )


def build_community_notification_payload(
    results: tuple[CommunityNotificationResult, ...],
) -> NotifyPayload:
    """把结构化社区结果渲染为统一通知载荷。

    同时提供纯文本、Markdown 和 HTML 表达，由每个目标按声明能力选择。
    """

    title = "社区签到通知"
    plain_text = format_community_notification(
        results, output_format="text", include_title=False
    )
    markdown = DeferredContent(
        lambda: format_community_notification(results, include_title=False)
    )
    return NotifyPayload(
        title=title,
        body_title="【社区签到通知】",
        text=plain_text,
        append_signature=False,
        html=DeferredContent(
            lambda: _prepare_community_html(results, title)(),
            prepare_factory=lambda: _prepare_community_html(results, title),
        ),
        markdown=markdown,
        images=DeferredContent(
            lambda: _prepare_community_images(results)(),
            prepare_factory=lambda: _prepare_community_images(results),
        ),
    )
