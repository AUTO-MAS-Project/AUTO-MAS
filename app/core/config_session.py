#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
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

from typing import Literal, Optional, Tuple

from app.core.ws import Publisher, protocol
from app.models.schema import WSTaskConfigDiscardedData, WSTaskNoticeData
from app.utils import get_logger

logger = get_logger("配置会话")

# 原生配置会话的最终结果登记点。
#
# 会话由具体脚本任务执行（app/task/*/ScriptConfig.py），任务终态却由调度器统一合成
# （app/core/task_manager.py 的 Task.final_task）。两者共享同一个 task_id，这里做最小
# 解耦：脚本侧登记「到底写没写盘、为何没写」，调度器侧在收尾时读取一次并合成 TaskOutcome。
#
# 登记只在收尾读取时清除，因此长期驻留的只有尚未收尾的会话，不会随任务数增长。
ConfigSessionResultKind = Literal["saved", "discarded", "completed_without_write"]

_PENDING: dict[str, Tuple[ConfigSessionResultKind, Optional[str]]] = {}


def note_config_session_result(
    task_id: str,
    kind: ConfigSessionResultKind,
    reason: Optional[str] = None,
) -> None:
    """登记一个原生配置会话的最终结果，供调度器合成统一任务终态。

    Args:
        task_id (str): 配置会话所属任务 ID，与调度器侧任务 ID 相同。
        kind (ConfigSessionResultKind): saved 已写盘, discarded 改动未写入,
            completed_without_write 只读查看等未回写场景。
        reason (Optional[str]): 机器可读原因，与 TASK_CONFIG_DISCARDED 的 reason 对齐。
    """
    _PENDING[str(task_id)] = (kind, reason)


def take_config_session_result(
    task_id: str,
) -> Optional[Tuple[str, Optional[str]]]:
    """读取并清除该任务登记的结果，返回 None 表示会话没有登记过。"""
    return _PENDING.pop(str(task_id), None)


async def publish_config_session_result(
    task_id: str,
    kind: ConfigSessionResultKind,
    reason: Optional[str] = None,
) -> None:
    """登记配置会话终态，并把「没写盘」的结论即时下发前端。

    回写失败过去只留在日志里，界面上却提示「已保存」。这里统一收口：登记供
    调度器合成 TaskOutcome，同时把丢弃事实按 TASK_CONFIG_DISCARDED 发出，
    供只订阅 WebSocket 的旧入口兜底；未回写的正常结束也补一条 info 提示。

    Args:
        task_id (str): 配置会话所属任务 ID，与调度器侧任务 ID 相同。
        kind (ConfigSessionResultKind): saved 已写盘, discarded 改动未写入,
            completed_without_write 只读查看等未回写场景。
        reason (Optional[str]): 机器可读原因，与 TASK_CONFIG_DISCARDED 的 reason 对齐。
    """

    note_config_session_result(task_id, kind, reason)

    if kind == "saved":
        return
    if kind == "discarded":
        sent = await Publisher.send(
            id=str(task_id),
            type=protocol.TASK_CONFIG_DISCARDED,
            data=WSTaskConfigDiscardedData(reason=reason),
        )
        if not sent:
            logger.warning(f"配置会话丢弃提示未送达前端: reason={reason}")
        return
    # 未回写（查看会话、直控、跳过回写）：终态文案由 TaskOutcome.messageKey 呈现，
    # 这条 info 只兜底仍按「已保存」解读完成消息的入口。
    await Publisher.send(
        id=str(task_id),
        type=protocol.TASK_NOTICE,
        data=WSTaskNoticeData(
            level="info",
            message=f"本次配置会话未回写 MAS 配置（{reason or 'unknown'}）",
        ),
    )
