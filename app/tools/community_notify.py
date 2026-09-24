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


import base64
import re
from html import escape
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw, ImageFont

from app.core import Config
from app.core.notify import DispatchResult, NotifyPayload, dispatch, global_target
from app.utils.logger import get_logger

logger = get_logger("游戏社区通知")

NOTIFICATION_SEND_ATTEMPTS = 2
NOTIFICATION_RETRY_DELAY_SECONDS = 1
_SUCCESS_STATUSES = {"成功", "已签到"}
_PLATFORM_ORDER = ("森空岛", "米游社", "库街区", "塔吉多", "云异环")
NotificationBodyFormat = Literal["text", "markdown"]


def detect_community_notification_format(content: str) -> NotificationBodyFormat:
    """识别通知正文是否包含 Markdown 块级标记。"""

    for line in content.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("# ", "## ", "### ", "- ", "* ", "> ", "```")):
            return "markdown"
    return "markdown" if "**" in content else "text"


def _result_status_text(item: dict[str, object]) -> str:
    """将单条签到结果转换为模板中的短状态。"""

    status = str(item.get("status", "失败"))
    if status == "已签到":
        return "已签"
    if status == "成功":
        return "签到成功"
    if status == "风控":
        return "签到失败-风控"

    reason = str(item.get("reason", "") or "").strip()
    if not reason or reason in {"失败", "签到失败"}:
        return "签到失败"
    if reason.startswith("签到失败-"):
        return reason
    return f"签到失败-{reason}"


def _result_account(item: dict[str, object]) -> str:
    """返回优先使用角色名/UID 的账号标识。"""

    account = str(item.get("account", "") or "").strip()
    if account:
        return account
    account_uid = str(item.get("account_uid", "") or "").strip()
    return account_uid or "未知用户"


def _result_nickname(item: dict[str, object]) -> str:
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
            item.get("platform"),
            item.get("game"),
            "官服",
            "B服",
        )
    ):
        return alias
    return account


def _notification_results(
    results: list[dict[str, object]],
) -> list[dict[str, object]]:
    """过滤没有实际签到角色的平台占位结果。"""

    return [item for item in results if not item.get("_notification_only")]


def _ordered_platforms(
    grouped: dict[str, list[dict[str, object]]],
) -> list[str]:
    """按通知模板固定社区顺序，并保留未知平台结果。"""

    return [
        *[platform for platform in _PLATFORM_ORDER if platform in grouped],
        *[platform for platform in grouped if platform not in _PLATFORM_ORDER],
    ]


def _result_detail(item: dict[str, object]) -> str:
    """保留已签和失败原因，有奖励的成功结果省去重复状态文案。"""

    status = _result_status_text(item)
    game = str(item.get("game", "") or "").strip()
    reward = str(item.get("reward", "") or "").strip().replace("×", "x")
    if not reward:
        return status
    # 云异环的剩余时长属于状态，不能标成新领取的奖励。
    duration_only = game == "云异环" and not reward.startswith("每日首登")
    reward_text = reward if duration_only else f"📥{reward}"
    if item.get("status") == "成功" and not duration_only:
        return reward_text
    return f"{status} {reward_text}"


def _format_notification_item(item: dict[str, object]) -> str:
    """生成各通知渠道共用的紧凑单行结果。"""

    marker = "✅" if item.get("status") in _SUCCESS_STATUSES else "❌"
    game = str(item.get("game") or item.get("platform") or "未知")
    identity = _result_nickname(item)
    detail = _result_detail(item)
    return " ".join(f"{marker} [{game}] {identity} {detail}".splitlines())


_FONT_CANDIDATES = (
    Path("C:/Windows/Fonts/msyh.ttc"),
    Path("C:/Windows/Fonts/simhei.ttf"),
    Path("/System/Library/Fonts/PingFang.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
)
_SYMBOL_FONT_CANDIDATES = (
    Path("C:/Windows/Fonts/seguiemj.ttf"),
    Path("/System/Library/Fonts/Apple Color Emoji.ttc"),
    Path("/usr/share/fonts/truetype/noto/NotoEmoji-Regular.ttf"),
    Path("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"),
)
_SYMBOL_FALLBACK = {"✅": "[OK]", "❌": "[X]", "📥": "[+]"}


def _load_notification_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """加载可显示中文的通知字体，缺失时回退到 Pillow 内置字体。"""

    for path in _FONT_CANDIDATES:
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size=size)


def _load_notification_symbol_font(size: int) -> ImageFont.FreeTypeFont | None:
    """加载通知符号字体，固定尺寸字体不可用时保留文字回退。"""

    for path in _SYMBOL_FONT_CANDIDATES:
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                continue
    return None


def _notification_text_runs(
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    symbol_font: ImageFont.FreeTypeFont | None,
) -> list[tuple[str, ImageFont.FreeTypeFont | ImageFont.ImageFont]]:
    """测量与绘制使用相同字体，避免中文字体缺少图标时产生方框。"""

    runs = []
    for part in re.split(r"([✅❌📥])", text):
        if not part:
            continue
        if part in _SYMBOL_FALLBACK:
            runs.append(
                (part, symbol_font) if symbol_font else (_SYMBOL_FALLBACK[part], font)
            )
        else:
            runs.append((part, font))
    return runs


def _wrap_notification_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
    *,
    symbol_font: ImageFont.FreeTypeFont | None = None,
) -> list[str]:
    """按像素宽度换行，兼容中文这类没有空格分隔的长文本。"""

    lines: list[str] = []
    current = ""
    for char in text:
        if char == "\n":
            lines.append(current)
            current = ""
            continue
        candidate = current + char
        candidate_width = sum(
            draw.textlength(part, font=run_font)
            for part, run_font in _notification_text_runs(
                candidate, font=font, symbol_font=symbol_font
            )
        )
        if current and candidate_width > max_width:
            lines.append(current)
            current = char
        else:
            current = candidate
    lines.append(current)
    return lines


def _community_notification_rows(
    results: list[dict[str, object]],
    *,
    include_signature: bool = True,
    include_title: bool = True,
) -> list[tuple[str, str]]:
    """统一文本、Markdown、HTML 与图片中的平台分组和结果行。"""

    results = _notification_results(results)
    if not results:
        return []

    grouped: dict[str, list[dict[str, object]]] = {}
    for item in results:
        platform = str(item.get("platform", "未知") or "未知")
        grouped.setdefault(platform, []).append(item)

    rows: list[tuple[str, str]] = []
    if include_title:
        rows.append(("title", "【社区签到通知】"))
    for platform in _ordered_platforms(grouped):
        items = grouped[platform]
        total = len(items)
        success_count = sum(
            1 for item in items if item.get("status") in _SUCCESS_STATUSES
        )
        platform = " ".join(platform.splitlines())
        rows.append(("heading", f"• {platform}({success_count}/{total})："))
        for item in items:
            rows.append(("item", _format_notification_item(item)))
    if include_signature:
        rows.append(("footer", "AUTO-MAS 敬上"))
    return rows


def _community_notification_image(results: list[dict[str, object]]) -> bytes:
    """把社区签到结果渲染为适合聊天渠道展示的 PNG 图片。"""

    width = 760
    card_margin = 16
    padding = 32
    inner_width = width - (card_margin + padding) * 2
    row_specs: list[tuple[str, list[str], int]] = []
    total_height = card_margin * 2 + padding * 2
    symbol_font = _load_notification_symbol_font(22)

    with Image.new("RGB", (width, 100), "#f4f4f4") as measure_image:
        measure = ImageDraw.Draw(measure_image)
        for kind, text in _community_notification_rows(results):
            if kind == "title":
                size = 32
                spacing = 16
            elif kind == "heading":
                size = 24
                spacing = 14
            elif kind == "footer":
                size = 18
                spacing = 16
            else:
                size = 22
                spacing = 8
            font = _load_notification_font(size)
            lines = _wrap_notification_text(
                measure,
                text,
                font,
                inner_width,
                symbol_font=symbol_font,
            )
            line_height = int(size * 1.55)
            row_height = len(lines) * line_height
            row_specs.append((kind, lines, row_height))
            total_height += row_height + spacing

    image = Image.new("RGB", (width, total_height), "#f4f4f4")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (card_margin, card_margin, width - card_margin, total_height - card_margin),
        radius=18,
        fill="#ffffff",
    )

    y = card_margin + padding
    for kind, lines, row_height in row_specs:
        if kind == "title":
            font = _load_notification_font(32)
            color = "#009faa"
            spacing = 16
        elif kind == "heading":
            font = _load_notification_font(24)
            color = "#009faa"
            spacing = 14
        elif kind == "footer":
            font = _load_notification_font(18)
            color = "#888888"
            spacing = 16
        else:
            font = _load_notification_font(22)
            color = "#303133"
            spacing = 8

        for line_index, line in enumerate(lines):
            x = 48.0
            line_y = y + line_index * (row_height // len(lines))
            baseline = (
                font.getmetrics()[0] if isinstance(font, ImageFont.FreeTypeFont) else 0
            )
            for part, run_font in _notification_text_runs(
                line, font=font, symbol_font=symbol_font
            ):
                draw.text(
                    (x, line_y + baseline),
                    part,
                    font=run_font,
                    fill=color,
                    anchor="ls" if baseline else None,
                    embedded_color=True,
                )
                x += draw.textlength(part, font=run_font)
        y += row_height + spacing

    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _community_notification_image_base64(
    results: list[dict[str, object]],
) -> str:
    """生成 OneBot 等渠道可用的纯 Base64 PNG 数据。"""

    return base64.b64encode(_community_notification_image(results)).decode("ascii")


def _escape_markdown_text(value: str) -> str:
    """账号和奖励作为文字展示，不解释为 Markdown 或 HTML。"""

    return re.sub(r"([\\`*_{}\[\]<>!#|])", r"\\\1", " ".join(value.splitlines()))


def format_community_notification(
    results: list[dict[str, object]],
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
    results: list[dict[str, object]],
    *,
    output_format: NotificationBodyFormat = "text",
) -> str:
    """复用紧凑通知格式追加社区结果，签名由原任务报告保留。"""

    return format_community_notification(
        results, output_format=output_format, include_signature=False
    )


def get_task_community_summary(
    task_info: object, *, output_format: NotificationBodyFormat = "text"
) -> str:
    """读取尚未发送的社区签到汇总，兼容旧任务字段。"""

    consumed = (
        getattr(task_info, "community_summary_consumed", False)
        if hasattr(task_info, "community_summary_consumed")
        else getattr(task_info, "game_sign_summary_consumed", False)
    )
    if consumed:
        return ""

    results = (
        getattr(task_info, "community_results", [])
        if hasattr(task_info, "community_results")
        else getattr(task_info, "game_sign_results", [])
    )
    if not results:
        return ""

    return format_community_task_summary(list(results), output_format=output_format)


def mark_task_community_summary_consumed(task_info: object) -> None:
    """标记社区签到汇总已由任务报告消费。"""

    if hasattr(task_info, "community_summary_consumed"):
        setattr(task_info, "community_summary_consumed", True)
    else:
        setattr(task_info, "game_sign_summary_consumed", True)


def append_task_community_summary(
    task_info: object,
    result: str,
    *,
    output_format: NotificationBodyFormat = "text",
) -> str:
    """将尚未发送的社区签到汇总附加到任务报告。"""

    if not Config.ToolsConfig.get("GameSign", "NotifyEnabled"):
        return result

    summary = get_task_community_summary(task_info, output_format=output_format)
    return f"{result}\n\n{summary}" if summary else result


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
    results: list[dict[str, object]],
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


def _render_community_html(
    results: list[dict[str, object]],
    title: str,
) -> str:
    """按 MAS 通知模板渲染社区签到邮件正文。"""

    return Config.notify_env.get_template("community_result.html").render(
        title=title,
        content=_community_html_fragment(
            results, include_signature=False, include_title=False
        ),
    )


def build_community_notification_payload(
    results: list[dict[str, object]],
) -> NotifyPayload:
    """把结构化社区结果渲染为统一通知载荷。

    Markdown 是独立社区通知的主内容形态；ServerChan/Webhook 使用 Markdown
    源码，Koishi 使用转换后的 HTML，系统/OpenClaw 等纯文本渠道使用不带
    Markdown 标记的可读文本，邮件使用 MAS HTML 卡片模板。
    """

    results = _notification_results(results)
    title = "社区签到通知"
    plain_text = format_community_notification(
        results, output_format="text", include_title=False
    )
    markdown_text = format_community_notification(results, include_title=False)
    return NotifyPayload(
        title=title,
        standalone_title="【社区签到通知】",
        text=plain_text,
        append_signature=False,
        html=_render_community_html(results, title),
        markdown_text=markdown_text,
        webhook_image_base64=_community_notification_image_base64(results),
        koishi_text=_community_html_fragment(results),
        koishi_msgtype="html",
    )


async def dispatch_community_notification(
    results: list[dict[str, object]],
) -> DispatchResult:
    """分发社区通知并保留完整渠道结果，供新旧入口共同使用。"""
    results = _notification_results(results)
    if not results:
        return DispatchResult()

    payload = build_community_notification_payload(results)
    return await dispatch(
        payload,
        [global_target(include_system=True)],
        attempts=NOTIFICATION_SEND_ATTEMPTS,
        retry_delay=NOTIFICATION_RETRY_DELAY_SECONDS,
    )


async def push_community_notification(
    results: list[dict[str, object]],
) -> list[str]:
    """推送手动或启动时触发的社区通知，返回失败渠道。"""

    dispatch_result = await dispatch_community_notification(results)
    return list(dispatch_result.failed)


__all__ = [
    "append_task_community_summary",
    "detect_community_notification_format",
    "format_community_notification",
    "format_community_task_summary",
    "get_task_community_summary",
    "mark_task_community_summary_consumed",
    "push_community_notification",
]
