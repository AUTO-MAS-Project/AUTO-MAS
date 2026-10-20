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

"""任务报告与社区签到结果的协调、合并及迟到补发。"""

import asyncio
from dataclasses import replace
from typing import Any

from app.core.config import Config
from app.core.notify import DispatchResult, Notifier, NotifyTarget, dispatch
from app.models.notification import NotifyPayload
from app.runtime_tasks import RuntimeTasks
from app.utils import get_logger

logger = get_logger("任务报告")

_PENDING_TASK_COMMUNITY_NOTIFICATIONS: set[asyncio.Task[Any]] = set()


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
            if (
                self.task_info.community_summary_consumed
                or not Config.ToolsConfig.GameSign.NotifyEnabled
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


async def shutdown_community_notifications() -> None:
    """退出时取消并等待任务报告补发，然后才能释放共享连接。"""

    tasks = [task for task in _PENDING_TASK_COMMUNITY_NOTIFICATIONS if not task.done()]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


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
            and (not community_sign.completed.is_set())
            and Config.ToolsConfig.GameSign.NotifyEnabled
        ):
            return True

    result_time = Config.setting.Notify.SendTaskResultTime
    if result_time == "任何时刻":
        return True

    return result_time == "仅失败时" and message["uncompleted_count"] != 0


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
        notify_enabled = Config.ToolsConfig.GameSign.NotifyEnabled
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

    # 按需读取社区报告格式化工具。
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
        catalog_failures = {
            failure for target in targets for failure in target.catalog_failures
        }
        result = DispatchResult(
            attempted=with_summary.attempted + without_summary.attempted,
            succeeded=with_summary.succeeded + without_summary.succeeded,
            failed=with_summary.failed
            + tuple(
                failure
                for failure in without_summary.failed
                if failure not in catalog_failures
            ),
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
