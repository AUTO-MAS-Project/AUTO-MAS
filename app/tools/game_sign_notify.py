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


"""历史游戏签到通知兼容入口。"""

import dataclasses

from app.core.notify import (
    DispatchResult,
    NotifyPayload,
    NotifyTarget,
    dispatch,
    target_channel_names,
)
from app.utils.logger import get_logger

from .community_notify import (
    append_task_community_summary,
    detect_community_notification_format,
    format_community_notification,
    format_community_task_summary,
    get_task_community_summary,
    mark_task_community_summary_consumed,
    push_community_notification,
)

logger = get_logger("游戏社区通知兼容入口")

format_game_sign_notification = format_community_notification
format_game_sign_task_summary = format_community_task_summary
get_task_game_sign_summary = get_task_community_summary
mark_task_game_sign_summary_consumed = mark_task_community_summary_consumed
append_task_game_sign_summary = append_task_community_summary
push_game_sign_notification = push_community_notification


def finalize_task_game_sign_notification(
    task_info: object,
    has_summary: bool,
    result: DispatchResult,
) -> None:
    """记录部分失败，并在汇总送达全部渠道后消费签到汇总。"""

    if result.failed:
        logger.warning(f"推送代理结果部分失败: {'、'.join(result.failed)}")
    if not has_summary:
        return
    # 渠道级投递状态由 dispatch_task_report 写入:
    # 零实际渠道时 delivered 为空, 不会误标为已送达。
    if getattr(task_info, "game_sign_summary_delivered", ()) and not getattr(
        task_info, "game_sign_summary_pending", ()
    ):
        mark_task_game_sign_summary_consumed(task_info)


async def dispatch_task_report(
    payload: NotifyPayload,
    targets: list[NotifyTarget],
    task_info: object,
    *,
    summary_text: str = "",
    attempts: int = 1,
    retry_delay: float = 0,
) -> DispatchResult:
    """分发带社区签到汇总的任务报告，并按渠道维护投递状态。

    含汇总的完整载荷只发送给尚未送达汇总的渠道；已送达汇总的渠道只补发
    去掉汇总的载荷，避免多脚本任务中已成功渠道收到重复摘要。渠道级状态
    继续记录在旧任务字段上，兼容已有任务报告协议。
    """

    delivered = set(getattr(task_info, "game_sign_summary_delivered", ()))
    if not summary_text:
        return await dispatch(
            payload, targets, attempts=attempts, retry_delay=retry_delay
        )

    channels = [
        channel for target in targets for channel in target_channel_names(target)
    ]
    with_summary = await dispatch(
        payload,
        targets,
        attempts=attempts,
        retry_delay=retry_delay,
        skip_channels=delivered,
    )
    delivered = delivered | set(with_summary.succeeded)

    if delivered:
        pending = [channel for channel in channels if channel not in delivered]
        clean_text = payload.text.replace(summary_text, "").rstrip()
        clean_html = (
            payload.html.replace(summary_text, "").rstrip()
            if payload.html is not None
            else None
        )
        without_summary = await dispatch(
            dataclasses.replace(payload, text=clean_text, html=clean_html),
            targets,
            attempts=attempts,
            retry_delay=retry_delay,
            skip_channels=pending,
        )
    else:
        without_summary = DispatchResult()

    setattr(task_info, "game_sign_summary_delivered", delivered)
    setattr(task_info, "game_sign_summary_pending", with_summary.failed)
    return DispatchResult(
        attempted=with_summary.attempted + without_summary.attempted,
        succeeded=with_summary.succeeded + without_summary.succeeded,
        failed=with_summary.failed + without_summary.failed,
    )


__all__ = [
    "append_task_game_sign_summary",
    "detect_community_notification_format",
    "dispatch_task_report",
    "finalize_task_game_sign_notification",
    "format_game_sign_notification",
    "format_game_sign_task_summary",
    "get_task_game_sign_summary",
    "mark_task_game_sign_summary_consumed",
    "push_game_sign_notification",
]
