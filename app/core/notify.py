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
``app.services.notification`` 只保留具体渠道的传输实现。
"""

import asyncio
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from typing import Any, Literal, Protocol

from app.core.config import Config
from app.core.notify_channels import (
    ChannelTarget,
    NotifyChannel,
    TargetConfigView,
    get_notify_channels,
)
from app.core.notify_render import render_for_target
from app.models.notification import (
    NOTIFICATION_SIGNATURE,
    NotificationImage,
    NotifyPayload,
    WebhookTargetSnapshot,
)
from app.runtime_tasks import RuntimeTasks
from app.services.notification import Notification, Notify
from app.utils import get_logger

logger = get_logger("通知编排")

SIGNATURE = NOTIFICATION_SIGNATURE
_PENDING_TASK_COMMUNITY_NOTIFICATIONS: set[asyncio.Task[Any]] = set()


def track_community_notification(task: asyncio.Task[Any]) -> None:
    """手动签到的慢渠道同样交给关闭/热更前的补发等待。"""
    _PENDING_TASK_COMMUNITY_NOTIFICATIONS.add(task)
    task.add_done_callback(_PENDING_TASK_COMMUNITY_NOTIFICATIONS.discard)


EmptyPolicy = Literal["send", "warn", "skip"]


@dataclass(frozen=True)
class NotifyTarget:
    """一组通知渠道及其配置来源。

    ``channels`` 是「渠道 + 已解析目标」的配对：发送方法是渠道的、空值策略在
    目标上，两个都要带得出来。构造时现读一次配置并固定为快照，分发全程不再
    读配置。
    """

    name: str
    channels: tuple[tuple[NotifyChannel, ChannelTarget], ...] = ()
    empty_policy: EmptyPolicy = "send"


@dataclass(frozen=True)
class DispatchResult:
    """一次通知分发的明确结果。

    ``attempted`` 是本次实际尝试投递的渠道数（被跳过的渠道不计入）；
    ``succeeded`` / ``failed`` 分别是成功与失败的渠道名。零目标或全跳过时
    ``attempted`` 为 0，切勿把该状态当作「已送达」。
    """

    attempted: int = 0
    succeeded: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()
    # 内部投递记录使用 ID，用户可见的 succeeded/failed 继续保留渠道名称。
    succeeded_ids: tuple[str, ...] = ()


class TaskCommunitySignNotification:
    """接收后台签到完成事件，串行协调报告合并和迟到结果补发。"""

    def __init__(self, task_info: Any) -> None:
        self.task_info = task_info
        self.completed = asyncio.Event()
        self.lock = asyncio.Lock()
        self.targets: list[NotifyTarget] | None = None
        self.report_sent = False
        self.wait_expired = False
        self.result_unavailable = False
        self.task_finished = False
        self.delivery_task: asyncio.Task[None] | None = None

    def receive(self, results: list[dict[str, object]] | None) -> None:
        """先保存结果再发布完成事件；报告等待超时不会取消签到。"""

        from app.tools.community_notify import filter_community_notification_results

        self.result_unavailable = results is None
        # 占位项不参与实际通知，先统一过滤，确保空结果也能结清待确认提示。
        self.task_info.community_results = filter_community_notification_results(
            results or []
        )
        self.completed.set()
        self.schedule_supplement()

    @property
    def completion_notice(self) -> str:
        """异常不能推断实际签到失败，正常空结果只结清已发出的待确认提示。"""

        from app.tools.community_notify import (
            COMMUNITY_SIGN_EMPTY_RESULT_TEXT,
            COMMUNITY_SIGN_RESULT_UNAVAILABLE_TEXT,
        )

        if self.result_unavailable:
            return COMMUNITY_SIGN_RESULT_UNAVAILABLE_TEXT
        if (
            self.wait_expired
            and self.completed.is_set()
            and not self.task_info.community_results
        ):
            return COMMUNITY_SIGN_EMPTY_RESULT_TEXT
        return ""

    def finish(self) -> None:
        """没有脚本报告（如预检失败或手动停止）时也保留签到通知出口。"""

        self.task_finished = True
        self.schedule_supplement()

    def schedule_supplement(self) -> None:
        if not self.completed.is_set() or not (
            self.task_finished or (self.report_sent and self.wait_expired)
        ):
            return
        if not self.task_info.community_results and not self.completion_notice:
            return
        if self.delivery_task is not None and not self.delivery_task.done():
            return
        self.delivery_task = RuntimeTasks.spawn(
            self._send_supplement(),
            name=f"task-community-notification:{self.task_info.task_id}",
        )
        if self.delivery_task is not None:
            _PENDING_TASK_COMMUNITY_NOTIFICATIONS.add(self.delivery_task)
            self.delivery_task.add_done_callback(
                _PENDING_TASK_COMMUNITY_NOTIFICATIONS.discard
            )

    async def _send_supplement(self) -> None:
        from app.tools.community_notify import (
            dispatch_community_notification,
            report_community_notification_failure,
        )

        # 与报告投递共用锁：即使结果在报告发送中到达，也只补发未收到摘要的渠道。
        async with self.lock:
            if self.task_info.community_summary_consumed or not Config.ToolsConfig.get(
                "GameSign", "NotifyEnabled"
            ):
                return
            delivered = set(getattr(self.task_info, "game_sign_summary_delivered", ()))
            result = await dispatch_community_notification(
                self.task_info.community_results,
                targets=self.targets,
                skip_channel_ids=delivered,
                completion_notice=self.completion_notice,
            )
            delivered.update(result.succeeded_ids)
            self.task_info.game_sign_summary_delivered = delivered
            self.task_info.game_sign_summary_pending = result.failed
            if result.attempted and not result.failed:
                self.task_info.community_summary_consumed = True
            if result.failed:
                await report_community_notification_failure(
                    list(result.failed),
                    results_saved=bool(self.task_info.community_results),
                )


async def drain_task_community_notifications(timeout: float) -> bool:
    """电源动作前有限等待签到补发，超时只停止等待，不取消投递。"""

    deadline = asyncio.get_running_loop().time() + timeout
    while tasks := {
        task for task in _PENDING_TASK_COMMUNITY_NOTIFICATIONS if not task.done()
    }:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            return False
        _, pending = await asyncio.wait(tasks, timeout=remaining)
        if pending:
            return False
    return True


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
        # include_system 只作用于系统通知渠道，False 时对应路径不弹系统通知
        if channel.key == "system" and not include_system:
            continue
        for target in channel.targets(TargetConfigView(Config), scope="global"):
            if channel.key == "system" and system_timeout_seconds is not None:
                target = replace(target, timeout_seconds=system_timeout_seconds)
            pairs.append((channel, target))
    return NotifyTarget(
        name="全局",
        channels=tuple(pairs),
        empty_policy=empty_policy,
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
        name="用户",
        channels=tuple(pairs),
        empty_policy="warn",
    )


def should_send_result(message: dict, *, task_info: object | None = None) -> bool:
    """判断代理结果是否满足全局推送时机。"""

    if message.get("game_sign_summary", False):
        return True

    if task_info is not None:
        from app.tools.community_notify import append_task_community_summary

        if append_task_community_summary(task_info, ""):
            return True
        community_sign = getattr(task_info, "community_sign_notification", None)
        if (
            community_sign is not None
            and not community_sign.completed.is_set()
            and Config.ToolsConfig.get("GameSign", "NotifyEnabled")
        ):
            return True

    result_time = Config.get("Notify", "SendTaskResultTime")
    if result_time == "任何时刻":
        return True

    return result_time == "仅失败时" and message["uncompleted_count"] != 0


def user_statistic_targets(user_config: Any | None) -> list[NotifyTarget]:
    """返回已启用统计通知的用户目标。"""

    if (
        user_config is None
        or not user_config.get("Notify", "Enabled")
        or not user_config.get("Notify", "IfSendStatistic")
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
    if Config.get("Notify", "IfSendStatistic"):
        targets.append(global_target(empty_policy=global_empty_policy))
    targets.extend(user_statistic_targets(user_config))
    if compact_summary:
        targets = [_prefer_webhook_summaries(target) for target in targets]
    return targets


def _prefer_webhook_summaries(target: NotifyTarget) -> NotifyTarget:
    """为明确提供紧凑摘要的统计消息设置 Webhook 摘要偏好。"""

    channels = []
    for channel, channel_target in target.channels:
        if channel.key == "webhook":
            channel_target = replace(channel_target, summary_policy="preferred")
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
                logger.warning(f"{channel}通知发送失败: {exc}")
                break
            logger.warning(f"{channel}通知发送失败，将重试: {exc}")
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
    """``dispatch`` 需要的通知渠道发送面。

    默认实现是 ``app.services.notification.Notify``（模块级单例），测试与
    未来的渠道扩展可传入自己的实现。按 ``_send`` 的判定，返回 ``False``
    表示该渠道发送失败，``None`` 表示成功。
    """

    async def push_plyer(
        self, title: str, message: str, ticker: str, t: int
    ) -> bool | None: ...

    async def send_mail(
        self,
        mode: Literal["文本", "网页"],
        title: str,
        content: str,
        to_address: str,
        *,
        images: Sequence[NotificationImage] = (),
    ) -> bool | None: ...

    async def ServerChanPush(
        self, title: str, content: str, send_key: str
    ) -> bool | None: ...

    async def send_cmcc_newmsg(
        self, title: str, content: str, api_key: str
    ) -> bool | None: ...

    async def WebhookPush(
        self,
        title: str,
        content: str,
        webhook: WebhookTargetSnapshot,
        *,
        images: Sequence[NotificationImage] = (),
    ) -> bool | None: ...

    async def send_koishi(
        self, message: str, msgtype: str = "text", client_name: str = "Koishi"
    ) -> bool | None: ...

    async def send_openclaw_qq(
        self,
        title: str,
        content: str,
        *,
        images: Sequence[NotificationImage] = (),
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

    ``skip_channels`` 中的渠道不会被发送（也不计入尝试次数），用于签到汇总
    等场景只向尚未送达的渠道重试，避免已成功渠道收到重复内容。
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
            if isinstance(sender, Notification):
                return await sender.send_channel(channel_impl, channel_target, rendered)
            return await channel_impl.send(sender, channel_target, rendered)

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
        failed=tuple(failed),
        succeeded_ids=tuple(succeeded_ids),
    )


async def dispatch_task_report(
    payload: NotifyPayload,
    targets: list[NotifyTarget],
    task_info: object | None,
    *,
    summary_text: str = "",
    attempts: int = 1,
    retry_delay: float = 0,
    notifier: Notifier | None = None,
) -> DispatchResult:
    """报告只短暂等待签到事件，超时照常投递，迟到结果在后台补发。"""

    community_sign = getattr(task_info, "community_sign_notification", None)
    if community_sign is None:
        return await _dispatch_task_report(
            payload=payload,
            targets=targets,
            task_info=task_info,
            summary_text=summary_text,
            attempts=attempts,
            retry_delay=retry_delay,
            notifier=notifier,
        )

    from app.tools.community_notify import (
        NOTIFICATION_FAST_PATH_WAIT_SECONDS,
        append_community_summary_html,
    )

    async with community_sign.lock:
        community_sign.targets = targets
        notify_enabled = Config.ToolsConfig.get("GameSign", "NotifyEnabled")
        if (
            notify_enabled
            and not community_sign.completed.is_set()
            and not community_sign.wait_expired
        ):
            try:
                await asyncio.wait_for(
                    community_sign.completed.wait(),
                    timeout=NOTIFICATION_FAST_PATH_WAIT_SECONDS,
                )
            except asyncio.TimeoutError:
                community_sign.wait_expired = True
                logger.info("签到结果尚未返回，先发送任务报告，完成后补发签到结果")
        if notify_enabled and not community_sign.completed.is_set():
            pending_text = "社区签到结果待确认，完成后另行通知。"
            payload = replace(
                payload,
                text=f"{payload.text}\n\n{pending_text}",
                html=(
                    append_community_summary_html(payload.html, pending_text)
                    if payload.html is not None
                    else None
                ),
                markdown=f"{payload.markdown or payload.text}\n\n{pending_text}",
                summary=(
                    replace(
                        payload.summary,
                        text=f"{payload.summary.text}\n\n{pending_text}",
                        overflow_text=(
                            f"{payload.summary.overflow_text or payload.text}"
                            f"\n\n{pending_text}"
                        ),
                    )
                    if payload.summary is not None
                    else None
                ),
            )
        try:
            return await _dispatch_task_report(
                payload=payload,
                targets=targets,
                task_info=task_info,
                summary_text=summary_text,
                attempts=attempts,
                retry_delay=retry_delay,
                notifier=notifier,
            )
        finally:
            community_sign.report_sent = True
            community_sign.schedule_supplement()


async def _dispatch_task_report(
    payload: NotifyPayload,
    targets: list[NotifyTarget],
    task_info: object | None,
    *,
    summary_text: str = "",
    attempts: int = 1,
    retry_delay: float = 0,
    notifier: Notifier | None = None,
) -> DispatchResult:
    """统一附加社区结果，并按渠道维护任务报告的投递状态。

    专项只提供原始报告与任务信息。旧调用传入的 summary_text 继续兼容，
    已送达摘要的渠道接收后续脚本报告时不再重复摘要。
    """

    # 社区渲染器复用 NotifyPayload，按需导入以避免模块初始化循环。
    from app.tools.community_notify import (
        append_community_summary_html,
        append_task_community_summary,
        mark_task_community_summary_consumed,
    )

    delivered = set(getattr(task_info, "game_sign_summary_delivered", ()))
    if summary_text:
        markdown_summary = (
            append_task_community_summary(
                task_info, "", output_format="markdown"
            ).strip()
            if task_info is not None
            else summary_text
        )
        markdown = payload.markdown or payload.text
        if markdown_summary and markdown_summary not in markdown:
            markdown = (
                markdown.replace(summary_text, markdown_summary)
                if summary_text in markdown
                else f"{markdown}\n\n{markdown_summary}"
            )
        clean_payload = replace(
            payload,
            text=payload.text.replace(summary_text, "").rstrip(),
            html=(
                payload.html.replace(summary_text, "").rstrip()
                if payload.html is not None
                else None
            ),
            summary=(
                replace(
                    payload.summary,
                    text=payload.summary.text.replace(summary_text, "").rstrip(),
                    overflow_text=(
                        payload.summary.overflow_text.replace(summary_text, "").rstrip()
                        if payload.summary.overflow_text is not None
                        else None
                    ),
                )
                if payload.summary is not None
                else None
            ),
            markdown=(
                payload.markdown.replace(markdown_summary, "").rstrip()
                if payload.markdown is not None
                else payload.text.replace(summary_text, "").rstrip()
            ),
        )
        payload = replace(payload, markdown=markdown)
    else:
        clean_payload = payload
        if task_info is not None:
            summary_text = append_task_community_summary(task_info, "").strip()
        if summary_text:
            summary_markdown = append_task_community_summary(
                task_info, "", output_format="markdown"
            ).strip()
            markdown = payload.markdown or payload.text
            if summary_markdown:
                markdown = f"{markdown}\n\n{summary_markdown}"
            payload = replace(
                payload,
                text=f"{payload.text}\n\n{summary_text}",
                html=(
                    append_community_summary_html(payload.html, summary_text)
                    if payload.html is not None
                    else None
                ),
                markdown=markdown,
                summary=(
                    replace(
                        payload.summary,
                        text=f"{payload.summary.text}\n\n{summary_text}",
                        overflow_text=(
                            f"{payload.summary.overflow_text or payload.text}"
                            f"\n\n{summary_text}"
                        ),
                    )
                    if payload.summary is not None
                    else None
                ),
            )

    if not summary_text:
        result = await dispatch(
            payload,
            targets,
            attempts=attempts,
            retry_delay=retry_delay,
            notifier=notifier,
        )
    else:
        channels = {ct.id for target in targets for _, ct in target.channels}
        with_summary = await dispatch(
            payload,
            targets,
            attempts=attempts,
            retry_delay=retry_delay,
            skip_channel_ids=delivered,
            notifier=notifier,
        )
        # 只给本轮开始前已送达摘要的渠道发原始报告，避免同一轮发送两次。
        without_summary = (
            await dispatch(
                clean_payload,
                targets,
                attempts=attempts,
                retry_delay=retry_delay,
                skip_channel_ids=channels - delivered,
                notifier=notifier,
            )
            if delivered & channels
            else DispatchResult()
        )
        delivered.update(with_summary.succeeded_ids)
        if task_info is not None:
            setattr(task_info, "game_sign_summary_delivered", delivered)
            setattr(task_info, "game_sign_summary_pending", with_summary.failed)
            if delivered & channels and not with_summary.failed:
                mark_task_community_summary_consumed(task_info)
        result = DispatchResult(
            attempted=with_summary.attempted + without_summary.attempted,
            succeeded=with_summary.succeeded + without_summary.succeeded,
            failed=with_summary.failed + without_summary.failed,
            succeeded_ids=with_summary.succeeded_ids + without_summary.succeeded_ids,
        )

    await _publish_task_notification_failure(task_info, result)
    return result


async def _publish_task_notification_failure(
    task_info: object | None, result: DispatchResult
) -> None:
    """把任务报告的渠道失败同步提示到当前任务页面。"""

    if not result.failed or task_info is None:
        return
    task_id = getattr(task_info, "task_id", None)
    if not task_id:
        return

    from app.core.ws import Publisher, protocol
    from app.models.schema import WSTaskNoticeData

    failed_channels = tuple(dict.fromkeys(result.failed))
    title = "部分通知发送失败" if result.succeeded else "通知发送失败"
    message = f"{title}：{'、'.join(failed_channels)}"
    try:
        await Publisher.send(
            id=str(task_id),
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level="warning", message=message),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"发送通知失败提示到前端时出现异常: {exc}")


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
