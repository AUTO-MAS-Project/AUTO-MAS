import asyncio
import inspect
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import app.core.notify.rendering as _notification_rendering
from app.core import Config
from app.core.notify.bootstrap import (
    get_notify_channel_failures as get_notify_channel_failures,
)
from app.core.notify.bootstrap import get_notify_channels as get_notify_channels
from app.core.notify.manager import NotificationManager as NotificationManager
from app.core.runtime_tasks import OwnedTaskRegistry
from app.models.notification import NotificationSummary, NotifyPayload
from app.models.notification.channel import Notifier
from app.models.notification.community import CommunityNotificationResult
from app.models.notification.report import TaskReportPolicy
from app.models.task import TaskItem

_UNSET = object()


class _Webhook:
    def __init__(self, enabled: bool = True, name: str = "值班群") -> None:
        self._enabled = enabled
        self._name = name
        self.Data = SimpleNamespace(
            Url="https://example.com/webhook",
            Template='{"title": "{title}", "content": "{content}"}',
            Headers="{}",
            Method="POST",
        )

    @property
    def Info(self):
        return SimpleNamespace(Name=self._name, Enabled=self._enabled)

    def get(self, group: str, key: str) -> str | bool:
        values = {
            ("Info", "Name"): self._name,
            ("Info", "Enabled"): self._enabled,
            ("Data", "Url"): "https://example.com/webhook",
            ("Data", "Template"): '{"title": "{title}", "content": "{content}"}',
            ("Data", "Headers"): "{}",
            ("Data", "Method"): "POST",
        }
        return values[(group, key)]


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
        "OpenClawQQAppId",
        "OpenClawQQTargetOpenId",
    )
}


class _NotifyFields:
    def __init__(self, owner):
        self.owner = owner

    def __getattr__(self, name):
        self.owner.reads += 1
        return self.owner._values[name]


class _Config:
    """提供通知分组与 Webhook 集合的配置替身。"""

    def __init__(self, values: dict | None = None, webhooks=()) -> None:
        self._values = {
            **_SWITCHES,
            **_TEXTS,
            "OpenClawQQGroupOpenIds": [],
            "OpenClawQQTargetType": "c2c",
            **(values or {}),
        }
        self.Notify_CustomWebhooks = _Webhooks(webhooks)
        self.reads = 0
        self.Notify = _NotifyFields(self)
        self.setting = self

    def get(self, group: str, name: str):
        assert group == "Notify"
        self.reads += 1
        return self._values[name]


class _Notify:
    """通过统一投递面记录各渠道适配器的实际调用。

    传输方法保留显式参数，防止适配器悄悄写错关键字；
    哨兵默认值用于区分“省略参数”与“显式传默认值”。
    """

    def __init__(self, plan: dict[str, list[str]] | None = None) -> None:
        self.calls: list[str] = []
        self.kwargs: list[dict] = []
        self.plan = plan or {}

    async def send_channel(self, channel, target, rendered):
        return await channel.send(self, target, rendered)

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

    async def send_openclaw_qq(
        self, title=_UNSET, content=_UNSET, *, images=_UNSET, target=_UNSET
    ):
        return await self._run(
            "send_openclaw_qq",
            title=title,
            content=content,
            images=images,
            target=target,
        )


PAYLOAD = NotifyPayload(title="标题", text="正文", html="<p>正文</p>")
_COMMUNITY_RESULTS = (
    CommunityNotificationResult(
        account="summary-account",
        account_uid="summary-uid",
        game="test-game",
        platform="test-platform",
        status="success",
    ),
)


def _run(awaitable):
    return asyncio.run(awaitable)


@contextmanager
def _service(config=None, *, notifier=None):
    from app.core import Notify
    from app.core.notify import manager, tasks
    from app.core.notify.tasks import NotificationTasks

    environment = SimpleNamespace(
        setting=config if config is not None else Config.setting,
        ToolsConfig=Config.ToolsConfig,
        startup_notices=[],
    )
    renderer = _notification_rendering.AsyncNotificationRenderer()
    # 各用例隔离全局实例的资源，实际调用仍经过所有调用方共享的 Notify。
    with (
        patch.object(manager, "Config", environment),
        patch.object(tasks, "RuntimeTasks", OwnedTaskRegistry()),
        patch.dict(
            Notify.__dict__,
            {
                "_channels": get_notify_channels(),
                "_catalog_failures": get_notify_channel_failures(),
                "_transport": notifier if notifier is not None else _Notify(),
                "_renderer": renderer,
                "_runtime_config": SimpleNamespace(read_proxy=lambda: None),
                "tasks": NotificationTasks(),
            },
        ),
    ):
        try:
            yield Notify
        finally:
            renderer.close()


def _global_target(config, **kwargs):
    with _service(config) as notifications:
        return notifications.global_target(**kwargs)


def user_target(config):
    with _service() as notifications:
        return notifications.user_target(config)


async def dispatch(payload, targets, *, notifier, **kwargs):
    with _service(notifier=notifier) as notifications:
        return await notifications.dispatch(payload, targets, **kwargs)


def _protocol_members():
    return {
        name: method
        for name, method in inspect.getmembers(Notifier, inspect.isfunction)
        if not name.startswith("__")
    }


def test_notifier_fake_matches_protocol_signatures() -> None:
    members = _protocol_members()
    assert list(members) == ["send_channel"]
    assert list(inspect.signature(_Notify.send_channel).parameters) == list(
        inspect.signature(Notifier.send_channel).parameters
    )


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
    # 未提供摘要时，系统通知使用通用标题、正文和默认显示时长。
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
                    title="系统标题", text="系统ticker\n系统正文"
                ),
            ),
            [_global_target(config, include_system=True, system_timeout_seconds=7)],
            notifier=notify,
        )
    )

    assert notify.kwargs[0] == {
        "title": "系统标题",
        "message": "系统ticker\n系统正文",
        "ticker": "系统ticker",
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


def test_dispatch_honors_skip_by_id() -> None:
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
            skip_channel_ids=("全局邮件", "全局 Koishi", "全局 Webhook hook-1"),
            notifier=_Notify(),
        )
    )

    assert result.attempted == 1
    assert list(result.succeeded) == ["全局 Webhook 二番"]


class _Task(TaskItem):
    def __init__(self) -> None:
        super().__init__(
            mode="AutoProxy",
            task_id="task-1",
            queue_id=None,
            script_id=None,
            user_id=None,
        )

    def schedule_on_change(self) -> None:
        pass

    async def on_change(self) -> None:
        pass


def test_prepared_task_report_retries_only_failed_channels() -> None:
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
    task.notification_state.results = _COMMUNITY_RESULTS
    payload = NotifyPayload(title="报告", text="正文", html=None)

    notify = _Notify({"send_mail": ["false"]})
    with _service(notifier=notify) as notifications:
        notifications.read_task_report_policy = lambda: TaskReportPolicy(
            result_time="任何时刻", community_enabled=True, wait_seconds=0
        )
        result = _run(
            notifications.prepare_task_report(task).dispatch(
                payload, [_global_target(config)]
            )
        )

    # 第一次: 邮件失败, ServerChan 成功 → 汇总不消费, delivered 记录 ServerChan
    assert list(result.failed) == ["全局邮件"]
    assert task.notification_state.delivered == {"全局 ServerChan"}
    assert task.notification_state.summary_consumed is False

    # 第二次: 只向失败渠道重发含汇总的载荷; 已送达渠道收到不含汇总的载荷
    notify = _Notify()
    with _service(notifier=notify) as notifications:
        notifications.read_task_report_policy = lambda: TaskReportPolicy(
            result_time="任何时刻", community_enabled=True, wait_seconds=0
        )
        result = _run(
            notifications.prepare_task_report(task).dispatch(
                payload, [_global_target(config)]
            )
        )

    assert list(result.failed) == []
    assert task.notification_state.delivered == {"全局 ServerChan", "全局邮件"}
    # 邮件拿到含汇总的重试版, ServerChan 只拿到去掉汇总的报告
    sent = [kwargs["content"] for kwargs in notify.kwargs]
    assert "summary-account" in sent[0]
    assert "summary-account" not in sent[1]


def test_prepared_task_report_zero_targets_keeps_summary() -> None:
    task = _Task()
    task.notification_state.results = _COMMUNITY_RESULTS

    with _service() as notifications:
        notifications.read_task_report_policy = lambda: TaskReportPolicy(
            result_time="任何时刻", community_enabled=True, wait_seconds=0
        )
        result = _run(
            notifications.prepare_task_report(task).dispatch(
                NotifyPayload(title="报告", text="正文", html=None),
                [],
            )
        )

    assert result.attempted == 0
    assert task.notification_state.delivered == set()
    assert task.notification_state.summary_consumed is False


def test_prepared_task_report_publishes_failure_notice() -> None:
    config = _Config({"IfSendMail": True, "ToAddress": "user@example.com"})
    task = _Task()
    task.task_id = "task-1"

    with _service(notifier=_Notify({"send_mail": ["false"]})) as notifications:
        with patch(
            "app.core.notify.Notify.push_system_notice", new_callable=AsyncMock
        ) as publish:
            result = _run(
                notifications.prepare_task_report(task).dispatch(
                    NotifyPayload(title="报告", text="正文"),
                    [_global_target(config)],
                )
            )

    assert result.failed == ("全局邮件",)
    publish.assert_awaited_once()
    assert publish.await_args.kwargs["level"] == "warning"
    assert "全局邮件" in publish.await_args.kwargs["lines"][0]


def test_descriptor_fields_exist_in_config_and_schema() -> None:
    """描述表字段名两个方向都查：配置类里真的存在，且在下发模型里不会被静默丢弃。"""

    from typing import get_args

    from app.config.wire import config_contract
    from app.core import Config
    from app.models.config import GlobalConfig

    notify_contract = config_contract(GlobalConfig).model_fields["Notify"].annotation
    GlobalConfig_Notify = next(
        item for item in get_args(notify_contract) if item is not type(None)
    )

    for channel in get_notify_channels():
        for items in channel.fields.values():
            for item in items:
                getattr(getattr(Config.setting, item.group), item.name)
                assert item.name in GlobalConfig_Notify.model_fields, item.name
        if channel.enable_field:
            getattr(
                getattr(Config.setting, channel.enable_field[0]),
                channel.enable_field[1],
            )
            assert channel.enable_field[1] in GlobalConfig_Notify.model_fields


def test_channels_endpoint_returns_metadata_only() -> None:
    from app.api.setting import get_notify_channels as endpoint
    from app.models.legacy_config.base import ConfigBase

    with patch.object(
        ConfigBase, "get", side_effect=AssertionError("描述端点不得读取配置")
    ):
        result = _run(endpoint())

    assert result.code == 200
    assert len(result.channels) == 8
    assert [channel.key for channel in result.channels][0] == "system"
    assert result.channels[-1].kind == "policy"
