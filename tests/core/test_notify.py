import asyncio
from unittest.mock import AsyncMock, patch

from app.core.notify import (
    DispatchResult,
    NotifyPayload,
    NotifyTarget,
    dispatch,
    dispatch_task_report,
    send_test_notification,
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
        result = _run(dispatch(NotifyPayload(title="标题", text="正文"), [target]))

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
        result = _run(dispatch(NotifyPayload(title="标题", text="正文"), [target]))

    assert list(result.failed) == ["测试系统"]
    assert list(result.succeeded) == ["测试邮件", "测试 ServerChan"]
    assert notify.calls == ["邮件", "ServerChan"]


def test_dispatch_skips_disabled_webhook_channel() -> None:
    from app.core.notify import _webhooks

    webhooks = _webhooks(
        {
            "hook-1": _Webhook(enabled=True, name="启用"),
            "hook-2": _Webhook(enabled=False, name="禁用"),
        }
    )
    assert [uid for uid, _ in webhooks] == ["hook-1"]

    notify = _Notify()
    target = NotifyTarget(name="测试", webhooks=webhooks)

    with patch("app.core.notify.Notify", notify):
        result = _run(dispatch(NotifyPayload(title="标题", text="正文"), [target]))

    assert result.attempted == 1
    assert list(result.succeeded) == ["测试 Webhook 启用"]


class _Task:
    def __init__(self) -> None:
        self.game_sign_summary_consumed = False

    def _delivery(self, delivered=(), pending=()):
        self.game_sign_summary_delivered = delivered
        self.game_sign_summary_pending = pending


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


def test_dispatch_task_report_publishes_failure_notice() -> None:
    class _FailingMailNotify(_Notify):
        async def send_mail(self, **kwargs) -> bool:
            self.calls.append("邮件")
            return False

    task = _Task()
    task.task_id = "task-1"
    target = NotifyTarget(name="全局", mail_to="user@example.com")

    with (
        patch("app.core.notify.Notify", _FailingMailNotify()),
        patch("app.core.ws.Publisher.send", new_callable=AsyncMock) as publish,
    ):
        result = _run(
            dispatch_task_report(
                NotifyPayload(title="报告", text="正文"), [target], task
            )
        )

    assert result.failed == ("全局邮件",)
    publish.assert_awaited_once()
    assert publish.await_args.kwargs["id"] == "task-1"
    assert publish.await_args.kwargs["type"] == "task.notice"
    notice = publish.await_args.kwargs["data"]
    assert notice.level == "warning"
    assert "全局邮件" in notice.message


def test_send_test_notification_passes_through_injected_notifier() -> None:
    notify = _Notify()
    seen: dict[str, object] = {}

    async def _capture(payload, targets, **kwargs):
        seen["kwargs"] = kwargs
        return DispatchResult()

    with patch("app.core.notify.dispatch", _capture):
        _run(send_test_notification(notifier=notify))

    assert seen["kwargs"]["notifier"] is notify


def test_target_channels_enumerates_all_channels_in_order() -> None:
    """全开目标的渠道清单：成员、顺序、Webhook 稳定 ID 与显示名分离。"""

    from app.core.notify import _target_channels

    target = NotifyTarget(
        name="全局",
        system=True,
        mail_to="user@example.com",
        serverchan_key="send-key",
        cmcc_newmsg_api_key="cmcc-key",
        webhooks=(
            ("hook-1", _Webhook(name="值班群")),
            ("hook-2", _Webhook()),
        ),
        koishi=True,
        openclaw_weixin=True,
        openclaw_qq=True,
    )

    channels = _target_channels(target)

    assert list(channels) == [
        "全局系统",
        "全局邮件",
        "全局 ServerChan",
        "全局 中国移动5G短信",
        "全局 Webhook hook-1",
        "全局 Webhook hook-2",
        "全局 Koishi",
        "全局 微信（iLink）",
        "全局 QQ（官方机器人）",
    ]
    # 键是稳定投递 ID（uid），值是含配置名的显示名；同名 Webhook 键不同
    assert channels["全局 Webhook hook-1"] == "全局 Webhook 值班群"
    assert channels["全局 Webhook hook-2"] == "全局 Webhook 值班群"


def test_dispatch_empty_recipient_warn_policy_counts_failure() -> None:
    """空收件地址 + warn 策略：不发送但计入失败（收件配置为空是一种故障）。"""

    notify = _Notify()
    target = NotifyTarget(name="测试", mail_to="", empty_policy="warn")

    with patch("app.core.notify.Notify", notify):
        result = _run(dispatch(NotifyPayload(title="标题", text="正文"), [target]))

    assert list(result.failed) == ["测试邮件"]
    assert result.attempted == 1
    assert notify.calls == []


def test_dispatch_empty_recipient_skip_policy_not_attempted() -> None:
    """空收件密钥 + skip 策略：跳过且不计数（渠道视为未配置）。"""

    target = NotifyTarget(name="测试", serverchan_key="", empty_policy="skip")

    with patch("app.core.notify.Notify", _Notify()):
        result = _run(dispatch(NotifyPayload(title="标题", text="正文"), [target]))

    assert result.attempted == 0
    assert result.failed == ()
    assert result.succeeded == ()


def test_dispatch_empty_recipient_send_policy_still_sends() -> None:
    """空收件地址 + send 策略：照常发送，成败交给传输层判定。"""

    notify = _Notify()
    target = NotifyTarget(name="测试", mail_to="", empty_policy="send")

    with patch("app.core.notify.Notify", notify):
        result = _run(dispatch(NotifyPayload(title="标题", text="正文"), [target]))

    assert result.attempted == 1
    assert list(result.succeeded) == ["测试邮件"]
    assert notify.calls == ["邮件"]


def test_channel_registry_entries_are_complete() -> None:
    """注册表完整性：每条渠道必有发送闭包，有收件门控必有告警文案。"""

    from app.core.notify import (
        _CHANNELS_AFTER_WEBHOOKS,
        _CHANNELS_BEFORE_WEBHOOKS,
    )

    specs = _CHANNELS_BEFORE_WEBHOOKS + _CHANNELS_AFTER_WEBHOOKS

    assert len(specs) == 7
    for spec in specs:
        assert spec.send is not None
        if spec.recipient is not None:
            assert spec.hint is not None


def test_dispatch_sends_all_channels_in_order() -> None:
    """全开目标的发送顺序与结果命名：与渠道清单同序，逐渠道隔离成败。"""

    class _FullNotify(_Notify):
        async def send_cmcc_newmsg(self, **kwargs) -> None:
            self.calls.append("中国移动5G短信")

        async def send_openclaw_weixin(self, **kwargs) -> None:
            self.calls.append("微信（iLink）")

        async def send_openclaw_qq(self, **kwargs) -> None:
            self.calls.append("QQ（官方机器人）")

    notify = _FullNotify()
    target = NotifyTarget(
        name="全局",
        system=True,
        mail_to="user@example.com",
        serverchan_key="send-key",
        cmcc_newmsg_api_key="cmcc-key",
        webhooks=(("hook-1", _Webhook()),),
        koishi=True,
        openclaw_weixin=True,
        openclaw_qq=True,
    )

    with patch("app.core.notify.Notify", notify):
        result = _run(
            dispatch(
                NotifyPayload(title="标题", text="正文", html="<p>正文</p>"),
                [target],
            )
        )

    assert notify.calls == [
        "系统",
        "邮件",
        "ServerChan",
        "中国移动5G短信",
        "Webhook",
        "Koishi",
        "微信（iLink）",
        "QQ（官方机器人）",
    ]
    # _Notify.send_koishi 首次返回 False，验证失败不影响其他渠道计数
    assert result.attempted == 8
    assert list(result.failed) == ["全局 Koishi"]
    assert list(result.succeeded_ids) == [
        "全局系统",
        "全局邮件",
        "全局 ServerChan",
        "全局 中国移动5G短信",
        "全局 Webhook hook-1",
        "全局 微信（iLink）",
        "全局 QQ（官方机器人）",
    ]


def test_send_test_notification_defaults_to_global_notifier() -> None:
    seen: dict[str, object] = {}

    async def _capture(payload, targets, **kwargs):
        seen["kwargs"] = kwargs
        return DispatchResult()

    with patch("app.core.notify.dispatch", _capture):
        _run(send_test_notification())

    assert seen["kwargs"]["notifier"] is None
