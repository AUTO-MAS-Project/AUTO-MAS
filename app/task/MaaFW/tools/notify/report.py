"""MaaFW 任务报告推送。"""

from collections.abc import Sequence
from typing import Any

from app.core import Config
from app.core.notify import (
    DispatchResult,
    dispatch,
    statistic_targets,
)
from app.models.notification import (
    NotificationImage,
    NotifyPayload,
)
from app.task.notify_core import push_proxy_result
from app.utils import get_logger

logger = get_logger("MaaFW 通知工具")


async def push_notification(
    mode: str,
    title: str,
    message: dict,
    task_info: object | None = None,
    user_config: Any | None = None,
    images: Sequence[NotificationImage] = (),
    include_system: bool = True,
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
        images: 随报告附带的失败截图；模板通过资源 ID 引用对应图片。
        include_system: 代理结果是否弹系统通知；本轮已有信号通知弹过时传 False。
    """

    logger.info(f"开始推送通知, 模式: {mode}, 标题: {title}")

    if mode == "代理结果":
        return await push_proxy_result(
            title=title,
            message=message,
            task_info=task_info,
            images=images,
            include_system=include_system,
        )
    if mode == "统计信息":
        return await _push_statistics(title, message, user_config, images)
    return DispatchResult()


async def _push_statistics(
    title: str,
    message: dict,
    user_config: Any | None,
    images: Sequence[NotificationImage] = (),
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
            images=tuple(images),
        ),
        statistic_targets(user_config),
    )
