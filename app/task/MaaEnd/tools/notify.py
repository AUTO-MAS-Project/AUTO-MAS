#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
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
from app.models.config import MaaEndUserConfig
from app.services import Notify
from app.utils import get_logger

logger = get_logger("MaaEnd 通知工具")


async def push_notification(
    mode: str, title: str, message: dict, user_config: MaaEndUserConfig | None
) -> None:
    """通过所有渠道推送通知。"""

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
        template = Config.notify_env.get_template("general_result.html")
        message_html = template.render(message)
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
            await Notify.WebhookPush(title, f"{message_text}\n\nAUTO-MAS 敬上", webhook)

        if Config.get("Notify", "IfKoishiSupport"):
            await Notify.send_koishi(f"{title}\n\n{message_text}\n\nAUTO-MAS 敬上")

    elif mode == "统计信息":
        matrix_lines = []
        if "matrix_statistics" in message and message["matrix_statistics"]:
            matrix_lines.append("基质统计:")
            for skill, weapon in message["matrix_statistics"].items():
                matrix_lines.append(f"  {skill}: {weapon}")
        elif "matrix_statistics" in message:
            matrix_lines.append("基质统计: 无合适的基质")

        pull_count_lines = []
        pull_count = message.get("pull_count_statistics")
        if pull_count:
            pull_count_lines.extend(
                [
                    "抽数统计:",
                    f"  当前池可用: {pull_count['current_pool_total']} 抽",
                    f"  下版本池子总计: {pull_count['next_pool_total']} 抽",
                    f"  资源折算: {pull_count['resource_pulls']} 抽",
                    f"  可留到下版本的券: {pull_count['carry_over_pulls']} 抽",
                ]
            )

        statistic_sections = [
            section
            for section in ("\n".join(pull_count_lines), "\n".join(matrix_lines))
            if section
        ]

        message_text = (
            f"开始时间: {message['start_time']}\n"
            f"结束时间: {message['end_time']}\n"
            f"MaaEnd执行结果: {message['user_result']}"
        )
        if statistic_sections:
            message_text += f"\n\n{'\n\n'.join(statistic_sections)}"

        template = Config.notify_env.get_template("MaaEnd_statistics.html")
        message_html = template.render(message)
        serverchan_message = message_text.replace("\n", "\n\n")

        if Config.get("Notify", "IfSendStatistic"):
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
                await Notify.send_koishi(f"{title}\n\n{message_text}\n\nAUTO-MAS 敬上")

        if (
            user_config is not None
            and user_config.get("Notify", "Enabled")
            and user_config.get("Notify", "IfSendStatistic")
        ):
            if user_config.get("Notify", "IfSendMail"):
                if user_config.get("Notify", "ToAddress"):
                    await Notify.send_mail(
                        "网页",
                        title,
                        message_html,
                        user_config.get("Notify", "ToAddress"),
                    )
                else:
                    logger.warning("用户邮箱地址为空, 无法发送用户单独的邮件通知")

            if user_config.get("Notify", "IfServerChan"):
                if user_config.get("Notify", "ServerChanKey"):
                    await Notify.ServerChanPush(
                        title,
                        f"{serverchan_message}\n\nAUTO-MAS 敬上",
                        user_config.get("Notify", "ServerChanKey"),
                    )
                else:
                    logger.warning(
                        "用户ServerChan密钥为空, 无法发送用户单独的ServerChan通知"
                    )

            for webhook in user_config.Notify_CustomWebhooks.values():
                await Notify.WebhookPush(
                    title, f"{message_text}\n\nAUTO-MAS 敬上", webhook
                )
