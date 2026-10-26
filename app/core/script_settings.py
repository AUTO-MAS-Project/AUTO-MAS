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
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.
#   Contact: DLmaster_361@163.com
"""脚本编辑的提交入口，编排专项预处理与配置写入。"""

from typing import Any

from app.core import Config
from app.utils.emulator2 import service as emulator2_service


async def update_script(script_id: str, data: dict[str, Any]) -> str | None:
    """先检查模拟器绑定，拒绝时返回既有提示，允许后才提交。"""
    refusal = await emulator2_service.mod_avd_binding_error(script_id, data)
    if refusal:
        return refusal
    await Config.update_script(script_id, data)
    return None


async def update_user(script_id: str, user_id: str, data: dict[str, Any]) -> None:
    """保持队列同步先于最终提交，副本生成失败不阻断配置保存。"""
    od = data.get("OneDragon")
    if isinstance(od, dict) and "Queue" in od:
        from app.task.BetterGI import api_service as bettergi_api

        bettergi_api.prepare_user_update(script_id, user_id, data)
    await Config.update_user(script_id, user_id, data)
