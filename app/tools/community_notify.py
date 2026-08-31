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


"""社区工具通知消费入口，复用旧通知实现和历史结果契约。"""

from app.core import Config

from .game_sign_notify import (
    format_game_sign_notification as format_community_notification,
    format_game_sign_task_summary as format_community_task_summary,
    push_game_sign_notification as push_community_notification,
)

__all__ = [
    "append_task_community_summary",
    "format_community_notification",
    "format_community_task_summary",
    "get_task_community_summary",
    "mark_task_community_summary_consumed",
    "push_community_notification",
]


def get_task_community_summary(task_info: object) -> str:
    """读取尚未发送的社区签到汇总，兼容旧任务字段。"""

    consumed = (
        getattr(task_info, "community_summary_consumed", False)
        if hasattr(task_info, "community_summary_consumed")
        else getattr(task_info, "game_sign_summary_consumed", False)
    )
    if consumed:
        return ""

    results = (
        getattr(task_info, "community_results", [])
        if hasattr(task_info, "community_results")
        else getattr(task_info, "game_sign_results", [])
    )
    if not results:
        return ""
    return format_community_task_summary(list(results))


def mark_task_community_summary_consumed(task_info: object) -> None:
    """标记社区签到汇总已由任务报告消费。"""

    if hasattr(task_info, "community_summary_consumed"):
        setattr(task_info, "community_summary_consumed", True)
    else:
        setattr(task_info, "game_sign_summary_consumed", True)


def append_task_community_summary(task_info: object, result: str) -> str:
    """将尚未发送的社区签到汇总附加到任务报告。"""

    if not Config.ToolsConfig.get("GameSign", "NotifyEnabled"):
        return result

    summary = get_task_community_summary(task_info)
    return f"{result}\n\n{summary}" if summary else result
