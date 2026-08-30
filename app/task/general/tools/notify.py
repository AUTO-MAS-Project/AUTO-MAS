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

from app.core import Config
from app.core.notify import (
    NotifyPayload,
    dispatch,
    global_target,
    should_send_result,
    statistic_targets,
)
from app.models.config import GeneralUserConfig
from app.tools.push_log import append_push_log
from app.utils import get_logger

logger = get_logger("通用通知工具")


async def push_notification(
    mode: str, title: str, message: dict, user_config: GeneralUserConfig | None
) -> list[str]:
    """通过所有渠道推送通知; 返回发送失败的渠道名列表。"""

    logger.info(f"开始推送通知, 模式: {mode}, 标题: {title}")

    if mode == "代理结果":
        if not should_send_result(message):
            return []

        message_text = (
            f"任务开始时间: {message['start_time']}, 结束时间: {message['end_time']}\n"
            f"已完成数: {message['completed_count']}, 未完成数: {message['uncompleted_count']}\n\n"
            f"{message['result']}"
        )
        # 追加任务进程推送日志（若配置了推送日志匹配并采集到内容）
        message_text = append_push_log(message_text, message.get("push_log"))

        # 生成HTML通知内容
        template = Config.notify_env.get_template("general_result.html")

        return await dispatch(
            NotifyPayload(
                title=title,
                text=message_text,
                html=template.render(message),
            ),
            [global_target()],
        )

    if mode == "统计信息":
        message_text = (
            f"开始时间: {message['start_time']}\n"
            f"结束时间: {message['end_time']}\n"
            f"通用脚本执行结果: {message['user_result']}\n\n"
        )
        template = Config.notify_env.get_template("general_statistics.html")

        return await dispatch(
            NotifyPayload(
                title=title,
                text=message_text,
                html=template.render(message),
            ),
            statistic_targets(user_config),
        )

    return []
