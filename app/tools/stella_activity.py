#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""星塔旅人活动排期查询。

取数走 StellaBase 的公开接口（社区数据库，非官方）：它已经把活动分成
``current`` / ``upcoming`` / ``ended`` 三组，而且时间精确到分。MSS 专项据此
判断「当前有没有进行中的活动」，好把「活动快速战斗」挪到悬赏试炼前面。

首页的活动卡与横幅不用这里的数据了——那边改用官网公告（``stella_official.py``），
理由是官网才是官方口径、标题与配图更全；官网会把开始写成「维护结束后」，
这种时刻读不出来，不适合拿来做调度判定，所以两边各取所需。

取数失败一律返回 ``None``（判定入口返回 ``None`` 表示「这次说不准」），不能让一个
第三方站点的抖动拦住整轮任务。解析与判定都是纯函数，取数单独放在 :func:`fetch_events`。
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from app.utils import get_logger

logger = get_logger("星塔旅人活动")

EVENTS_URL = "https://stella.ennead.cc/api/stella/events"
## 站点按语言返回同一批活动的文案；各服同期进行同一个活动，取哪一服的文案都不影响判定
EVENTS_LANG = "CN"
## 响应 100 KB 量级，没必要每轮任务都拉；活动起止都是整点，缓存久一点无妨
CACHE_TTL_SECONDS = 30 * 60
REQUEST_TIMEOUT_SECONDS = 20

_cache: tuple[float, dict[str, Any]] | None = None


@dataclass(frozen=True)
class StellaEvent:
    """一场活动：名称与起止时间（Unix 秒）。"""

    name: str
    start_time: float
    end_time: float


def parse_event_time(value: object) -> float | None:
    """把接口返回的 ISO 8601 时间串折成 Unix 秒。

    Args:
        value: 形如 ``2026-09-08T12:00:00+08:00`` 的时间串。

    Returns:
        float | None: Unix 秒；解析不出来时为 None。
    """

    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def _to_event(raw: Mapping[str, Any]) -> StellaEvent | None:
    """把一条原始记录折成 :class:`StellaEvent`；缺名字或缺时间时返回 None。"""

    name = str(raw.get("title") or "").strip()
    start = parse_event_time(raw.get("startTime"))
    end = parse_event_time(raw.get("endTime"))
    if not name or start is None or end is None:
        return None
    return StellaEvent(name=name, start_time=start, end_time=end)


def iter_events(payload: Mapping[str, Any] | None) -> list[StellaEvent]:
    """把接口响应的三组记录拍平成一个列表。

    顺序沿用站点给的「进行中、即将开始、已结束」，不重新排序。

    Args:
        payload: :func:`fetch_events` 的返回值。

    Returns:
        list[StellaEvent]: 解析成功的活动；响应不可用时为空列表。
    """

    if not isinstance(payload, Mapping):
        return []

    events: list[StellaEvent] = []
    for group in ("current", "upcoming", "ended"):
        raw_items = payload.get(group)
        if not isinstance(raw_items, Sequence):
            continue
        for raw in raw_items:
            if not isinstance(raw, Mapping):
                continue
            event = _to_event(raw)
            if event is not None:
                events.append(event)
    return events


def has_running_event(events: Sequence[StellaEvent], now_seconds: float) -> bool:
    """判断是否存在正在进行中的活动。

    Args:
        events: :func:`iter_events` 的输出。
        now_seconds: 判定时刻的 Unix 秒。

    Returns:
        bool: 存在 ``开始时间 <= 当前时刻 < 结束时间`` 的活动时为 True。
    """

    return any(event.start_time <= now_seconds < event.end_time for event in events)


async def fetch_events(*, force: bool = False) -> dict[str, Any] | None:
    """拉取活动数据（带模块级缓存）。

    Args:
        force: 为 True 时忽略缓存。

    Returns:
        dict[str, Any] | None: 接口原始响应；取数失败时为 None。
    """

    global _cache

    now = time.time()
    if not force and _cache is not None and now - _cache[0] < CACHE_TTL_SECONDS:
        return _cache[1]

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(
                EVENTS_URL,
                params={"lang": EVENTS_LANG},
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                    "Accept": "application/json",
                },
            )
        response.raise_for_status()
        payload = response.json()
    except Exception as e:
        logger.warning(f"获取星塔旅人活动数据失败: {type(e).__name__}: {e}")
        return None

    if not isinstance(payload, dict):
        logger.warning("星塔旅人活动数据格式异常，按拿不到处理")
        return None

    _cache = (now, payload)
    return payload


async def has_running_event_now() -> bool | None:
    """调度侧入口：取数并判定当前是否有活动。

    Returns:
        bool | None: 有活动为 True、确实没有为 False、取不到数据为 None。取不到时
        调用方要**跳过**活动编排，不能当成「没有活动」——真在活动期却按没活动处理，
        会把外壳里的活动勾选摘掉，整轮漏打活动。
    """

    payload = await fetch_events()
    if payload is None:
        return None
    return has_running_event(iter_events(payload), time.time())
