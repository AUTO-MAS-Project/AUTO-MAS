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
from app.services.notify_dispatch import (
    NotifyPayload,
    NotifyTarget,
    dispatch,
    global_target,
    should_send_result,
    statistic_targets,
    user_target,
)
from app.utils import get_logger
from app.models.config import MaaUserConfig

logger = get_logger("MAA 通知工具")

# MAA 的签名只空一行, 与其余脚本不同
SIGNATURE_SEP = "\n"


def _statistic_text(message: dict) -> str:
    """拼装掉落与招募统计的纯文本正文。"""

    formatted = []
    if "drop_statistics" in message:
        for stage, items in message["drop_statistics"].items():
            formatted.append(f"掉落统计（{stage}）:")
            for item, quantity in items.items():
                formatted.append(f"  {item}: {quantity}")
    drop_text = "\n".join(formatted)

    formatted = ["招募统计:"]
    if "recruit_statistics" in message:
        for star, count in message["recruit_statistics"].items():
            formatted.append(f"  {star}: {count}")
    recruit_text = "\n".join(formatted)

    return (
        f"开始时间: {message['start_time']}\n"
        f"结束时间: {message['end_time']}\n"
        f"理智剩余: {message.get('sanity', '未知')}\n"
        f"回复时间: {message.get('sanity_full_at', '未知')}\n"
        f"MAA执行结果: {message['maa_result']}\n"
        f"{recruit_text}\n"
        f"{drop_text}"
    )


def _six_star_targets(user_config: MaaUserConfig | None) -> list[NotifyTarget]:
    """公招六星喜报的推送目标, 全局与用户各有独立开关。"""

    targets = []
    if Config.get("Notify", "IfSendSixStar"):
        targets.append(global_target())
    if (
        user_config is not None
        and user_config.get("Notify", "Enabled")
        and user_config.get("Notify", "IfSendSixStar")
    ):
        targets.append(user_target(user_config))
    return targets


async def push_notification(
    mode: str, title: str, message: dict, user_config: MaaUserConfig | None
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
        template = Config.notify_env.get_template("MAA_result.html")

        return await dispatch(
            NotifyPayload(
                title, message_text, template.render(message), SIGNATURE_SEP
            ),
            [global_target()],
        )

    if mode == "统计信息":
        template = Config.notify_env.get_template("MAA_statistics.html")

        return await dispatch(
            NotifyPayload(
                title, _statistic_text(message), template.render(message), SIGNATURE_SEP
            ),
            statistic_targets(user_config),
        )

    if mode == "公招六星":
        # 喜报正文是固定文案, message 只用于渲染 HTML
        template = Config.notify_env.get_template("MAA_six_star.html")

        return await dispatch(
            NotifyPayload(
                title, "好羡慕~", template.render(message), SIGNATURE_SEP
            ),
            _six_star_targets(user_config),
        )

    return []
