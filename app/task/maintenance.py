#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""MAS 账号区服匹配与维护跳过记账，不读取脚本内部状态。"""

import httpx

from app.models.config import MaaConfig, MaaEndConfig, MaaEndUserConfig, MaaUserConfig
from app.models.ConfigBase import ConfigBase
from app.services.game_maintenance import GameMaintenance, MaintenanceWindow


def get_maintenance_message(script_config: MaaConfig | MaaEndConfig) -> str:
    game = "明日方舟" if isinstance(script_config, MaaConfig) else "终末地"
    return f"{game}正在维护"


async def get_user_maintenance(
    user_config: ConfigBase, *, proxy: httpx.Proxy | None
) -> MaintenanceWindow | None:
    if isinstance(user_config, MaaUserConfig):
        if user_config.get("Info", "Server") not in ("Official", "Bilibili"):
            return None
        game = "arknights"
    elif isinstance(user_config, MaaEndUserConfig):
        if user_config.get("Info", "Resource") != "官服":
            return None
        game = "endfield"
    else:
        return None
    return await GameMaintenance.get_active(game, proxy=proxy)
