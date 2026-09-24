#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
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

from app.core import Config
from app.core.notify import (
    DispatchResult,
    NotifyPayload,
    dispatch,
    statistic_targets,
)
from app.models.config import BAAHUserConfig
from app.task.notify_core import push_proxy_result
from app.utils import get_logger

logger = get_logger("BAAH 通知工具")


async def push_notification(
    mode: str,
    title: str,
    message: dict,
    user_config: BAAHUserConfig | None,
    task_info: object | None = None,
) -> DispatchResult:
    """通过所有渠道推送通知; 返回分发的实际尝试/成功/失败结果。

    Args:
        mode: 通知模式——``"代理结果"``（任务级）或 ``"统计信息"``（用户级）。
        title: 通知标题。
        message: 各模式所需的字段；``"统计信息"`` 需要 ``start_time`` /
            ``end_time`` / ``user_result``。
        user_config: 该用户的 ``Notify`` 配置；``"统计信息"`` 由它决定投递渠道，
            缺失时只返回空结果。
        task_info: 任务信息，``"代理结果"`` 使用。
    """

    logger.info(f"开始推送通知, 模式: {mode}, 标题: {title}")

    if mode == "代理结果":
        return await push_proxy_result(
            title=title, message=message, task_info=task_info
        )

    if mode == "统计信息":
        message_text = (
            f"开始时间: {message['start_time']}\n"
            f"结束时间: {message['end_time']}\n"
            f"BAAH 执行结果: {message['user_result']}\n\n"
        )
        template = Config.notify_env.get_template("general_statistics.html")

        ## 渠道开关（邮件 / Server 酱 / 自定义 Webhook）统一由统计信息的收件目标解析，
        ## 用户配置缺失时返回空目标集，不会静默走全局渠道
        return await dispatch(
            NotifyPayload(
                title=title,
                text=message_text,
                html=template.render(message),
            ),
            statistic_targets(user_config),
        )

    return DispatchResult()
