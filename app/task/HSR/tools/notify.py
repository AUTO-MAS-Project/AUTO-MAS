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
#
#   Contact: DLmaster_361@163.com


from app.core import Config
from app.models.config import HSRUserConfig
from app.services.notify_dispatch import (
    NotifyPayload,
    dispatch,
    global_target,
    should_send_result,
    statistic_targets,
)
from app.utils import get_logger

logger = get_logger("HSR 通知工具")


async def push_notification(
    mode: str, title: str, message: dict, user_config: HSRUserConfig | None
) -> list[str]:
    """通过所有渠道推送 HSR 通知; 返回发送失败的渠道名列表。"""

    logger.info(f"开始推送通知, 模式: {mode}, 标题: {title}")

    if mode == "代理结果":
        if not should_send_result(message):
            return []

        message_text = (
            f"任务开始时间: {message['start_time']}, 结束时间: {message['end_time']}\n"
            f"已完成数: {message['completed_count']}, 未完成数: {message['uncompleted_count']}\n\n"
            f"{message['result']}"
        )
        message_html = Config.notify_env.get_template("general_result.html").render(
            message
        )

        # HSR 的全局渠道额外校验收件人非空, 配置不全时静默跳过
        return await dispatch(
            NotifyPayload(title, message_text, message_html),
            [global_target(skip_empty_recipient=True)],
        )

    if mode == "统计信息":
        message_text = (
            f"开始时间: {message['start_time']}\n"
            f"结束时间: {message['end_time']}\n"
            f"HSR执行结果: {message['user_result']}\n\n"
        )
        message_html = Config.notify_env.get_template("general_statistics.html").render(
            message
        )

        return await dispatch(
            NotifyPayload(title, message_text, message_html),
            statistic_targets(user_config, skip_empty_recipient=True),
        )

    return []
