"""通知专用注册表，不拥有共享连接，也不执行通知业务编排。"""

from __future__ import annotations

import inspect
import re
from collections import Counter
from collections.abc import Iterable
from types import MappingProxyType
from typing import Any

from app.models.notification_channel import ChannelDependencies, NotifyChannel


def validate_channel(channel: NotifyChannel) -> None:
    """先校验完整声明，调用方才能将其登记为可用渠道。"""

    if not isinstance(channel, NotifyChannel):
        raise ValueError("注册入口必须返回 NotifyChannel")
    if re.fullmatch(r"[a-z][a-z0-9_]*", channel.key) is None:
        raise ValueError("渠道 ID 格式无效")
    if not channel.name_key or type(channel.order) is not int:
        raise ValueError("渠道名称或顺序缺失")
    if channel.kind == "policy":
        raise ValueError("通知策略不属于发送渠道")
    if not channel.scopes or not channel.scopes <= {"global", "user"}:
        raise ValueError("渠道作用域无效")
    if not channel.capabilities.formats or not set(channel.capabilities.formats) <= {
        "text",
        "html",
        "markdown",
    }:
        raise ValueError("渠道格式声明无效")
    if not callable(channel.target_builder) or not callable(channel.sender_factory):
        raise ValueError("渠道目标构造器或发送器工厂缺失")
    if not inspect.iscoroutinefunction(channel.send_adapter):
        raise ValueError("渠道发送入口必须为异步函数")


class ChannelRegistry:
    def __init__(self, channels: Iterable[NotifyChannel]) -> None:
        entries = tuple(channels)
        for entry in entries:
            validate_channel(entry)
        duplicates = [
            key for key, n in Counter(c.key for c in entries).items() if n > 1
        ]
        if duplicates:
            raise ValueError(f"通知渠道 ID 重复: {', '.join(sorted(duplicates))}")
        self.channels = tuple(sorted(entries, key=lambda c: (c.order, c.key)))
        self.by_id = MappingProxyType({entry.key: entry for entry in self.channels})

    def bind(self, dependencies: ChannelDependencies) -> BoundChannels:
        senders: dict[str, Any] = {}
        for entry in self.channels:
            try:
                senders[entry.key] = entry.sender_factory(dependencies)
                if senders[entry.key] is None:
                    raise ValueError("发送器工厂返回空值")
            except Exception as exc:
                # 不记录异常原文，第三方异常可能包含传输凭据。
                senders.pop(entry.key, None)
                dependencies.logger.warning(
                    f"通知渠道 {entry.key} 装配失败: {type(exc).__name__}"
                )
        return BoundChannels(self, senders)


class BoundChannels:
    def __init__(self, registry: ChannelRegistry, senders: dict[str, Any]) -> None:
        self.registry = registry
        self._senders = MappingProxyType(senders)

    def sender(self, key: str) -> Any:
        try:
            return self._senders[key]
        except KeyError as exc:
            raise RuntimeError(f"通知渠道 {key} 不可用") from exc
