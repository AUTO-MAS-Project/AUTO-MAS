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

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.config import AppConfig
    from app.core.task_manager import _TaskManager


async def retry_script_by_name(
    name: str, *, config: AppConfig, task_manager: _TaskManager
) -> str:
    """将绑定用户提供的脚本名称解析为 ID，复用普通自动代理入口。"""

    matches = [
        uid for uid, script in config.ScriptConfig.items() if script.Info.Name == name
    ]
    if not matches:
        return "未找到该脚本，请使用 MAS 中显示的完整脚本名称。"
    if len(matches) > 1:
        return "存在同名脚本，请先在 MAS 中改为不同名称后重试。"
    try:
        await task_manager.add_task(mode="AutoProxy", id=str(matches[0]))
    except (ValueError, RuntimeError):
        return "暂时无法重试，请在 MAS 中检查脚本状态或等待当前任务结束。"
    return "已提交脚本重试，将按当前自动代理配置运行。"
