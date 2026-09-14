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

"""碧蓝档案活动排期查询。

数据取自 Kivo 古书馆时间轴。该接口对 Origin 做了白名单校验，只放行 kivo.wiki
自己的来源，浏览器直连必定 403，所以由服务端直接请求（不带 Origin）。

对外提供两个口径：调度侧只要「当前有没有进行中的活动」，界面还要知道活动
叫什么、什么时候开始结束。第三方接口不可用不应挡住脚本执行，因此取数失败
一律返回 None，由调用方退回默认行为。
"""

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from app.utils import get_logger

logger = get_logger("碧蓝档案活动")

## 地址末尾的斜杠不能省：少写会被 301 重定向到带斜杠的版本，而 httpx 默认不跟随
BLUEARCHIVE_TIMELINE_URL = "https://api.kivo.wiki/api/v1/timeline/"

## 活动排期变化很慢，缓存十分钟，避免每个用户、每次调度都打这个第三方接口
ACTIVITY_CACHE_TTL = 600

## 时间轴按开始时间倒序返回，当前进行中的活动必定落在最前面若干条里
ACTIVITY_PAGE_SIZE = 100
ACTIVITY_MAX_PAGES = 2

## 第三方接口的请求超时（秒）
REQUEST_TIMEOUT = 20

## 只有「活动」算活动，卡池、掉落加倍、维护等分类不算
WANTED_TYPE = "Event"

BlueArchiveLineType = Literal["JP", "Globle", "CN"]

## 只缓存原始条目：判定结果与「当前时刻」相关，缓存起来会在跨过活动起止时间后失真
_cache: dict[str, tuple[float, tuple[Mapping[str, object], ...]]] = {}


@dataclass(frozen=True)
class ActivityInfo:
    """一场活动：名称与起止时间（Unix 秒）"""

    name: str
    start_time: float
    end_time: float


def has_running_activity_in(
    items: Sequence[Mapping[str, object]], now_seconds: float
) -> bool:
    """判断给定时间轴上是否存在正在进行中的活动。

    Args:
        items: Kivo 时间轴条目，每项含 ``type`` 与 ``start_time`` / ``end_time``（Unix 秒）。
        now_seconds: 判定时刻的 Unix 秒。

    Returns:
        bool: 存在 ``开始时间 <= 当前时刻 < 结束时间`` 的活动时为 True。
    """

    for item in items:
        if item.get("type") != WANTED_TYPE:
            continue

        start = item.get("start_time")
        end = item.get("end_time")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            continue

        if start <= now_seconds < end:
            return True

    return False


def collect_activities(
    items: Sequence[Mapping[str, object]], now_seconds: float
) -> tuple[ActivityInfo | None, ActivityInfo | None]:
    """挑出正在进行中的活动与下一个还没开始的活动。

    与前端首页卡片的取值口径一致：只认「活动」分类，同一活动被拆成多条
    （活动本体与介绍 PV）时保留结束时间最晚的那条；没有标题的条目无法展示，
    直接跳过。

    Args:
        items: Kivo 时间轴条目。
        now_seconds: 判定时刻的 Unix 秒。

    Returns:
        tuple[ActivityInfo | None, ActivityInfo | None]: 依次为进行中的活动、
            下一个未开始的活动；没有则为 None。
    """

    picked: dict[str, ActivityInfo] = {}

    for item in items:
        if item.get("type") != WANTED_TYPE:
            continue

        start = item.get("start_time")
        end = item.get("end_time")
        name = str(item.get("title") or "").strip()
        if (
            not name
            or not isinstance(start, (int, float))
            or not isinstance(end, (int, float))
        ):
            continue

        existing = picked.get(name)
        if existing is not None and existing.end_time >= end:
            continue

        picked[name] = ActivityInfo(name, float(start), float(end))

    running = sorted(
        (item for item in picked.values() if item.start_time <= now_seconds < item.end_time),
        key=lambda item: item.start_time,
    )
    upcoming = sorted(
        (item for item in picked.values() if item.start_time > now_seconds),
        key=lambda item: item.start_time,
    )

    return (running[0] if running else None, upcoming[0] if upcoming else None)


async def _fetch_timeline(line_type: BlueArchiveLineType) -> tuple[Mapping[str, object], ...]:
    """分页取回指定服的活动时间轴。

    Args:
        line_type: 服务器标识，取 Kivo 的原文拼写。

    Returns:
        tuple[Mapping[str, object], ...]: 原始时间轴条目。

    Raises:
        httpx.HTTPError: 请求失败或响应状态异常。
        ValueError: 响应不是预期的 JSON 结构。
    """

    items: list[Mapping[str, object]] = []

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        for page in range(1, ACTIVITY_MAX_PAGES + 1):
            response = await client.get(
                BLUEARCHIVE_TIMELINE_URL,
                params={
                    "line_type": line_type,
                    "page": page,
                    "page_size": ACTIVITY_PAGE_SIZE,
                },
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                    "Accept": "application/json",
                },
            )
            response.raise_for_status()
            payload: Any = response.json()

            batch = payload.get("data", {}).get("timeline") if isinstance(payload, dict) else None
            if not isinstance(batch, list) or not batch:
                break

            items.extend(item for item in batch if isinstance(item, dict))

    return tuple(items)


async def _timeline(line_type: BlueArchiveLineType) -> tuple[Mapping[str, object], ...] | None:
    """取回时间轴，命中缓存时直接复用。

    Args:
        line_type: 服务器标识。

    Returns:
        tuple[Mapping[str, object], ...] | None: 时间轴条目；取数失败为 None。
    """

    now = time.time()
    cached = _cache.get(line_type)
    if cached is not None and now - cached[0] < ACTIVITY_CACHE_TTL:
        return cached[1]

    try:
        items = await _fetch_timeline(line_type)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"获取碧蓝档案活动排期失败({line_type}): {type(e).__name__}: {e}"
        )
        ## 失败不写缓存：下次调度应当重新尝试，而不是把一次失败沿用十分钟
        return None

    _cache[line_type] = (now, items)
    return items


async def has_running_activity(line_type: BlueArchiveLineType) -> bool | None:
    """查询指定服当前是否有进行中的活动。

    Args:
        line_type: 服务器标识（``JP`` / ``Globle`` / ``CN``）。

    Returns:
        bool: 当前有 / 没有进行中的活动。
        None: 取数失败，调用方应退回默认行为。
    """

    items = await _timeline(line_type)
    if items is None:
        return None

    return has_running_activity_in(items, time.time())


async def resolve_activity_state(
    line_type: BlueArchiveLineType,
) -> tuple[ActivityInfo | None, ActivityInfo | None] | None:
    """查询指定服正在进行的活动与下一个未开始的活动。

    Args:
        line_type: 服务器标识（``JP`` / ``Globle`` / ``CN``）。

    Returns:
        tuple[ActivityInfo | None, ActivityInfo | None] | None: 依次为进行中的
            活动、下一个未开始的活动；取数失败为 None。
    """

    items = await _timeline(line_type)
    if items is None:
        return None

    return collect_activities(items, time.time())
