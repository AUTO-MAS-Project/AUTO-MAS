#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""MAS 账号区服匹配与维护跳过记账，不读取脚本内部状态。"""

import httpx

from app.config import ConfigEntry
from app.core.game_maintenance import GameMaintenance
from app.models.config import (
    MaaConfig,
    MaaEndConfig,
    MaaEndUserConfig,
    MaaUserConfig,
    OkNteConfig,
    OkwwConfig,
)
from app.services.game_maintenance import MaintenanceWindow


def get_maintenance_message(
    script_config: MaaConfig | MaaEndConfig | OkNteConfig | OkwwConfig,
) -> str:
    if isinstance(script_config, MaaConfig):
        game = "明日方舟"
    elif isinstance(script_config, OkNteConfig):
        game = "异环"
    elif isinstance(script_config, OkwwConfig):
        game = "鸣潮"
    else:
        game = "终末地"
    return f"{game}正在维护"


async def get_user_maintenance(
    user_config: ConfigEntry, *, proxy: httpx.Proxy | None
) -> MaintenanceWindow | None:
    if isinstance(user_config, MaaUserConfig):
        if user_config.Info.Server not in ("Official", "Bilibili"):
            return None
        game = "arknights"
    elif isinstance(user_config, MaaEndUserConfig):
        if user_config.Info.Resource != "官服":
            return None
        game = "endfield"
    # 异环（nte）映射待数据侧接入维护公告后挂载（画面 OCR 检测先行兜底，
    # 见 app/task/OkNte/tools/launcher_start.py 的 detect_game_maintenance_text）：
    # elif isinstance(user_config, OkNteUserConfig):
    #     if user_config.get("Info", "Resource") != "官服":
    #         return None
    #     game = "nte"
    else:
        return None
    return await GameMaintenance.get_active(game, proxy=proxy)
