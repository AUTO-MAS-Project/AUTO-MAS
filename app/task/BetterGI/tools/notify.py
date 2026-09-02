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
    NotifyPayload,
    global_target,
    should_send_result,
)
from app.models.config import BetterGIUserConfig
from app.services import Notify
from app.tools.game_sign_notify import dispatch_task_report, get_task_game_sign_summary
from app.utils import get_logger

logger = get_logger("BetterGI 通知工具")

_STEP_TIME_FMT = "%H:%M:%S"

# 各发信渠道的正文长度上限（按需在分步表之外决定用完整版还是简略版）：
#   邮件(网页 HTML)：无实际字数瓶颈 → 始终用完整版（含「一条龙分步执行」表）。
#   ServerChan/Server酱 desp：上限约 32KB → 完整版，超过预算安全回退简略版。
#   自定义 Webhook（企业微信 text 2048 字节 / Discord 2000 字符 / Telegram 4096 字符）：聊天机器人
#   存在真实每消息字数瓶颈 → 始终用简略版（回退旧的 4 字段汇总），避免分步表被静默截断/丢弃。
_SERVERCHAN_MAX_BYTES = 30 * 1024


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
    total = max(0, total)
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
        if user_config is None or not (
            user_config.get("Notify", "Enabled")
            and user_config.get("Notify", "IfSendStatistic")
        ):
            return DispatchResult()

        # 简略版（所有渠道的兜底）：仅 4 字段汇总，旧版格式
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
        # 完整版：4 字段 + 「一条龙分步执行」
        message_text_full = f"{message_text}{steps_text}"
        message_html = Config.notify_env.get_template("general_statistics.html").render(
            message
        )

        if user_config.get("Notify", "IfSendMail"):
            if user_config.get("Notify", "ToAddress"):
                # 邮件无实际字数瓶颈，始终发完整版（含分步表）
                await Notify.send_mail(
                    "网页",
                    title,
                    message_html,
                    user_config.get("Notify", "ToAddress"),
                )
            else:
                logger.warning("用户邮箱地址为空, 无法发送 BetterGI 用户通知")

        if user_config.get("Notify", "IfServerChan"):
            if user_config.get("Notify", "ServerChanKey"):
                # Server酱 desp 上限约 32KB：分步表很小时用完整版，超预算回退简略版
                serverchan_content = message_text_full
                if len(serverchan_content.encode("utf-8")) > _SERVERCHAN_MAX_BYTES:
                    serverchan_content = message_text
                    logger.warning(
                        "Server酱内容超过字数上限，已回退为简略版（不含分步表）"
                    )
                await Notify.ServerChanPush(
                    title,
                    f"{serverchan_content.replace(chr(10), chr(10) * 2)}\n\nAUTO-MAS 敬上",
                    user_config.get("Notify", "ServerChanKey"),
                )
            else:
                logger.warning("用户ServerChan密钥为空, 无法发送 BetterGI 用户通知")

        for webhook in user_config.Notify_CustomWebhooks.values():
            # Webhook 目标多为聊天机器人（企业微信 2048 字节 / Discord 2000 字符 / Telegram
            # 4096 字符），有真实字数瓶颈 → 用回简略版，避免分步表塞爆被静默丢弃。
            await Notify.WebhookPush(
                title, f"{message_text}\n\nAUTO-MAS 敬上", webhook
            )
        return DispatchResult()

    if mode != "代理结果":
        return DispatchResult()

    if not should_send_result(message):
        return DispatchResult()

    message_text = (
        f"任务开始时间: {message['start_time']}, 结束时间: {message['end_time']}\n"
        f"已完成数: {message['completed_count']}, "
        f"未完成数: {message['uncompleted_count']}\n\n"
        f"{message['result']}"
    )
    message_html = Config.notify_env.get_template("general_result.html").render(
        message
    )
    counts = (
        f"已完成用户数: {message['completed_count']}, "
        f"未完成用户数: {message['uncompleted_count']}"
    )
    summary_text = (
        get_task_game_sign_summary(task_info)
        if task_info is not None and message.get("game_sign_summary")
        else ""
    )
    return await dispatch_task_report(
        NotifyPayload(
            title=title,
            text=message_text,
            html=message_html,
            system_title=message.get("system_title") or title.replace("报告", "已完成！"),
            system_message=counts,
            system_ticker=counts,
            system_timeout=10,
        ),
        [global_target(include_system=True)],
        task_info,
        summary_text=summary_text,
    )
