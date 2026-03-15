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
        Config.get("Notify", "SendTaskResultTime") == "任何时刻"
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
