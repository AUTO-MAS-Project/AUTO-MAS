"""MaaFW 任务报告推送。"""

from typing import Any

from app.core import Config
from app.core.notify import (
    DispatchResult,
    NotifyPayload,
    dispatch,
    global_target,
    should_send_result,
    statistic_targets,
)
from app.tools.game_sign_notify import dispatch_task_report, get_task_game_sign_summary
from app.utils import get_logger

logger = get_logger("MaaFW 通知工具")


async def push_notification(
    mode: str,
    title: str,
    message: dict,
    task_info: object | None = None,
    user_config: Any | None = None,
) -> DispatchResult:
    """通过统一通知编排推送 MaaFW 任务报告。

    Args:
        mode: 通知模式 —— "代理结果"（脚本级）或 "统计信息"（用户级）。
        title: 通知标题。
        message: 各模式所需字段不同：
            - "代理结果": start_time, end_time, completed_count,
              uncompleted_count, result
            - "统计信息": start_time, end_time, user_info, user_result,
              task_details
        task_info: 任务信息，代理结果模式用于签到汇总的渠道级重试。
        user_config: 用户配置，统计信息模式用于发送用户独立通知。
    """

    logger.info(f"开始推送通知, 模式: {mode}, 标题: {title}")

    if mode == "代理结果":
        return await _push_proxy_result(title, message, task_info)
    if mode == "统计信息":
        return await _push_statistics(title, message, user_config)
    return DispatchResult()


async def _push_proxy_result(
    title: str, message: dict, task_info: object | None
) -> DispatchResult:
    """推送脚本级「代理结果」报告（全局渠道）。"""

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


async def _push_statistics(
    title: str, message: dict, user_config: Any | None
) -> DispatchResult:
    """推送用户级「统计信息」（全局 + 用户独立渠道）。

    与 M9A 专项同形：走 ``statistic_targets``，因此除全局渠道外还会发到该
    用户自己配置的邮箱 / Server 酱。``MaaFWUserConfig`` 的 Notify 组一直都在、
    编辑页也能配，但在此之前没有任何代码往它发。

    模板 ``MaaFW_statistics.html`` 与 M9A 的同形：多一个「任务详情」块。
    任务集由项目 interface.json 决定、每个项目都不同，所以详情文本由
    ``runner_task`` 按各次尝试的结构化结果拼好后传进来。
    """

    task_details = message.get("task_details", "")
    detail_str = f"\n{task_details}\n" if task_details else ""
    message_text = (
        f"开始时间: {message['start_time']}\n"
        f"结束时间: {message['end_time']}\n"
        f"MaaFW 运行结果: {message['user_result']}"
        f"{detail_str}\n"
    )
    template = Config.notify_env.get_template("MaaFW_statistics.html")

    return await dispatch(
        NotifyPayload(
            title=title,
            text=message_text,
            html=template.render(message),
        ),
        statistic_targets(user_config),
    )
