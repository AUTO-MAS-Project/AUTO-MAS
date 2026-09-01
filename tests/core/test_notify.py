import asyncio
from unittest.mock import patch

from app.core.notify import DispatchResult, NotifyPayload, NotifyTarget, dispatch
from app.tools.game_sign_notify import (
    dispatch_task_report,
    finalize_task_game_sign_notification,
)


class _Webhook:
    def __init__(self, enabled: bool = True, name: str = "值班群") -> None:
        self._enabled = enabled
        self._name = name

    def get(self, group: str, key: str) -> str | bool:
        assert group == "Info"
        if key == "Name":
            return self._name
        assert key == "Enabled"
        return self._enabled


class _Notify:
    """记录渠道调用; 默认全部成功, 失败行为由子类覆盖。"""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.sent: list[str] = []
        self.koishi_attempts = 0

    async def send_mail(self, **kwargs) -> bool:
        self.calls.append("邮件")
        self.sent.append(str(kwargs["content"]))
        return True

    async def ServerChanPush(self, **kwargs) -> None:
        self.calls.append("ServerChan")
        self.sent.append(str(kwargs["content"]))

    async def WebhookPush(self, **kwargs) -> None:
        self.calls.append("Webhook")
        self.sent.append(str(kwargs["content"]))

    async def push_plyer(self, **kwargs) -> None:
        self.calls.append("系统")
        self.sent.append(str(kwargs["message"]))

    async def send_koishi(self, message: str) -> bool:
        self.calls.append("Koishi")
        self.sent.append(message)
        self.koishi_attempts += 1
        return self.koishi_attempts > 1


def _run(awaitable):
    return asyncio.run(awaitable)


def test_dispatch_isolates_false_result_and_names_webhook() -> None:
    class _FailingMailNotify(_Notify):
        async def send_mail(self, **kwargs) -> bool:
            self.calls.append("邮件")
            self.sent.append(str(kwargs["content"]))
            return False

    notify = _FailingMailNotify()
    target = NotifyTarget(
        name="测试",
        mail_to="user@example.com",
        serverchan_key="send-key",
        webhooks=(("hook-1", _Webhook()),),
    )

    with patch("app.core.notify.Notify", notify):
        result = _run(
            dispatch(
                NotifyPayload(title="标题", text="正文", html="<p>正文</p>"),
                [target],
            )
        )

    assert list(result.failed) == ["测试邮件"]
    assert list(result.succeeded) == ["测试 ServerChan", "测试 Webhook 值班群"]
    assert result.attempted == 3
    assert notify.calls == ["邮件", "ServerChan", "Webhook"]


def test_dispatch_retries_false_result() -> None:
    notify = _Notify()
    target = NotifyTarget(name="测试", koishi=True)

    with patch("app.core.notify.Notify", notify):
        result = _run(
            dispatch(
                NotifyPayload(title="标题", text="正文", html="<p>正文</p>"),
                [target],
                attempts=2,
            )
        )

    assert list(result.failed) == []
    assert result.attempted == 1
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
        result = _run(
            dispatch(NotifyPayload(title="标题", text="正文"), [target])
        )

    assert list(result.failed) == ["全局 Webhook 值班群"]


def test_dispatch_continues_after_system_failure() -> None:
    class _SystemFailingNotify(_Notify):
        async def push_plyer(self, **kwargs) -> None:
            raise RuntimeError("plyer 未初始化")

    notify = _SystemFailingNotify()
    target = NotifyTarget(
        name="测试",
        system=True,
        mail_to="user@example.com",
        serverchan_key="send-key",
    )

    with patch("app.core.notify.Notify", notify):
        result = _run(
            dispatch(NotifyPayload(title="标题", text="正文"), [target])
        )

    assert list(result.failed) == ["测试系统"]
    assert list(result.succeeded) == ["测试邮件", "测试 ServerChan"]
    assert notify.calls == ["邮件", "ServerChan"]


def test_dispatch_skips_disabled_webhook_channel() -> None:
    from app.core.notify import _webhooks

    webhooks = _webhooks(
        {"hook-1": _Webhook(enabled=True, name="启用"), "hook-2": _Webhook(enabled=False, name="禁用")}
    )
    assert [uid for uid, _ in webhooks] == ["hook-1"]

    notify = _Notify()
    target = NotifyTarget(name="测试", webhooks=webhooks)

    with patch("app.core.notify.Notify", notify):
        result = _run(
            dispatch(NotifyPayload(title="标题", text="正文"), [target])
        )

    assert result.attempted == 1
    assert list(result.succeeded) == ["测试 Webhook 启用"]


class _Task:
    def __init__(self) -> None:
        self.game_sign_summary_consumed = False

    def _delivery(self, delivered=(), pending=()):
        self.game_sign_summary_delivered = delivered
        self.game_sign_summary_pending = pending


def test_finalize_consumes_only_after_actual_delivery() -> None:
    # 零实际渠道 (无 delivered): 不得消费
    zero = _Task()
    finalize_task_game_sign_notification(zero, True, DispatchResult())
    assert zero.game_sign_summary_consumed is False

    # 部分失败: 不消费
    partial = _Task()
    partial._delivery(delivered=("全局邮件",), pending=("全局 ServerChan",))
    finalize_task_game_sign_notification(partial, True, DispatchResult())
    assert partial.game_sign_summary_consumed is False

    # 全部渠道成功: 消费
    success = _Task()
    success._delivery(delivered=("全局邮件", "全局 ServerChan"), pending=())
    finalize_task_game_sign_notification(success, True, DispatchResult())
    assert success.game_sign_summary_consumed is True


def test_dispatch_task_report_retries_only_failed_channels() -> None:
    """多脚本任务: 第二批报告只把汇总重发给上次失败的渠道,
    已送达渠道收到的报告不含汇总, 避免重复。"""

    notify = _Notify()
    target = NotifyTarget(
        name="全局",
        mail_to="user@example.com",
        serverchan_key="send-key",
    )
    task = _Task()
    summary = "签到情况: 小明: 签到成功"
    payload = NotifyPayload(title="报告", text=f"正文\n\n{summary}", html=None)

    class _FirstFailingNotify(_Notify):
        def __init__(self) -> None:
            super().__init__()
            self.mail_attempts = 0

        async def send_mail(self, **kwargs) -> bool:
            self.calls.append("邮件")
            self.sent.append(str(kwargs["content"]))
            self.mail_attempts += 1
            return self.mail_attempts > 1

    notify = _FirstFailingNotify()
    with patch("app.core.notify.Notify", notify):
        result = _run(
            dispatch_task_report(payload, [target], task, summary_text=summary)
        )

    # 第一次: 邮件失败, ServerChan 成功 → 汇总不消费, delivered 记录 ServerChan
    assert list(result.failed) == ["全局邮件"]
    assert task.game_sign_summary_delivered == {"全局 ServerChan"}
    assert task.game_sign_summary_pending == ("全局邮件",)
    assert task.game_sign_summary_consumed is False

    # 第二次: 只向失败渠道重发含汇总的载荷; 已送达渠道收到不含汇总的载荷
    notify.calls.clear()
    notify.sent.clear()
    with patch("app.core.notify.Notify", notify):
        result = _run(
            dispatch_task_report(payload, [target], task, summary_text=summary)
        )

    assert list(result.failed) == []
    assert task.game_sign_summary_delivered == {"全局 ServerChan", "全局邮件"}
    assert task.game_sign_summary_pending == ()
    # 邮件拿到含汇总的重试版, ServerChan 只拿到去掉汇总的报告
    assert "签到情况" in notify.sent[0]
    assert "签到情况" not in notify.sent[1]


def test_dispatch_task_report_zero_targets_keeps_summary() -> None:
    task = _Task()
    summary = "签到情况: 小明: 签到成功"

    with patch("app.core.notify.Notify", _Notify()):
        result = _run(
            dispatch_task_report(
                NotifyPayload(title="报告", text=f"正文\n\n{summary}", html=None),
                [],
                task,
                summary_text=summary,
            )
        )

    assert result.attempted == 0
    assert task.game_sign_summary_delivered == set()
    assert task.game_sign_summary_pending == ()
    assert task.game_sign_summary_consumed is False
