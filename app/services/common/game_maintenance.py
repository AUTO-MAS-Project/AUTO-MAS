#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""公开游戏维护时间与公告同口径的请求缓存。"""

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

import httpx

from app.models.game_maintenance import MaintenanceWindow as MaintenanceWindow
from app.utils import get_logger

logger = get_logger("游戏维护")

MAINTENANCE_URL = (
    "https://data.auto-mas.top/api/v1/files/auto-mas/Client/maintain-json/download"
)
CACHE_SECONDS = 60 * 60
RETRY_SECONDS = 60


@dataclass(frozen=True)
class MaintenanceCache:
    """宿主提供的维护缓存快照。"""

    content: str
    etag: str
    checked_at: datetime


class MaintenanceCacheWriter(Protocol):
    """异步保存缓存；未提供的正文和 ETag 保持不变，写入故障抛 OSError。"""

    def __call__(
        self,
        *,
        checked_at: datetime,
        content: str | None = None,
        etag: str | None = None,
    ) -> Awaitable[None]: ...


def parse_maintenance(data: object) -> dict[str, MaintenanceWindow]:
    """解析版本 1 的维护文件；无效内容由请求边界记录并放行。"""
    if not isinstance(data, dict) or type(data.get("schema_version")) is not int:
        raise ValueError("维护文件缺少有效版本")
    if data["schema_version"] != 1 or not isinstance(data.get("games"), dict):
        raise ValueError("维护文件版本或游戏列表无效")

    windows: dict[str, MaintenanceWindow] = {}
    for game, item in data["games"].items():
        # 只消费已接入公告的游戏，其他游戏不影响已支持的记录。
        # 异环（nte）待数据侧接入维护公告后挂载（挂载点见 app/task/OkNte/manager.py）：
        # if game not in ("arknights", "endfield", "nte"):
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
    def __init__(
        self,
        *,
        read_cache: Callable[[], MaintenanceCache],
        write_cache: MaintenanceCacheWriter,
    ) -> None:
        self._read_cache = read_cache
        self._write_cache = write_cache
        self._windows: dict[str, MaintenanceWindow] = {}
        self._next_refresh = 0.0
        self._lock = asyncio.Lock()

    async def get_active(
        self, game: str, *, proxy: httpx.Proxy | None = None
    ) -> MaintenanceWindow | None:
        """查询当前维护；过期缓存刷新失败时放行，不沿用旧时段。"""
        async with self._lock:
            if time.monotonic() >= self._next_refresh:
                await self._refresh(proxy=proxy)

            window = self._windows.get(game)
            now = datetime.now(timezone.utc)
            return window if window is not None and window.contains(now) else None

    async def _refresh(self, *, proxy: httpx.Proxy | None) -> None:
        # 与公告一样持久保存内容、ETag 和检查时间，重启后继续复用。
        cache = self._read_cache()
        try:
            cached_windows = parse_maintenance(json.loads(cache.content))
        except ValueError as exc:
            cached_windows = None
            logger.warning(f"维护信息缓存无效，重新获取: {exc}")
        checked_at = cache.checked_at
        remaining = (
            CACHE_SECONDS - (datetime.now().astimezone() - checked_at).total_seconds()
        )
        if cached_windows is not None and 0 < remaining <= CACHE_SECONDS:
            self._windows = cached_windows
            self._next_refresh = time.monotonic() + remaining
            return

        try:
            etag = cache.etag
            headers = (
                {"If-None-Match": etag} if cached_windows is not None and etag else {}
            )
            async with asyncio.timeout(10):
                async with httpx.AsyncClient(
                    proxy=proxy, follow_redirects=True, timeout=5
                ) as client:
                    response = await client.get(MAINTENANCE_URL, headers=headers)
                    if response.status_code == 304:
                        if cached_windows is None:
                            raise ValueError("维护信息未变更但本地缓存无效")
                        windows = cached_windows
                        await self._write_cache(checked_at=datetime.now().astimezone())
                    elif response.status_code == 200:
                        data = response.json()
                        windows = parse_maintenance(data)
                        await self._write_cache(
                            content=json.dumps(data, ensure_ascii=False),
                            etag=response.headers.get("ETag", ""),
                            checked_at=datetime.now().astimezone(),
                        )
                    else:
                        response.raise_for_status()
                        raise ValueError(
                            f"维护信息响应状态无效: {response.status_code}"
                        )
        except (httpx.HTTPError, TimeoutError, ValueError, OSError) as exc:
            self._windows = {}
            self._next_refresh = time.monotonic() + RETRY_SECONDS
            logger.warning(f"检查游戏维护失败，继续正常运行: {exc}")
        else:
            self._windows = windows
            self._next_refresh = time.monotonic() + CACHE_SECONDS
