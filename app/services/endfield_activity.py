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
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx

from app.utils import get_logger
from app.utils.io import write_file

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
AKEDATA_CACHE_PATH = Path.cwd() / "data/cache/endfield_activity.json"
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


def _parse_activity_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y/%m/%d %H:%M:%S").replace(
        tzinfo=ENDFIELD_TIMEZONE
    )


def _resolve_text(
    reference: dict[str, Any], text_table: dict[str, str], fallback: str
) -> str:
    return text_table.get(str(reference.get("id")), fallback)


def _first_time_range(
    record: dict[str, Any],
    time_ranges: dict[str, Any],
    time_key: str,
    default_time_id: str = "",
) -> dict[str, str]:
    time_id = record.get(time_key) or default_time_id
    return time_ranges.get(time_id, {}).get("timeRangeList", [{}])[0]


def _build_activity_records(
    activities: dict[str, Any],
    time_ranges: dict[str, Any],
    activity_tags: dict[str, Any],
    text_table: dict[str, str],
) -> list[_ResolvedActivity]:
    records: list[_ResolvedActivity] = []
    for index, (activity_id, activity) in enumerate(activities.items()):
        time_range = _first_time_range(activity, time_ranges, "timeId")
        tab_image = activity.get("tabImg")
        image_url = (
            f"{AKEDATA_BASE_URL}/{AKEDATA_ACTIVITY_IMAGE_PATH}/"
            f"{quote(tab_image, safe='')}.png"
            if tab_image
            else ""
        )
        tag_names = [
            _resolve_text(activity_tags[tag_id]["name"], text_table, str(tag_id))
            for tag_id in activity.get("tagIds", [])
        ]

        records.append(
            _ResolvedActivity(
                activity_id=activity_id,
                name=_resolve_text(activity["name"], text_table, activity_id),
                start_time=_parse_activity_time(time_range.get("openTime")),
                end_time=_parse_activity_time(time_range.get("closeTime")),
                image_url=image_url,
                tags=tuple(tag_names),
                sort_id=int(activity.get("sortId", index)),
            )
        )
    return records


def _build_pool_records(
    pools: dict[str, Any],
    time_ranges: dict[str, Any],
    characters: dict[str, Any],
    text_table: dict[str, str],
) -> list[_ResolvedPool]:
    pool_type_names = {0: "特许寻访", 1: "新手寻访", 2: "常驻寻访", 3: "联合寻访"}
    records: list[_ResolvedPool] = []
    for index, (pool_id, pool) in enumerate(pools.items()):
        time_range = _first_time_range(
            pool,
            time_ranges,
            "clientTopTimeId",
            default_time_id=f"time_{pool_id}",
        )
        up_character_ids = pool.get("upCharIds", [])
        up_characters = tuple(
            _resolve_text(
                characters[character_id]["name"],
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
                name=_resolve_text(pool["name"], text_table, pool_id),
                pool_type=pool_type_names.get(pool_type, "角色寻访"),
                start_time=_parse_activity_time(time_range.get("openTime")),
                end_time=_parse_activity_time(time_range.get("closeTime")),
                image_url=image_url,
                up_characters=up_characters,
                sort_id=int(pool.get("sortId", index)),
            )
        )
    return records


class EndfieldActivityService:
    def __init__(self) -> None:
        self._version_id = ""
        self._source_updated_at = ""
        self._activities: list[_ResolvedActivity] = []
        self._pools: list[_ResolvedPool] = []
        self._last_error = ""
        self._next_manifest_check = 0.0
        self._refresh_task: asyncio.Task[None] | None = None
        self._load_cache()

    async def get_overview(self) -> dict[str, Any]:
        if (
            time.monotonic() >= self._next_manifest_check
            and self._refresh_task is None
        ):
            self._refresh_task = asyncio.create_task(self._refresh_if_needed())
        refresh_task = self._refresh_task
        if not self._version_id and refresh_task is not None:
            await asyncio.shield(refresh_task)
        return self._build_overview()

    async def _refresh_if_needed(self) -> None:
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
        finally:
            self._refresh_task = None

    async def _refresh(self) -> None:
        timeout = httpx.Timeout(AKEDATA_REQUEST_TIMEOUT_SECONDS)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            manifest = await self._fetch_json(client, AKEDATA_MANIFEST_URL)
            version = self._get_latest_version(manifest)
            version_id = version["id"]
            source_updated_at = str(manifest.get("updatedAt", ""))
            if version_id == self._version_id:
                if source_updated_at != self._source_updated_at:
                    self._source_updated_at = source_updated_at
                    self._save_cache()
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
        self._save_cache()

    def _load_cache(self) -> None:
        if not AKEDATA_CACHE_PATH.exists():
            return

        try:
            cache = json.loads(AKEDATA_CACHE_PATH.read_text(encoding="utf-8"))
            self._version_id = cache["version_id"]
            self._source_updated_at = cache["source_updated_at"]
            self._activities = [
                _ResolvedActivity(
                    activity_id=item["activity_id"],
                    name=item["name"],
                    start_time=(
                        datetime.fromisoformat(item["start_time"])
                        if item["start_time"]
                        else None
                    ),
                    end_time=(
                        datetime.fromisoformat(item["end_time"])
                        if item["end_time"]
                        else None
                    ),
                    image_url=item["image_url"],
                    tags=tuple(item["tags"]),
                    sort_id=item["sort_id"],
                )
                for item in cache["activities"]
            ]
            self._pools = [
                _ResolvedPool(
                    pool_id=item["pool_id"],
                    name=item["name"],
                    pool_type=item["pool_type"],
                    start_time=(
                        datetime.fromisoformat(item["start_time"])
                        if item["start_time"]
                        else None
                    ),
                    end_time=(
                        datetime.fromisoformat(item["end_time"])
                        if item["end_time"]
                        else None
                    ),
                    image_url=item["image_url"],
                    up_characters=tuple(item["up_characters"]),
                    sort_id=item["sort_id"],
                )
                for item in cache["pools"]
            ]
        except (OSError, KeyError, TypeError, ValueError) as error:
            self._version_id = ""
            self._source_updated_at = ""
            self._activities = []
            self._pools = []
            logger.warning(f"加载终末地活动缓存失败: {error}")

    def _save_cache(self) -> None:
        cache = {
            "version_id": self._version_id,
            "source_updated_at": self._source_updated_at,
            "activities": [
                {
                    "activity_id": item.activity_id,
                    "name": item.name,
                    "start_time": (
                        item.start_time.isoformat() if item.start_time else ""
                    ),
                    "end_time": item.end_time.isoformat() if item.end_time else "",
                    "image_url": item.image_url,
                    "tags": list(item.tags),
                    "sort_id": item.sort_id,
                }
                for item in self._activities
            ],
            "pools": [
                {
                    "pool_id": item.pool_id,
                    "name": item.name,
                    "pool_type": item.pool_type,
                    "start_time": (
                        item.start_time.isoformat() if item.start_time else ""
                    ),
                    "end_time": item.end_time.isoformat() if item.end_time else "",
                    "image_url": item.image_url,
                    "up_characters": list(item.up_characters),
                    "sort_id": item.sort_id,
                }
                for item in self._pools
            ],
        }
        try:
            write_file(AKEDATA_CACHE_PATH, cache)
        except (OSError, TypeError, ValueError) as error:
            logger.warning(f"保存终末地活动缓存失败: {error}")

    @staticmethod
    async def _fetch_json(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _get_latest_version(manifest: dict[str, Any]) -> dict[str, str]:
        latest = manifest["latest"]
        version = next(item for item in manifest["versions"] if item["id"] == latest)
        return {"id": latest, "tableCfgPath": version["tableCfgPath"].strip("/")}

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
            "Available": bool(self._version_id),
            "Stale": bool(self._last_error and self._version_id),
            "Message": (
                "终末地活动数据暂不可用"
                if self._last_error and not self._version_id
                else (
                    "正在使用上次成功获取的活动数据"
                    if self._last_error
                    else (
                        "正在获取终末地活动数据"
                        if not self._version_id and self._refresh_task is not None
                        else ""
                    )
                )
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
