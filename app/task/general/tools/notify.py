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

from app.core.notify import DispatchResult
from app.models.config import GeneralUserConfig
from app.task.notify_core import push_task_notice
from app.utils import get_logger

logger = get_logger("通用通知工具")


async def push_notification(
    mode: str,
    title: str,
    message: dict,
    user_config: GeneralUserConfig | None,
    task_info: object | None = None,
) -> DispatchResult:
    """通过所有渠道推送通知; 返回分发的实际尝试/成功/失败结果。"""

    logger.info(f"开始推送通知, 模式: {mode}, 标题: {title}")

    return await push_task_notice(
        mode,
        title,
        message,
        user_config,
        task_info,
        statistics_text=lambda: (
            f"开始时间: {message['start_time']}\n"
            f"结束时间: {message['end_time']}\n"
            f"通用脚本执行结果: {message['user_result']}\n\n"
        ),
    )
