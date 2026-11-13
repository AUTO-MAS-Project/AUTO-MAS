"""宿主 Notify 单例与真实通知消息类型。"""

from app.core import Notify as Notify
from app.models.notification import NotificationImage, NotifyPayload, image_reference
from app.models.notification.channel import DispatchResult
from app.models.notification.report import TaskResultReport

__all__ = [
    "Notify",
    "DispatchResult",
    "NotificationImage",
    "NotifyPayload",
    "TaskResultReport",
    "image_reference",
]
