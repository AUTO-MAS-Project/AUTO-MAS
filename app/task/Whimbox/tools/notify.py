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
「代理结果」复用通用入口 ``app/task/notify_core.push_proxy_result``（全专项统一，
不自行拼接）；统计通知的**正文**按渠道分流（长渠道全文、短渠道摘要，对齐 BetterGI
tools/notify.py），**投递**一律交 ``app.core.notify.dispatch``——全局 + 用户目标、
渠道级重试、失败隔离与 ``DispatchResult`` 都由通用核心负责，本模块不直接调渠道。

结果块是单步成败的唯一载体（见 ``tools/marker.py``），因此它同时进文本渠道与
邮件/网页正文（模板 ``general_statistics.html`` 的 ``result_block_body`` 区块）。
"""

from app.core import Config
from app.core.notify import (
    SIGNATURE,
    DispatchResult,
    NotifyPayload,
    dispatch,
    statistic_targets,
)
from app.models.config import WhimboxUserConfig
from app.task.notify_core import push_proxy_result
from app.utils import get_logger

from .marker import WHIMBOX_RESULT_BLOCK_HEAD

logger = get_logger("奇想盒 通知工具")

# Server酱 desp 上限约 32KB：结果块超预算安全回退简略版
_SERVERCHAN_MAX_BYTES = 30 * 1024


def _signed(text: str, *, serverchan: bool = False) -> str:
    """按 ``NotifyPayload`` 的默认口径补签名（ServerChan 另把换行折成双换行）。

    只用于需要覆盖 payload 默认正文的两个渠道：聊天机器人类 Webhook 的简略版，
    以及 ServerChan 超预算时的降级版。
    """

    body = text.replace("\n", "\n\n") if serverchan else text
    return f"{body}\n\n{SIGNATURE}"


async def push_notification(
    mode: str,
    title: str,
    message: dict,
    user_config: WhimboxUserConfig | None = None,
    task_info: object | None = None,
) -> DispatchResult:
    """通过全局或用户配置的渠道推送奇想盒任务报告。"""

    logger.info(f"开始推送通知, 模式: {mode}, 标题: {title}")

    if mode == "统计信息":
        # 简略版（所有渠道的兜底）：仅 4 字段汇总
        message_text = (
            f"用户: {message['user_info']}\n"
            f"开始时间: {message['start_time']}\n"
            f"结束时间: {message['end_time']}\n"
            f"执行结果: {message['user_result']}"
        )
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
        message_html = Config.notify_env.get_template("general_statistics.html").render(
            render_data
        )

        serverchan_text = None
        if len(message_text_full.encode("utf-8")) > _SERVERCHAN_MAX_BYTES:
            # Server酱 desp 上限约 32KB：结果块很小时用完整版，超预算回退简略版
            serverchan_text = _signed(message_text, serverchan=True)
            logger.warning("Server酱内容超过字数上限，已回退为简略版（不含结果块）")

        # 正文只按渠道分流，投递交 dispatch：用户侧开关在用户目标内判定，
        # 全局渠道与「统计信息」总开关在 statistic_targets 内判定
        return await dispatch(
            NotifyPayload(
                title=title,
                text=message_text_full,
                html=message_html,
                serverchan_text=serverchan_text,
                webhook_text=_signed(message_text),
            ),
            statistic_targets(user_config),
        )

    if mode != "代理结果":
        return DispatchResult()

    return await push_proxy_result(title=title, message=message, task_info=task_info)
