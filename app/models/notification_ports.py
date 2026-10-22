"""业务侧可注入的本地提示与草稿测试能力。"""

from dataclasses import dataclass
from typing import Protocol

from app.models.notification import NotifyPayload, WebhookTargetSnapshot


@dataclass(frozen=True)
class LocalNotice:
    title: str
    message: str
    ticker: str
    duration_seconds: int


class LocalNotifier(Protocol):
    async def send_notice(self, notice: LocalNotice) -> None: ...


class WebhookTester(Protocol):
    async def test_webhook(
        self, payload: NotifyPayload, webhook: WebhookTargetSnapshot
    ) -> None: ...


class CommunityNotifier(Protocol):
    async def send(self, results: list[dict[str, object]]) -> list[str]: ...

    async def submit(self, results: list[dict[str, object]]) -> list[str] | None: ...

    async def drain(self, timeout: float) -> bool: ...
