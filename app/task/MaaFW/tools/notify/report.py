"""MaaFW 任务报告推送。"""

from app.core import Config
from app.services import Notify
from app.utils import get_logger

logger = get_logger("MaaFW 通知工具")


async def push_notification(mode: str, title: str, message: dict) -> None:
    """通过全局配置的渠道推送 MaaFW 任务报告。

    「摘取+适配」自 Okww ``tools/notify.py`` 的「代理结果」分支：沿用
    ``Notify.SendTaskResultTime`` 门控（任何时刻 / 仅失败时）、
    ``general_result.html`` 模板与四类全局渠道（邮件 / ServerChan /
    自定义 Webhook / Koishi）。适配点：

    - MaaFW 是引擎无关的通用外部运行，没有游戏签到摘要
      （``game_sign_summary``）与推送日志（``push_log``）采集，相关分支不搬。
    - 用户级「统计信息」依赖统计合并，暂未接线（属独立能力），本层只发
      脚本级「代理结果」报告。
    """

    logger.info(f"开始推送通知, 模式: {mode}, 标题: {title}")

    if mode != "代理结果":
        return

    result_time_setting = Config.get("Notify", "SendTaskResultTime")
    if result_time_setting != "任何时刻" and (
        result_time_setting != "仅失败时" or message["uncompleted_count"] == 0
    ):
        return

    message_text = (
        f"任务开始时间: {message['start_time']}, 结束时间: {message['end_time']}\n"
        f"已完成数: {message['completed_count']}, "
        f"未完成数: {message['uncompleted_count']}\n\n"
        f"{message['result']}"
    )
    message_html = Config.notify_env.get_template("general_result.html").render(message)

    # ServerChan的换行是两个换行符。故而将\n替换为\n\n
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
