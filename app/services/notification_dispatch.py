"""只执行已解析的通知目标；配置、业务状态和发送器装配由宿主负责。"""

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from app.models.notification import NotifyPayload
from app.models.notification_channel import (
    ChannelTarget,
    DispatchResult,
    EmptyPolicy,
    Notifier,
    NotifyChannel,
    NotifyTarget,
)
from app.utils import get_logger
from app.utils.notification_render import render_for_target

logger = get_logger("通知投递")


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


async def dispatch(
    payload: NotifyPayload,
    targets: Iterable[NotifyTarget],
    *,
    attempts: int = 1,
    retry_delay: float = 0,
    skip_channels: Iterable[str] = (),
    skip_channel_ids: Iterable[str] = (),
    notifier: Notifier,
) -> DispatchResult:
    """向所有目标分发通知，返回实际尝试/成功/失败渠道。

    ``skip_channels`` 中的渠道不会被发送（也不计入尝试次数），用于只向
    尚未送达的渠道重试，避免已成功渠道收到重复内容。
    ``skip_channel_ids`` 按稳定 ID 跳过，不受 Webhook 同名或改名影响。
    ``notifier`` 由宿主注入；本模块不读取全局配置或查找通知单例。
    """

    if attempts < 1:
        raise ValueError("通知发送次数必须大于 0")

    sender = notifier

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
        for failure in target.unresolved:
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
