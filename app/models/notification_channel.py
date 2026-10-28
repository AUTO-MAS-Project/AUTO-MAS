"""内置通知渠道契约；不导入渠道实现、通知编排或应用初始化。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from app.models.notification import (
    NotificationCapabilities,
    RenderedNotification,
    SummaryPolicy,
)

SCOPE_GLOBAL = "global"
SCOPE_USER = "user"
CHANNEL_INTERFACE_VERSION = 1
EmptyPolicy = Literal["send", "warn", "skip"]
DeliveryErrorKind = Literal[
    "configuration", "transport", "rate_limited", "rejected", "unavailable", "unknown"
]
DeliveryStage = Literal["catalog", "preparation", "recipient", "render", "send"]


class NotificationDeliveryError(RuntimeError):
    """渠道声明失败类别及是否可重试；执行器不解释协议状态码或文案。"""

    def __init__(
        self, message: str, *, kind: DeliveryErrorKind, retryable: bool
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable


@dataclass(frozen=True)
class DeliveryFailure:
    label: str
    stage: DeliveryStage
    kind: DeliveryErrorKind
    retryable: bool
    target_id: str | None = None
    attempts: int = 0
    error_type: str | None = None


class NotificationSourceConfig(Protocol):
    """宿主配置的通知分组；动态渠道字段由 TargetConfigView 投影。"""

    @property
    def Notify(self) -> object: ...

    @property
    def Notify_CustomWebhooks(self) -> Any: ...


class UserNotificationPolicy(Protocol):
    @property
    def Enabled(self) -> bool: ...

    @property
    def IfSendStatistic(self) -> bool: ...


class UserNotificationConfig(NotificationSourceConfig, Protocol):
    @property
    def Notify(self) -> UserNotificationPolicy: ...


class RecruitmentNotificationPolicy(UserNotificationPolicy, Protocol):
    @property
    def IfSendSixStar(self) -> bool: ...


class RecruitmentNotificationConfig(NotificationSourceConfig, Protocol):
    @property
    def Notify(self) -> RecruitmentNotificationPolicy: ...


class ChannelConfig(Protocol):
    """宿主提供的目标配置视图，不暴露全局配置或专项对象。"""

    def get(self, group: str, name: str) -> Any: ...

    @property
    def Notify_CustomWebhooks(self) -> Any: ...


class NotificationConfigReader(Protocol):
    def get(self, name: str) -> Any: ...


class ChannelRuntimeConfig(NotificationConfigReader, Protocol):
    """沿用现有 Notify 配置的读写与变更订阅，不暴露全局 Config。"""

    def get(self, name: str) -> Any: ...

    async def update(self, values: Mapping[str, Any]) -> None: ...

    def bind(self, name: str, callback: Callable[[Any], Any]) -> None: ...


NotificationCommandAction = Literal["retry_script", "start_queue"]
NotificationCommandExecutor = Callable[[NotificationCommandAction, str], Awaitable[str]]


CommandExecutor = Callable[[str, dict[str, Any] | None], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class NotificationTransportSnapshot:
    """单次无会话传输的数据；凭据和代理仅保存在内存中。"""

    values: tuple[tuple[str, str | bool], ...] = field(default=(), repr=False)
    proxy: str | None = field(default=None, repr=False)

    def get(self, name: str) -> Any:
        return dict(self.values)[name]


@dataclass(frozen=True)
class ChannelDependencies:
    """仅供宿主和渠道工厂装配；传输实例接收各自的窄依赖。"""

    config: ChannelRuntimeConfig
    read_proxy: Callable[[], str | None]
    smtp_factory: Callable[..., Any]
    http_factory: Callable[..., Any]
    websocket_connect: Callable[..., Any]
    websocket_manager_factory: Callable[..., Any]
    system_notify: Callable[..., Any] | None
    system_icon: str
    logger: Any
    command_executor: CommandExecutor | None = None
    notification_command_executor: NotificationCommandExecutor | None = None
    transport: NotificationTransportSnapshot | None = field(default=None, repr=False)


@dataclass(frozen=True)
class MailDependencies:
    config: NotificationConfigReader
    smtp_factory: Callable[..., Any]
    logger: Any


@dataclass(frozen=True)
class HttpDependencies:
    read_proxy: Callable[[], str | None]
    http_factory: Callable[..., Any]
    logger: Any


@dataclass(frozen=True)
class WebSocketDependencies:
    read_proxy: Callable[[], str | None]
    websocket_connect: Callable[..., Any]
    logger: Any


@dataclass(frozen=True)
class SystemNoticeDependencies:
    config: NotificationConfigReader
    system_notify: Callable[..., Any] | None
    system_icon: str
    logger: Any


@dataclass(frozen=True)
class KoishiDependencies:
    config: NotificationConfigReader
    websocket_manager_factory: Callable[..., Any]
    logger: Any
    command_executor: CommandExecutor | None = None


@dataclass(frozen=True)
class QQSessionDependencies:
    config: ChannelRuntimeConfig
    read_proxy: Callable[[], str | None]
    http_factory: Callable[..., Any]
    websocket_connect: Callable[..., Any]
    notification_command_executor: NotificationCommandExecutor | None = None


@dataclass(frozen=True)
class NotifyChannelField:
    group: str
    name: str
    label_key: str
    control: Literal["bool", "text", "password", "url", "select", "json"]
    options: tuple[tuple[Any, str], ...] = ()
    placeholder_key: str = ""
    tip_key: str = ""


@dataclass(frozen=True)
class ChannelTarget:
    """一次投递的固定目标；ID 用于去重，label 仅供显示。"""

    id: str
    label: str
    value: Any = field(default=None, repr=False)
    empty_recipient: str | None = field(default=None, repr=False)
    empty_hint: str = ""
    timeout_seconds: int | None = None
    summary_policy: SummaryPolicy = "never"
    use_summary_title: bool = False
    capabilities: NotificationCapabilities = NotificationCapabilities()
    is_local: bool = False
    compact_summary_policy: SummaryPolicy | None = None
    transport: NotificationTransportSnapshot | None = field(default=None, repr=False)
    announcement_capabilities: NotificationCapabilities | None = None


SendAdapter = Callable[
    [Any, ChannelTarget, RenderedNotification], Awaitable[bool | None]
]


@dataclass(frozen=True)
class DeliveryChannel:
    """一次投递仅需的执行描述，不携带目录、控件、工厂和生命周期。"""

    key: str
    send_adapter: SendAdapter | None = field(repr=False)

    async def send(
        self, sender: Any, target: ChannelTarget, rendered: RenderedNotification
    ) -> bool | None:
        if self.send_adapter is None:
            raise RuntimeError(f"通知渠道 {self.key} 未绑定发送器")
        return await self.send_adapter(sender, target, rendered)


@dataclass(frozen=True)
class NotifyChannel:
    """渠道声明及全部行为绑定；公开 API 仍逐字段选择展示元数据。"""

    key: str
    name_key: str
    desc_key: str
    icon: str
    group: Literal["builtin", "custom"]
    order: int
    doc_url: str | None
    scopes: frozenset[str]
    kind: Literal["fields", "custom", "policy"]
    custom_block: str | None
    enable_field: tuple[str, str] | None
    summary_key: str | None
    summary_fields: tuple[str, ...]
    fields: Mapping[str, tuple[NotifyChannelField, ...]]
    target_builder: Callable[..., tuple[ChannelTarget, ...]] | None = None
    send_adapter: SendAdapter | None = None
    sender_factory: Callable[[ChannelDependencies], Any] | None = None
    start_adapter: Callable[[Any], Awaitable[None]] | None = None
    stop_adapter: Callable[[Any], Awaitable[None]] | None = None
    lifecycle_order: int = 0
    # None 保留渠道会话；元组声明无会话传输需要从全局配置固定的字段。
    transport_fields: tuple[str, ...] | None = None

    def targets(
        self, config: ChannelConfig, *, scope: str
    ) -> tuple[ChannelTarget, ...]:
        if self.kind == "policy" or scope not in self.scopes:
            return ()
        if self.enable_field and not bool(config.get(*self.enable_field)):
            return ()
        if self.target_builder is None:
            raise RuntimeError(f"通知渠道 {self.key} 未绑定目标构造器")
        return self.target_builder(config, scope=scope)

    def delivery(self) -> DeliveryChannel:
        return DeliveryChannel(key=self.key, send_adapter=self.send_adapter)


def target_prefix(scope: str) -> str:
    return "全局" if scope == SCOPE_GLOBAL else "用户"


@dataclass(frozen=True)
class NotifyTarget:
    """已解析的投递目标；目录和目标解析失败均保留给本次结果。"""

    channels: tuple[tuple[DeliveryChannel, ChannelTarget], ...] = ()
    empty_policy: EmptyPolicy = "send"
    catalog_failures: tuple[str, ...] = ()
    preparation_failures: tuple[str, ...] = ()

    @property
    def unresolved(self) -> tuple[str, ...]:
        """尚未解析出目标的失败，不伪造一次实际投递。"""
        return tuple(
            dict.fromkeys((*self.catalog_failures, *self.preparation_failures))
        )


@dataclass(frozen=True)
class DispatchResult:
    """分发结果；零目标和全跳过均不表示已送达。

    attempted 只统计进入投递处理的目标，目录或目标解析失败不增加计数。
    succeeded/failed 保留显示名称，succeeded_ids 用于按稳定 ID 补发。
    """

    attempted: int = 0
    succeeded: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()
    succeeded_ids: tuple[str, ...] = ()
    failures: tuple[DeliveryFailure, ...] = ()
    # 已由宿主接管，尚未实际投递；不得作为送达成功消费。
    queued: bool = False

    @property
    def failed_ids(self) -> tuple[str, ...]:
        """只有已解析目标才有稳定 ID，目录错误不伪造目标。"""

        return tuple(f.target_id for f in self.failures if f.target_id is not None)


class Notifier(Protocol):
    """统一投递面；渠道内部的传输方法不进入公共协议。"""

    async def send_channel(
        self,
        channel: DeliveryChannel,
        target: ChannelTarget,
        rendered: RenderedNotification,
    ) -> bool | None: ...
