"""插件通知入口：业务生成报告，宿主统一选择渠道并记录投递结果。"""

from app.core.notify import (
    DispatchResult,
    NotifyTarget,
    dispatch,
    dispatch_task_report,
    global_target,
    statistic_targets,
    user_target,
)
from app.models.notification import (
    NotificationImage,
    NotifyPayload,
    image_reference,
)
from app.task.notify_core import push_proxy_result

__all__ = [
    "DispatchResult", "NotifyTarget", "NotificationImage", "NotifyPayload",
    "dispatch", "dispatch_task_report", "global_target", "statistic_targets",
    "user_target", "image_reference", "push_proxy_result",
]
