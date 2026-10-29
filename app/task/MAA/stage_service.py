#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""MAA 关卡解释与共享刷新；缓存、网络和时间由宿主注入。"""

import asyncio
import calendar
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Protocol

import httpx

import app.task.MAA.constants as _maa_constants
from app.domain.MAA import constants as _maa_domain
from app.utils import get_logger

from .constants import RESOURCE_STAGE_DATE_TEXT, RESOURCE_STAGE_DROP_INFO

logger = get_logger("MAA 关卡")


@dataclass(frozen=True)
class MaaStageCache:
    """宿主提供的共享缓存；content 已由宿主校验为 JSON 对象字符串。"""

    content: str
    etag: str
    checked_at: datetime


class MaaStageCacheWriter(Protocol):
    """校验并一起提交缓存字段；未提供的正文和 ETag 保持不变。"""

    def __call__(
        self,
        *,
        checked_at: datetime,
        content: str | None = None,
        etag: str | None = None,
    ) -> Awaitable[None]: ...


def _parse_stage_data(content: str, *, now: datetime) -> dict[str, Any]:
    """解释现有多区服缓存，兼容旧版只有官服活动的缓存。"""
    try:
        raw_stage_data = json.loads(content)
        if "Official" in raw_stage_data:
            stage_data_by_server = {
                server: data.get("sideStoryStage", {})
                for server, data in raw_stage_data.items()
                if isinstance(data, dict)
            }
        else:
            stage_data_by_server = {"Official": raw_stage_data}
        all_stage_data = {}
        for server, server_stage_data in stage_data_by_server.items():
            activity_stage_drop_info = []
            activity_stage_combox = []
            for side_story in server_stage_data.values():
                activity = side_story["Activity"]
                activity_timezone = timezone(
                    timedelta(hours=activity.get("TimeZone", 8))
                )
                if (
                    datetime.strptime(
                        activity["UtcStartTime"], "%Y/%m/%d %H:%M:%S"
                    ).replace(tzinfo=activity_timezone)
                    < now
                    < datetime.strptime(
                        activity["UtcExpireTime"], "%Y/%m/%d %H:%M:%S"
                    ).replace(tzinfo=activity_timezone)
                ):
                    for stage in side_story["Stages"]:
                        activity_stage_combox.append(
                            {"label": stage["Display"], "value": stage["Value"]}
                        )
                        if "SSReopen" not in stage["Display"]:
                            if stage["Drop"] in _maa_constants.MATERIALS_MAP:
                                drop_id = stage["Drop"]
                            elif "玉" in stage["Drop"]:
                                drop_id = "30012"
                            else:
                                drop_id = "NotFound"
                            activity_stage_drop_info.append(
                                {
                                    "Display": stage["Display"],
                                    "Value": stage["Value"],
                                    "Drop": drop_id,
                                    "DropName": _maa_constants.MATERIALS_MAP.get(
                                        stage["Drop"], stage["Drop"]
                                    ),
                                    "Activity": activity,
                                }
                            )
            stage_data = {"Info": activity_stage_drop_info}
            for day in range(0, 8):
                res_stage = []
                for stage in _maa_domain.RESOURCE_STAGE_INFO:
                    if day in stage["days"] or day == 0:
                        res_stage.append(
                            {"label": stage["text"], "value": stage["value"]}
                        )
                stage_data[calendar.day_name[day - 1] if day > 0 else "ALL"] = (
                    res_stage[0:1] + activity_stage_combox + res_stage[1:]
                )
            all_stage_data[server] = stage_data
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        logger.warning(f"解析活动关卡信息失败, 按空关卡处理: {type(e).__name__}: {e}")
        return {}
    return all_stage_data


class MaaStageService:
    def __init__(
        self,
        *,
        read_cache: Callable[[], MaaStageCache],
        write_cache: MaaStageCacheWriter,
        fetch: Callable[[dict[str, str]], Awaitable[httpx.Response]],
        now: Callable[[], datetime],
        track_task: Callable[[asyncio.Task[None]], None],
    ) -> None:
        self._read_cache = read_cache
        self._write_cache = write_cache
        self._fetch = fetch
        self._now = now
        self._track_task = track_task
        self._stage_refresh_task: asyncio.Task[None] | None = None
        # 上次活动关卡刷新失败的时间: 冷却期内不再重复请求远端
        self._stage_refresh_failed_at: datetime | None = None

    async def get_stage_info(
        self,
        type: Literal[
            "User",
            "Today",
            "ALL",
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
            "Info",
        ],
        refresh: bool = False,
        server: str = "Official",
    ):
        """获取关卡信息"""

        stage_by_server = await self.get_stage(refresh=refresh)
        # 开放日按区服的游戏日判断
        game_today = self._now().astimezone(_maa_domain.get_game_day_tz(server))
        server = "Official" if server == "Bilibili" else server
        stage_data = stage_by_server.get(server, {})

        if type == "Info":
            today = game_today.isoweekday()
            res_stage_info = []
            for stage in _maa_domain.RESOURCE_STAGE_INFO:
                if (
                    today in stage["days"]
                    and stage["value"] in RESOURCE_STAGE_DROP_INFO
                ):
                    res_stage_info.append(RESOURCE_STAGE_DROP_INFO[stage["value"]])
            stage_options = [dict(item) for item in stage_data.get("ALL", [])]
            for combox in stage_options:
                combox["label"] = RESOURCE_STAGE_DATE_TEXT.get(
                    combox["value"], combox["label"]
                )
            cache = self._read_cache()
            raw_stage_data = json.loads(cache.content)
            has_cache = isinstance(raw_stage_data.get(server), dict) and (
                "sideStoryStage" in raw_stage_data[server]
            )
            activity_stages = stage_data.get("Info", [])
            activity_status = "ready" if activity_stages else "empty"
            if not has_cache:
                activity_status = "unavailable"
            elif self._stage_refresh_failed_at is not None:
                activity_status = "stale"
            return {
                "Activity": activity_stages,
                "ActivityStatus": activity_status,
                "ActivityUpdatedAt": cache.checked_at.isoformat(),
                "Resource": res_stage_info,
                "Options": stage_options,
            }
        elif type == "User":
            data = stage_data.get("ALL", [])
            for combox in data:
                combox["label"] = RESOURCE_STAGE_DATE_TEXT.get(
                    combox["value"], combox["label"]
                )
            return data
        elif type == "Today":
            return stage_data.get(game_today.strftime("%A"), [])
        else:
            return stage_data.get(type, [])

    async def get_stage(
        self, *, refresh: bool = False, wait_stale: bool = True
    ) -> dict[str, Any]:
        """更新活动关卡信息。

        refresh=True 强制远端检查；wait_stale=True 时缓存过期也等本次刷新完成，
        调用方拿到的是本次请求触发的那次刷新的结果（刷新失败则仍是旧缓存）。
        wait_stale=False 只把刷新丢到后台并立即返回缓存，供启动预热使用。
        """

        cache = self._read_cache()
        raw_stage_data = json.loads(cache.content)
        has_server_data = isinstance(raw_stage_data.get("Official"), dict) and (
            "sideStoryStage" in raw_stage_data["Official"]
        )
        # 缺官方缓存也必须抓一次, 但这不等于调用方要求等待本次刷新
        if (
            not refresh
            and has_server_data
            and (self._stage_refresh_failed_at is None)
            and (self._now() - timedelta(hours=1) < cache.checked_at)
        ):
            logger.info("一小时内已进行过一次检查, 直接使用缓存的活动关卡信息")
            return _parse_stage_data(cache.content, now=self._now())

        if (
            not refresh
            and self._stage_refresh_failed_at is not None
            and self._now() - self._stage_refresh_failed_at < timedelta(seconds=60)
        ):
            # 刚失败过就先不再抓: 断网时总览与注入流程会串行重复等超时
            logger.info("活动关卡信息刷新刚失败过, 直接使用缓存")
            return _parse_stage_data(cache.content, now=self._now())

        if self._stage_refresh_task is None:
            task = asyncio.create_task(self._refresh_stage())
            self._stage_refresh_task = task

            def _done(t: asyncio.Task[None]) -> None:
                if self._stage_refresh_task is t:
                    self._stage_refresh_task = None

            task.add_done_callback(_done)
            self._track_task(task)
        else:
            logger.info("活动关卡信息更新任务已在进行中")

        refresh_task = self._stage_refresh_task
        if refresh_task is not None and (refresh or wait_stale):
            await asyncio.shield(refresh_task)

        return _parse_stage_data(self._read_cache().content, now=self._now())

    async def _refresh_stage(self) -> None:
        """从远端刷新活动关卡信息（仅后台调用）。"""

        logger.info("开始获取活动关卡信息")
        try:
            cache = self._read_cache()
            raw_stage_data = json.loads(cache.content)
            has_server_data = isinstance(raw_stage_data.get("Official"), dict) and (
                "sideStoryStage" in raw_stage_data["Official"]
            )
            headers = {"If-None-Match": cache.etag} if has_server_data else {}
            response = await self._fetch(headers)

            if response.status_code == 304:
                await self._write_cache(checked_at=self._now())
                self._stage_refresh_failed_at = None
                logger.info("关卡信息未更新，使用本地缓存的活动关卡信息")
            elif response.status_code == 200:
                await self._write_cache(
                    content=json.dumps(response.json(), ensure_ascii=False),
                    etag=response.headers.get("ETag", ""),
                    checked_at=self._now(),
                )
                self._stage_refresh_failed_at = None
                logger.success("成功获取远端活动关卡信息")
            else:
                logger.warning(f"无法从MAA服务器获取活动关卡信息:{response.text}")
                self._stage_refresh_failed_at = self._now()
        except Exception as e:
            self._stage_refresh_failed_at = self._now()
            logger.warning(f"无法从MAA服务器获取活动关卡信息: {type(e).__name__}: {e}")
