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

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, replace
from typing import Any, Literal, Protocol

from app.core.config import Config
from app.core.notify_channels import (
    ChannelTarget,
    NotifyChannel,
    TargetConfigView,
    get_notify_channel_failures,
    get_notify_channels,
)
from app.models.notification import (
    NotifyPayload,
    RenderedNotification,
)
from app.services.notification import Notify
from app.utils import get_logger
from app.utils.notification_render import render_for_target

logger = get_logger("通知编排")

EmptyPolicy = Literal["send", "warn", "skip"]


@dataclass(frozen=True)
class NotifyTarget:
    """一组通知渠道及其配置来源。

    ``channels`` 是「渠道 + 已解析目标」的配对：发送方法是渠道的、空值策略在
    目标上，两个都要带得出来。构造时现读一次配置并固定为快照，分发全程不再
    读配置。
    """

    channels: tuple[tuple[NotifyChannel, ChannelTarget], ...] = ()
    empty_policy: EmptyPolicy = "send"
    # 声明损坏时无法确定目标；只记目录未确认，不计作一次实际投递。
    catalog_failures: tuple[str, ...] = ()


@dataclass(frozen=True)
class DispatchResult:
    """一次通知分发的明确结果。

    ``attempted`` 是本次实际尝试投递的渠道数（被跳过的渠道不计入）；
    ``succeeded`` / ``failed`` 分别是成功与失败的渠道名。零目标或全跳过时
    ``attempted`` 为 0，切勿把该状态当作「已送达」。
    ``failed`` 也保留无法确认的渠道目录；这类错误不增加 ``attempted``。
    """

    attempted: int = 0
    succeeded: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()
    # 内部投递记录使用 ID，用户可见的 succeeded/failed 继续保留渠道名称。
    succeeded_ids: tuple[str, ...] = ()


def global_target(
    *,
    include_system: bool = False,
    empty_policy: EmptyPolicy = "send",
    system_timeout_seconds: int | None = None,
) -> NotifyTarget:
    """按全局配置构造通知目标。"""

    # 构造时现读一次配置并固定为快照；扫码解绑等运行期写入只对之后构造的目标可见。
    pairs: list[tuple[NotifyChannel, ChannelTarget]] = []
    for channel in get_notify_channels():
        for target in channel.targets(TargetConfigView(Config.setting), scope="global"):
            if target.is_local and not include_system:
                continue
            if target.is_local and system_timeout_seconds is not None:
                target = replace(target, timeout_seconds=system_timeout_seconds)
            pairs.append((channel, target))
    return NotifyTarget(
        channels=tuple(pairs),
        empty_policy=empty_policy,
        catalog_failures=get_notify_channel_failures(),
    )


def user_target(user_config: Any) -> NotifyTarget:
    """按用户配置构造独立通知目标。"""

    pairs: list[tuple[NotifyChannel, ChannelTarget]] = []
    for channel in get_notify_channels():
        pairs.extend(
            (channel, target)
            for target in channel.targets(TargetConfigView(user_config), scope="user")
        )
    return NotifyTarget(
        channels=tuple(pairs),
        empty_policy="warn",
        catalog_failures=get_notify_channel_failures(),
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


async def _send(
    channel: str,
    send: Callable[[], Awaitable[Any]],
    *,
    attempts: int,
    retry_delay: float,
) -> bool:
    """发送单个渠道，并把异常和显式 False 都视作失败。"""

    for attempt in range(1, attempts + 1):
        try:
            result = await send()
            if result is False:
                raise RuntimeError("通知渠道返回失败状态")
            return True
        except Exception as exc:
            if attempt == attempts:
                logger.warning(f"{channel}通知发送失败: {type(exc).__name__}")
                break
            logger.warning(f"{channel}通知发送失败，将重试: {type(exc).__name__}")
            if retry_delay > 0:
                await asyncio.sleep(retry_delay)
    return False


def _recipient_action(
    value: str,
    policy: EmptyPolicy,
    *,
    channel: str,
    hint: str,
) -> tuple[bool, bool]:
    """返回是否发送，以及跳过是否应记为失败。"""

    if value or policy == "send":
        return True, False
    if policy == "warn":
        logger.warning(f"{hint}为空，无法发送{channel}通知")
        return False, True
    return False, False


class Notifier(Protocol):
    """统一投递面；渠道内部的传输方法不进入公共协议。"""

    async def send_channel(
        self,
        channel: NotifyChannel,
        target: ChannelTarget,
        rendered: RenderedNotification,
    ) -> bool | None: ...


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
    """向所有目标分发通知，返回实际尝试/成功/失败渠道。

    ``skip_channels`` 中的渠道不会被发送（也不计入尝试次数），用于只向
    尚未送达的渠道重试，避免已成功渠道收到重复内容。
    ``skip_channel_ids`` 按稳定 ID 跳过，不受 Webhook 同名或改名影响。
    ``notifier`` 缺省用全局 Notify 单例，注入面供测试与渠道扩展替换。
    """

    if attempts < 1:
        raise ValueError("通知发送次数必须大于 0")

    sender = Notify if notifier is None else notifier

    skip = set(skip_channels)
    skip_ids = set(skip_channel_ids)
    succeeded: list[str] = []
    succeeded_ids: list[str] = []
    failed: list[str] = []
    attempted = 0
    catalog_failures: list[str] = []

    async def attempt(
        channel: str,
        channel_impl: NotifyChannel,
        channel_target: ChannelTarget,
        *,
        channel_id: str | None = None,
    ) -> None:
        nonlocal attempted
        delivery_id = channel_id or channel
        if channel in skip or delivery_id in skip_ids:
            return
        attempted += 1
        try:
            rendered = render_for_target(
                payload,
                channel_target.capabilities,
                summary_policy=channel_target.summary_policy,
                use_summary_title=channel_target.use_summary_title,
            )
        except Exception as exc:
            logger.warning(f"{channel}通知内容准备失败: {exc}")
            failed.append(channel)
            return
        for diagnostic in rendered.diagnostics:
            logger.warning(f"{channel}通知内容降级: {diagnostic}")

        async def send() -> Any:
            return await sender.send_channel(channel_impl, channel_target, rendered)

        if await _send(channel, send, attempts=attempts, retry_delay=retry_delay):
            succeeded.append(channel)
            succeeded_ids.append(delivery_id)
        else:
            failed.append(channel)

    def miss(channel: str) -> None:
        nonlocal attempted
        if channel in skip or channel in skip_ids:
            return
        attempted += 1
        failed.append(channel)

    for target in targets:
        # 跳过已送达 ID 不能消除目录不完整；不伪造目标、发送或递增尝试数。
        for failure in target.catalog_failures:
            if failure not in catalog_failures:
                catalog_failures.append(failure)
        for channel, ct in target.channels:
            should_send = True
            # None 表示该渠道不做空值判定（系统通知 / Koishi / QQ / Webhook），
            # 不能进 _recipient_action：None 与空串同判真值会把它们在 warn 下误记失败。
            if ct.empty_recipient is not None:
                should_send, missing = _recipient_action(
                    ct.empty_recipient,
                    target.empty_policy,
                    channel=ct.label,
                    hint=ct.empty_hint,
                )
                if missing:
                    miss(ct.label)
            if should_send:
                await attempt(
                    ct.label,
                    channel,
                    ct,
                    channel_id=ct.id,
                )

    return DispatchResult(
        attempted=attempted,
        succeeded=tuple(succeeded),
        failed=tuple((*failed, *catalog_failures)),
        succeeded_ids=tuple(succeeded_ids),
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
