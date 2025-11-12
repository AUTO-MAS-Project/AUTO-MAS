#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

from app.core import Config
from app.services import Notify
from app.utils import get_logger
from app.models.config import GeneralUserConfig

logger = get_logger("MAA 通知工具")


async def push_notification(
    mode: str, title: str, message: dict, user_config: GeneralUserConfig | None
) -> None:
    """通过所有渠道推送通知"""

    logger.info(f"开始推送通知, 模式: {mode}, 标题: {title}")

    if mode == "代理结果" and (
        Config.get("Notify", "SendTaskResultTime") == "任何时刻"
        or (
            Config.get("Notify", "SendTaskResultTime") == "仅失败时"
            and message["uncompleted_count"] != 0
        )
    ):
        # 生成文本通知内容
        message_text = (
            f"任务开始时间: {message['start_time']}, 结束时间: {message['end_time']}\n"
            f"已完成数: {message['completed_count']}, 未完成数: {message['uncompleted_count']}\n\n"
        )

        if len(message["failed_user"]) > 0:
            message_text += f"未成功的用户: \n{"\n".join(message['failed_user'])}\n"
        if len(message["waiting_user"]) > 0:
            message_text += f"\n未开始的用户: \n{"\n".join(message['waiting_user'])}\n"

        # 生成HTML通知内容
        message["failed_user"] = "、".join(message["failed_user"])
        message["waiting_user"] = "、".join(message["waiting_user"])

        template = Config.notify_env.get_template("general_result.html")
        message_html = template.render(message)

        # ServerChan的换行是两个换行符。故而将\n替换为\n\n
        serverchan_message = message_text.replace("\n", "\n\n")

        # 发送全局通知
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

        # 发送自定义Webhook通知
        for webhook in Config.Notify_CustomWebhooks.values():
            await Notify.WebhookPush(title, f"{message_text}\n\nAUTO-MAS 敬上", webhook)

    elif mode == "统计信息":
        message_text = (
            f"开始时间: {message['start_time']}\n"
            f"结束时间: {message['end_time']}\n"
            f"通用脚本执行结果: {message['user_result']}\n\n"
        )

        # 生成HTML通知内容
        template = Config.notify_env.get_template("general_statistics.html")
        message_html = template.render(message)

        # ServerChan的换行是两个换行符。故而将\n替换为\n\n
        serverchan_message = message_text.replace("\n", "\n\n")

        # 发送全局通知
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

            # 发送自定义Webhook通知
            for webhook in Config.Notify_CustomWebhooks.values():
                await Notify.WebhookPush(
                    title, f"{message_text}\n\nAUTO-MAS 敬上", webhook
                )

        # 发送用户单独通知
        if (
            user_config is not None
            and user_config.get("Notify", "Enabled")
            and user_config.get("Notify", "IfSendStatistic")
        ):
            # 发送邮件通知
            if user_config.get("Notify", "IfSendMail"):
                if user_config.get("Notify", "ToAddress"):
                    await Notify.send_mail(
                        "网页",
                        title,
                        message_html,
                        user_config.get("Notify", "ToAddress"),
                    )
                else:
                    logger.error("用户邮箱地址为空, 无法发送用户单独的邮件通知")

            # 发送ServerChan通知
            if user_config.get("Notify", "IfServerChan"):
                if user_config.get("Notify", "ServerChanKey"):
                    await Notify.ServerChanPush(
                        title,
                        f"{serverchan_message}\n\nAUTO-MAS 敬上",
                        user_config.get("Notify", "ServerChanKey"),
                    )
                else:
                    logger.error(
                        "用户ServerChan密钥为空, 无法发送用户单独的ServerChan通知"
                    )

            # 推送CompanyWebHookBot通知
            for webhook in user_config.Notify_CustomWebhooks.values():
                await Notify.WebhookPush(
                    title, f"{message_text}\n\nAUTO-MAS 敬上", webhook
                )
