#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
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

"""各专项通知工具共用的「代理结果」推送核心。

SRC / HSR / MaaEnd / OkNte / general / Okww / MAA / M9A / MaaFW / BetterGI 的
代理结果分支原本逐字重复，仅模板名、签名分隔符与跳过日志存在授权差异，统一
收敛到本模块。各专项的统计信息分支差异较大，保留在各自 notify 模块内。
"""

from collections.abc import Sequence
from typing import Any

from app.core import Config
from app.core.notify import (
    DispatchResult,
    dispatch_task_report,
    global_target,
    should_send_result,
)
from app.models.notification import (
    NotificationImage,
    NotificationSummary,
    NotifyPayload,
)
from app.tools.community_notify import get_task_community_summary


async def push_proxy_result(
    *,
    title: str,
    message: dict,
    task_info: object | None = None,
    result_template: str = "general_result.html",
    signature_sep: str = "\n\n",
    logger: Any | None = None,
    skip_debug_message: str | None = None,
    images: Sequence[NotificationImage] = (),
) -> DispatchResult:
    """推送全局「代理结果」报告；签到汇总与渠道级重试由 dispatch_task_report 承担。

    Args:
        title: 通知标题。
        message: 需含 start_time / end_time / completed_count /
            uncompleted_count / result 字段。
        task_info: 任务信息，用于签到汇总的渠道级重试。
        result_template: 结果 HTML 模板名，MAA 用 MAA_result.html。
        signature_sep: 签名分隔符，默认与 NotifyPayload 缺省一致；MAA 只空一行。
        logger: 调用方模块 logger，仅用于可选的跳过 debug 日志。
        skip_debug_message: SendTaskResultTime 不满足时的 debug 文案，仅 M9A 传入。
        images: 随报告提供的图片资源。HTML 模板通过稳定资源 ID 引用需要展示的图片。
    """

    if not should_send_result(message, task_info=task_info):
        if logger is not None and skip_debug_message:
            logger.debug(skip_debug_message)
        return DispatchResult()

    message_text = (
        f"任务开始时间: {message['start_time']}, 结束时间: {message['end_time']}\n"
        f"已完成数: {message['completed_count']}, 未完成数: {message['uncompleted_count']}\n\n"
        f"{message['result']}"
    )
    template = Config.notify_env.get_template(result_template)
    counts = (
        f"已完成用户数: {message['completed_count']}, "
        f"未完成用户数: {message['uncompleted_count']}"
    )
    summary_text = (
        get_task_community_summary(task_info)
        if task_info is not None and message.get("game_sign_summary")
        else ""
    )
    # 有未完成的用户时摘要标题不能再说「已完成！」；调用方显式给的摘要标题优先
    summary_title = message.get("summary_title") or title.replace(
        "报告", "存在异常" if message["uncompleted_count"] > 0 else "已完成！"
    )
    return await dispatch_task_report(
        NotifyPayload(
            title=title,
            text=message_text,
            html=template.render(message),
            signature_sep=signature_sep,
            summary=NotificationSummary(
                text=counts,
                title=summary_title,
                overflow_text=message_text,
            ),
            images=tuple(images),
        ),
        [global_target(include_system=True, system_timeout_seconds=10)],
        task_info,
        summary_text=summary_text,
    )
