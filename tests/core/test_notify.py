import asyncio
from unittest.mock import patch

from app.core.notify import NotifyPayload, NotifyTarget, dispatch


class _Webhook:
    def get(self, group: str, key: str) -> str:
        assert (group, key) == ("Info", "Name")
        return "值班群"


class _Notify:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.koishi_attempts = 0

    async def send_mail(self, **kwargs) -> bool:
        self.calls.append("邮件")
        return False

    async def ServerChanPush(self, **kwargs) -> None:
        self.calls.append("ServerChan")

    async def WebhookPush(self, **kwargs) -> None:
        self.calls.append("Webhook")

    async def send_koishi(self, message: str) -> bool:
        self.calls.append("Koishi")
        self.koishi_attempts += 1
        return self.koishi_attempts > 1


def test_dispatch_isolates_false_result_and_names_webhook() -> None:
    notify = _Notify()
    target = NotifyTarget(
        name="测试",
        mail_to="user@example.com",
        serverchan_key="send-key",
        webhooks=(("hook-1", _Webhook()),),
    )

    with patch("app.core.notify.Notify", notify):
        failed = asyncio.run(
            dispatch(NotifyPayload("标题", "正文", "<p>正文</p>"), [target])
        )

    assert failed == ["测试邮件"]
    assert notify.calls == ["邮件", "ServerChan", "Webhook"]


def test_dispatch_retries_false_result() -> None:
    notify = _Notify()
    target = NotifyTarget(name="测试", koishi=True)

    with patch("app.core.notify.Notify", notify):
        failed = asyncio.run(
            dispatch(
                NotifyPayload("标题", "正文", "<p>正文</p>"),
                [target],
                attempts=2,
            )
        )

    assert failed == []
    assert notify.calls == ["Koishi", "Koishi"]


def test_dispatch_reports_named_webhook_failure() -> None:
    class _FailingWebhookNotify(_Notify):
        async def WebhookPush(self, **kwargs) -> bool:
            return False

    notify = _FailingWebhookNotify()
    target = NotifyTarget(
        name="全局",
        webhooks=(("hook-1", _Webhook()),),
    )

    with patch("app.core.notify.Notify", notify):
        failed = asyncio.run(dispatch(NotifyPayload("标题", "正文"), [target]))

    assert failed == ["全局 Webhook 值班群"]
