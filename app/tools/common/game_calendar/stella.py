#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""StellaBase 中文活动日历，供主页与 MSS 活动编排共用。"""

import time
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urljoin

import httpx

from app.utils import get_logger

logger = get_logger("星塔旅人活动")
STELLABASE_BASE = "https://stella.ennead.cc"
STELLABASE_EVENTS_URL = f"{STELLABASE_BASE}/api/stella/events"
CACHE_TTL_SECONDS = 600
RUNNING_CHECK_FAILURE_TTL_SECONDS = 300
REQUEST_TIMEOUT_SECONDS = 20
RECENT_WINDOW_DAYS = 14
BEIJING = timezone(timedelta(hours=8))
VERSION_KIND = "版本活动"
PERMANENT_KIND = "常驻活动"
PERMANENT_KEYWORDS = ("灾变防线", "创业激励基金", "猎影合围")
_Calendar = tuple[list[dict[str, Any]], bool]
_cache: tuple[float, _Calendar | None] | None = None


def classify_activity_name(name: str) -> str:
    """补全 SRA 备用数据的常驻活动分类。"""
    if any(keyword in name for keyword in PERMANENT_KEYWORDS):
        return PERMANENT_KIND
    return "活动"


def _stellabase_activities(payload: Mapping[str, Any]) -> _Calendar:
    """逐条读取可游玩时段；坏记录不影响已确认开放的活动。"""
    activities = []
    complete = True
    for group in ("current", "upcoming", "ended"):
        entries = payload.get(group)
        if not isinstance(entries, list):
            complete = False
            continue
        for entry in entries:
            try:
                start = datetime.fromisoformat(entry["startTime"])
                end = datetime.fromisoformat(entry["endTime"])
                if start.tzinfo is None or end.tzinfo is None or end <= start:
                    raise ValueError("活动时间范围无效")
                name = entry["title"]
                description = entry["description"]
                if not isinstance(name, str) or not name.strip():
                    raise ValueError("活动名称为空")
                if not isinstance(description, str) or not description.strip():
                    raise ValueError("活动说明为空")
                # 弹珠小游戏也写有「活动限时关卡」；版本活动同时列有关卡和故事剧情。
                story = "活动限时关卡" in description and "故事剧情" in description
            except (ValueError, TypeError, KeyError, AttributeError):
                complete = False
                continue

            # 封面是展示字段，损坏时用空图，不改变活动有效性或排期判定。
            cover = ""
            textures = entry.get("textures")
            if isinstance(textures, Mapping):
                for key in ("banner", "tabBackground"):
                    image = textures.get(key)
                    if not isinstance(image, str) or not image:
                        continue
                    try:
                        cover = urljoin(
                            STELLABASE_BASE,
                            f"/api/asset{image}"
                            if image.startswith("/stella/assets/")
                            else image,
                        )
                    except ValueError:
                        continue
                    break
            activities.append(
                {
                    "name": name,
                    "kind": VERSION_KIND if story else "活动",
                    "startTime": start.isoformat(),
                    "endTime": end.isoformat(),
                    "cover": cover,
                    "url": f"{STELLABASE_BASE}/events",
                    "description": description,
                }
            )
    return activities, complete and bool(activities)


async def _fetch_calendar(*, force: bool = False) -> _Calendar | None:
    """主页与编排共享日历，失败时短暂缓存以免各账号重复等待。"""
    global _cache
    now = time.monotonic()
    if not force and _cache is not None:
        fetched_at, calendar = _cache
        ttl = (
            CACHE_TTL_SECONDS
            if calendar is not None
            else RUNNING_CHECK_FAILURE_TTL_SECONDS
        )
        if now - fetched_at < ttl:
            return calendar
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(STELLABASE_EVENTS_URL, params={"lang": "cn"})
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, Mapping):
                raise ValueError("活动日历不是对象")
            calendar = _stellabase_activities(payload)
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(f"获取 StellaBase 活动日历失败: {exc}")
        calendar = None
    _cache = (now, calendar)
    return calendar


async def fetch_official_activities(*, force: bool = False) -> dict[str, Any] | None:
    """取主页活动与横幅；结束时间使用关卡关闭时间。"""
    calendar = await _fetch_calendar(force=force)
    if calendar is None or not calendar[0]:
        return None
    now = datetime.now(BEIJING)
    horizon = now - timedelta(days=RECENT_WINDOW_DAYS)
    activities = [
        item
        for item in calendar[0]
        if datetime.fromisoformat(item["endTime"]) >= horizon
    ]
    # 主页只展示进行中的活动。剩余条目即使还在最近结束窗口内，
    # 也不能拿它们证明损坏的当前分组确实为空。
    if not calendar[1] and not any(
        datetime.fromisoformat(item["startTime"])
        <= now
        < datetime.fromisoformat(item["endTime"])
        for item in activities
    ):
        return None
    return {
        "activities": activities,
        "sourceName": "StellaBase",
        "sourceUrl": f"{STELLABASE_BASE}/events",
    }


async def has_running_official_activity() -> bool | None:
    """确认开放即可编排；坏数据导致无法确认空档时保留手动队列。"""
    calendar = await _fetch_calendar()
    if calendar is None:
        return None
    activities, complete = calendar
    now = datetime.now(BEIJING)
    active = [
        item
        for item in activities
        if datetime.fromisoformat(item["startTime"])
        <= now
        < datetime.fromisoformat(item["endTime"])
    ]
    if any(item["kind"] == VERSION_KIND for item in active):
        return True
    if active or not complete:
        return None
    return False
