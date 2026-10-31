"""本地通知的发送器与装配契约。"""

from typing import Protocol


class NotificationSender(Protocol):
    def __call__(
        self,
        *,
        title: str,
        message: str,
        app_name: str,
        app_icon: str,
        timeout: int,
        ticker: str,
        toast: bool,
    ) -> None: ...


class NotificationAPI(Protocol):
    def prepare_sender(self) -> NotificationSender: ...


class PrepareSender(Protocol):
    def __call__(self) -> NotificationSender: ...
