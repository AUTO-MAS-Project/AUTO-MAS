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
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx

from app.utils import get_logger

logger = get_logger("终末地活动服务")

AKEDATA_BASE_URL = "https://data.akedata.wiki"
AKEDATA_MANIFEST_URL = f"{AKEDATA_BASE_URL}/manifest.json"
AKEDATA_SOURCE_URL = "https://www.akedata.wiki"
AKEDATA_ACTIVITY_IMAGE_PATH = (
    "public/images/assets/beyond/dynamicassets/gameplay/ui/sprites/activity"
)
AKEDATA_CHARACTER_IMAGE_PATH = (
    "public/images/assets/beyond/dynamicassets/gameplay/ui/sprites/charremoteicon"
)
AKEDATA_REQUEST_TIMEOUT_SECONDS = 20
AKEDATA_MANIFEST_CACHE_SECONDS = 30 * 60
AKEDATA_RETRY_SECONDS = 5 * 60
ENDFIELD_TIMEZONE = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class _ResolvedActivity:
    activity_id: str
    name: str
    start_time: datetime | None
    end_time: datetime | None
    image_url: str
    tags: tuple[str, ...]
    sort_id: int


@dataclass(frozen=True)
class _ResolvedPool:
    pool_id: str
    name: str
    pool_type: str
    start_time: datetime | None
    end_time: datetime | None
    image_url: str
    up_characters: tuple[str, ...]
    sort_id: int


def _parse_activity_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.strptime(value, "%Y/%m/%d %H:%M:%S")
    except ValueError:
        return None
    return parsed.replace(tzinfo=ENDFIELD_TIMEZONE)


def _resolve_text(reference: object, text_table: dict[str, Any], fallback: str) -> str:
    if not isinstance(reference, dict):
        return fallback
    text_id = reference.get("id")
    resolved = text_table.get(str(text_id))
    return resolved if isinstance(resolved, str) and resolved else fallback


def _resolve_sort_id(value: object, fallback: int) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            pass
    return fallback


def _build_activity_records(
    activities: dict[str, Any],
    time_ranges: dict[str, Any],
    activity_tags: dict[str, Any],
    text_table: dict[str, Any],
) -> list[_ResolvedActivity]:
    records: list[_ResolvedActivity] = []
    for index, (activity_id, activity) in enumerate(activities.items()):
        if not isinstance(activity, dict):
            continue

        time_id = activity.get("timeId")
        time_config = time_ranges.get(time_id, {})
        ranges = (
            time_config.get("timeRangeList", [])
            if isinstance(time_config, dict)
            else []
        )
        time_range = ranges[0] if ranges and isinstance(ranges[0], dict) else {}
        tab_image = activity.get("tabImg")
        image_url = ""
        if isinstance(tab_image, str) and tab_image:
            image_url = (
                f"{AKEDATA_BASE_URL}/{AKEDATA_ACTIVITY_IMAGE_PATH}/"
                f"{quote(tab_image, safe='')}.png"
            )

        tag_names: list[str] = []
        raw_tag_ids = activity.get("tagIds", [])
        if isinstance(raw_tag_ids, list):
            for tag_id in raw_tag_ids:
                tag = activity_tags.get(tag_id, {})
                tag_name = _resolve_text(
                    tag.get("name") if isinstance(tag, dict) else None,
                    text_table,
                    str(tag_id),
                )
                tag_names.append(tag_name)

        records.append(
            _ResolvedActivity(
                activity_id=activity_id,
                name=_resolve_text(activity.get("name"), text_table, activity_id),
                start_time=_parse_activity_time(time_range.get("openTime")),
                end_time=_parse_activity_time(time_range.get("closeTime")),
                image_url=image_url,
                tags=tuple(tag_names),
                sort_id=_resolve_sort_id(activity.get("sortId"), index),
            )
        )
    return records


def _build_pool_records(
    pools: dict[str, Any],
    time_ranges: dict[str, Any],
    characters: dict[str, Any],
    text_table: dict[str, Any],
) -> list[_ResolvedPool]:
    pool_type_names = {0: "特许寻访", 1: "新手寻访", 2: "常驻寻访", 3: "联合寻访"}
    records: list[_ResolvedPool] = []
    for index, (pool_id, pool) in enumerate(pools.items()):
        if not isinstance(pool, dict):
            continue

        time_id = pool.get("clientTopTimeId") or f"time_{pool_id}"
        time_config = time_ranges.get(time_id, {})
        ranges = (
            time_config.get("timeRangeList", [])
            if isinstance(time_config, dict)
            else []
        )
        time_range = ranges[0] if ranges and isinstance(ranges[0], dict) else {}

        up_character_ids = pool.get("upCharIds", [])
        if not isinstance(up_character_ids, list):
            up_character_ids = []
        up_characters = tuple(
            _resolve_text(
                characters.get(character_id, {}).get("name")
                if isinstance(characters.get(character_id), dict)
                else None,
                text_table,
                str(character_id),
            )
            for character_id in up_character_ids
        )
        image_url = ""
        if up_character_ids:
            image_url = (
                f"{AKEDATA_BASE_URL}/{AKEDATA_CHARACTER_IMAGE_PATH}/"
                f"icon_{quote(str(up_character_ids[0]), safe='')}.png"
            )

        pool_type = pool.get("type")
        records.append(
            _ResolvedPool(
                pool_id=pool_id,
                name=_resolve_text(pool.get("name"), text_table, pool_id),
                pool_type=pool_type_names.get(pool_type, "角色寻访"),
                start_time=_parse_activity_time(time_range.get("openTime")),
                end_time=_parse_activity_time(time_range.get("closeTime")),
                image_url=image_url,
                up_characters=up_characters,
                sort_id=_resolve_sort_id(pool.get("sortId"), index),
            )
        )
    return records


class EndfieldActivityService:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._version_id = ""
        self._source_updated_at = ""
        self._activities: list[_ResolvedActivity] = []
        self._pools: list[_ResolvedPool] = []
        self._has_cache = False
        self._last_error = ""
        self._next_manifest_check = 0.0

    async def get_overview(self) -> dict[str, Any]:
        if time.monotonic() >= self._next_manifest_check:
            await self._refresh_if_needed()
        return self._build_overview()

    async def _refresh_if_needed(self) -> None:
        async with self._lock:
            if time.monotonic() < self._next_manifest_check:
                return

            try:
                await self._refresh()
            except Exception as error:
                self._last_error = f"{type(error).__name__}: {str(error)}"
                self._next_manifest_check = time.monotonic() + AKEDATA_RETRY_SECONDS
                logger.warning(f"更新终末地活动数据失败: {self._last_error}")
            else:
                self._last_error = ""
                self._next_manifest_check = (
                    time.monotonic() + AKEDATA_MANIFEST_CACHE_SECONDS
                )

    async def _refresh(self) -> None:
        timeout = httpx.Timeout(AKEDATA_REQUEST_TIMEOUT_SECONDS)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            manifest = await self._fetch_json(client, AKEDATA_MANIFEST_URL)
            version = self._get_latest_version(manifest)
            version_id = version["id"]
            source_updated_at = str(manifest.get("updatedAt", ""))
            if self._has_cache and version_id == self._version_id:
                self._source_updated_at = source_updated_at
                return

            table_root = f"{AKEDATA_BASE_URL}/{version['tableCfgPath']}"
            (
                activities,
                time_ranges,
                activity_tags,
                text_table,
                pools,
                characters,
            ) = await asyncio.gather(
                self._fetch_json(client, f"{table_root}/ActivityTable.json"),
                self._fetch_json(client, f"{table_root}/TimeRangeTable.json"),
                self._fetch_json(client, f"{table_root}/ActivityTagTable.json"),
                self._fetch_json(client, f"{table_root}/I18nTextTable_CN.json"),
                self._fetch_json(client, f"{table_root}/GachaCharPoolTable.json"),
                self._fetch_json(client, f"{table_root}/CharacterTable.json"),
            )
            resolved = _build_activity_records(
                activities=activities,
                time_ranges=time_ranges,
                activity_tags=activity_tags,
                text_table=text_table,
            )
            resolved_pools = _build_pool_records(
                pools=pools,
                time_ranges=time_ranges,
                characters=characters,
                text_table=text_table,
            )

        self._activities = resolved
        self._pools = resolved_pools
        self._version_id = version_id
        self._source_updated_at = source_updated_at
        self._has_cache = True

    @staticmethod
    async def _fetch_json(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError(f"远程数据不是 JSON 对象: {url}")
        return data

    @staticmethod
    def _get_latest_version(manifest: dict[str, Any]) -> dict[str, str]:
        latest = manifest.get("latest")
        versions = manifest.get("versions")
        if not isinstance(latest, str) or not isinstance(versions, list):
            raise ValueError("AKEDatabase 版本清单缺少 latest 或 versions")

        for version in versions:
            if not isinstance(version, dict) or version.get("id") != latest:
                continue
            table_path = version.get("tableCfgPath")
            if not isinstance(table_path, str) or not table_path:
                break
            return {"id": latest, "tableCfgPath": table_path.strip("/")}
        raise ValueError("AKEDatabase 版本清单中找不到 latest 数据路径")

    def _build_overview(self) -> dict[str, Any]:
        now = datetime.now(tz=ENDFIELD_TIMEZONE)
        active = [
            activity
            for activity in self._activities
            if activity.end_time is not None
            and activity.end_time > now
            and (activity.start_time is None or activity.start_time <= now)
        ]
        active.sort(key=lambda activity: (activity.sort_id, activity.activity_id))
        active_pools = [
            pool
            for pool in self._pools
            if pool.end_time is not None
            and pool.end_time > now
            and (pool.start_time is None or pool.start_time <= now)
        ]
        active_pools.sort(key=lambda pool: (pool.sort_id, pool.pool_id))

        return {
            "Available": self._has_cache,
            "Stale": bool(self._last_error and self._has_cache),
            "Message": (
                "终末地活动数据暂不可用"
                if self._last_error and not self._has_cache
                else ("正在使用上次成功获取的活动数据" if self._last_error else "")
            ),
            "Version": self._version_id,
            "UpdatedAt": self._source_updated_at,
            "SourceName": "AKEData",
            "SourceUrl": AKEDATA_SOURCE_URL,
            "Pools": [
                {
                    "Id": pool.pool_id,
                    "Name": pool.name,
                    "Type": pool.pool_type,
                    "StartTime": pool.start_time.isoformat() if pool.start_time else "",
                    "EndTime": pool.end_time.isoformat(),
                    "ImageUrl": pool.image_url,
                    "UpCharacters": list(pool.up_characters),
                }
                for pool in active_pools
            ],
            "Activities": [
                {
                    "Id": activity.activity_id,
                    "Name": activity.name,
                    "StartTime": (
                        activity.start_time.isoformat() if activity.start_time else ""
                    ),
                    "EndTime": activity.end_time.isoformat(),
                    "ImageUrl": activity.image_url,
                    "Tags": list(activity.tags),
                }
                for activity in active
            ],
        }


endfield_activity_service = EndfieldActivityService()
