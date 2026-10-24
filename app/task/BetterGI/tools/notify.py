#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

from datetime import datetime

from app.models.notification import NotificationSummary, NotifyPayload
from app.task.notify_core import user_statistics_text
from app.utils.notification_template import deferred_notification_template

from .drop_statistics import format_drop_statistics

_STEP_TIME_FMT = "%H:%M:%S"


def _step_duration(step: dict) -> str:
    """把一步的起止时刻换算成人类可读用时（秒/分+秒）；缺时间或解析失败返回 —。"""
    try:
        a = datetime.strptime(step["start"].split(".")[0], _STEP_TIME_FMT)
        b = datetime.strptime(step["end"].split(".")[0], _STEP_TIME_FMT)
    except (KeyError, ValueError, AttributeError):
        return "—"
    total = (
        (b.hour - a.hour) * 3600 + (b.minute - a.minute) * 60 + (b.second - a.second)
    )
    if total < 0:
        # 跨零点（如 23:59:30 → 00:00:30）：时间戳只有时分秒，差值为负即补一天
        total += 86400
    if total < 60:
        return f"{total}秒"
    return f"{total // 60}分{total % 60}秒"


def _render_one_dragon_steps(steps: list[dict]) -> str:
    """把「一条龙分步执行」拼成通知文本段落：每步一行，成功 ✓+时间，异常标注原因/次数+时间。"""
    if not steps:
        return ""
    lines = ["【一条龙分步执行】"]
    for s in steps:
        tag = f"{s['index']}/{s['total']}"
        span = f"{s['start']} → {s['end']}（{_step_duration(s)}）"
        if s["ok"] and not s["issue_count"]:
            lines.append(f"✓ {tag} {s['task']} 成功 {span}")
        elif s["ok"]:
            lines.append(
                f"✓ {tag} {s['task']} 成功（含 {s['issue_count']} 处异常: {s['issue_text']}） {span}"
            )
        else:
            reason = (
                f" · {s['issue_text']}" if s["issue_text"] else " · 未走完就结束/中断"
            )
            lines.append(f"✗ {tag} {s['task']} 失败{reason} {span}")
    return "\n".join(lines)


def build_statistics_payload(*, title: str, message: dict) -> NotifyPayload:
    """构造专项统计正文，投递由注入的通知服务负责。"""

    # 简略版（聊天机器人类渠道的兜底）：仅 4 字段汇总，旧版格式
    message_text = user_statistics_text(message)
    steps_text = (
        "\n\n" + _render_one_dragon_steps(steps)
        if (steps := message.get("one_dragon_steps"))
        else ""
    )
    # 掉落统计（BGI 奖励识别）：物品 + 数量两列，排在「一条龙分步执行」之后
    drops_text = (
        f"\n\n{drops}"
        if (drops := format_drop_statistics(message.get("drop_statistics")))
        else ""
    )
    # 完整版：4 字段 + 「一条龙分步执行」+ 掉落统计
    message_text_full = f"{message_text}{steps_text}{drops_text}"
    message_html = deferred_notification_template("general_statistics.html", message)

    return NotifyPayload(
        title=title,
        text=message_text_full,
        html=message_html,
        summary=NotificationSummary(text=message_text),
    )
