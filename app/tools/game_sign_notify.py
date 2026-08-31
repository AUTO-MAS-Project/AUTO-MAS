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


"""历史游戏签到通知兼容入口。"""

from .community_notify import (
    append_task_community_summary,
    detect_community_notification_format,
    format_community_notification,
    format_community_task_summary,
    get_task_community_summary,
    mark_task_community_summary_consumed,
    push_community_notification,
)

format_game_sign_notification = format_community_notification
format_game_sign_task_summary = format_community_task_summary
get_task_game_sign_summary = get_task_community_summary
mark_task_game_sign_summary_consumed = mark_task_community_summary_consumed
append_task_game_sign_summary = append_task_community_summary
push_game_sign_notification = push_community_notification

__all__ = [
    "append_task_game_sign_summary",
    "detect_community_notification_format",
    "format_game_sign_notification",
    "format_game_sign_task_summary",
    "get_task_game_sign_summary",
    "mark_task_game_sign_summary_consumed",
    "push_game_sign_notification",
]
