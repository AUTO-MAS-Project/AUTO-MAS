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
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.
#
#   Contact: DLmaster_361@163.com


from app.core import Config
from app.models.config import HSRUserConfig
from app.tools.notify_channels import send_to_global_channels, send_to_user_channels
from app.utils import get_logger

logger = get_logger("HSR 通知工具")


async def push_notification(
    mode: str, title: str, message: dict, user_config: HSRUserConfig | None
) -> None:
    """通过所有渠道推送 HSR 通知。"""

    logger.info(f"开始推送通知, 模式: {mode}, 标题: {title}")

    if mode == "代理结果" and (
        message.get("game_sign_summary", False)
        or Config.get("Notify", "SendTaskResultTime") == "任何时刻"
        or (
            Config.get("Notify", "SendTaskResultTime") == "仅失败时"
            and message["uncompleted_count"] != 0
        )
    ):
        message_text = (
            f"任务开始时间: {message['start_time']}, 结束时间: {message['end_time']}\n"
            f"已完成数: {message['completed_count']}, 未完成数: {message['uncompleted_count']}\n\n"
            f"{message['result']}"
        )
        message_html = Config.notify_env.get_template("general_result.html").render(
            message
        )

        # HSR 独有: 全局邮件/ServerChan 要求收件人非空才发(其余脚本不校验)
        await send_to_global_channels(
            title, message_text, message_html, require_recipient=True
        )

    elif mode == "统计信息":
        message_text = (
            f"开始时间: {message['start_time']}\n"
            f"结束时间: {message['end_time']}\n"
            f"HSR执行结果: {message['user_result']}\n\n"
        )
        message_html = Config.notify_env.get_template("general_statistics.html").render(
            message
        )
        if Config.get("Notify", "IfSendStatistic"):
            await send_to_global_channels(
                title, message_text, message_html, require_recipient=True
            )

        if (
            user_config is not None
            and user_config.get("Notify", "Enabled")
            and user_config.get("Notify", "IfSendStatistic")
        ):
            await send_to_user_channels(title, message_text, message_html, user_config)
