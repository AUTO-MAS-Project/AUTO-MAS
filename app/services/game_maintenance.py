#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""公开游戏维护时间与进程内请求缓存。"""

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from app.utils import get_logger

logger = get_logger("游戏维护")

MAINTENANCE_URL = (
    "https://data.auto-mas.top/api/v1/files/auto-mas/Client/maintain-json/download"
)
CACHE_SECONDS = 300
RETRY_SECONDS = 60


@dataclass(frozen=True)
class MaintenanceWindow:
    start: datetime
    end: datetime

    def contains(self, now: datetime) -> bool:
        return self.start <= now < self.end

    @property
    def reason(self) -> str:
        # 保留文件时区，避免用户电脑的时区改变公告时间的含义。
        return (
            "游戏维护中，本次跳过（"
            f"{self.start.isoformat(sep=' ', timespec='minutes')} 至 "
            f"{self.end.isoformat(sep=' ', timespec='minutes')}）"
        )


def parse_maintenance(data: object) -> dict[str, MaintenanceWindow]:
    """解析版本 1 的维护文件；无效内容由请求边界记录并放行。"""
    if not isinstance(data, dict) or type(data.get("schema_version")) is not int:
        raise ValueError("维护文件缺少有效版本")
    if data["schema_version"] != 1 or not isinstance(data.get("games"), dict):
        raise ValueError("维护文件版本或游戏列表无效")

    windows: dict[str, MaintenanceWindow] = {}
    for game, item in data["games"].items():
        # 第一版只消费已接入的两款游戏，其他游戏不影响已支持的记录。
        if game not in ("arknights", "endfield"):
            continue
        if not isinstance(item, dict) or "maintenance" not in item:
            raise ValueError(f"{game} 维护记录无效")
        maintenance = item["maintenance"]
        if maintenance is None:
            continue
        if not isinstance(maintenance, dict):
            raise ValueError(f"{game} 维护时段无效")
        try:
            start = datetime.fromisoformat(maintenance["planned_start_at"])
            end = datetime.fromisoformat(maintenance["planned_end_at"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{game} 维护时间无效") from exc
        if start.utcoffset() is None or end.utcoffset() is None or start >= end:
            raise ValueError(f"{game} 维护时间缺少时区或起止顺序错误")
        windows[game] = MaintenanceWindow(start=start, end=end)
    return windows


class GameMaintenanceClient:
    def __init__(self) -> None:
        self._windows: dict[str, MaintenanceWindow] = {}
        self._next_refresh = 0.0
        self._lock = asyncio.Lock()

    async def get_active(
        self, game: str, *, proxy: httpx.Proxy | None = None
    ) -> MaintenanceWindow | None:
        """查询当前维护；过期缓存刷新失败时放行，不沿用旧时段。"""
        async with self._lock:
            if time.monotonic() >= self._next_refresh:
                try:
                    async with asyncio.timeout(10):
                        async with httpx.AsyncClient(
                            proxy=proxy, follow_redirects=True, timeout=5
                        ) as client:
                            response = await client.get(MAINTENANCE_URL)
                            response.raise_for_status()
                            windows = parse_maintenance(response.json())
                except (httpx.HTTPError, TimeoutError, ValueError) as exc:
                    self._windows = {}
                    self._next_refresh = time.monotonic() + RETRY_SECONDS
                    logger.warning(f"检查游戏维护失败，继续正常运行: {exc}")
                else:
                    self._windows = windows
                    self._next_refresh = time.monotonic() + CACHE_SECONDS

            window = self._windows.get(game)
            now = datetime.now(timezone.utc)
            return window if window is not None and window.contains(now) else None


GameMaintenance = GameMaintenanceClient()
