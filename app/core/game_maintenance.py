#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""连接维护公告客户端与宿主配置，所有查询共享同一客户端。"""

from datetime import datetime

from app.core import Config
from app.services.game_maintenance import GameMaintenanceClient, MaintenanceCache


def _read_cache() -> MaintenanceCache:
    data = Config.setting.Data
    return MaintenanceCache(
        content=data.Maintenance,
        etag=data.MaintenanceETag,
        checked_at=data.LastMaintenanceUpdated,
    )


async def _write_cache(
    *,
    checked_at: datetime,
    content: str | None = None,
    etag: str | None = None,
) -> None:
    data: dict[str, str | datetime] = {"LastMaintenanceUpdated": checked_at}
    if content is not None:
        data["Maintenance"] = content
    if etag is not None:
        data["MaintenanceETag"] = etag
    await Config.setting.update(
        type(Config.setting).model_validate({"Data": data}),
        check_visibility=False,
    )


GameMaintenance = GameMaintenanceClient(
    read_cache=_read_cache, write_cache=_write_cache
)
