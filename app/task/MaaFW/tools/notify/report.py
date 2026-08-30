"""MaaFW 任务报告推送。"""

from app.core import Config
from app.core.notify import NotifyPayload, dispatch, global_target, should_send_result
from app.utils import get_logger

logger = get_logger("MaaFW 通知工具")


async def push_notification(mode: str, title: str, message: dict) -> list[str]:
    """通过统一通知编排推送 MaaFW 任务报告。"""

    logger.info(f"开始推送通知, 模式: {mode}, 标题: {title}")

    if mode != "代理结果":
        return []

    if not should_send_result(message):
        return []

    message_text = (
        f"任务开始时间: {message['start_time']}, 结束时间: {message['end_time']}\n"
        f"已完成数: {message['completed_count']}, "
        f"未完成数: {message['uncompleted_count']}\n\n"
        f"{message['result']}"
    )
    message_html = Config.notify_env.get_template("general_result.html").render(message)
    return await dispatch(
        NotifyPayload(title=title, text=message_text, html=message_html),
        [global_target()],
    )
