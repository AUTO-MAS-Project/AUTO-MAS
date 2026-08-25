#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

from app.core import Config
from app.tools.notify_channels import send_to_global_channels, send_to_user_channels
from app.utils import get_logger
from app.models.config import MaaUserConfig

logger = get_logger("MAA 通知工具")


async def push_notification(
    mode: str, title: str, message: dict, user_config: MaaUserConfig | None
) -> None:
    """通过所有渠道推送通知"""

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
        template = Config.notify_env.get_template("MAA_result.html")
        message_html = template.render(message)

        await send_to_global_channels(title, message_text, message_html, sig_sep="\n")
    elif mode == "统计信息":
        formatted = []
        if "drop_statistics" in message:
            for stage, items in message["drop_statistics"].items():
                formatted.append(f"掉落统计（{stage}）:")
                for item, quantity in items.items():
                    formatted.append(f"  {item}: {quantity}")
        drop_text = "\n".join(formatted)
        formatted = ["招募统计:"]
        if "recruit_statistics" in message:
            for star, count in message["recruit_statistics"].items():
                formatted.append(f"  {star}: {count}")
        recruit_text = "\n".join(formatted)
        message_text = (
            f"开始时间: {message['start_time']}\n"
            f"结束时间: {message['end_time']}\n"
            f"理智剩余: {message.get('sanity', '未知')}\n"
            f"回复时间: {message.get('sanity_full_at', '未知')}\n"
            f"MAA执行结果: {message['maa_result']}\n"
            f"{recruit_text}\n"
            f"{drop_text}"
        )
        template = Config.notify_env.get_template("MAA_statistics.html")
        message_html = template.render(message)

        if Config.get("Notify", "IfSendStatistic"):
            await send_to_global_channels(
                title, message_text, message_html, sig_sep="\n"
            )
        if (
            user_config is not None
            and user_config.get("Notify", "Enabled")
            and user_config.get("Notify", "IfSendStatistic")
        ):
            await send_to_user_channels(
                title, message_text, message_html, user_config, sig_sep="\n"
            )
    elif mode == "公招六星":
        template = Config.notify_env.get_template("MAA_six_star.html")
        message_html = template.render(message)
        # 六星通知的正文是固定文案, 不由 message 拼出
        message_text = "好羡慕~"

        if Config.get("Notify", "IfSendSixStar"):
            await send_to_global_channels(
                title, message_text, message_html, sig_sep="\n"
            )
        if (
            user_config is not None
            and user_config.get("Notify", "Enabled")
            and user_config.get("Notify", "IfSendSixStar")
        ):
            await send_to_user_channels(
                title, message_text, message_html, user_config, sig_sep="\n"
            )
