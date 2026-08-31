"""MaaFW 任务报告推送。"""

from app.core import Config
from app.core.notify import (
    DispatchResult,
    NotifyPayload,
    global_target,
    should_send_result,
)
from app.tools.game_sign_notify import dispatch_task_report, get_task_game_sign_summary
from app.utils import get_logger

logger = get_logger("MaaFW 通知工具")


async def push_notification(
    mode: str,
    title: str,
    message: dict,
    task_info: object | None = None,
) -> DispatchResult:
    """通过统一通知编排推送 MaaFW 任务报告。"""

    logger.info(f"开始推送通知, 模式: {mode}, 标题: {title}")

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
    message_html = Config.notify_env.get_template("general_result.html").render(message)
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
