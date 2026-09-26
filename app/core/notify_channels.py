#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""通知渠道描述表。

通知设置页的展示元数据来源：渠道卡片、配置弹窗里的字段与文档链接都由这张表
驱动；``app.core.notify`` 分发时遍历同一张表，保证界面呈现的渠道与实际投递的
渠道永远一致。描述表只含展示元数据，不携带任何配置值（服务无鉴权，负载不得
回带密钥）。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Mapping

if TYPE_CHECKING:
    # 只在类型标注里用；注解靠 from __future__ import annotations 延迟求值，
    # 避免 app.core.notify ↔ 本模块的运行期导入环（先例：app/core/config.py:50-51）。
    from app.core.notify import Notifier, NotifyPayload

SCOPE_GLOBAL = "global"
SCOPE_USER = "user"


@dataclass(frozen=True)
class NotifyChannelField:
    """渠道在某个作用域下暴露给界面的一个配置字段。"""

    group: str  # 配置组，恒为 "Notify"
    name: str  # 配置字段名，如 "SMTPServerAddress"
    label_key: str  # 字段标签词表键
    control: Literal["bool", "text", "password", "url", "select", "json"]
    # (值, 文案键) 对；值保持后端配置字面量（含布尔），不能窄成 str。
    options: tuple[tuple[Any, str], ...] = ()
    placeholder_key: str = ""
    tip_key: str = ""
    # 所属作用域由 NotifyChannel.fields 的键决定，字段上不重复声明。


@dataclass(frozen=True)
class ChannelTarget:
    """一次投递的目标：ID 进补发记录，label 进用户可见文案，value 供发送使用。"""

    id: str  # 投递 ID（进 DispatchResult.succeeded_ids / 补发记录），逐字保持
    label: str  # 显示名（进 succeeded / failed 文案）
    value: Any = None  # 发送所需配置值：收件字符串，或活的 Webhook 对象
    # None = 不做空值判定（系统通知 / Koishi / QQ / Webhook）；
    # 非 None 时按真值判定，warn 策略下为空会计入失败。
    empty_recipient: str | None = None
    empty_hint: str = ""  # 空值告警提示词，逐字保持


def _webhook_name(uid: str, webhook: Any) -> str:
    """返回便于定位失败配置的 Webhook 名称。"""

    try:
        return str(webhook.get("Info", "Name") or uid)
    except (AttributeError, KeyError):
        return uid


@dataclass(frozen=True)
class NotifyChannel:
    """一个渠道的描述：界面渲染与后端分发共用同一份元数据。"""

    key: str
    name_key: str  # 卡片/弹窗标题，短名称
    desc_key: str  # 弹窗头部一句话说明；policy 段可为空串
    icon: str  # 图标标识；policy 段为空串
    group: Literal["builtin", "custom"]
    order: int  # 前端排序用，必须与投递顺序一致
    doc_url: str | None
    scopes: frozenset[str]
    kind: Literal["fields", "custom", "policy"]  # policy = 通知内容这类非渠道段
    custom_block: str | None  # "claw:qq" / "webhook_list"
    enable_field: tuple[str, str] | None
    # 空值摘要变体的词表键约定为 f"{summary_key}Empty"（Empty 后缀，与前端一致）；
    # summary_fields 兼作摘要插值的 i18n 占位符名。
    summary_key: str | None
    summary_fields: tuple[str, ...]
    # 键即作用域（global/user）；policy 段的键用 global。
    fields: Mapping[str, tuple[NotifyChannelField, ...]]

    def targets(self, config: Any, *, scope: str) -> tuple[ChannelTarget, ...]:
        """按配置构造该渠道的投递目标。

        渠道出现规则统一在此判定：作用域不符或开关（enable_field）关闭都产出
        为空；配置值缺失的判断仍归各渠道构造器。
        """

        if self.kind == "policy" or scope not in self.scopes:
            return ()
        if self.enable_field and not bool(config.get(*self.enable_field)):
            return ()
        return _TARGET_BUILDERS[self.key](config, scope=scope)

    async def send(
        self,
        sender: Notifier,
        target: ChannelTarget,
        payload: NotifyPayload,
    ) -> bool | None:
        """执行一次发送；返回值语义与 Notifier 协议一致（False 即失败）。"""

        return await _SENDERS[self.key](sender, target, payload)


_MAIL_FIELD_TO = NotifyChannelField(
    group="Notify",
    name="ToAddress",
    label_key="setting.notify.to",
    control="text",
    placeholder_key="setting.notify.toPlaceholder",
    tip_key="setting.notify.toTip",
)

_SERVERCHAN_FIELD = NotifyChannelField(
    group="Notify",
    name="ServerChanKey",
    label_key="setting.notify.serverChanKey",
    control="password",
    placeholder_key="setting.notify.serverChanPlaceholder",
    tip_key="setting.notify.serverChanKeyTip",
)

# 邮件：全局侧配全套 SMTP，用户侧只填收件地址
_MAIL_FIELDS: Mapping[str, tuple[NotifyChannelField, ...]] = {
    SCOPE_GLOBAL: (
        NotifyChannelField(
            group="Notify",
            name="SMTPServerAddress",
            label_key="setting.notify.smtp",
            control="text",
            placeholder_key="setting.notify.smtpPlaceholder",
            tip_key="setting.notify.smtpTip",
        ),
        NotifyChannelField(
            group="Notify",
            name="FromAddress",
            label_key="setting.notify.from",
            control="text",
            placeholder_key="setting.notify.fromPlaceholder",
            tip_key="setting.notify.fromTip",
        ),
        NotifyChannelField(
            group="Notify",
            name="AuthorizationCode",
            label_key="setting.notify.authCode",
            control="password",
            placeholder_key="setting.notify.authCodePlaceholder",
            tip_key="setting.notify.authCodeTip",
        ),
        _MAIL_FIELD_TO,
    ),
    SCOPE_USER: (_MAIL_FIELD_TO,),
}

# 通知内容（policy 段）的选项值是后端配置字面量，should_send_result 直接比对
# 中文原文，不能翻译。
_POLICY_FIELDS: Mapping[str, tuple[NotifyChannelField, ...]] = {
    SCOPE_GLOBAL: (
        NotifyChannelField(
            group="Notify",
            name="SendTaskResultTime",
            label_key="setting.notify.resultTime",
            control="select",
            options=(
                ("不推送", "setting.pushTime.never"),
                ("任何时刻", "setting.pushTime.always"),
                ("仅失败时", "setting.pushTime.failOnly"),
            ),
            tip_key="setting.notify.resultTimeTip",
        ),
        NotifyChannelField(
            group="Notify",
            name="IfSendStatistic",
            label_key="setting.notify.statistics",
            control="bool",
            tip_key="setting.notify.statisticsTip",
        ),
        NotifyChannelField(
            group="Notify",
            name="IfSendSixStar",
            label_key="setting.notify.recruit",
            control="bool",
            tip_key="setting.notify.recruitTip",
        ),
    )
}

# 顺序即投递顺序（系统 → 邮件 → Server酱 → 5G → Webhook → Koishi → QQ），
# succeeded/failed 文案按此顺序拼接，用户可见，不能调整。
_CHANNELS: tuple[NotifyChannel, ...] = (
    NotifyChannel(
        key="system",
        name_key="setting.notify.systemSection",
        desc_key="setting.notify.systemTip",
        icon="bell",
        group="builtin",
        order=10,
        doc_url=None,
        scopes=frozenset({SCOPE_GLOBAL}),
        kind="fields",
        custom_block=None,
        enable_field=("Notify", "IfPushPlyer"),
        summary_key="setting.notify.summary.system",
        summary_fields=(),
        fields={},
    ),
    NotifyChannel(
        key="mail",
        name_key="setting.notify.mailSection",
        desc_key="setting.notify.mailEnableTip",
        icon="mail",
        group="builtin",
        order=20,
        doc_url="https://doc.auto-mas.top/docs/advanced-features/notification.html#smtp-%E9%82%AE%E4%BB%B6%E6%8E%A8%E9%80%81%E6%B8%A0%E9%81%93",
        scopes=frozenset({SCOPE_GLOBAL, SCOPE_USER}),
        kind="fields",
        custom_block=None,
        enable_field=("Notify", "IfSendMail"),
        summary_key="setting.notify.summary.mail",
        summary_fields=("SMTPServerAddress", "ToAddress"),
        fields=_MAIL_FIELDS,
    ),
    NotifyChannel(
        key="serverchan",
        name_key="setting.notify.serverChanSection",
        desc_key="setting.notify.serverChanTip",
        icon="plane",
        group="builtin",
        order=30,
        doc_url="https://doc.auto-mas.top/docs/advanced-features/notification.html#serverchan-%E9%80%9A%E7%9F%A5%E6%8E%A8%E9%80%81%E6%B8%A0%E9%81%93",
        scopes=frozenset({SCOPE_GLOBAL, SCOPE_USER}),
        kind="fields",
        custom_block=None,
        enable_field=("Notify", "IfServerChan"),
        summary_key="setting.notify.summary.serverchan",
        summary_fields=("ServerChanKey",),
        fields={SCOPE_GLOBAL: (_SERVERCHAN_FIELD,), SCOPE_USER: (_SERVERCHAN_FIELD,)},
    ),
    NotifyChannel(
        key="cmcc",
        name_key="setting.notify.cmccNewMsgName",
        desc_key="setting.notify.cmccNewMsgTip",
        icon="signal",
        group="builtin",
        order=40,
        doc_url="https://doc.auto-mas.top/docs/advanced-features/notification.html",
        scopes=frozenset({SCOPE_GLOBAL}),
        kind="fields",
        custom_block=None,
        enable_field=("Notify", "IfCMCCNewMsg"),
        summary_key="setting.notify.summary.cmcc",
        summary_fields=("CMCCNewMsgApiKey",),
        fields={
            SCOPE_GLOBAL: (
                NotifyChannelField(
                    group="Notify",
                    name="CMCCNewMsgApiKey",
                    label_key="setting.notify.cmccNewMsgApiKey",
                    control="password",
                    placeholder_key="setting.notify.cmccNewMsgApiKeyPlaceholder",
                    tip_key="setting.notify.cmccNewMsgApiKeyTip",
                ),
            )
        },
    ),
    NotifyChannel(
        key="webhook",
        name_key="setting.notify.webhookName",
        desc_key="setting.notify.webhookDesc",
        icon="webhook",
        group="custom",
        order=50,
        doc_url="https://doc.auto-mas.top/docs/advanced-features/notification.html",
        scopes=frozenset({SCOPE_GLOBAL, SCOPE_USER}),
        kind="custom",
        custom_block="webhook_list",
        enable_field=None,
        summary_key="setting.notify.summary.webhook",
        summary_fields=(),
        fields={},
    ),
    NotifyChannel(
        key="koishi",
        name_key="setting.notify.koishiSection",
        desc_key="setting.notify.koishiTip",
        icon="chat",
        group="builtin",
        order=60,
        doc_url=None,
        scopes=frozenset({SCOPE_GLOBAL}),
        kind="fields",
        custom_block=None,
        enable_field=("Notify", "IfKoishiSupport"),
        summary_key="setting.notify.summary.koishi",
        summary_fields=("KoishiServerAddress",),
        fields={
            SCOPE_GLOBAL: (
                NotifyChannelField(
                    group="Notify",
                    name="KoishiServerAddress",
                    label_key="setting.notify.koishiWs",
                    control="text",
                    placeholder_key="setting.notify.koishiWsPlaceholder",
                    tip_key="setting.notify.koishiWsTip",
                ),
                NotifyChannelField(
                    group="Notify",
                    name="KoishiToken",
                    label_key="setting.notify.koishiToken",
                    control="password",
                    placeholder_key="setting.notify.koishiTokenPlaceholder",
                    tip_key="setting.notify.koishiTokenTip",
                ),
            )
        },
    ),
    NotifyChannel(
        key="openclaw_qq",
        name_key="setting.notify.openclawQqSection",
        desc_key="setting.notify.openclawQqTip",
        icon="qq",
        group="builtin",
        order=80,
        doc_url="https://bot.q.qq.com/wiki/",
        scopes=frozenset({SCOPE_GLOBAL}),
        kind="custom",
        custom_block="claw:qq",
        enable_field=("Notify", "IfOpenClawQQ"),
        summary_key=None,
        summary_fields=(),
        fields={},
    ),
    # 通知内容是全局推送策略，不是投递渠道：渲染在渠道卡片网格之外。
    NotifyChannel(
        key="policy",
        name_key="setting.notify.contentSection",
        desc_key="",
        icon="",
        group="builtin",
        order=90,
        doc_url=None,
        scopes=frozenset({SCOPE_GLOBAL}),
        kind="policy",
        custom_block=None,
        enable_field=None,
        summary_key=None,
        summary_fields=(),
        fields=_POLICY_FIELDS,
    ),
)


def get_notify_channels() -> tuple[NotifyChannel, ...]:
    """返回全部渠道描述，顺序即投递顺序。"""

    return _CHANNELS


# ==================== 投递目标构造与发送 ====================


def _prefix(scope: str) -> str:
    """投递 ID / 显示名的前缀，与目标名（全局 / 用户）逐字一致。"""

    return "全局" if scope == SCOPE_GLOBAL else "用户"


def _system_targets(config: Any, *, scope: str) -> tuple[ChannelTarget, ...]:
    name = f"{_prefix(scope)}系统"
    return (ChannelTarget(id=name, label=name),)


async def _system_send(
    sender: Notifier, target: ChannelTarget, payload: NotifyPayload
) -> bool | None:
    return await sender.push_plyer(
        title=payload.system_title or payload.title,
        message=payload.system_message or payload.system_content,
        ticker=payload.system_ticker or payload.title,
        t=payload.system_timeout,
    )


def _mail_targets(config: Any, *, scope: str) -> tuple[ChannelTarget, ...]:
    value = config.get("Notify", "ToAddress")
    if value is None:
        return ()
    name = f"{_prefix(scope)}邮件"
    return (
        ChannelTarget(
            id=name,
            label=name,
            value=value,
            empty_recipient=value,
            empty_hint=f"{_prefix(scope)}邮箱地址",
        ),
    )


async def _mail_send(
    sender: Notifier, target: ChannelTarget, payload: NotifyPayload
) -> bool | None:
    return await sender.send_mail(
        mode=payload.email_mode,
        title=payload.title,
        content=payload.email_content,
        to_address=target.value,
        images=payload.mail_images,
    )


def _serverchan_targets(config: Any, *, scope: str) -> tuple[ChannelTarget, ...]:
    value = config.get("Notify", "ServerChanKey")
    if value is None:
        return ()
    name = f"{_prefix(scope)} ServerChan"
    return (
        ChannelTarget(
            id=name,
            label=name,
            value=value,
            empty_recipient=value,
            empty_hint=f"{_prefix(scope)}ServerChan 密钥",
        ),
    )


async def _serverchan_send(
    sender: Notifier, target: ChannelTarget, payload: NotifyPayload
) -> bool | None:
    return await sender.ServerChanPush(
        title=payload.title,
        content=payload.serverchan_content,
        send_key=target.value,
    )


def _cmcc_targets(config: Any, *, scope: str) -> tuple[ChannelTarget, ...]:
    value = config.get("Notify", "CMCCNewMsgApiKey")
    if value is None:
        return ()
    name = f"{_prefix(scope)} 中国移动5G短信"
    return (
        ChannelTarget(
            id=name,
            label=name,
            value=value,
            empty_recipient=value,
            empty_hint=f"{_prefix(scope)}中国移动5G短信 API Key",
        ),
    )


async def _cmcc_send(
    sender: Notifier, target: ChannelTarget, payload: NotifyPayload
) -> bool | None:
    return await sender.send_cmcc_newmsg(
        title=payload.title,
        content=payload.cmcc_newmsg_content,
        api_key=target.value,
    )


def _webhook_targets(config: Any, *, scope: str) -> tuple[ChannelTarget, ...]:
    prefix = _prefix(scope)
    # 顺序按 MultipleConfig.order（items() 的产出顺序），不按 uid
    return tuple(
        ChannelTarget(
            id=f"{prefix} Webhook {uid}",
            label=f"{prefix} Webhook {_webhook_name(uid, webhook)}",
            value=webhook,
        )
        for uid, webhook in config.Notify_CustomWebhooks.items()
        if bool(webhook.get("Info", "Enabled"))
    )


async def _webhook_send(
    sender: Notifier, target: ChannelTarget, payload: NotifyPayload
) -> bool | None:
    return await sender.WebhookPush(
        title=payload.title,
        content=payload.webhook_content_for(target.value),
        image_base64=payload.webhook_image_base64 or "",
        webhook=target.value,
    )


def _koishi_targets(config: Any, *, scope: str) -> tuple[ChannelTarget, ...]:
    name = f"{_prefix(scope)} Koishi"
    return (ChannelTarget(id=name, label=name),)


async def _koishi_send(
    sender: Notifier, target: ChannelTarget, payload: NotifyPayload
) -> bool | None:
    if payload.koishi_msgtype != "text":
        return await sender.send_koishi(
            payload.koishi_content, msgtype=payload.koishi_msgtype
        )
    return await sender.send_koishi(payload.koishi_content)


def _openclaw_qq_targets(config: Any, *, scope: str) -> tuple[ChannelTarget, ...]:
    name = f"{_prefix(scope)} QQ（官方机器人）"
    return (ChannelTarget(id=name, label=name),)


async def _openclaw_qq_send(
    sender: Notifier, target: ChannelTarget, payload: NotifyPayload
) -> bool | None:
    return await sender.send_openclaw_qq(
        title=payload.title,
        content=payload.openclaw_qq_content,
    )


# 渠道行为注册表：加渠道 = 描述表加一条 + 这里各加一个构造器/发送器
_TARGET_BUILDERS: Mapping[str, Callable[..., tuple[ChannelTarget, ...]]] = {
    "system": _system_targets,
    "mail": _mail_targets,
    "serverchan": _serverchan_targets,
    "cmcc": _cmcc_targets,
    "webhook": _webhook_targets,
    "koishi": _koishi_targets,
    "openclaw_qq": _openclaw_qq_targets,
}

_SENDERS: Mapping[str, Callable[..., Awaitable[bool | None]]] = {
    "system": _system_send,
    "mail": _mail_send,
    "serverchan": _serverchan_send,
    "cmcc": _cmcc_send,
    "webhook": _webhook_send,
    "koishi": _koishi_send,
    "openclaw_qq": _openclaw_qq_send,
}
