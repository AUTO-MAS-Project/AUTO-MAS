"""从应用生命周期取得通知实例；请求不创建渠道或后台任务。"""

from typing import Annotated

from fastapi import Depends, Request

from app.core.notify import HostNotificationService
from app.models.notification_ports import CommunityNotifier, WebhookTester


def get_notification_service(request: Request) -> HostNotificationService:
    return request.app.state.notifications


def get_webhook_tester(
    notifications: Annotated[
        HostNotificationService, Depends(get_notification_service)
    ],
) -> WebhookTester:
    return notifications


def get_community_notifier(
    notifications: Annotated[
        HostNotificationService, Depends(get_notification_service)
    ],
) -> CommunityNotifier:
    return notifications.community
