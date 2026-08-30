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

from app.core import Config
from app.core.notify import (
    NotifyPayload,
    dispatch,
    global_target,
    should_send_result,
    user_statistic_targets,
)
from app.models.config import OkwwUserConfig
from app.tools.push_log import append_push_log
from app.utils import get_logger

logger = get_logger("OK-WW 通知工具")


async def push_notification(
    mode: str,
    title: str,
    message: dict,
    user_config: OkwwUserConfig | None = None,
) -> list[str]:
    """通过全局或用户配置的渠道推送 OK-WW 任务报告; 返回发送失败的渠道名列表。"""

    logger.info(f"开始推送通知, 模式: {mode}, 标题: {title}")

    if mode == "统计信息":
        # OK-WW 的统计信息只推用户独立渠道, 不走全局
        targets = user_statistic_targets(user_config)
        if not targets:
            return []

        message_text = (
            f"用户: {message['user_info']}\n"
            f"开始时间: {message['start_time']}\n"
            f"结束时间: {message['end_time']}\n"
            f"执行结果: {message['user_result']}"
        )
        message_html = Config.notify_env.get_template("general_statistics.html").render(
            message
        )

        return await dispatch(NotifyPayload(title, message_text, message_html), targets)

    if mode != "代理结果":
        return []

    if not should_send_result(message):
        return []

    message_text = (
        f"任务开始时间: {message['start_time']}, 结束时间: {message['end_time']}\n"
        f"已完成数: {message['completed_count']}, "
        f"未完成数: {message['uncompleted_count']}\n\n"
        f"{message['result']}"
    )
    # 通知详情追加采集的推送日志（任务进程信息，与 HTML 模板的 push_log 区块一致）
    message_text = append_push_log(message_text, message.get("push_log"))
    message_html = Config.notify_env.get_template("general_result.html").render(message)

    return await dispatch(
        NotifyPayload(title, message_text, message_html), [global_target()]
    )
