#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""统一通知编排。

脚本和业务模块负责生成正文，本模块负责读取通知配置、选择目标渠道、失败隔离与重试；
``app.services.notification`` 持有已装配发送器，具体传输由各渠道实现。
"""

from collections.abc import Iterable
from dataclasses import replace
from typing import Any

from app.core.config import Config
from app.core.notify_channels import (
    TargetConfigView,
    get_notify_channel_failures,
    get_notify_channels,
    read_notification_proxy,
)
from app.models.notification import NotifyPayload
from app.models.notification_channel import (
    ChannelTarget,
    NotificationTransportSnapshot,
    NotifyChannel,
)
from app.models.notification_channel import (
    DispatchResult as DispatchResult,
)
from app.models.notification_channel import (
    EmptyPolicy as EmptyPolicy,
)
from app.models.notification_channel import (
    Notifier as Notifier,
)
from app.models.notification_channel import (
    NotifyTarget as NotifyTarget,
)
from app.services.notification import Notify
from app.services.notification_dispatch import dispatch as dispatch_notification
from app.utils import get_logger

logger = get_logger("通知编排")


def global_target(
    *,
    include_system: bool = False,
    empty_policy: EmptyPolicy = "send",
    system_timeout_seconds: int | None = None,
) -> NotifyTarget:
    """按全局配置构造通知目标。"""

    return _resolve_target(
        config=Config.setting,
        scope="global",
        include_system=include_system,
        empty_policy=empty_policy,
        system_timeout_seconds=system_timeout_seconds,
    )


def user_target(user_config: Any) -> NotifyTarget:
    """按用户配置构造独立通知目标。"""
    return _resolve_target(config=user_config, scope="user", empty_policy="warn")


def _resolve_target(
    *,
    config: Any,
    scope: str,
    empty_policy: EmptyPolicy,
    include_system: bool = False,
    system_timeout_seconds: int | None = None,
) -> NotifyTarget:
    """逐渠道解析快照；一个渠道失败时保留其不确定性并继续其他渠道。"""
    pairs: list[tuple[NotifyChannel, ChannelTarget]] = []
    failures: list[str] = []
    for channel in get_notify_channels():
        try:
            channel_targets = channel.targets(TargetConfigView(config), scope=scope)
            resolved = []
            for target in channel_targets:
                if target.is_local and not include_system:
                    continue
                if target.is_local and system_timeout_seconds is not None:
                    target = replace(target, timeout_seconds=system_timeout_seconds)
                resolved.append((channel, target))
            if resolved and channel.transport_fields is not None:
                transport = NotificationTransportSnapshot(
                    values=tuple(
                        (name, getattr(Config.setting.Notify, name))
                        for name in channel.transport_fields
                    ),
                    proxy=read_notification_proxy(),
                )
                resolved = [
                    (channel, replace(target, transport=transport))
                    for channel, target in resolved
                ]
            pairs.extend(resolved)
        except Exception as exc:
            prefix = "全局" if scope == "global" else "用户"
            failure = f"{prefix}通知渠道 {channel.key} 目标准备失败"
            failures.append(failure)
            logger.warning(f"{failure}: {type(exc).__name__}")
    return NotifyTarget(
        channels=tuple(pairs),
        empty_policy=empty_policy,
        catalog_failures=get_notify_channel_failures(),
        preparation_failures=tuple(failures),
    )


def user_statistic_targets(user_config: Any | None) -> list[NotifyTarget]:
    """返回已启用统计通知的用户目标。"""

    if (
        user_config is None
        or not user_config.Notify.Enabled
        or (not user_config.Notify.IfSendStatistic)
    ):
        return []
    return [user_target(user_config)]


def statistic_targets(
    user_config: Any | None,
    *,
    global_empty_policy: EmptyPolicy = "send",
    compact_summary: bool = False,
) -> list[NotifyTarget]:
    """返回全局与用户级统计通知目标。"""

    targets = []
    if Config.setting.Notify.IfSendStatistic:
        targets.append(global_target(empty_policy=global_empty_policy))
    targets.extend(user_statistic_targets(user_config))
    if compact_summary:
        targets = [_prefer_compact_summaries(target) for target in targets]
    return targets


def _prefer_compact_summaries(target: NotifyTarget) -> NotifyTarget:
    """按渠道目标声明应用业务提供的紧凑摘要偏好。"""

    channels = []
    for channel, channel_target in target.channels:
        if channel_target.compact_summary_policy is not None:
            channel_target = replace(
                channel_target, summary_policy=channel_target.compact_summary_policy
            )
        channels.append((channel, channel_target))
    return replace(
        target,
        channels=tuple(channels),
    )


async def dispatch(
    payload: NotifyPayload,
    targets: Iterable[NotifyTarget],
    *,
    attempts: int = 1,
    retry_delay: float = 0,
    skip_channels: Iterable[str] = (),
    skip_channel_ids: Iterable[str] = (),
    notifier: Notifier | None = None,
) -> DispatchResult:
    """保留业务入口；发送器在此装配，底层投递只接受显式依赖。"""
    return await dispatch_notification(
        payload=payload,
        targets=targets,
        attempts=attempts,
        retry_delay=retry_delay,
        skip_channels=skip_channels,
        skip_channel_ids=skip_channel_ids,
        notifier=Notify if notifier is None else notifier,
    )


async def send_test_notification() -> DispatchResult:
    """向全部已启用的全局渠道发送测试通知。"""

    text = (
        "这是 AUTO-MAS 外部通知测试信息。如果你看到了这段内容，说明 AUTO-MAS "
        "的通知功能已经正确配置且可以正常工作！"
    )
    return await dispatch(
        NotifyPayload(
            title="AUTO-MAS测试通知",
            text=text,
            append_signature=False,
        ),
        [
            global_target(
                include_system=True,
                empty_policy="warn",
                system_timeout_seconds=3,
            )
        ],
    )
