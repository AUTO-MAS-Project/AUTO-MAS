"""内置通知渠道契约；不导入渠道实现、通知编排或应用初始化。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol

from app.models.notification import (
    NotificationCapabilities,
    RenderedNotification,
    SummaryPolicy,
)

if TYPE_CHECKING:
    from httpx import Proxy

SCOPE_GLOBAL = "global"
SCOPE_USER = "user"
CHANNEL_INTERFACE_VERSION = 1


class ChannelConfig(Protocol):
    """宿主提供的目标配置视图，不暴露全局配置或专项对象。"""

    def get(self, group: str, name: str) -> Any: ...

    @property
    def Notify_CustomWebhooks(self) -> Any: ...


class ChannelRuntimeConfig(Protocol):
    """沿用现有 Notify 配置的读写与变更订阅，不暴露全局 Config。"""

    def get(self, name: str) -> Any: ...

    async def update(self, values: Mapping[str, Any]) -> None: ...

    def bind(self, name: str, callback: Callable[[Any], Any]) -> None: ...


CommandExecutor = Callable[[str, dict[str, Any] | None], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class ChannelDependencies:
    """宿主装配的传输能力；读取器在每次尝试开始时返回当前配置。"""

    config: ChannelRuntimeConfig
    read_proxy: Callable[[], str | Proxy | None]
    smtp_factory: Callable[..., Any]
    http_factory: Callable[..., Any]
    websocket_connect: Callable[..., Any]
    websocket_manager_factory: Callable[..., Any]
    system_notify: Callable[..., Any] | None
    system_icon: str
    logger: Any
    command_executor: CommandExecutor | None = None


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
    send_adapter: Callable[..., Awaitable[bool | None]] | None = None
    sender_factory: Callable[[ChannelDependencies], Any] | None = None
    start_adapter: Callable[[Any], Awaitable[None]] | None = None
    stop_adapter: Callable[[Any], Awaitable[None]] | None = None
    lifecycle_order: int = 0

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

    async def send(
        self, sender: Any, target: ChannelTarget, rendered: RenderedNotification
    ) -> bool | None:
        """执行单次发送；None/True 成功，False 失败，取消和异常向上传播。"""

        if self.send_adapter is None:
            raise RuntimeError(f"通知渠道 {self.key} 未绑定发送器")
        return await self.send_adapter(sender, target, rendered)


def target_prefix(scope: str) -> str:
    return "全局" if scope == SCOPE_GLOBAL else "用户"
