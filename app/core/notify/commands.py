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

from typing import Literal

from app.models.notification.channel import NotificationCommandAction


async def execute_notification_command(
    action: NotificationCommandAction,
    name: str,
) -> str:
    """将渠道传入的名称解析为 ID，复用现有脚本和队列启动入口。"""

    from app.core import Config, TaskManager

    if action == "retry_script":
        targets = Config.ScriptConfig
        label = "脚本"
    elif action == "start_queue":
        targets = Config.QueueConfig
        label = "队列"
    else:
        return "不支持该指令。"
    matches = [uid for uid, target in targets.items() if target.Info.Name == name]
    if not matches:
        return f"未找到该{label}，请使用 MAS 中显示的完整{label}名称。"
    if len(matches) > 1:
        return f"存在同名{label}，请先在 MAS 中改为不同名称后重试。"
    uid = matches[0]
    mode: Literal["AutoProxy", "CycleRun"] = "AutoProxy"
    if action == "start_queue" and Config.QueueConfig[uid].Info.CycleEnabled:
        mode = "CycleRun"
    try:
        await TaskManager.add_task(mode=mode, id=str(uid))
    except (ValueError, RuntimeError):
        return f"暂时无法启动，请在 MAS 中检查{label}状态或等待当前任务结束。"
    if action == "retry_script":
        return "已提交脚本重试，将按当前自动代理配置运行。"
    if mode == "CycleRun":
        return "已提交循环队列启动，将按当前循环配置运行。"
    return "已提交队列启动，将按当前队列配置运行一次。"
