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


"""通知渠道的文字命令适配，执行仍交给宿主现有业务入口。"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from app.models.notification.channel import NotificationCommandAction

if TYPE_CHECKING:
    from app.config import ConfigCollection
    from app.models.config import QueueConfig, ScriptConfigType


async def execute_notification_command(
    action: NotificationCommandAction,
    name: str,
) -> str:
    """查询配置名称，或按完整名称复用现有托管和队列启动入口。"""

    from app.core import Config

    targets: ConfigCollection[ScriptConfigType] | ConfigCollection[QueueConfig]
    if action in {"retry_script", "list_scripts"}:
        targets = Config.ScriptConfig
        label = "托管"
        command = "retry"
    elif action in {"start_queue", "list_queues"}:
        targets = Config.QueueConfig
        label = "队列"
        command = "start"
    else:
        return "不支持该指令。"
    if action in {"list_scripts", "list_queues"}:
        names = [target.Info.Name for target in targets.values()]
        if not names:
            return f"尚未配置{label}，请先在 MAS 中添加。"
        counts = Counter(names)
        lines = [f"已配置的{label}（{len(names)}）："]
        lines.extend(
            f"- {name}" + ("（同名，请先重命名）" if counts[name] > 1 else "")
            for name in names
        )
        lines.append(f"使用：{command} <{label}完整名称>；名称须与 MAS 中完全一致。")
        lines.append(
            "名称与帮助或列表指令冲突时，在名称前加 --，"
            f"如 {command} -- help、{command} -- list 2；"
            f"名称为 -- help 时用 {command} -- -- help。"
        )
        return "\n".join(lines)
    matches = [uid for uid, target in targets.items() if target.Info.Name == name]
    if not matches:
        return (
            f"未找到该{label}，请使用 MAS 中显示的完整{label}名称。"
            f"发送 {command} list 查看名称。"
        )
    if len(matches) > 1:
        return f"存在同名{label}，请先在 MAS 中改为不同名称后重试。"
    uid = matches[0]
    from app.core import TaskManager
    from app.models.task import TaskMode

    selection = (
        {"uid": str(uid)}
        if action == "start_queue"
        else {"uid": "-", "children": {0: {"uid": str(uid)}}}
    )
    try:
        await TaskManager.start(TaskMode.AUTO_PROXY, {0: selection})
    except (ValueError, RuntimeError):
        return f"暂时无法启动，请在 MAS 中检查{label}状态或等待当前任务结束。"
    if action == "retry_script":
        return "已提交脚本重试，将按当前自动代理配置运行。"
    return "已提交队列启动，将按当前队列配置运行一次。"
