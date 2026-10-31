"""只执行已解析的通知目标；配置、业务状态和发送器装配由宿主负责。"""

import asyncio
from collections.abc import Iterable

from app.models.notification import (
    NotificationCapabilities,
    NotificationRenderer,
    NotifyPayload,
    RenderedNotification,
    SummaryPolicy,
)
from app.models.notification.channel import (
    ChannelTarget,
    DeliveryChannel,
    DeliveryFailure,
    DispatchResult,
    EmptyPolicy,
    NotificationDeliveryError,
    Notifier,
    NotifyTarget,
)
from app.utils import get_logger

logger = get_logger("通知投递")


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
    skip_channel_ids: Iterable[str] = (),
    notifier: Notifier,
    renderer: NotificationRenderer,
    concurrent: bool = True,
) -> DispatchResult:
    """按渠道独立投递并按输入顺序汇总，取消时回收本轮全部子任务。

    目录及目标解析失败不计 attempted，也不能因跳过已送达 ID 而消失。
    事务内调用由宿主传 concurrent=False，保持同 Task 的配置提交语义。
    """
    if attempts < 1:
        raise ValueError("通知发送次数必须大于 0")

    skip_ids = set(skip_channel_ids)
    unresolved: list[str] = []
    unresolved_failures: list[DeliveryFailure] = []
    jobs: list[tuple[DeliveryChannel, ChannelTarget, EmptyPolicy]] = []
    groups: dict[str, list[int]] = {}
    for target in targets:
        for failure in target.unresolved:
            if failure not in unresolved:
                unresolved.append(failure)
                unresolved_failures.append(
                    DeliveryFailure(
                        label=failure,
                        stage="catalog"
                        if failure in target.catalog_failures
                        else "preparation",
                        kind="unavailable",
                        retryable=False,
                    )
                )
        for channel, ct in target.channels:
            if ct.id not in skip_ids:
                groups.setdefault(channel.key, []).append(len(jobs))
                jobs.append((channel, ct, target.empty_policy))
    del skip_ids

    rendered_cache: dict[
        tuple[NotificationCapabilities, SummaryPolicy, bool], RenderedNotification
    ] = {}
    render_locks: dict[
        tuple[NotificationCapabilities, SummaryPolicy, bool], asyncio.Lock
    ] = {}

    async def render(target: ChannelTarget) -> RenderedNotification:
        capabilities = (
            target.announcement_capabilities
            if payload.presentation == "announcement"
            and target.announcement_capabilities is not None
            else target.capabilities
        )
        if len(jobs) <= 1:
            return await renderer.render(
                payload,
                capabilities,
                summary_policy=target.summary_policy,
                use_summary_title=target.use_summary_title,
            )
        key = capabilities, target.summary_policy, target.use_summary_title
        cached = rendered_cache.get(key)
        if cached is not None:
            return cached
        lock = render_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            render_locks[key] = lock
        # 只合并本轮相同表达的内容计算；传输不持锁，失败也不缓存。
        async with lock:
            cached = rendered_cache.get(key)
            if cached is None:
                cached = await renderer.render(
                    payload,
                    capabilities,
                    summary_policy=target.summary_policy,
                    use_summary_title=target.use_summary_title,
                )
                rendered_cache[key] = cached
                # 等待者已持有各自的锁引用，成功结果可替代本轮的锁登记。
                del render_locks[key]
                if not render_locks:
                    render_locks.clear()  # 释放空字典仍保留的容量。
            return cached

    async def deliver(
        channel: DeliveryChannel, target: ChannelTarget, policy: EmptyPolicy
    ) -> DispatchResult:
        # None 表示渠道不做空接收者判定，不能与空串共用真值判断。
        if target.empty_recipient is not None:
            should_send, missing = _recipient_action(
                value=target.empty_recipient,
                policy=policy,
                channel=target.label,
                hint=target.empty_hint,
            )
            if not should_send:
                return DispatchResult(
                    attempted=int(missing),
                    failed=(target.label,) if missing else (),
                    failures=(
                        DeliveryFailure(
                            label=target.label,
                            target_id=target.id,
                            stage="recipient",
                            kind="configuration",
                            retryable=False,
                        ),
                    )
                    if missing
                    else (),
                )
        try:
            rendered = await render(target)
        except Exception as exc:
            logger.warning(f"{target.label}通知内容准备失败: {type(exc).__name__}")
            return DispatchResult(
                attempted=1,
                failed=(target.label,),
                failures=(
                    DeliveryFailure(
                        label=target.label,
                        target_id=target.id,
                        stage="render",
                        kind="configuration",
                        retryable=False,
                        error_type=type(exc).__name__,
                    ),
                ),
            )
        for diagnostic in rendered.diagnostics:
            logger.warning(f"{target.label}通知内容降级: {diagnostic}")

        # 在目标协程里重试，发送期间不再额外保留闭包和转发协程。
        for attempt in range(1, attempts + 1):
            try:
                result = await notifier.send_channel(
                    channel=channel, target=target, rendered=rendered
                )
                if result is False:
                    raise RuntimeError("通知渠道返回失败状态")
            except Exception as exc:
                if isinstance(exc, NotificationDeliveryError):
                    kind, retryable = exc.kind, exc.retryable
                elif isinstance(exc, ValueError):
                    kind, retryable = "configuration", False
                elif isinstance(exc, (OSError, TimeoutError, ConnectionError)):
                    kind, retryable = "transport", True
                else:
                    kind, retryable = "unknown", True
                failure = DeliveryFailure(
                    label=target.label,
                    target_id=target.id,
                    stage="send",
                    kind=kind,
                    retryable=retryable,
                    attempts=attempt,
                    error_type=type(exc).__name__,
                )
                if attempt == attempts or not retryable:
                    logger.warning(f"{target.label}通知发送失败: {type(exc).__name__}")
                    break
                logger.warning(
                    f"{target.label}通知发送失败，将重试: {type(exc).__name__}"
                )
                if retry_delay > 0:
                    await asyncio.sleep(retry_delay)
            else:
                return DispatchResult(
                    attempted=1, succeeded=(target.label,), succeeded_ids=(target.id,)
                )
        return DispatchResult(attempted=1, failed=(target.label,), failures=(failure,))

    if len(jobs) == 1 and not unresolved:
        channel, target, policy = jobs[0]
        return await deliver(channel=channel, target=target, policy=policy)

    results: dict[int, DispatchResult] = {}

    if not concurrent or len(groups) <= 1:
        # 不建子 Task；配置事务的所有者必须与渠道内部提交者相同。
        for index, (channel, target, policy) in enumerate(jobs):
            results[index] = await deliver(
                channel=channel, target=target, policy=policy
            )
    else:
        pending = iter(groups.values())

        async def send_groups() -> None:
            for group in pending:
                for index in group:
                    channel, target, policy = jobs[index]
                    results[index] = await deliver(
                        channel=channel, target=target, policy=policy
                    )

        tasks = [
            asyncio.create_task(send_groups(), name=f"notification:{worker}")
            for worker in range(min(4, len(groups)))
        ]
        joined = asyncio.gather(*tasks)
        try:
            await asyncio.shield(joined)
        except BaseException:
            # 只向子任务取消一次；父任务的后续取消不能中断渠道 finally 的异步清理。
            for task in tasks:
                if not task.done():
                    task.cancel()
            cleanup = asyncio.gather(*tasks, return_exceptions=True)
            while not cleanup.done():
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    continue
            # 父任务取消时 joined 没有被直接等待，取走其异常以免留下未消费的 Future。
            if joined.done() and not joined.cancelled():
                joined.exception()
            raise

    ordered = [results[index] for index in range(len(jobs))]
    return DispatchResult(
        attempted=sum(result.attempted for result in ordered),
        succeeded=tuple(name for result in ordered for name in result.succeeded),
        failed=tuple(name for result in ordered for name in result.failed)
        + tuple(unresolved),
        succeeded_ids=tuple(uid for result in ordered for uid in result.succeeded_ids),
        failures=tuple(f for result in ordered for f in result.failures)
        + tuple(unresolved_failures),
    )
