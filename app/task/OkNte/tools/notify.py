#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

from app.models.config import OkNteUserConfig
from app.models.notification import NotifyPayload
from app.models.notification_channel import DispatchResult
from app.models.notification_report import TaskNoticeMode, TaskResultReport
from app.models.task import TaskItem
from app.task.notify_core import push_statistics_report
from app.utils import get_logger
from app.utils.notification_template import deferred_notification_template

logger = get_logger("OK-NTE 通知工具")


async def push_notification(
    mode: TaskNoticeMode,
    title: str,
    message: dict,
    user_config: OkNteUserConfig | None,
    *,
    task_info: TaskItem,
) -> DispatchResult:
    """通过所有渠道推送 OK-NTE 通知; 返回分发结果。"""

    logger.info(f"开始推送通知, 模式: {mode}, 标题: {title}")

    if mode == "代理结果":
        return await task_info.notifications.push_proxy_result(
            title=title,
            report=TaskResultReport.from_message(message),
            task_info=task_info,
        )
    if mode != "统计信息":
        return DispatchResult()

    message_html = deferred_notification_template("general_statistics.html", message)
    return await push_statistics_report(
        payload=NotifyPayload(
            title=title,
            text=f"开始时间: {message['start_time']}\n结束时间: {message['end_time']}\nOK-NTE 执行结果: {message['user_result']}\n\n",
            html=message_html,
        ),
        user_config=user_config,
        task_info=task_info,
    )
