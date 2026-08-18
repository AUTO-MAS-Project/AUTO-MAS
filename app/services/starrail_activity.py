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


import asyncio
import json
import time
from pathlib import Path
from typing import Any

import httpx

from app.utils import get_logger

logger = get_logger("SRA 活动服务")

ACTIVITY_URL = "https://starrailassistant.top/api/v1/activity/{game}.json"
CACHE_SECONDS = 10 * 60
RETRY_SECONDS = 5 * 60
REQUEST_TIMEOUT_SECONDS = 20


class SraActivityService:
    """SRA 公开活动接口服务，按游戏标识（sr/ys/zzz/ww/nte）提供活动总览。"""

    def __init__(self, game: str, display_name: str) -> None:
        self._game = game
        self._display_name = display_name
        self._cache_path = Path.cwd() / "data/cache" / f"sra_{game}_activity.json"
        self._data: dict[str, Any] = {}
        self._etag = ""
        self._last_error = ""
        self._next_check = 0.0
        self._refresh_task: asyncio.Task[None] | None = None
        self._load_cache()

    async def get_overview(self) -> dict[str, Any]:
        if time.monotonic() >= self._next_check and self._refresh_task is None:
            self._refresh_task = asyncio.create_task(self._refresh())
        return {
            "Available": bool(self._data),
            "Stale": bool(self._data and self._last_error),
            "Message": (
                "正在使用上次成功获取的活动数据"
                if self._data and self._last_error
                else (
                    f"{self._display_name}活动数据正在获取中"
                    if not self._data and self._refresh_task is not None
                    else (
                        f"{self._display_name}活动数据暂不可用"
                        if self._last_error
                        else ""
                    )
                )
            ),
            **self._data,
        }

    async def _refresh(self) -> None:
        try:
            headers = {"If-None-Match": self._etag} if self._etag else {}
            async with httpx.AsyncClient(
                timeout=REQUEST_TIMEOUT_SECONDS,
                follow_redirects=True,
            ) as client:
                response = await client.get(
                    ACTIVITY_URL.format(game=self._game), headers=headers
                )
            if response.status_code == 304:
                self._next_check = time.monotonic() + CACHE_SECONDS
                self._last_error = ""
                return
            response.raise_for_status()
            self._data = response.json()
            self._etag = response.headers.get("ETag", "")
            self._last_error = ""
            self._next_check = time.monotonic() + CACHE_SECONDS
            self._save_cache()
        except Exception as e:
            self._last_error = f"{type(e).__name__}: {str(e)}"
            self._next_check = time.monotonic() + RETRY_SECONDS
            logger.warning(f"更新{self._display_name}活动数据失败: {self._last_error}")
        finally:
            self._refresh_task = None

    def _load_cache(self) -> None:
        cache_path = self._cache_path
        if not cache_path.exists():
            return
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            self._data = cache["data"]
            self._etag = cache.get("etag", "")
        except (OSError, KeyError, TypeError, ValueError) as e:
            logger.warning(f"加载{self._display_name}活动缓存失败: {e}")

    def _save_cache(self) -> None:
        cache_path = self._cache_path
        temporary_path = cache_path.with_suffix(".tmp")
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path.write_text(
                json.dumps({"etag": self._etag, "data": self._data}, ensure_ascii=False),
                encoding="utf-8",
            )
            temporary_path.replace(cache_path)
        except OSError as e:
            logger.warning(f"保存{self._display_name}活动缓存失败: {e}")


starrail_activity_service = SraActivityService("sr", "星穹铁道")
genshin_activity_service = SraActivityService("ys", "原神")
zenless_zone_zero_activity_service = SraActivityService("zzz", "绝区零")
wuthering_waves_activity_service = SraActivityService("ww", "鸣潮")
neverness_to_everness_activity_service = SraActivityService("nte", "异环")
