"""通知专用注册表，不拥有共享连接，也不执行通知业务编排。"""

from __future__ import annotations

import inspect
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import replace
from types import MappingProxyType
from typing import Any

from app.models.notification.channel import (
    ChannelDependencies,
    NotificationTransportSnapshot,
    NotifyChannel,
    NotifyChannelField,
)


def validate_channel(channel: NotifyChannel) -> None:
    """先校验完整声明，调用方才能将其登记为可用渠道。"""

    if not isinstance(channel, NotifyChannel):
        raise ValueError("注册入口必须返回 NotifyChannel")
    if re.fullmatch(r"[a-z][a-z0-9_]*", channel.key) is None:
        raise ValueError("渠道 ID 格式无效")
    if (
        not isinstance(channel.name_key, str)
        or not channel.name_key
        or type(channel.order) is not int
        or type(channel.lifecycle_order) is not int
    ):
        raise ValueError("渠道名称或顺序缺失")
    if channel.kind not in {"fields", "custom"} or channel.group not in {
        "builtin",
        "custom",
    }:
        raise ValueError("渠道类别无效")
    if not isinstance(channel.desc_key, str) or not isinstance(channel.icon, str):
        raise ValueError("渠道展示声明无效")
    if (
        any(
            value is not None and not isinstance(value, str)
            for value in (channel.doc_url, channel.custom_block, channel.summary_key)
        )
        or not isinstance(channel.summary_fields, tuple)
        or any(not isinstance(name, str) for name in channel.summary_fields)
    ):
        raise ValueError("渠道摘要声明无效")
    if channel.enable_field is not None and (
        not isinstance(channel.enable_field, tuple)
        or len(channel.enable_field) != 2
        or channel.enable_field[0] != "Notify"
        or not isinstance(channel.enable_field[1], str)
    ):
        raise ValueError("渠道启用字段无效")
    if (
        not isinstance(channel.scopes, frozenset)
        or not channel.scopes
        or not channel.scopes <= {"global", "user"}
    ):
        raise ValueError("渠道作用域无效")
    if (
        not isinstance(channel.fields, Mapping)
        or not channel.fields.keys() <= channel.scopes
    ):
        raise ValueError("渠道配置字段声明无效")
    for fields in channel.fields.values():
        if not isinstance(fields, tuple):
            raise ValueError("渠道配置字段必须为元组")
        for item in fields:
            if (
                not isinstance(item, NotifyChannelField)
                or item.group != "Notify"
                or item.control
                not in {"bool", "text", "password", "url", "select", "json"}
            ):
                raise ValueError("渠道配置控件声明无效")
            if (
                any(
                    not isinstance(value, str)
                    for value in (
                        item.name,
                        item.label_key,
                        item.placeholder_key,
                        item.tip_key,
                    )
                )
                or not isinstance(item.options, tuple)
                or any(
                    not isinstance(option, tuple)
                    or len(option) != 2
                    or not isinstance(option[0], (bool, str))
                    or not isinstance(option[1], str)
                    for option in item.options
                )
            ):
                raise ValueError("渠道配置字段元数据无效")
    if not callable(channel.target_builder) or not callable(channel.sender_factory):
        raise ValueError("渠道目标构造器或发送器工厂缺失")
    if channel.transport_fields is not None and (
        not isinstance(channel.transport_fields, tuple)
        or any(
            not isinstance(name, str) or not name for name in channel.transport_fields
        )
        or channel.start_adapter is not None
        or channel.stop_adapter is not None
    ):
        raise ValueError("传输快照只适用于无会话渠道及其配置字段")
    if not inspect.iscoroutinefunction(channel.send_adapter):
        raise ValueError("渠道发送入口必须为异步函数")
    inspect.signature(channel.target_builder).bind(object(), scope="global")
    inspect.signature(channel.sender_factory).bind(object())
    inspect.signature(channel.send_adapter).bind(object(), object(), object())
    for adapter in (channel.start_adapter, channel.stop_adapter):
        if adapter is not None:
            if not inspect.iscoroutinefunction(adapter):
                raise ValueError("渠道生命周期入口必须为异步函数")
            inspect.signature(adapter).bind(object())


class ChannelRegistry:
    def __init__(
        self,
        channels: Iterable[NotifyChannel],
        *,
        unavailable: Iterable[str] = (),
        unresolved: Iterable[str] = (),
    ) -> None:
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
        self.unavailable = frozenset(unavailable)
        # 未取得有效声明时，不能推测启用状态或伪造投递目标。
        self.unresolved = tuple(sorted(set(unresolved)))

    def bind(self, dependencies: ChannelDependencies) -> BoundChannels:
        senders: dict[str, Any] = {}
        for entry in self.channels:
            if entry.key in self.unavailable:
                continue
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
        return BoundChannels(senders, channels=self.channels, dependencies=dependencies)


class BoundChannels:
    def __init__(
        self,
        senders: dict[str, Any],
        *,
        channels: tuple[NotifyChannel, ...],
        dependencies: ChannelDependencies,
    ) -> None:
        self._senders = MappingProxyType(senders)
        self._channels = tuple(
            sorted(channels, key=lambda c: (c.lifecycle_order, c.key))
        )
        self._dependencies = dependencies
        self._logger = dependencies.logger
        self._started = False

    async def start(self) -> None:
        """逐渠道启动；单个渠道失败不阻止其他渠道恢复连接。"""
        if self._started:
            return
        self._started = True
        for channel in self._channels:
            if channel.start_adapter is None or channel.key not in self._senders:
                continue
            try:
                await channel.start_adapter(self.sender(channel.key))
            except Exception as exc:
                self._logger.warning(
                    f"通知渠道 {channel.key} 启动失败: {type(exc).__name__}"
                )

    async def stop(self) -> None:
        """通知任务结束后，逆序释放渠道拥有的连接和后台任务。"""
        for channel in reversed(self._channels):
            if channel.stop_adapter is None or channel.key not in self._senders:
                continue
            try:
                await channel.stop_adapter(self.sender(channel.key))
            except Exception as exc:
                self._logger.warning(
                    f"通知渠道 {channel.key} 停止失败: {type(exc).__name__}"
                )
        self._started = False

    def sender(
        self, key: str, *, transport: NotificationTransportSnapshot | None = None
    ) -> Any:
        try:
            sender = self._senders[key]
        except KeyError as exc:
            raise RuntimeError(f"通知渠道 {key} 不可用") from exc
        if transport is None:
            return sender
        channel = next(channel for channel in self._channels if channel.key == key)
        if channel.transport_fields is None or channel.sender_factory is None:
            raise RuntimeError(f"通知渠道 {key} 不支持无会话传输快照")
        dependencies = replace(
            self._dependencies,
            transport=transport,
            read_proxy=lambda: transport.proxy,
        )
        return channel.sender_factory(dependencies)
