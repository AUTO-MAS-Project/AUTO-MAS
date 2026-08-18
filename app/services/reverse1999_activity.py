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


import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.utils import get_logger
from app.utils.io import write_file

logger = get_logger("1999活动服务")

SOURCE_URL = "https://api.1999.fan/api/data/activity/cn.json"
SOURCE_NAME = "1999.fan"
BANNER_URL = "https://re.bluepoch.com/assets/img/BG.jpg"
TIMEZONE = ZoneInfo("Asia/Shanghai")
REQUEST_TIMEOUT_SECONDS = 20
REFRESH_INTERVAL_SECONDS = 30 * 60
RETRY_SECONDS = 5 * 60
CACHE_PATH = Path.cwd() / "data/cache/reverse1999_activity.json"

_ACTIVITY_KEY_FALLBACK = {
    "combat": "版本活动",
    "re-release": "复刻活动",
    "anecdote": "轶事活动",
}

_EVENT_TYPE_NAME = {
    "MainStory": "主线活动",
    "SideStory": "限时活动",
}


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=TIMEZONE)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _format_activity(activity: dict[str, Any], key: str) -> dict[str, Any]:
    event_type = activity.get("event_type")
    name = (
        activity.get("name")
        or activity.get("alias")
        or _EVENT_TYPE_NAME.get(event_type)
        or _ACTIVITY_KEY_FALLBACK.get(key, key)
    )
    start_time = _parse_time(activity.get("start_time"))
    end_time = _parse_time(activity.get("end_time"))
    return {
        "name": name,
        "description": _EVENT_TYPE_NAME.get(event_type, ""),
        "startTime": start_time.isoformat(timespec="seconds") if start_time else "",
        "endTime": end_time.isoformat(timespec="seconds") if end_time else "",
    }


class Reverse1999ActivityService:
    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._etag = ""
        self._last_error = ""
        self._next_check = 0.0
        self._refresh_task: asyncio.Task[None] | None = None
        self._load_cache()

    async def get_overview(self) -> dict[str, Any]:
        if (
            time.monotonic() >= self._next_check
            and self._refresh_task is None
        ):
            self._refresh_task = asyncio.create_task(self._refresh_if_needed())
        refresh_task = self._refresh_task
        if not self._data and refresh_task is not None:
            await asyncio.shield(refresh_task)
        return self._build_overview()

    async def _refresh_if_needed(self) -> None:
        try:
            await self._refresh()
        except Exception as error:
            self._last_error = f"{type(error).__name__}: {str(error)}"
            self._next_check = time.monotonic() + RETRY_SECONDS
            logger.warning(f"更新1999活动数据失败: {self._last_error}")
        else:
            self._last_error = ""
            self._next_check = time.monotonic() + REFRESH_INTERVAL_SECONDS
        finally:
            self._refresh_task = None

    async def _refresh(self) -> None:
        timeout = httpx.Timeout(REQUEST_TIMEOUT_SECONDS)
        headers = {"If-None-Match": self._etag} if self._etag else {}
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(SOURCE_URL, headers=headers)
            if response.status_code == 304:
                return
            response.raise_for_status()
            self._data = response.json()
            self._etag = response.headers.get("ETag", "")
        self._save_cache()

    def _load_cache(self) -> None:
        if not CACHE_PATH.exists():
            return

        try:
            cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            self._data = cache["data"]
            self._etag = cache.get("etag", "")
        except (OSError, KeyError, TypeError, ValueError) as error:
            self._data = {}
            self._etag = ""
            logger.warning(f"加载1999活动缓存失败: {error}")

    def _save_cache(self) -> None:
        cache = {"etag": self._etag, "data": self._data}
        try:
            write_file(CACHE_PATH, cache)
        except (OSError, TypeError, ValueError) as error:
            logger.warning(f"保存1999活动缓存失败: {error}")

    def _select_version(self) -> tuple[str, dict[str, Any]] | None:
        now = datetime.now(tz=TIMEZONE)
        versions: list[
            tuple[str, dict[str, Any], datetime | None, datetime | None]
        ] = []
        for key, version in self._data.items():
            if not isinstance(version, dict):
                continue
            start_time = _parse_time(version.get("start_time"))
            end_time = _parse_time(version.get("end_time"))
            versions.append((key, version, start_time, end_time))

        active = [
            item
            for item in versions
            if item[2] is not None
            and item[3] is not None
            and item[2] <= now <= item[3]
        ]
        if active:
            return active[0]
        upcoming = [item for item in versions if item[2] is not None and item[2] > now]
        if upcoming:
            return min(upcoming, key=lambda item: item[2])
        ended = [item for item in versions if item[3] is not None and item[3] <= now]
        if ended:
            return max(ended, key=lambda item: item[3])
        return None

    def _build_overview(self) -> dict[str, Any]:
        selected = self._select_version()
        version_id = selected[0] if selected else ""
        version = selected[1] if selected else {}
        activities = version.get("activity", {})
        start_time = _parse_time(version.get("start_time"))
        end_time = _parse_time(version.get("end_time"))
        return {
            "Available": bool(selected),
            "Stale": bool(self._last_error and selected),
            "Message": (
                "1999活动数据暂不可用"
                if self._last_error and not selected
                else (
                    "正在使用上次成功获取的活动数据"
                    if self._last_error
                    else (
                        "正在获取1999活动数据"
                        if not selected and self._refresh_task is not None
                        else ""
                    )
                )
            ),
            "Version": version_id,
            "SourceName": SOURCE_NAME,
            "SourceUrl": SOURCE_URL,
            "version": version_id,
            "versionName": version.get("version_name", ""),
            "cover": BANNER_URL,
            "startTime": start_time.isoformat(timespec="seconds") if start_time else "",
            "endTime": end_time.isoformat(timespec="seconds") if end_time else "",
            "activities": [
                _format_activity(activity, key)
                for key, activity in activities.items()
                if isinstance(activity, dict)
            ],
        }


reverse1999_activity_service = Reverse1999ActivityService()
