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

from app.core import Config
from app.core.notify import (
    DispatchResult,
    dispatch,
    statistic_targets,
)
from app.models.config import BetterGIUserConfig
from app.models.notification import NotificationSummary, NotifyPayload
from app.task.notify_core import push_proxy_result
from app.utils import get_logger

from .drop_statistics import format_drop_statistics

logger = get_logger("BetterGI 通知工具")

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


async def push_notification(
    mode: str,
    title: str,
    message: dict,
    user_config: BetterGIUserConfig | None = None,
    task_info: object | None = None,
) -> DispatchResult:
    """通过全局或用户配置的渠道推送 BetterGI 任务报告。"""

    logger.info(f"开始推送通知, 模式: {mode}, 标题: {title}")

    if mode == "统计信息":
        # 简略版（聊天机器人类渠道的兜底）：仅 4 字段汇总，旧版格式
        message_text = (
            f"用户: {message['user_info']}\n"
            f"开始时间: {message['start_time']}\n"
            f"结束时间: {message['end_time']}\n"
            f"执行结果: {message['user_result']}"
        )
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
        message_html = Config.notify_env.get_template("general_statistics.html").render(
            message
        )

        return await dispatch(
            NotifyPayload(
                title=title,
                text=message_text_full,
                html=message_html,
                summary=NotificationSummary(text=message_text),
            ),
            statistic_targets(user_config, compact_summary=True),
        )

    if mode != "代理结果":
        return DispatchResult()

    # 与其余专项一致：正文模板差异保留在本模块（default general_result.html），
    # 推送时机、社区签到摘要注入、渠道级重试与已送达渠道去重交共用核心。
    return await push_proxy_result(title=title, message=message, task_info=task_info)
