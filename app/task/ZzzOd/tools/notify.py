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

from app.core.notify import DispatchResult
from app.models.config import ZzzOdUserConfig
from app.task.notify_core import push_task_notice
from app.utils import get_logger

logger = get_logger("ZZZ-OD 通知工具")


async def push_notification(
    mode: str,
    title: str,
    message: dict,
    user_config: ZzzOdUserConfig | None,
    task_info: object | None = None,
) -> DispatchResult:
    """通过全局或用户配置的渠道推送 ZZZ-OD 任务报告; 返回分发结果。"""

    logger.info(f"开始推送通知, 模式: {mode}, 标题: {title}")

    return await push_task_notice(
        mode,
        title,
        message,
        user_config,
        task_info,
        statistics_text=lambda: (
            f"用户: {message['user_info']}\n"
            f"开始时间: {message['start_time']}\n"
            f"结束时间: {message['end_time']}\n"
            f"执行结果: {message['user_result']}"
        ),
    )
