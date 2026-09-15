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
    SIGNATURE,
    DispatchResult,
    NotifyPayload,
    dispatch,
    statistic_targets,
)
from app.models.config import BetterGIUserConfig
from app.task.notify_core import push_proxy_result
from app.utils import get_logger

logger = get_logger("BetterGI 通知工具")

_STEP_TIME_FMT = "%H:%M:%S"

# 各发信渠道的正文长度上限（按需在分步表之外决定用完整版还是简略版）：
#   邮件(网页 HTML)：无实际字数瓶颈 → 模板渲染完整版（含「一条龙分步执行」表）。
#   ServerChan/Server酱 desp：上限约 32KB → 完整版，超过预算安全回退简略版。
#   自定义 Webhook（企业微信 text 2048 字节 / Discord 2000 字符 / Telegram 4096 字符）：聊天机器人
#   存在真实每消息字数瓶颈 → 始终用简略版（回退旧的 4 字段汇总），避免分步表被静默截断/丢弃。
# 分流只决定「哪个渠道拿哪份正文」，投递本身一律交 app.core.notify.dispatch。
_SERVERCHAN_MAX_BYTES = 30 * 1024


def _signed(text: str, *, serverchan: bool = False) -> str:
    """按 ``NotifyPayload`` 的默认口径补签名（ServerChan 另把换行折成双换行）。

    只用于需要覆盖 payload 默认正文的两个渠道：聊天机器人类 Webhook 的简略版，
    以及 ServerChan 超预算时的降级版。
    """

    body = text.replace("\n", "\n\n") if serverchan else text
    return f"{body}\n\n{SIGNATURE}"


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
        # 完整版：4 字段 + 「一条龙分步执行」
        message_text_full = f"{message_text}{steps_text}"
        message_html = Config.notify_env.get_template("general_statistics.html").render(
            message
        )

        # 正文只按渠道分流，投递一律交 dispatch：目标渠道（全局 + 用户）、渠道级重试、
        # 失败隔离与 DispatchResult 都由 app.core.notify 负责。
        serverchan_text = None
        if len(message_text_full.encode("utf-8")) > _SERVERCHAN_MAX_BYTES:
            # Server酱 desp 上限约 32KB：分步表很小时用完整版，超预算回退简略版
            serverchan_text = _signed(message_text, serverchan=True)
            logger.warning("Server酱内容超过字数上限，已回退为简略版（不含分步表）")

        return await dispatch(
            NotifyPayload(
                title=title,
                text=message_text_full,
                html=message_html,
                serverchan_text=serverchan_text,
                webhook_text=_signed(message_text),
            ),
            statistic_targets(user_config),
        )

    if mode != "代理结果":
        return DispatchResult()

    # 与其余专项一致：正文模板差异保留在本模块（default general_result.html），
    # 推送时机、社区签到摘要注入、渠道级重试与已送达渠道去重交共用核心。
    return await push_proxy_result(title=title, message=message, task_info=task_info)
