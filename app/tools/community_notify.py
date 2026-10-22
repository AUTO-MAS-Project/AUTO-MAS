#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


"""社区通知兼容入口；编排和后台任务所有权由 core 负责。"""

from collections.abc import Iterable

from app.core.community_notify import (
    get_community_notifier,
    report_community_notification_failure,
)
from app.core.notification_report import (
    COMMUNITY_SIGN_EMPTY_RESULT_TEXT,
    COMMUNITY_SIGN_RESULT_UNAVAILABLE_TEXT,
    NOTIFICATION_FAST_PATH_WAIT_SECONDS,
    NOTIFICATION_RETRY_DELAY_SECONDS,
    NOTIFICATION_SEND_ATTEMPTS,
)
from app.models.notification import NotifyPayload
from app.models.notification_channel import DispatchResult, NotifyTarget
from app.models.notification_community import community_notification_results
from app.services import community_notification as content
from app.services.community_notification import NotificationBodyFormat


def filter_community_notification_results(
    results: list[dict[str, object]],
) -> list[dict[str, object]]:
    return [item for item in results if not item.get("_notification_only")]


def build_community_notification_payload(
    results: list[dict[str, object]],
) -> NotifyPayload:
    return content.build_community_notification_payload(
        community_notification_results(results)
    )


def format_community_notification(
    results: list[dict[str, object]],
    *,
    output_format: NotificationBodyFormat = "markdown",
    include_signature: bool = True,
    include_title: bool = True,
) -> str:
    return content.format_community_notification(
        community_notification_results(results),
        output_format=output_format,
        include_signature=include_signature,
        include_title=include_title,
    )


def format_community_task_summary(
    results: list[dict[str, object]],
    *,
    output_format: NotificationBodyFormat = "text",
) -> str:
    return content.format_community_task_summary(
        community_notification_results(results),
        output_format=output_format,
    )


async def dispatch_community_notification(
    results: list[dict[str, object]],
    *,
    targets: list[NotifyTarget] | None = None,
    skip_channel_ids: Iterable[str] = (),
    completion_notice: str = "",
) -> DispatchResult:
    return await get_community_notifier().dispatch(
        community_notification_results(results),
        targets=targets,
        skip_channel_ids=skip_channel_ids,
        completion_notice=completion_notice,
    )


async def push_community_notification(results: list[dict[str, object]]) -> list[str]:
    return await get_community_notifier().send(community_notification_results(results))


__all__ = [
    "COMMUNITY_SIGN_EMPTY_RESULT_TEXT",
    "COMMUNITY_SIGN_RESULT_UNAVAILABLE_TEXT",
    "NOTIFICATION_FAST_PATH_WAIT_SECONDS",
    "NOTIFICATION_RETRY_DELAY_SECONDS",
    "NOTIFICATION_SEND_ATTEMPTS",
    "build_community_notification_payload",
    "dispatch_community_notification",
    "filter_community_notification_results",
    "format_community_notification",
    "format_community_task_summary",
    "push_community_notification",
    "report_community_notification_failure",
]
