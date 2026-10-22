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


"""社区通知入口；内容生成与发送装配分别由服务层和 core 负责。"""

from collections.abc import Iterable

from app.core import Config
from app.core.notification_report import (
    COMMUNITY_SIGN_EMPTY_RESULT_TEXT,
    COMMUNITY_SIGN_RESULT_UNAVAILABLE_TEXT,
    NOTIFICATION_FAST_PATH_WAIT_SECONDS,
    NOTIFICATION_RETRY_DELAY_SECONDS,
    NOTIFICATION_SEND_ATTEMPTS,
)
from app.core.notify import DispatchResult, NotifyTarget, dispatch, global_target
from app.models.notification import NotifyPayload
from app.services.community_notification import (
    build_community_notification_payload,
    filter_community_notification_results,
    format_community_notification,
    format_community_task_summary,
)


async def dispatch_community_notification(
    results: list[dict[str, object]],
    *,
    targets: list[NotifyTarget] | None = None,
    skip_channel_ids: Iterable[str] = (),
    completion_notice: str = "",
) -> DispatchResult:
    """分发社区通知并保留完整渠道结果，供新旧入口共同使用。"""
    results = filter_community_notification_results(results)
    if not results and not completion_notice:
        return DispatchResult()

    payload = (
        build_community_notification_payload(results)
        if results
        else NotifyPayload(title="社区签到执行结束", text=completion_notice)
    )
    return await dispatch(
        payload,
        targets if targets is not None else [global_target(include_system=True)],
        attempts=NOTIFICATION_SEND_ATTEMPTS,
        retry_delay=NOTIFICATION_RETRY_DELAY_SECONDS,
        skip_channel_ids=skip_channel_ids,
    )


async def report_community_notification_failure(
    failed_channels: list[str], *, results_saved: bool = True
) -> None:
    """通知渠道级失败改用系统提示回传，不让发送结果只留在日志里。

    Args:
        failed_channels: 本次分发中发送失败的渠道名。
        results_saved: 是否存在已保存的签到结果，空结果终态不宣称保存成功。
    """

    await Config.push_system_notice(
        level="warning",
        title="游戏社区通知发送不完整",
        lines=[
            f"发送失败的渠道：{'、'.join(failed_channels)}",
            (
                "签到结果已保存，请检查这些渠道的通知配置后重试。"
                if results_saved
                else "请检查这些渠道的通知配置后重试。"
            ),
        ],
    )


async def push_community_notification(
    results: list[dict[str, object]],
) -> list[str]:
    """推送手动或启动时触发的社区通知，返回失败渠道；失败时另发系统提示。"""

    dispatch_result = await dispatch_community_notification(results)
    failed_channels = list(dispatch_result.failed)
    if failed_channels:
        await report_community_notification_failure(failed_channels)
    return failed_channels


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
