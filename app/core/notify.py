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

脚本和业务模块负责生成正文，本模块负责配置、通知范围和默认发送器装配。
投递服务消费目标快照并执行渲染、重试与结果汇总，具体传输由各渠道实现。
"""

from collections.abc import Iterable
from dataclasses import replace

from app.config import config_manager
from app.core.config import Config
from app.core.notify_channels import (
    TargetConfigView,
    get_notify_channel_failures,
    get_notify_channels,
    read_notification_proxy,
)
from app.models.config import Webhook
from app.models.notification import NotifyPayload, WebhookTargetSnapshot
from app.models.notification_channel import (
    ChannelTarget,
    DeliveryChannel,
    NotificationSourceConfig,
    NotificationTransportSnapshot,
    RecruitmentNotificationConfig,
    UserNotificationConfig,
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
from app.models.notification_ports import WebhookTester
from app.services.notification import Notify
from app.services.notification_dispatch import dispatch as dispatch_notification
from app.utils import get_logger

logger = get_logger("通知编排")


def get_webhook_tester() -> WebhookTester:
    return Notify


def webhook_test_snapshot(webhook: Webhook) -> WebhookTargetSnapshot:
    """草稿测试固定输入，不按正式目标的启用状态过滤。"""

    return WebhookTargetSnapshot(
        name=str(webhook.Info.Name),
        enabled=bool(webhook.Info.Enabled),
        url=webhook.Data.Url,
        template=webhook.Data.Template,
        headers=webhook.Data.Headers,
        method=webhook.Data.Method,
    )


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


def user_target(user_config: NotificationSourceConfig) -> NotifyTarget:
    """按用户配置构造独立通知目标。"""
    return _resolve_target(config=user_config, scope="user", empty_policy="warn")


def _resolve_target(
    *,
    config: NotificationSourceConfig,
    scope: str,
    empty_policy: EmptyPolicy,
    include_system: bool = False,
    system_timeout_seconds: int | None = None,
) -> NotifyTarget:
    """逐渠道解析快照；一个渠道失败时保留其不确定性并继续其他渠道。"""
    pairs: list[tuple[DeliveryChannel, ChannelTarget]] = []
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
                resolved.append((channel.delivery(), target))
            if resolved and channel.transport_fields is not None:
                transport = NotificationTransportSnapshot(
                    values=tuple(
                        (name, getattr(Config.setting.Notify, name))
                        for name in channel.transport_fields
                    ),
                    proxy=read_notification_proxy(),
                )
                resolved = [
                    (delivery, replace(target, transport=transport))
                    for delivery, target in resolved
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


def user_statistic_targets(
    user_config: UserNotificationConfig | None,
) -> list[NotifyTarget]:
    """返回已启用统计通知的用户目标。"""

    if (
        user_config is None
        or not user_config.Notify.Enabled
        or not user_config.Notify.IfSendStatistic
    ):
        return []
    return [user_target(user_config)]


def recruitment_targets(
    user_config: RecruitmentNotificationConfig | None,
) -> list[NotifyTarget]:
    """按全局和个人订阅准备喜报目标，不识别具体传输渠道。"""

    targets = []
    if Config.setting.Notify.IfSendSixStar:
        targets.append(global_target())
    if (
        user_config is not None
        and user_config.Notify.Enabled
        and user_config.Notify.IfSendSixStar
    ):
        targets.append(user_target(user_config))
    return targets


def failure_targets() -> list[NotifyTarget]:
    """任务失败信号沿用任务结果开关，包含受自身开关约束的本地提示。"""

    if Config.setting.Notify.SendTaskResultTime == "不推送":
        return []
    return [global_target(include_system=True, system_timeout_seconds=10)]


def statistic_targets(
    user_config: UserNotificationConfig | None,
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
        concurrent=not config_manager.in_transaction,
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
