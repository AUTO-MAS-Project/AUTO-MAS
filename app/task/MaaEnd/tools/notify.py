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
    DispatchResult,
    NotifyPayload,
    dispatch,
    global_target,
    should_send_result,
    statistic_targets,
)
from app.models.config import MaaEndUserConfig
from app.tools.game_sign_notify import dispatch_task_report, get_task_game_sign_summary
from app.utils import get_logger

logger = get_logger("MaaEnd 通知工具")


def _statistic_sections(message: dict) -> list[str]:
    """拼装抽数与基质统计段落; 无对应数据时返回空列表。"""

    matrix_lines = []
    # matrix_statistics 键存在但为空表示「查过了, 没有合适的」, 与键不存在语义不同
    if "matrix_statistics" in message and message["matrix_statistics"]:
        matrix_lines.append("基质统计:")
        for skill, weapon in message["matrix_statistics"].items():
            matrix_lines.append(f"  {skill}: {weapon}")
    elif "matrix_statistics" in message:
        matrix_lines.append("基质统计: 无合适的基质")

    pull_count_lines = []
    pull_count = message.get("pull_count_statistics")
    if pull_count:
        pull_count_lines.extend(
            [
                "抽数统计:",
                f"  当前池可用: {pull_count['current_pool_total']} 抽",
                f"  下版本池子总计: {pull_count['next_pool_total']} 抽",
                f"  资源折算: {pull_count['resource_pulls']} 抽",
                f"  可留到下版本的券: {pull_count['carry_over_pulls']} 抽",
            ]
        )

    return [
        section
        for section in ("\n".join(pull_count_lines), "\n".join(matrix_lines))
        if section
    ]


async def push_notification(
    mode: str,
    title: str,
    message: dict,
    user_config: MaaEndUserConfig | None,
    task_info: object | None = None,
) -> DispatchResult:
    """通过所有渠道推送通知; 返回分发的实际尝试/成功/失败结果。"""

    logger.info(f"开始推送通知, 模式: {mode}, 标题: {title}")

    if mode == "代理结果":
        if not should_send_result(message):
            return DispatchResult()

        message_text = (
            f"任务开始时间: {message['start_time']}, 结束时间: {message['end_time']}\n"
            f"已完成数: {message['completed_count']}, 未完成数: {message['uncompleted_count']}\n\n"
            f"{message['result']}"
        )
        template = Config.notify_env.get_template("general_result.html")
        counts = (
            f"已完成用户数: {message['completed_count']}, "
            f"未完成用户数: {message['uncompleted_count']}"
        )
        summary_text = (
            get_task_game_sign_summary(task_info)
            if task_info is not None and message.get("game_sign_summary")
            else ""
        )
        return await dispatch_task_report(
            NotifyPayload(
                title=title,
                text=message_text,
                html=template.render(message),
                system_title=message.get("system_title") or title.replace("报告", "已完成！"),
                system_message=counts,
                system_ticker=counts,
                system_timeout=10,
            ),
            [global_target(include_system=True)],
            task_info,
            summary_text=summary_text,
        )

    if mode == "统计信息":
        message_text = (
            f"开始时间: {message['start_time']}\n"
            f"结束时间: {message['end_time']}\n"
            f"MaaEnd执行结果: {message['user_result']}"
        )
        sections = _statistic_sections(message)
        if sections:
            message_text += "\n\n" + "\n\n".join(sections)

        template = Config.notify_env.get_template("MaaEnd_statistics.html")

        return await dispatch(
            NotifyPayload(
                title=title,
                text=message_text,
                html=template.render(message),
            ),
            statistic_targets(user_config),
        )

    return DispatchResult()
