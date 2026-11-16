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
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""奇想盒通知：上游「任务结果如下」结果块原样透传进报告正文。

多账号时上游结果块天然按「账号N：」分组，MAS 不重组（值经手、语义不过手）。
本模块只构造统计正文与摘要，投递和目标选择交给注入的宿主服务。

结果块是单步成败的唯一载体（见 ``tools/marker.py``），因此它同时进文本渠道与
邮件/网页正文（模板 ``general_statistics.html`` 的 ``result_block_body`` 区块）。
"""

from app.core.notify import templates as _notification_template
from app.core.notify.task_content import user_statistics_text
from app.models.notification import NotificationSummary, NotifyPayload
from app.task.Whimbox.tools.marker import WHIMBOX_RESULT_BLOCK_HEAD


def build_statistics_payload(*, title: str, message: dict) -> NotifyPayload:
    """构造专项统计正文，投递由注入的通知服务负责。"""

    # 简略版（所有渠道的兜底）：仅 4 字段汇总
    message_text = user_statistics_text(message)
    # 完整版：4 字段 + 上游结果块原文透传（含各步 ✅/⏭️/❌ 与多账号分组）
    result_block = str(message.get("result_block") or "")
    result_text = f"\n\n{result_block}" if result_block else ""
    # 「未完成原因」：结果块里默认步骤只有三态、不带原因，这里附上上游的 ❌/🛑 行原文
    failure_notes_text = "\n".join(
        f"· {note}" for note in (message.get("failure_notes") or [])
    )
    notes_text = (
        f"\n\n未完成原因（上游提示原文）：\n{failure_notes_text}"
        if failure_notes_text
        else ""
    )
    message_text_full = f"{message_text}{result_text}{notes_text}"
    # 邮件/网页正文：结果块去掉块头（模板自带区块标题），避免重复一行
    render_data = {
        **message,
        "result_block_body": result_block.replace(
            WHIMBOX_RESULT_BLOCK_HEAD, "", 1
        ).strip(),
        "failure_notes_text": failure_notes_text,
    }
    message_html = _notification_template.deferred_notification_template(
        "general_statistics.html", render_data
    )

    # 完整正文与短摘要同时保留，宿主再按渠道能力选择表达。
    return NotifyPayload(
        title=title,
        text=message_text_full,
        html=message_html,
        summary=NotificationSummary(text=message_text),
    )
