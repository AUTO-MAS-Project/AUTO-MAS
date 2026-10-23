#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License
#   as published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

from app.models.notification import NotifyPayload
from app.utils.notification_template import deferred_notification_template


def build_statistics_payload(*, title: str, message: dict) -> NotifyPayload:
    """构造专项统计正文，投递由注入的通知服务负责。"""

    message_html = deferred_notification_template("general_statistics.html", message)
    return NotifyPayload(
        title=title,
        text=f"用户: {message['user_info']}\n开始时间: {message['start_time']}\n结束时间: {message['end_time']}\n执行结果: {message['user_result']}",
        html=message_html,
    )
