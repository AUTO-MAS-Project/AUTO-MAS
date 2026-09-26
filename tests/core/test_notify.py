import asyncio
import inspect
from dataclasses import replace
from unittest.mock import AsyncMock, patch

from app.core import notify as notify_module
from app.core.notify import (
    Notifier,
    NotifyPayload,
    dispatch,
    dispatch_task_report,
    global_target,
    user_target,
)
from app.core.notify_channels import get_notify_channels
from app.core.notify_render import render_for_target
from app.models.notification import (
    NotificationCapabilities,
    NotificationImage,
    NotificationSummary,
    image_reference,
)

_UNSET = object()


class _Webhook:
    def __init__(
        self,
        enabled: bool = True,
        name: str = "值班群",
        *,
        url: str = "https://example.com/webhook",
        template: str = "",
        headers: str = "{ }",
        method: str = "POST",
    ) -> None:
        self._enabled = enabled
        self._name = name
        self._data = {
            "Url": url,
            "Template": template,
            "Headers": headers,
            "Method": method,
        }

    def get(self, group: str, key: str) -> str | bool:
        if group == "Info":
            if key == "Name":
                return self._name
            assert key == "Enabled"
            return self._enabled
        assert group == "Data"
        return self._data[key]


class _Webhooks:
    def __init__(self, webhooks: list[tuple[str, _Webhook]]) -> None:
        self._items = [(str(uid), webhook) for uid, webhook in webhooks]

    def items(self) -> list[tuple[str, _Webhook]]:
        return list(self._items)


_SWITCHES = {
    "IfPushPlyer": False,
    "IfSendMail": False,
    "IfServerChan": False,
    "IfKoishiSupport": False,
    "IfCMCCNewMsg": False,
    "IfOpenClawQQ": False,
}
_TEXTS = {
    name: ""
    for name in (
        "SMTPServerAddress",
        "FromAddress",
        "AuthorizationCode",
        "ToAddress",
        "ServerChanKey",
        "KoishiServerAddress",
        "KoishiToken",
        "CMCCNewMsgApiKey",
    )
}


class _Config:
    """同时提供 .get(group, name) 与 .Notify_CustomWebhooks.items() 的鸭子配置。"""

    def __init__(self, values: dict | None = None, webhooks=()) -> None:
        self._values = {**_SWITCHES, **_TEXTS, **(values or {})}
        self.Notify_CustomWebhooks = _Webhooks(webhooks)
        self.reads = 0

    def get(self, group: str, name: str):
        assert group == "Notify"
        self.reads += 1
        return self._values[name]


class _Notify:
    """与 Notifier 协议同名同参的录制发送器（不是 ``**kwargs``）。

    参数名与协议不一致会直接 TypeError，防止发送调用悄悄写错关键字；
    哨兵默认值用于区分“省略参数”与“显式传默认值”。
    """

    def __init__(self, plan: dict[str, list[str]] | None = None) -> None:
        self.calls: list[str] = []
        self.kwargs: list[dict] = []
        self.plan = plan or {}

    async def _run(self, method: str, **kwargs):
        self.calls.append(method)
        self.kwargs.append(
            {k: ("<UNSET>" if v is _UNSET else v) for k, v in kwargs.items()}
        )
        behavior = None
        seq = self.plan.get(method)
        if seq:
            count = self.calls.count(method)
            behavior = seq[count - 1] if count <= len(seq) else None
        if behavior == "raise":
            raise RuntimeError("渠道异常")
        return False if behavior == "false" else None

    async def push_plyer(self, title=_UNSET, message=_UNSET, ticker=_UNSET, t=_UNSET):
        return await self._run(
            "push_plyer", title=title, message=message, ticker=ticker, t=t
        )

    async def send_mail(
        self,
        mode=_UNSET,
        title=_UNSET,
        content=_UNSET,
        to_address=_UNSET,
        *,
        images=_UNSET,
    ):
        return await self._run(
            "send_mail",
            mode=mode,
            title=title,
            content=content,
            to_address=to_address,
            images=images,
        )

    async def ServerChanPush(self, title=_UNSET, content=_UNSET, send_key=_UNSET):
        return await self._run(
            "ServerChanPush", title=title, content=content, send_key=send_key
        )

    async def send_cmcc_newmsg(self, title=_UNSET, content=_UNSET, api_key=_UNSET):
        return await self._run(
            "send_cmcc_newmsg", title=title, content=content, api_key=api_key
        )

    async def WebhookPush(
        self, title=_UNSET, content=_UNSET, webhook=_UNSET, *, images=_UNSET
    ):
        return await self._run(
            "WebhookPush",
            title=title,
            content=content,
            webhook=webhook,
            images=images,
        )

    async def send_koishi(self, message=_UNSET, msgtype=_UNSET, client_name=_UNSET):
        return await self._run(
            "send_koishi", message=message, msgtype=msgtype, client_name=client_name
        )

    async def send_openclaw_qq(self, title=_UNSET, content=_UNSET):
        return await self._run("send_openclaw_qq", title=title, content=content)


PAYLOAD = NotifyPayload(title="标题", text="正文", html="<p>正文</p>")


def _run(awaitable):
    return asyncio.run(awaitable)


def _global_target(
    config: _Config,
    *,
    include_system: bool = False,
    empty_policy="send",
    system_timeout_seconds: int | None = None,
):
    with patch.object(notify_module, "Config", config):
        return global_target(
            include_system=include_system,
            empty_policy=empty_policy,
            system_timeout_seconds=system_timeout_seconds,
        )


def _protocol_members():
    return {
        name: method
        for name, method in inspect.getmembers(Notifier, inspect.isfunction)
        if not name.startswith("__")
    }


def test_notifier_fake_matches_protocol_signatures() -> None:
    """录制发送器与 Notifier 协议逐方法同参同名同默认形态（真实实现的对比
    见 test_real_notify_implementation_matches_protocol）。"""

    members = _protocol_members()
    assert sorted(members) == [
        "ServerChanPush",
        "WebhookPush",
        "push_plyer",
        "send_cmcc_newmsg",
        "send_koishi",
        "send_mail",
        "send_openclaw_qq",
    ]
    for name, protocol_method in members.items():
        fake = getattr(_Notify, name, None)
        assert fake is not None, name
        proto = inspect.signature(protocol_method).parameters
        fake_params = inspect.signature(fake).parameters
        assert list(proto) == list(fake_params), name
        for param_name, proto_param in proto.items():
            if param_name == "self":
                continue
            fake_param = fake_params[param_name]
            assert proto_param.kind == fake_param.kind, (name, param_name)
            # 哨兵默认值必须存在（用于区分省参与显式传默认值），
            # 协议里有默认值的参数假实现里也得有
            assert fake_param.default is not fake_param.empty, (name, param_name)


def test_real_notify_implementation_matches_protocol() -> None:
    """仓库无类型检查器，这是 Notifier 协议与真实 Notify 实现不漂移的唯一断言。"""

    from app.services.notification import Notification

    for name, protocol_method in _protocol_members().items():
        # 取类而不是实例：实例方法是绑定签名，会少掉 self，与协议不可比
        real = getattr(Notification, name, None)
        assert real is not None, name
        real_params = inspect.signature(real).parameters
        assert list(real_params) == list(
            inspect.signature(protocol_method).parameters
        ), name
        for param_name, param in real_params.items():
            if param_name == "self":
                continue
            assert (
                param.kind
                == inspect.signature(protocol_method).parameters[param_name].kind
            ), (name, param_name)
            assert (param.default is param.empty) == (
                inspect.signature(protocol_method).parameters[param_name].default
                is inspect.signature(protocol_method).parameters[param_name].empty
            ), (name, param_name)


def test_dispatch_isolates_false_result_and_names_webhook() -> None:
    config = _Config(
        {
            "IfSendMail": True,
            "ToAddress": "user@example.com",
            "IfServerChan": True,
            "ServerChanKey": "send-key",
        },
        webhooks=[("hook-1", _Webhook(name="值班群"))],
    )
    notify = _Notify({"send_mail": ["false"]})

    result = _run(dispatch(PAYLOAD, [_global_target(config)], notifier=notify))

    assert list(result.failed) == ["全局邮件"]
    assert list(result.succeeded) == ["全局 ServerChan", "全局 Webhook 值班群"]
    assert result.attempted == 3
    assert notify.calls == ["send_mail", "ServerChanPush", "WebhookPush"]
    assert notify.kwargs[0]["to_address"] == "user@example.com"


def test_dispatch_retries_false_result() -> None:
    config = _Config({"IfKoishiSupport": True})
    notify = _Notify({"send_koishi": ["false"]})

    result = _run(
        dispatch(
            PAYLOAD,
            [_global_target(config)],
            attempts=2,
            notifier=notify,
        )
    )

    assert list(result.failed) == []
    assert result.attempted == 1
    assert notify.calls == ["send_koishi", "send_koishi"]


def test_dispatch_reports_named_webhook_failure() -> None:
    config = _Config(webhooks=[("hook-1", _Webhook())])
    notify = _Notify({"WebhookPush": ["false"]})

    result = _run(dispatch(PAYLOAD, [_global_target(config)], notifier=notify))

    assert list(result.failed) == ["全局 Webhook 值班群"]


def test_mail_keeps_html_template_signature_without_adding_another() -> None:
    config = _Config({"IfSendMail": True, "ToAddress": "user@example.com"})
    notify = _Notify()

    _run(dispatch(PAYLOAD, [_global_target(config)], notifier=notify))

    assert notify.kwargs[0]["content"] == "<p>正文</p>"


def test_dispatch_continues_after_system_failure() -> None:
    config = _Config(
        {
            "IfPushPlyer": True,
            "IfSendMail": True,
            "ToAddress": "user@example.com",
            "IfServerChan": True,
            "ServerChanKey": "send-key",
        }
    )
    notify = _Notify({"push_plyer": ["raise"]})

    result = _run(
        dispatch(
            PAYLOAD,
            [_global_target(config, include_system=True)],
            notifier=notify,
        )
    )

    assert list(result.failed) == ["全局系统"]
    assert list(result.succeeded) == ["全局邮件", "全局 ServerChan"]
    assert notify.calls == ["push_plyer", "send_mail", "ServerChanPush"]


def test_render_failure_isolated_to_one_target() -> None:
    config = _Config(
        {
            "IfSendMail": True,
            "ToAddress": "user@example.com",
            "IfServerChan": True,
            "ServerChanKey": "send-key",
        }
    )
    target = _global_target(config)
    channel, channel_target = target.channels[0]
    broken_target = replace(
        target,
        channels=(
            (
                channel,
                replace(
                    channel_target,
                    capabilities=NotificationCapabilities(formats=()),
                ),
            ),
            *target.channels[1:],
        ),
    )
    notify = _Notify()

    result = _run(dispatch(PAYLOAD, [broken_target], notifier=notify))

    assert result.failed == ("全局邮件",)
    assert result.succeeded == ("全局 ServerChan",)
    assert notify.calls == ["ServerChanPush"]


def test_dispatch_skips_disabled_webhook_channel() -> None:
    config = _Config(
        webhooks=[
            ("hook-1", _Webhook(enabled=True, name="启用")),
            ("hook-2", _Webhook(enabled=False, name="禁用")),
        ]
    )
    notify = _Notify()

    result = _run(dispatch(PAYLOAD, [_global_target(config)], notifier=notify))

    assert result.attempted == 1
    assert list(result.succeeded) == ["全局 Webhook 启用"]


def test_webhook_succeeded_ids_use_uid_while_succeeded_uses_name() -> None:
    config = _Config(
        webhooks=[("hook-1", _Webhook(name="值班群")), ("hook-2", _Webhook(name=""))]
    )
    notify = _Notify()

    result = _run(dispatch(PAYLOAD, [_global_target(config)], notifier=notify))

    assert list(result.succeeded) == ["全局 Webhook 值班群", "全局 Webhook hook-2"]
    assert list(result.succeeded_ids) == ["全局 Webhook hook-1", "全局 Webhook hook-2"]


def test_dispatch_channel_names_are_verbatim() -> None:
    config = _Config(
        {
            "IfCMCCNewMsg": True,
            "CMCCNewMsgApiKey": "ak_x",
            "IfKoishiSupport": True,
            "IfOpenClawQQ": True,
        }
    )

    result = _run(dispatch(PAYLOAD, [_global_target(config)], notifier=_Notify()))

    assert list(result.succeeded) == [
        "全局 中国移动5G短信",
        "全局 Koishi",
        "全局 QQ（官方机器人）",
    ]


def test_system_notification_fallbacks() -> None:
    config = _Config({"IfPushPlyer": True})
    notify = _Notify()

    result = _run(
        dispatch(
            PAYLOAD,
            [_global_target(config, include_system=True)],
            notifier=notify,
        )
    )

    assert result.attempted == 1
    # 三个 or 回退：system_* 缺省时标题/正文/ticker 落到通用字段
    assert notify.kwargs[0] == {
        "title": "标题",
        "message": "正文",
        "ticker": "标题",
        "t": 5,
    }


def test_system_notification_passes_override_values() -> None:
    config = _Config({"IfPushPlyer": True})
    notify = _Notify()

    _run(
        dispatch(
            NotifyPayload(
                title="标题",
                text="正文",
                summary=NotificationSummary(
                    title="系统标题", text="系统正文\n系统ticker"
                ),
            ),
            [_global_target(config, include_system=True, system_timeout_seconds=7)],
            notifier=notify,
        )
    )

    assert notify.kwargs[0] == {
        "title": "系统标题",
        "message": "系统正文\n系统ticker",
        "ticker": "系统正文",
        "t": 7,
    }


def test_empty_recipient_warn_records_failure() -> None:
    config = _Config(
        {
            "IfSendMail": True,
            "ToAddress": "",
            "IfServerChan": True,
            "ServerChanKey": "send-key",
        }
    )
    notify = _Notify()

    result = _run(
        dispatch(
            PAYLOAD,
            [_global_target(config, empty_policy="warn")],
            notifier=notify,
        )
    )

    # 空收件人按失败记账（attempted+1 且进 failed），邮件不实际发送
    assert list(result.failed) == ["全局邮件"]
    assert result.attempted == 2
    assert notify.calls == ["ServerChanPush"]


def test_target_is_a_config_snapshot() -> None:
    config = _Config(
        {"IfSendMail": True, "ToAddress": "user@example.com", "IfServerChan": True}
    )
    target = _global_target(config)
    reads_after_construction = config.reads

    _run(dispatch(PAYLOAD, [target], notifier=_Notify()))

    # 构造后固定为快照：分发全程不再读配置
    assert config.reads == reads_after_construction


def test_empty_recipient_skip_policy_silently_omits() -> None:
    config = _Config({"IfSendMail": True, "ToAddress": ""})

    result = _run(
        dispatch(
            PAYLOAD,
            [_global_target(config, empty_policy="skip")],
            notifier=_Notify(),
        )
    )

    # skip 策略下空收件人不发送、也不记失败
    assert result.attempted == 0
    assert result.failed == ()
    assert result.succeeded == ()


def test_same_name_webhooks_keep_distinct_delivery_ids() -> None:
    config = _Config(
        webhooks=[("a", _Webhook(name="同名")), ("b", _Webhook(name="同名"))]
    )

    result = _run(dispatch(PAYLOAD, [_global_target(config)], notifier=_Notify()))

    # 显示名相同但补发记录按 uid 区分
    assert list(result.succeeded) == ["全局 Webhook 同名", "全局 Webhook 同名"]
    assert list(result.succeeded_ids) == ["全局 Webhook a", "全局 Webhook b"]


def test_webhook_snapshot_keeps_config_and_capabilities_together() -> None:
    webhook = _Webhook(
        url="https://example.com/old",
        template='{"msgtype": "markdown", "content": "{content}"}',
        headers='{"X-Test": "old"}',
    )
    target = _global_target(_Config(webhooks=[("hook-1", webhook)]))
    channel_target = target.channels[0][1]
    webhook._data.update(
        Url="https://example.com/new",
        Template='{"content": "{content}"}',
        Headers='{"X-Test": "new"}',
    )

    notify = _Notify()
    _run(dispatch(PAYLOAD, [target], notifier=notify))

    snapshot = notify.kwargs[0]["webhook"]
    assert snapshot.url == "https://example.com/old"
    assert snapshot.headers == '{"X-Test": "old"}'
    assert channel_target.capabilities.formats == ("markdown", "text")


def test_compact_statistics_enable_webhook_summary_only_for_that_target_set() -> None:
    from app.core.notify import statistic_targets

    config = _Config({"IfSendStatistic": True}, webhooks=[("hook-1", _Webhook())])
    with patch.object(notify_module, "Config", config):
        targets = statistic_targets(None, compact_summary=True)

    webhook_target = targets[0].channels[0][1]
    assert webhook_target.summary_policy == "preferred"


def test_task_report_summary_does_not_shorten_default_webhook_content() -> None:
    webhook = _Webhook()
    target = _global_target(_Config(webhooks=[("hook-1", webhook)]))
    notify = _Notify()
    payload = NotifyPayload(
        title="任务报告",
        text="完整任务报告",
        summary=NotificationSummary(text="已完成用户数: 2, 未完成用户数: 0"),
    )

    _run(dispatch(payload, [target], notifier=notify))

    assert notify.kwargs[0]["content"].startswith("完整任务报告")
    assert "已完成用户数" not in notify.kwargs[0]["content"]


def test_user_target_uses_user_scope_and_warn_policy() -> None:
    config = _Config(
        {
            "IfSendMail": True,
            "ToAddress": "",
            "IfServerChan": True,
            "ServerChanKey": "send-key",
        },
        webhooks=[("hook-1", _Webhook(name="值班群"))],
    )
    notify = _Notify()

    result = _run(dispatch(PAYLOAD, [user_target(config)], notifier=notify))

    # 用户级只有邮件 / Server酱 / Webhook；空收件人按 warn 记失败，前缀为「用户」
    assert list(result.failed) == ["用户邮件"]
    assert list(result.succeeded) == ["用户 ServerChan", "用户 Webhook 值班群"]
    assert notify.calls == ["ServerChanPush", "WebhookPush"]


def test_dispatch_honors_skip_by_name_and_by_id() -> None:
    config = _Config(
        {
            "IfSendMail": True,
            "ToAddress": "user@example.com",
            "IfKoishiSupport": True,
        },
        webhooks=[("hook-1", _Webhook()), ("hook-2", _Webhook(name="二番"))],
    )

    result = _run(
        dispatch(
            PAYLOAD,
            [_global_target(config)],
            skip_channels=("全局邮件", "全局 Koishi"),
            skip_channel_ids=("全局 Webhook hook-1",),
            notifier=_Notify(),
        )
    )

    assert result.attempted == 1
    assert list(result.succeeded) == ["全局 Webhook 二番"]


class _Task:
    def __init__(self) -> None:
        self.game_sign_summary_consumed = False


def test_dispatch_task_report_retries_only_failed_channels() -> None:
    """多脚本任务: 第二批报告只把汇总重发给上次失败的渠道,
    已送达渠道收到的报告不含汇总, 避免重复。"""

    config = _Config(
        {
            "IfSendMail": True,
            "ToAddress": "user@example.com",
            "IfServerChan": True,
            "ServerChanKey": "send-key",
        }
    )
    task = _Task()
    summary = "签到情况: 小明: 签到成功"
    payload = NotifyPayload(title="报告", text=f"正文\n\n{summary}", html=None)

    notify = _Notify({"send_mail": ["false"]})
    with patch.object(notify_module, "Notify", notify):
        result = _run(
            dispatch_task_report(
                payload, [_global_target(config)], task, summary_text=summary
            )
        )

    # 第一次: 邮件失败, ServerChan 成功 → 汇总不消费, delivered 记录 ServerChan
    assert list(result.failed) == ["全局邮件"]
    assert task.game_sign_summary_delivered == {"全局 ServerChan"}
    assert task.game_sign_summary_pending == ("全局邮件",)
    assert task.game_sign_summary_consumed is False

    # 第二次: 只向失败渠道重发含汇总的载荷; 已送达渠道收到不含汇总的载荷
    notify = _Notify()
    with patch.object(notify_module, "Notify", notify):
        result = _run(
            dispatch_task_report(
                payload, [_global_target(config)], task, summary_text=summary
            )
        )

    assert list(result.failed) == []
    assert task.game_sign_summary_delivered == {"全局 ServerChan", "全局邮件"}
    assert task.game_sign_summary_pending == ()
    # 邮件拿到含汇总的重试版, ServerChan 只拿到去掉汇总的报告
    sent = [kwargs["content"] for kwargs in notify.kwargs]
    assert "签到情况" in sent[0]
    assert "签到情况" not in sent[1]


def test_dispatch_task_report_zero_targets_keeps_summary() -> None:
    task = _Task()
    summary = "签到情况: 小明: 签到成功"

    with patch.object(notify_module, "Notify", _Notify()):
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
    config = _Config({"IfSendMail": True, "ToAddress": "user@example.com"})
    task = _Task()
    task.task_id = "task-1"

    with patch.object(notify_module, "Notify", _Notify({"send_mail": ["false"]})):
        with patch("app.core.ws.Publisher.send", new_callable=AsyncMock) as publish:
            result = _run(
                dispatch_task_report(
                    NotifyPayload(title="报告", text="正文"),
                    [_global_target(config)],
                    task,
                )
            )

    assert result.failed == ("全局邮件",)
    publish.assert_awaited_once()
    assert publish.await_args.kwargs["id"] == "task-1"
    assert publish.await_args.kwargs["type"] == "task.notice"
    notice = publish.await_args.kwargs["data"]
    assert notice.level == "warning"
    assert "全局邮件" in notice.message


def test_descriptor_fields_exist_in_config_and_schema() -> None:
    """描述表字段名两个方向都查：配置类里真的存在，且在下发模型里不会被静默丢弃。"""

    from app.core.config import Config
    from app.models.schema import GlobalConfig_Notify

    for channel in get_notify_channels():
        for items in channel.fields.values():
            for item in items:
                Config.get(item.group, item.name)
                assert item.name in GlobalConfig_Notify.model_fields, item.name
        if channel.enable_field:
            Config.get(*channel.enable_field)
            assert channel.enable_field[1] in GlobalConfig_Notify.model_fields


def test_renderer_inlines_only_referenced_html_images() -> None:
    image = NotificationImage(id="report-shot", data=b"png", alt="失败截图")
    rendered = render_for_target(
        NotifyPayload(
            title="结果",
            text="结果",
            html=(
                f"<p>{image_reference(image.id)}</p>"
                f'<img src="{image_reference(image.id)}" alt="失败截图">'
            ),
            images=(image,),
        ),
        NotificationCapabilities(
            formats=("html", "text"),
            image_presentations=frozenset({"html"}),
            append_signature=False,
        ),
    )

    assert rendered.format == "html"
    assert rendered.content.count(image_reference(image.id)) == 1
    assert "<p>失败截图</p>" in rendered.content
    assert rendered.images == (image,)


def test_renderer_degrades_unavailable_image_to_alt_text() -> None:
    rendered = render_for_target(
        NotifyPayload(
            title="结果",
            text=f"检查 {image_reference('missing-shot')}",
        ),
        NotificationCapabilities(formats=("text",), append_signature=False),
    )

    assert rendered.content == "检查 "
    assert any("不存在的图片 missing-shot" in item for item in rendered.diagnostics)


def test_renderer_uses_alt_text_when_target_cannot_access_image_data() -> None:
    image = NotificationImage(id="local-only", data=b"png", alt="本地图片")
    rendered = render_for_target(
        NotifyPayload(
            title="结果",
            text="结果",
            markdown=f"![本地图片]({image_reference(image.id)})",
            images=(image,),
        ),
        NotificationCapabilities(
            formats=("markdown", "text"),
            image_presentations=frozenset({"markdown"}),
            append_signature=False,
        ),
    )

    assert rendered.content == "本地图片"
    assert rendered.images == ()
    assert any("无法直接显示图片 local-only" in item for item in rendered.diagnostics)


def test_renderer_counts_signature_and_newline_expansion_in_byte_limit() -> None:
    rendered = render_for_target(
        NotifyPayload(
            title="标题",
            text="x" * 35 + "\ny",
            summary=NotificationSummary(text="短摘要"),
        ),
        NotificationCapabilities(
            formats=("text",),
            max_content_utf8_bytes=54,
            double_text_newlines=True,
        ),
        summary_policy="if_over_limit",
    )

    assert rendered.content == "短摘要\n\nAUTO-MAS 敬上"
    assert len(rendered.content.encode("utf-8")) <= 54


def test_renderer_appends_html_signature_only_when_missing() -> None:
    capabilities = NotificationCapabilities(formats=("html",))
    plain = render_for_target(
        NotifyPayload(title="标题", text="正文", html="<p>正文</p>"), capabilities
    )
    signed = render_for_target(
        NotifyPayload(title="标题", text="正文", html="<p>AUTO-MAS 敬上</p>"),
        capabilities,
    )

    assert plain.content.endswith("<p>AUTO-MAS 敬上</p>")
    assert signed.content.count("AUTO-MAS 敬上") == 1


def test_channels_endpoint_returns_metadata_only() -> None:
    from app.api.setting import get_notify_channels as endpoint
    from app.models.ConfigBase import ConfigBase

    with patch.object(
        ConfigBase, "get", side_effect=AssertionError("描述端点不得读取配置")
    ):
        result = _run(endpoint())

    assert result.code == 200
    assert len(result.channels) == 8
    assert [channel.key for channel in result.channels][0] == "system"
    assert result.channels[-1].kind == "policy"
