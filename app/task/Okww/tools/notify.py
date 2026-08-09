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

from app.core import Config
from app.services import Notify
from app.utils import get_logger

logger = get_logger("OK-WW 通知工具")


async def push_notification(mode: str, title: str, message: dict) -> None:
    """通过已启用的全局渠道推送 OK-WW 任务报告。"""

    logger.info(f"开始推送通知, 模式: {mode}, 标题: {title}")

    if mode != "代理结果":
        return

    result_time_setting = Config.get("Notify", "SendTaskResultTime")
    if not message.get("game_sign_summary", False) and (
        result_time_setting != "任何时刻"
        and (
            result_time_setting != "仅失败时"
            or message["uncompleted_count"] == 0
        )
    ):
        return

    message_text = (
        f"任务开始时间: {message['start_time']}, 结束时间: {message['end_time']}\n"
        f"已完成数: {message['completed_count']}, "
        f"未完成数: {message['uncompleted_count']}\n\n"
        f"{message['result']}"
    )
    message_html = Config.notify_env.get_template("general_result.html").render(
        message
    )
    serverchan_message = message_text.replace("\n", "\n\n")

    if Config.get("Notify", "IfSendMail"):
        await Notify.send_mail(
            "网页", title, message_html, Config.get("Notify", "ToAddress")
        )

    if Config.get("Notify", "IfServerChan"):
        await Notify.ServerChanPush(
            title,
            f"{serverchan_message}\n\nAUTO-MAS 敬上",
            Config.get("Notify", "ServerChanKey"),
        )

    for webhook in Config.Notify_CustomWebhooks.values():
        await Notify.WebhookPush(
            title, f"{message_text}\n\nAUTO-MAS 敬上", webhook
        )

    if Config.get("Notify", "IfKoishiSupport"):
        await Notify.send_koishi(
            f"{title}\n\n{message_text}\n\nAUTO-MAS 敬上"
        )
