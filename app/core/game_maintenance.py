#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""连接维护公告客户端与宿主配置，所有查询共享同一客户端。"""

from datetime import datetime

from app.config import ConfigError, config_manager
from app.core import Config
from app.services import game_maintenance as _service_game_maintenance


def _read_cache() -> _service_game_maintenance.MaintenanceCache:
    data = Config.setting.Data
    return _service_game_maintenance.MaintenanceCache(
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
    try:
        # 正文、ETag 与检查时间必须一起提交，避免旧内容被标记为新缓存。
        async with config_manager.transaction():
            await Config.setting.update(
                type(Config.setting).model_validate({"Data": data}),
                check_visibility=False,
            )
    except ConfigError as exc:
        # 在宿主边界转换框架异常，客户端仍只处理通用缓存写入失败。
        raise OSError(f"维护信息缓存更新失败: {exc}") from exc


GameMaintenance = _service_game_maintenance.GameMaintenanceClient(
    read_cache=_read_cache, write_cache=_write_cache
)


__all__ = ["GameMaintenance"]
