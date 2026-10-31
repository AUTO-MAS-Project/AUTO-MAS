"""MaaFW 统计报告正文。"""

from collections.abc import Sequence

from app.core.notify import templates as _notification_template
from app.models.notification import (
    NotificationImage,
    NotifyPayload,
)


def build_statistics_payload(
    *, title: str, message: dict, images: Sequence[NotificationImage] = ()
) -> NotifyPayload:
    """构造专项统计正文，投递由注入的通知服务负责。"""

    # 各项目任务集不同，详情由 runner 的结构化结果生成，这里只负责展示。
    task_details = message.get("task_details", "")
    detail_str = f"\n{task_details}\n" if task_details else ""
    message_text = (
        f"开始时间: {message['start_time']}\n"
        f"结束时间: {message['end_time']}\n"
        f"MaaFW 运行结果: {message['user_result']}"
        f"{detail_str}\n"
    )

    return NotifyPayload(
        title=title,
        text=message_text,
        html=_notification_template.deferred_notification_template(
            "MaaFW_statistics.html", message
        ),
        images=tuple(images),
    )
