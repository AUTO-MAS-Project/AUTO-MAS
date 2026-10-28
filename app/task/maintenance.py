#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""查询专项已声明的维护对象；不解释账号配置或连接宿主单例。"""

from collections.abc import Awaitable, Callable

from app.services.game_maintenance import MaintenanceWindow


async def get_user_maintenance(
    game: str | None,
    *,
    lookup: Callable[[str], Awaitable[MaintenanceWindow | None]],
) -> MaintenanceWindow | None:
    if game is None:
        return None
    return await lookup(game)
